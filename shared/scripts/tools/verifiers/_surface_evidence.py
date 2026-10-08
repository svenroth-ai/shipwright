"""Cross-check an F0.5 block's ``tests_run`` / ``exit_code`` against the staged evidence.

The F0.5 block is typed into ``shipwright_test_results.json`` / the F5c entry by
the run itself, so on its own it proves nothing. The staged evidence is the
run's real runner reports, copied by ``stage_f0_evidence.py`` / ``evidence_drop
stage`` into ``.shipwright/compliance/evidence/`` with a provenance sidecar
(``run_id`` + ``head_commit``). This module accepts the block only when that
evidence exists and agrees with it:

1. **present**: a provenance sidecar with at least one staged report;
2. **this run's**: the sidecar names this ``run_id``;
3. **this revision's**: the code the reports ran against is the code in the
   verified commit (:mod:`._surface_revision`: ancestry + the ``tested_tree``
   fingerprint, compared path by path; trunk merges and finalization records
   do not count);
4. **this surface's**: ``web`` needs a staged Playwright report, and only its
   results count. ``cli`` / ``api`` count every staged result, but when the
   diff touches a runnable surface (``_surface_detect``) the runner must name
   the test files that drive it, so unrelated passing tests cannot stand in;
5. **consistent**: no staged result failed (the block says ``exit_code`` 0),
   at least ``tests_run`` results passed, and every test path the runner
   names has a passing result under it.

Every failure says which of the five it is and how to repair it. The index is
built in memory from the provenance-listed reports only (``fresh_evidence``);
nothing is written.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import evidence_drop  # noqa: E402

from ._layer_coverage_evidence import fresh_evidence  # noqa: E402
from ._layer_coverage_regen import _load_collector  # noqa: E402
from ._surface_detect import is_test_path  # noqa: E402
from ._surface_revision import revision_problem  # noqa: E402

__all__ = ["SURFACE_RUNNERS", "evidence_problem", "runner_test_paths"]

#: Staged report kinds a surface's results must come from; absent = any kind.
SURFACE_RUNNERS: dict[str, frozenset[str]] = {"web": frozenset({"playwright"})}

_STAGE = ("stage this run's reports after F0 / F0.5: `uv run shared/scripts/tools/"
          "stage_f0_evidence.py --project-root . --run-id {run_id} --head-commit "
          "\"$(git rev-parse HEAD)\"` (or `shared/scripts/lib/evidence_drop.py stage`)")


def runner_test_paths(project_root: Path, runner: object) -> list[str]:
    """Project-relative test paths the runner command names and that exist."""
    if not isinstance(runner, str) or not runner.strip():
        return []
    try:
        tokens = shlex.split(runner.replace("\\", "/"))
    except ValueError:
        tokens = runner.replace("\\", "/").split()
    paths = []
    for token in tokens:
        rel = token.split("::", 1)[0].rstrip("/")
        while rel.startswith("./"):
            rel = rel[2:]
        named_test = is_test_path(rel) or is_test_path(rel + "/_")  # a test file, or a test dir
        if token.startswith("-") or not rel or Path(rel).is_absolute() or not named_test:
            continue  # a flag, an absolute path, or not a test path (a probe script, a tool)
        if (Path(project_root) / rel).exists():
            paths.append(rel)
    return paths


def _provenance_problem(project_root: Path, run_id: str, commit: str, surface: str) -> str | None:
    prov = evidence_drop.read_provenance(project_root)
    stage = _STAGE.format(run_id=run_id)
    if not prov or not prov.get("reports"):
        return f"absent: no staged evidence for surface={surface}. To repair, {stage}"
    owner = str(prov.get("run_id") or "")
    if owner != run_id:
        return f"stale: the staged evidence belongs to run {owner[:60]!r}, not {run_id}. To repair, {stage}"
    head = str(prov.get("head_commit") or "")
    if not head:
        return f"stale: the staged evidence names no head_commit, so no revision vouches for it. To repair, {stage}"
    if not commit:
        return "stale: the verified commit is unresolvable, so the staged evidence cannot be tied to it"
    problem = revision_problem(project_root, head, prov.get("tested_tree"), commit)
    if problem:
        return f"stale: {problem}. Re-run F0 / F0.5 on this revision, then {stage}"
    needed = SURFACE_RUNNERS.get(surface)
    if needed and not needed.intersection(prov["reports"]):
        return (f"surface={surface} needs a staged {'/'.join(sorted(needed))} report, but only "
                f"{', '.join(sorted(prov['reports']))} was staged. Stage the surface runner's report "
                "(`evidence_drop.py stage --playwright <report.json>` together with the JUnit reports)")
    return None


def evidence_problem(project_root: Path, run_id: str, commit: str, block: dict,
                     touched: dict[str, list[str]] | None = None) -> tuple[str | None, str]:
    """``(problem, summary)``: ``problem`` is ``None`` when the evidence backs the block.

    ``touched`` is the diff's runnable surfaces (``_surface_detect.detect_surfaces``).
    """
    surface = str(block.get("surface"))
    named = runner_test_paths(project_root, block.get("runner"))
    if touched and surface in ("cli", "api") and not named:
        kinds = ", ".join(f"{kind}: {paths[0]}" for kind, paths in touched.items())
        return (f"the diff touches a runnable surface ({kinds}), but the surface runner "
                f"{str(block.get('runner'))[:80]!r} names no test file, so no staged result can be "
                "tied to it. Drive the surface through a test file named in --runner (e.g. "
                "`uv run pytest <path/to/test_file.py>`) and stage its report"), ""
    problem = _provenance_problem(project_root, run_id, commit, surface)
    if problem:
        return problem, ""
    loaded = _load_collector()
    if loaded is None:
        return ("the evidence reader (compliance plugin `_execution_evidence_io`) could not be "
                "loaded, so the staged evidence cannot be read; F11 does not pass unread evidence"), ""
    results = fresh_evidence(project_root, run_id, commit, loaded[2])
    needed = SURFACE_RUNNERS.get(surface)
    if needed:
        results = {tid: e for tid, e in results.items() if e.get("runner") in needed}
    if not results:
        return f"absent: the staged reports parse to no {surface} test results", ""
    failed = sorted(tid for tid, e in results.items() if e.get("executed") == "fail")
    if failed:
        return (f"the block records exit_code 0, but the staged evidence has {len(failed)} failing "
                f"test(s), first {failed[0]!r}"), ""
    passed = [tid for tid, e in results.items()
              if e.get("executed") == "pass" and e.get("status") == "enabled"]
    tests_run = block.get("tests_run")
    if len(passed) < tests_run:
        return (f"the block records tests_run={tests_run}, but the staged evidence shows only "
                f"{len(passed)} passing {surface} test(s)"), ""
    for path in named:
        if not any(tid == path or tid.startswith(path + "/") or tid.startswith(path + "::")
                   for tid in passed):
            return (f"the surface runner names {path!r}, but the staged evidence has no passing "
                    "test under it: stage the reports of the run that executed it"), ""
    return None, f"staged evidence agrees ({len(passed)} passing, 0 failing)"
