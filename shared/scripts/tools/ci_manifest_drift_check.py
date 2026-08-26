#!/usr/bin/env python3
"""Regenerate the traceability manifest from a real, fresh CI test run and
compare it to the committed one (iterate-2026-08-26-r1b-ci-manifest-regen-gate,
AC4 b-e). This is the second half of SPEC D8: R1a staged evidence from a real
run; this closes the loop by checking the manifest actually reflects it.

Runs, in order, all fail-closed except the final comparison:

  1. Capture the COMMITTED `test-traceability.json` at HEAD (`git show`) to a
     scratch path, before it gets overwritten below.
  2. Stage this CI run's JUnit reports (`ci_junit_plan.py plan`'s output,
     read from `--plan`) via `evidence_drop.stage_reports` — ONE call, the
     multi-root form, exact bases.
  3. Regenerate `.shipwright/compliance/test-traceability.json` in place via
     `test_links.generate_file()` — the same call `/shipwright-compliance`
     makes locally, now backed by a real CI-fresh run instead of whatever
     was last staged on someone's machine.
  4. Compare the captured baseline against the regenerated file
     (`compare_traceability_manifest`) and return its own 3-way exit code
     (0/1/2) UNCHANGED — this script's exit code IS the comparator's.

Exit 0/1 always run every step; exit 2 can come from ANY step (a crash, a
missing committed file, a malformed manifest) — the caller (ci.yml) must
never swallow it. Advisory ONLY: exit 1 (structural drift) is real drift,
reported, never a reason by itself to fail the build — see AC4's design
note in the iterate spec for why, and what has to be true before that changes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2]
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
from scripts.lib import evidence_drop  # noqa: E402
from scripts.tools import compare_traceability_manifest as _compare_mod  # noqa: E402

EXIT_OK = _compare_mod.EXIT_OK
EXIT_STRUCTURAL_DRIFT = _compare_mod.EXIT_STRUCTURAL_DRIFT
EXIT_ERROR = _compare_mod.EXIT_ERROR

TRACKED_MANIFEST_REL = Path(".") / ".shipwright" / "compliance" / "test-traceability.json"


class DriftCheckError(Exception):
    """A step before comparison failed — always exit 2, never advisory."""


def capture_committed_manifest(project_root: Path, scratch_path: Path) -> None:
    proc = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
        ["git", "show", f"HEAD:{TRACKED_MANIFEST_REL.as_posix()}"],
        cwd=project_root, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False, shell=False,
    )
    if proc.returncode != 0:
        raise DriftCheckError(
            f"could not read the committed manifest at HEAD:{TRACKED_MANIFEST_REL.as_posix()} "
            f"in {project_root}: {proc.stderr.strip()}"
        )
    scratch_path.parent.mkdir(parents=True, exist_ok=True)
    scratch_path.write_text(proc.stdout, encoding="utf-8")


def stage_ci_reports(project_root: Path, *, run_id: str, head_commit: str, plan_path: Path) -> None:
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DriftCheckError(f"cannot read {plan_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DriftCheckError(f"{plan_path} is not valid JSON: {exc}") from exc
    if not isinstance(plan, list):
        raise DriftCheckError(f"{plan_path} must be a JSON list, got {type(plan).__name__}")
    for i, entry in enumerate(plan):
        if (not isinstance(entry, dict) or not isinstance(entry.get("base"), str)
                or not isinstance(entry.get("junit_out"), str)):
            raise DriftCheckError(
                f"{plan_path}[{i}] must be an object with string 'base' and "
                f"'junit_out' fields, got {entry!r}"
            )
    junit_reports = [(entry["base"], entry["junit_out"]) for entry in plan]
    missing = [path for _base, path in junit_reports if not Path(path).is_file()]
    if missing:
        raise DriftCheckError(
            f"{missing} named in {plan_path} do not exist — the verify step should "
            "have already caught this; refusing to stage a partial evidence set."
        )
    evidence_drop.stage_reports(
        project_root, run_id=run_id, head_commit=head_commit, junit_reports=junit_reports,
    )


#: Run in a FRESH subprocess (`uv run --project <plugin>`), never imported in-process:
#: this process already binds the top-level name `scripts` to `shared/scripts`
#: (via the `evidence_drop` import above), and `shipwright-compliance` owns its
#: OWN `scripts/` tree (ADR-044/045) — a bare in-process import of
#: `scripts.lib.collectors.test_links` would resolve `scripts.lib` against the
#: ALREADY-CACHED shared package instead, whose `__path__` never reaches the
#: plugin's `collectors/` submodule, and silently import the wrong (or no)
#: module. Verified empirically: a first draft of this function did exactly
#: that and passed only because pytest's own test-collection sys.path
#: manipulation masked it — it failed immediately as a real CLI invocation.
_REGEN_SCRIPT = """\
import sys
from pathlib import Path

plugin_root = Path(sys.argv[1])
project_root = Path(sys.argv[2])
sys.path.insert(0, str(plugin_root))
from scripts.lib.collectors.test_links import generate_file
generate_file(project_root)
"""


def regenerate_manifest(project_root: Path) -> None:
    plugin_root = project_root / "plugins" / "shipwright-compliance"
    script_path = project_root / ".ci-junit" / "_regen_test_links.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(_REGEN_SCRIPT, encoding="utf-8")
    proc = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
        ["uv", "run", "--project", str(plugin_root), "python", str(script_path),
         str(plugin_root), str(project_root)],
        cwd=project_root, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False, shell=False,
    )
    if proc.returncode != 0:
        raise DriftCheckError(
            f"test_links.generate_file() failed (uv run exit {proc.returncode}): "
            f"{proc.stderr.strip()[-2000:]}"
        )


def run(project_root: Path, *, run_id: str, head_commit: str, plan_path: Path) -> tuple[int, str]:
    scratch = project_root / ".ci-junit" / "committed-manifest.json"
    try:
        capture_committed_manifest(project_root, scratch)
        stage_ci_reports(project_root, run_id=run_id, head_commit=head_commit, plan_path=plan_path)
        regenerate_manifest(project_root)
    except DriftCheckError as exc:
        return EXIT_ERROR, f"ERROR: {exc}"
    except Exception as exc:  # noqa: BLE001 - deliberate: an UNANTICIPATED
        # failure here (a disk/OSError from evidence_drop.stage_reports, or
        # any other exception this file's steps did not think to name) must
        # exit 2, never Python's bare default of 1 — which silently ALIASES
        # with EXIT_STRUCTURAL_DRIFT and lets ci.yml's advisory wrapper
        # swallow a real infra failure as if it were reported drift
        # (doubt-reviewer Stage 3, doubt #1).
        return EXIT_ERROR, f"ERROR: unexpected failure before comparison: {exc}"

    regenerated = project_root / TRACKED_MANIFEST_REL
    return _compare_mod.main_with_output([
        "--check", "--committed", str(scratch), "--regenerated", str(regenerated),
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", default=".", type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--head-commit", required=True)
    ap.add_argument("--plan", required=True, type=Path,
                    help="ci_junit_plan.py plan's output (plan.json)")
    args = ap.parse_args(argv)

    code, output = run(
        args.project_root.resolve(), run_id=args.run_id, head_commit=args.head_commit,
        plan_path=args.plan,
    )
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
