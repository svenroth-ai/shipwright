"""Record the CI supply-chain acknowledgement required by the F11 gate.

A CI trust-boundary change (`.github/workflows/**`, a hosted dependency-updater
config, composite actions) must name the recorded posture decision it is
consistent with. This CLI computes the run/content binding itself, so nobody
hand-edits ``shipwright_test_results.json`` — a machine-written artifact whose
hand-injected fields get dropped on the next regen (external-review finding).

Run it AFTER the final `shipwright_test_results.json` write (F5) and BEFORE the
F6 commit stages it: at that point the CI change lives in the WORKING TREE, which
is what this tool fingerprints. The F11 verifier re-fingerprints the committed
content, so any edit to a CI file between recording and committing invalidates the
ack — deliberately, because the recorded sentence would otherwise describe a
change that no longer exists.

Usage::

    uv run shared/scripts/tools/record_ci_supplychain_ack.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug \\
      --consistent-with "ADR-042" \\
      --statement "GitHub-owned actions stay on mutable tags; third-party SHA-pinned."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parent
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

from tools.verifiers.ci_supplychain import (  # noqa: E402
    _ci_paths,
    ci_supplychain_fingerprint,
    worktree_reader,
)
from tools.verifiers.git_helpers import _run_git  # noqa: E402


def worktree_ci_paths(project_root: Path) -> list[str]:
    """CI-boundary paths changed in the WORKING TREE (tracked edits + untracked).

    The ack is recorded pre-F6, so the change is not committed yet — asking git for
    a commit range here would find nothing and the tool would refuse to record an
    ack for a change that plainly exists.
    """
    paths: list[str] = []
    rc, out, _ = _run_git(project_root, "diff", "--name-only", "HEAD")
    if rc == 0:
        paths += out.splitlines()
    rc, out, _ = _run_git(project_root, "ls-files", "--others", "--exclude-standard")
    if rc == 0:
        paths += out.splitlines()
    return _ci_paths(paths)


def build_ack(project_root: Path, run_id: str, consistent_with: str, statement: str) -> dict:
    """Compute the run- and content-bound acknowledgement block."""
    ci_paths = worktree_ci_paths(project_root)
    if not ci_paths:
        raise SystemExit(
            "the working tree touches no CI supply-chain file — no acknowledgement "
            "is needed (and recording one would only plant a stale ack for later)"
        )
    return {
        "run_id": run_id,
        "paths_fingerprint": ci_supplychain_fingerprint(ci_paths, worktree_reader(project_root)),
        "consistent_with": consistent_with.strip(),
        "statement": statement.strip(),
        "ci_paths": ci_paths,
    }


def write_ack(project_root: Path, ack: dict) -> Path:
    """Merge the ack into ``iterate_latest`` WITHOUT disturbing any other key.

    Read-modify-write on purpose: a wholesale rewrite of this file has silently
    dropped sibling blocks before (the top-level ``coverage`` block feeding the CI
    coverage-baseline lint), so every untouched key is carried verbatim.
    """
    path = project_root / "shipwright_test_results.json"
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            raise SystemExit(f"shipwright_test_results.json is unreadable ({exc})") from exc
    if not isinstance(data, dict):
        raise SystemExit("shipwright_test_results.json is not a JSON object")
    latest = data.setdefault("iterate_latest", {})
    if not isinstance(latest, dict):
        raise SystemExit("iterate_latest is not an object — refusing to overwrite it")
    latest["ci_supplychain_ack"] = ack
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record the CI supply-chain acknowledgement")
    ap.add_argument("--project-root", default=".", help="iterate worktree root")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--consistent-with", required=True,
                    help="the recorded decision this change agrees with (ADR-NNN, "
                         "an iterate-YYYY-MM-DD-slug run id, or #NNN)")
    ap.add_argument("--statement", required=True,
                    help="what this change does to the CI trust boundary")
    args = ap.parse_args(argv)

    root = Path(args.project_root).resolve()
    ack = build_ack(root, args.run_id, args.consistent_with, args.statement)
    path = write_ack(root, ack)
    print(json.dumps({"written": str(path), "ci_supplychain_ack": ack}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
