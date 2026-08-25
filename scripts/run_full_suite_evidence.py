"""Full-suite execution-evidence runner (R1a, E-D/E-E — repo tool, not a plugin tool).

This repo has 18 pytest test-roots (ADR-044: one root per pytest process — a single
process cannot emit one ``junit.xml`` spanning them). Coverage evidence (`.shipwright/
compliance/test-evidence-index.json`) was therefore, until this iterate, always ONE
root's worth — every other root's tagged tests reported ``MISSING`` even when
enabled and passing (SPEC §4 P0a). This tool drives every discovered root, one pytest
process at a time, each with its own ``--junitxml``, then stages all of them together
via ``evidence_drop.stage_reports`` (the E-B multi-report form).

**E-E — root list AND base mapping are DERIVED, never hand-maintained.** Both come
from ``conftest.py::discover_test_roots`` — the SAME function the repo-root pytest
guard uses to refuse a multi-root session. A new ``plugins/<name>/tests`` is picked
up automatically; there is no second list to fall out of sync with it.

The per-root invocation mirrors ``.github/workflows/ci.yml`` (the shape already
proven to produce joinable evidence), derived structurally from each root's own
path — never a hand-maintained per-root table:

* ``plugins/<name>/tests`` — ``cd plugins/<name> && uv run --with pytest --with
  pytest-mock pytest tests/ -v --junitxml=<path>``. Base = ``plugins/<name>`` (the
  JUnit ``file`` attribute is plugin-dir-relative, so the id needs rebasing to join
  the manifest's project-root-relative ids).
* Every other root (``shared/...``, ``integration-tests``) — run from the repo root
  with the root's own repo-relative path as the pytest argument. Base = ``""`` (the
  JUnit ``file`` attribute is already project-root-relative). Roots under ``shared/``
  additionally get ``-m "not slow and not cross_plugin"`` (mirrors ci.yml's shared-tier
  step; ``cross_plugin``-tagged tests are excluded from a ``shared/tests`` session by
  design, ADR-044).

A root whose process never produces a ``--junitxml`` file (crash, collection error) is
reported as a HARD failure (this tool's own exit code is nonzero) — that root
contributed NO evidence at all, which is a materially different, more serious outcome
than "ran and some tests failed" (a red root still emits a valid report, and its
``executed: fail`` entries are correct, wanted evidence, not something to suppress).
This tool never aborts early on one root's failure (ADR-044 exit-4 landmine); it always
attempts every discovered root and stages whatever reports it collected.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_discover_test_roots(repo_root: Path = _REPO_ROOT):
    """Load ``conftest.py::discover_test_roots`` by path (ADR-045: register in
    ``sys.modules`` BEFORE ``exec_module``), never via a bare ``sys.path`` insert —
    a real pytest session may already have its OWN ``conftest`` module cached, and
    binding a second one to that name would be exactly the collision class ADR-044's
    guard exists to prevent. A unique synthetic name sidesteps it entirely.

    Loads from ``repo_root`` (the CALLER's ``--project-root``, defaulting to this
    script's own repo for the common in-place invocation) — external-review finding:
    always loading this script's own compile-time ``_REPO_ROOT/conftest.py`` regardless
    of ``--project-root`` would silently discover a DIFFERENT target repo's roots using
    THIS repo's discovery logic, defeating E-E's "derive from the target's own guard
    function" contract for any caller that legitimately points elsewhere (tests,
    a future multi-repo invocation).
    """
    conftest_path = Path(repo_root) / "conftest.py"
    spec = importlib.util.spec_from_file_location("_full_suite_evidence_conftest", conftest_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_full_suite_evidence_conftest"] = module
    spec.loader.exec_module(module)
    return module.discover_test_roots


@dataclass(frozen=True)
class RootPlan:
    root: Path          # absolute path to the discovered `tests/` dir
    rel_root: str        # repo-root-relative posix path to that `tests/` dir (for display)
    cwd: Path              # absolute cwd the pytest process runs in
    pytest_arg: str         # the path argument passed to pytest, relative to `cwd`
    base: str                # id-rebase base (repo-root-relative posix, "" = no rebase)
    marker_expr: str | None   # -m expression, or None (rely on the root's own addopts)
    junit_out: Path            # absolute path this root's --junitxml is written to


def plan_root(repo_root: Path, root: Path, raw_dir: Path, index: int) -> RootPlan:
    """Derive one root's invocation plan structurally from its OWN path — no
    hand-maintained per-root table (E-E). ``index`` only picks the junit filename."""
    rel_root = root.relative_to(repo_root).as_posix()
    plugins_dir = repo_root / "plugins"
    junit_out = raw_dir / f"{index:02d}-{rel_root.replace('/', '_')}.xml"
    try:
        under_plugins = root.relative_to(plugins_dir)
    except ValueError:
        under_plugins = None

    if under_plugins is not None:
        plugin_name = under_plugins.parts[0]
        plugin_dir = plugins_dir / plugin_name
        return RootPlan(
            root=root, rel_root=rel_root, cwd=plugin_dir,
            pytest_arg=root.relative_to(plugin_dir).as_posix(),
            base=plugin_dir.relative_to(repo_root).as_posix(),
            marker_expr=None, junit_out=junit_out,
        )

    marker_expr = None
    try:
        root.relative_to(repo_root / "shared")
        marker_expr = "not slow and not cross_plugin"
    except ValueError:
        pass
    return RootPlan(
        root=root, rel_root=rel_root, cwd=repo_root,
        pytest_arg=rel_root, base="", marker_expr=marker_expr, junit_out=junit_out,
    )


def plan_all_roots(repo_root: Path, roots, raw_dir: Path) -> list[RootPlan]:
    """Deterministic order (sorted by repo-relative path) so console output and the
    staged junit numbering are stable across runs — an unordered ``set`` otherwise
    makes every invocation's report/base pairing arbitrary."""
    ordered = sorted(roots, key=lambda p: p.relative_to(repo_root).as_posix())
    return [plan_root(repo_root, root, raw_dir, i) for i, root in enumerate(ordered, start=1)]


def pytest_command(plan: RootPlan) -> list[str]:
    cmd = ["uv", "run", "--with", "pytest", "--with", "pytest-mock",
           "pytest", plan.pytest_arg, "-v", f"--junitxml={plan.junit_out}"]
    if plan.marker_expr:
        cmd += ["-m", plan.marker_expr]
    return cmd


@dataclass(frozen=True)
class RootRunResult:
    plan: RootPlan
    returncode: int
    produced_junit: bool


def run_root(plan: RootPlan, *, runner=None) -> RootRunResult:
    # Looked up at CALL time (not a bound default) so a test can monkeypatch
    # `subprocess.run` on this module and have it take effect without threading an
    # explicit `runner=` through `main()`'s loop.
    runner = runner or subprocess.run
    plan.junit_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = pytest_command(plan)
    print(f"--- Running tests in {plan.rel_root} (cwd={plan.cwd}) ---", flush=True)
    proc = runner(cmd, cwd=str(plan.cwd))
    returncode = proc.returncode if hasattr(proc, "returncode") else int(proc)
    produced = plan.junit_out.is_file()
    verdict = "ok" if returncode == 0 else "TESTS FAILED (evidence still collected)"
    if not produced:
        verdict = "NO EVIDENCE PRODUCED (process crashed before writing junit)"
    print(f"--- {plan.rel_root}: {verdict} ---", flush=True)
    return RootRunResult(plan=plan, returncode=returncode, produced_junit=produced)


def stage_all(repo_root: Path, results: list[RootRunResult], *, run_id: str, head_commit: str) -> dict:
    """Stage every root that produced a report, via the E-B multi-report form. A root
    that failed to write a junit contributes nothing (never fabricated)."""
    shared_scripts = repo_root / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    from lib import evidence_drop  # noqa: PLC0415 — deferred so pure planning stays import-light

    junit_reports = [(r.plan.base, r.plan.junit_out) for r in results if r.produced_junit]
    return evidence_drop.stage_reports(
        repo_root, run_id=run_id, head_commit=head_commit, junit_reports=junit_reports,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(_REPO_ROOT))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--head-commit", default="")
    parser.add_argument(
        "--skip-sync", action="store_true",
        help="Skip `uv sync --extra dev` (assume the root venv already has dev deps).",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.project_root).resolve()
    if not args.skip_sync:
        subprocess.run(["uv", "sync", "--extra", "dev"], cwd=str(repo_root), check=True)

    shared_scripts = repo_root / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    from lib import evidence_drop  # noqa: PLC0415 — deferred so pure planning stays import-light

    # Clear stale evidence BEFORE running any root (F5.md's "clear before, stage
    # after" contract) — not just implicitly via stage_all()'s own clear at the very
    # END. A full-suite pass takes ~20 minutes; leaving a PRIOR run's raw report
    # sitting under .shipwright/compliance/evidence/ for that whole window is not a
    # dormant risk — another test in one of the 18 roots this tool itself drives can
    # observe (and fail on) that stale file mid-run (e.g. a repo-wide file scanner
    # tripping over an oversized/foreign junit.xml it cannot read).
    evidence_drop.clear_evidence_reports(repo_root)

    discover_test_roots = _load_discover_test_roots(repo_root)
    roots = discover_test_roots(repo_root)
    raw_dir = repo_root / ".shipwright" / "runs" / "full-suite-evidence" / "raw"
    if raw_dir.is_dir():
        for stale in raw_dir.glob("*.xml"):
            stale.unlink()
    plans = plan_all_roots(repo_root, roots, raw_dir)

    print(f"Discovered {len(plans)} test root(s):", flush=True)
    for plan in plans:
        print(f"  - {plan.rel_root}  (cwd={plan.cwd.relative_to(repo_root).as_posix() or '.'}, "
              f"base={plan.base or '(none)'})", flush=True)

    results = [run_root(plan) for plan in plans]

    prov = stage_all(repo_root, results, run_id=args.run_id, head_commit=args.head_commit)

    no_evidence = [r.plan.rel_root for r in results if not r.produced_junit]
    failed_tests = [r.plan.rel_root for r in results if r.returncode != 0 and r.produced_junit]
    summary = {
        "roots_total": len(results),
        "roots_staged": len(prov.get("reports", {}).get("junit", [])),
        "roots_with_no_evidence": no_evidence,
        "roots_with_failing_tests": failed_tests,
        "run_id": prov.get("run_id"),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 1 if no_evidence else 0


if __name__ == "__main__":
    raise SystemExit(main())
