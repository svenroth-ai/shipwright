"""Measurements behind the REPLAY report (BP unit BL0): the numbers N and the costs rest on.

Each function returns plain JSON so ``measure_baseline.py`` can write it into the REPLAY data
and the report can cite it. Nothing here gates anything.

* ``fanout_changed``  - the brief's definition: FRs reached per CHANGED function (T-code leg).
* ``fanout_executed`` - a disclosed variant: FRs reached per function EXECUTED by any test in the
  measured files at one revision (a much larger population than the changed functions).
* ``verifier_wallclock`` - wall-clock of ``verify_iterate_finalization.py`` on merged iterate commits.
* ``time_root`` / ``discover_roots`` - cost of one pytest root with and without ``--cov-context=test``.
"""

from __future__ import annotations

import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

from ._baseline_touch_binding import index_tests
from ._baseline_touch_coverage import _spans
from ._baseline_touch_git import is_test_path

__all__ = ["fanout_changed", "fanout_executed", "verifier_wallclock", "time_root", "discover_roots"]

_PYTEST = ["uv", "run", "--with", "pytest", "--with", "pytest-mock", "--with", "pytest-cov", "pytest"]


def _stats(sizes: list[int]) -> dict:
    nz = sorted(s for s in sizes if s)
    if not nz:
        return {"nonzero": 0, "median": None, "p90": None, "p95": None, "max": None}
    return {"nonzero": len(nz), "median": statistics.median(nz), "p90": nz[max(int(len(nz) * 0.9) - 1, 0)],
            "p95": nz[max(int(len(nz) * 0.95) - 1, 0)], "max": nz[-1]}


def _over(sizes: list[int], n: int) -> int:
    return sum(1 for s in sizes if s > n)


def fanout_changed(code_prs: list[dict]) -> dict:
    """FRs per changed function, from the T-code leg's per-PR ``fan_out`` (function -> FRs).

    ``changed_unattributed`` counts the changed FUNCTIONS no measured FR-bound test executes (function-level
    ``unattributed`` notes); ``changed_files_no_coverage`` counts the FILE-level "no coverage at base" notes
    (a different unit: whole files the measured tiers never ran), split into production and test files.
    """
    sizes = [len(frs) for pr in code_prs for frs in (pr.get("fan_out") or {}).values()]
    notes = [note for pr in code_prs for note in pr.get("unattributed", [])]
    unattributed = sum(1 for note in notes if "executed by no FR-bound test" in note)
    no_cov = [note.split(": ", 1)[0] for note in notes if "no coverage at base" in note]
    tests = sum(1 for path in no_cov if is_test_path(path))
    return {"definition": "FRs reached per changed function (brief section 3, BL0)", "prs": len(code_prs),
            "changed_functions_attributed": len(sizes), "changed_unattributed": unattributed,
            "changed_files_no_coverage": {"total": len(no_cov), "production": len(no_cov) - tests, "test_files": tests},
            "histogram": dict(sorted(Counter(sizes).items())), **_stats(sizes),
            "over_n": {str(n): _over(sizes, n) for n in (1, 2, 5, 8)}}


def fanout_executed(contexts: dict[str, dict[int, set[str]]], repo_root: str | Path, top: int = 8) -> dict:
    """FRs per executed function in the measured files at ``repo_root`` (variant, see module docstring)."""
    root = Path(repo_root)
    cache: dict[str, frozenset[str]] = {}

    def frs_of(test_id: str) -> frozenset[str]:
        if test_id not in cache:
            path, _, name = test_id.partition("::")
            file = root / path
            found = (index_tests(file.read_text(encoding="utf-8", errors="replace")) or {}).get(name) if file.is_file() else None
            cache[test_id] = found.frs if found else frozenset()
        return cache[test_id]

    fan: dict[str, set[str]] = {}
    total = 0
    for rel, lines in sorted(contexts.items()):
        file = root / rel
        if not file.is_file() or "/tests/" in rel:
            continue
        for name, a, b in _spans(file.read_text(encoding="utf-8", errors="replace")):
            total += 1
            tests = set().union(*(lines.get(ln, set()) for ln in range(a, b + 1)))
            if tests:
                fan[f"{rel}::{name}"] = {fr for t in tests for fr in frs_of(t)}
    sizes = [len(v) for v in fan.values()]
    return {"definition": "FRs per function executed by any test, files measured at one revision",
            "files_measured": len(contexts), "functions_in_measured_files": total, "functions_executed_by_any_test": len(fan),
            "functions_with_fr_bound_test": sum(1 for s in sizes if s), "histogram": dict(sorted(Counter(sizes).items())),
            **_stats(sizes), "over_n": {str(n): _over(sizes, n) for n in (1, 2, 5, 8)},
            "widest": sorted(((len(v), k) for k, v in fan.items()), reverse=True)[:top]}


def verifier_wallclock(repo: str | Path, records: list[dict], count: int = 5, workdir: str | Path | None = None) -> dict:
    """Wall-clock of the CURRENT finalization verifier on the ``count`` most recent merged iterate commits.

    With ``workdir`` each commit is checked out into a detached worktree first (as F11 sees it, a clean tree
    at that commit); the checkout is not timed. Without it the working tree of ``repo`` is verified, which
    makes later-aggregated artifacts read as missing (non-zero ``rc``) - the seconds are comparable either way.
    """
    picked = [r for r in sorted(records, key=lambda r: -r["pr"]) if r.get("run_id") and r.get("merge") and r.get("class") in ("iterate", "campaign-unit")][:count]
    script = str(Path(repo) / "shared" / "scripts" / "tools" / "verify_iterate_finalization.py")
    runs = []
    for rec in picked:
        tree = Path(workdir) / f"verify-{rec['pr']}" if workdir else Path(repo)
        if workdir:
            subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(tree), rec["merge"]], capture_output=True, check=True)
        try:
            cmd = ["uv", "run", script, "--run-id", rec["run_id"], "--project-root", str(tree), "--commit", rec["merge"]]
            started = time.monotonic()
            proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
            runs.append({"pr": rec["pr"], "run_id": rec["run_id"], "seconds": round(time.monotonic() - started, 1), "rc": proc.returncode,
                         **({"output_tail": (proc.stdout + proc.stderr).strip().splitlines()[-3:]} if proc.returncode else {})})
        finally:
            if workdir:
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)], capture_output=True, check=False)
    secs = [r["seconds"] for r in runs]
    return {"command": "uv run verify_iterate_finalization.py --run-id R --project-root <tree at the merge commit> --commit <merge>",
            "tree": "detached worktree at the merge commit" if workdir else "working tree of the repo", "runs": runs,
            "median_seconds": statistics.median(secs) if secs else None, "max_seconds": max(secs) if secs else None}


def discover_roots(repo: str | Path) -> list[str]:
    base = Path(repo)
    fixed = [r for r in ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests", "integration-tests") if (base / r).is_dir()]
    return fixed + sorted(p.relative_to(base).as_posix() for p in base.glob("plugins/*/tests") if p.is_dir())


def time_root(repo: str | Path, root: str, workdir: str | Path, *, contexts: bool, env: dict, target: str = "shared") -> dict:
    """One pytest process over one root, ``--cov-context=test`` on or off; returns time, outcome and database size."""
    db = Path(workdir) / f"cov-{root.replace('/', '_')}{'' if contexts else '-plain'}"
    db.parent.mkdir(parents=True, exist_ok=True)
    cmd = [*_PYTEST, root, "-q", "-p", "no:cacheprovider", "-m", "not slow and not cross_plugin", f"--cov={target}",
           "--cov-config=pyproject.toml", "--cov-report=", *(["--cov-context=test"] if contexts else [])]
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=repo, env={**env, "COVERAGE_FILE": str(db)}, capture_output=True, text=True, check=False)
    tail = (proc.stdout.strip().splitlines() or [""])[-1]
    return {"root": root, "contexts": contexts, "seconds": round(time.monotonic() - started, 1), "rc": proc.returncode,
            "summary": tail.strip("= "), "db": db.name, "db_bytes": db.stat().st_size if db.exists() else 0}
