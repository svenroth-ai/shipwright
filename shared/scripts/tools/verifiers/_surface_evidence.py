"""Cross-check an F0.5 block's ``tests_run`` / ``exit_code`` against the staged evidence.

The F0.5 block is typed into ``shipwright_test_results.json`` / the F5c entry by
the run itself, so on its own it proves nothing. The staged evidence is the
run's real runner reports, copied by ``stage_f0_evidence.py`` / ``evidence_drop
stage`` into ``.shipwright/compliance/evidence/`` with a provenance sidecar
(``run_id`` + ``head_commit`` + ``tested_tree``). This module accepts the block
only when that evidence exists and agrees with it:

1. **present**: a provenance sidecar with at least one staged report;
2. **this run's**: the sidecar names this ``run_id``;
3. **this revision's**: the code the reports ran against is the code in the
   verified commit (:mod:`._surface_revision`: the ``tested_tree`` fingerprint
   against the branch's own last write of each path it owns, so a trunk merge's
   hunks never count and a later fix or amend does);
4. **this surface's**: ``web`` needs a staged Playwright report, and only its
   results count. ``cli`` / ``api`` count every staged result, but when the
   diff touches a runnable surface (``_surface_detect``) the runner must name
   the test files that drive it, so unrelated passing tests cannot stand in;
5. **consistent**: every test path the runner names has a passing result under
   it, at least ``tests_run`` results passed, and none failed. When the runner
   names test paths (:func:`._surface_runner.runner_test_paths`) the count and
   the "none failed" rule look only at results under them, latest staged
   attempt per test id. When it names none, the whole staged suite is checked
   fail-closed, and the detail says so.

Every failure says which of the five it is and how to repair it. A stale or
absent verdict is repaired by re-running the tests (F0 / F0.5) and staging the
reports that run wrote; re-staging older reports is refused at staging
(``evidence_drop``). The index is built in memory from the provenance-listed
reports only (``fresh_evidence``); nothing is written.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import evidence_drop  # noqa: E402

from ._layer_coverage_evidence import fresh_evidence  # noqa: E402
from ._layer_coverage_regen import _load_collector  # noqa: E402
from ._surface_revision import revision_problem  # noqa: E402
from ._surface_runner import (  # noqa: E402
    latest_attempts,
    passing_case_count,
    passing_case_counts,
    runner_test_paths,
    under,
)

__all__ = ["SURFACE_RUNNERS", "evidence_problem", "runner_test_paths"]

#: Staged report kinds a surface's results must come from; absent = any kind.
SURFACE_RUNNERS: dict[str, frozenset[str]] = {"web": frozenset({"playwright"})}

_RERUN = ("re-run this run's tests (F0, and F0.5 for the surface) on this revision, then stage "
          "the reports that run wrote: `uv run shared/scripts/tools/stage_f0_evidence.py "
          "--project-root . --run-id {run_id} --head-commit \"$(git rev-parse HEAD)\"` (or "
          "`shared/scripts/lib/evidence_drop.py stage`). Re-staging older reports is refused")


def _provenance_problem(project_root: Path, run_id: str, commit: str, surface: str,
                        branch_paths: list[str]) -> tuple[str | None, str]:
    prov = evidence_drop.read_provenance(project_root)
    rerun = _RERUN.format(run_id=run_id)
    if not prov or not prov.get("reports"):
        return f"absent: no staged evidence for surface={surface}. To repair, {rerun}", ""
    owner = str(prov.get("run_id") or "")
    if owner != run_id:
        return f"stale: the staged evidence belongs to run {owner[:60]!r}, not {run_id}. To repair, {rerun}", ""
    head = str(prov.get("head_commit") or "")
    if not head:
        return f"stale: the staged evidence names no head_commit, so no revision vouches for it. To repair, {rerun}", ""
    if not commit:
        return "stale: the verified commit is unresolvable, so the staged evidence cannot be tied to it", ""
    problem, note = revision_problem(project_root, head, prov.get("tested_tree"), commit, branch_paths)
    if problem:
        return f"stale: {problem}. To repair, {rerun}", ""
    needed = SURFACE_RUNNERS.get(surface)
    if needed and not needed.intersection(prov["reports"]):
        return (f"surface={surface} needs a staged {'/'.join(sorted(needed))} report, but only "
                f"{', '.join(sorted(prov['reports']))} was staged. Stage the surface runner's report "
                "(`evidence_drop.py stage --playwright <report.json>` together with the JUnit reports)"), ""
    return None, note


def _passing(results: dict) -> list[str]:
    return [tid for tid, e in results.items() if e.get("executed") == "pass" and e.get("status") == "enabled"]


def evidence_problem(project_root: Path, run_id: str, commit: str, block: dict,
                     touched: dict[str, list[str]] | None = None,
                     branch_paths: list[str] | tuple[str, ...] = ()) -> tuple[str | None, str]:
    """``(problem, summary)``: ``problem`` is ``None`` when the evidence backs the block.

    ``touched`` is the diff's runnable surfaces (``_surface_detect.detect_surfaces``);
    ``branch_paths`` the diff's changed paths (``measure_diff``).
    """
    surface = str(block.get("surface"))
    named = runner_test_paths(project_root, block.get("runner"))
    if touched and surface in ("cli", "api") and not named:
        kinds = ", ".join(f"{kind}: {paths[0]}" for kind, paths in touched.items())
        return (f"the diff touches a runnable surface ({kinds}), but the surface runner "
                f"{str(block.get('runner'))[:80]!r} names no test file that could be resolved "
                "(`cd <dir> &&`, `--directory` / `--project <dir>` and absolute paths under the "
                "project are understood), so no staged result can be tied to it. Drive the surface "
                "through a test file named in --runner (e.g. `uv run pytest <path/to/test_file.py>`) "
                "and stage its report"), ""
    problem, note = _provenance_problem(project_root, run_id, commit, surface, list(branch_paths))
    if problem:
        return problem, ""
    loaded = _load_collector()
    if loaded is None:
        return ("the evidence reader (compliance plugin `_execution_evidence_io`) could not be "
                "loaded, so the staged evidence cannot be read; F11 does not pass unread evidence"), ""
    needed = SURFACE_RUNNERS.get(surface)

    def of_surface(results: dict) -> dict:
        return {tid: e for tid, e in results.items() if not needed or e.get("runner") in needed}

    # No commit: fresh_evidence's own ancestry test is replaced by revision_problem above,
    # which also accepts a consolidated (soft-reset) head whose tested tree equals the commit.
    results = of_surface(fresh_evidence(project_root, run_id, "", loaded[2]))
    if not results:
        return f"absent: the staged reports parse to no {surface} test results", ""
    if named:
        latest = latest_attempts(project_root, loaded[2])
        if latest is None:
            return "the staged reports could not be re-read per attempt; F11 does not pass unread evidence", ""
        results = {tid: e for tid, e in of_surface(latest).items() if under(tid, named)}
        scope = f"under the runner's {len(named)} test path(s), latest staged attempt per test"
        for path in named:
            if not any(under(tid, [path]) for tid in _passing(results)):
                return (f"the surface runner names {path!r}, but the staged evidence has no passing "
                        "test under it: stage the reports of the run that executed it"), ""
    else:
        scope = "whole staged suite: the runner names no test path that could be resolved"
    failed = sorted(tid for tid, e in results.items() if e.get("executed") == "fail")
    if failed:
        return (f"the block records exit_code 0, but the staged evidence has {len(failed)} failing "
                f"test(s) ({scope}), first {failed[0]!r}"), ""
    passed = _passing(results)
    tests_run = block.get("tests_run")
    # tests_run is the runner's own count, per CASE (pytest "N passed"); the index folds a
    # parametrized function into one id, so compare in the runner's unit, not the index's.
    cases = passing_case_count(passed, passing_case_counts(project_root, loaded[2]))
    if cases < tests_run:
        return (f"the block records tests_run={tests_run}, but the staged evidence shows only "
                f"{cases} passing {surface} case(s) in {len(passed)} test(s) ({scope})"), ""
    return None, (f"staged evidence agrees ({cases} passing case(s) in {len(passed)} test(s), "
                  f"0 failing; {scope}){note}")
