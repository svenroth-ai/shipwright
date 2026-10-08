"""F11 audit of F0.5: the ``surface_verification`` block, checked against the diff and the evidence.

The post-commit second layer behind the production-time gate in
``shared/scripts/surface_verification.py``. Moved out of ``iterate_checks.py``
(at its size cap, ADR-125), which re-exports it. Skipped at trivial/small.
Severity ERROR.

Fail-closed conditions (mirror of SKILL.md F0.5):

1. medium+ iterate but no ``surface_verification`` block (silent regression).
2. ``surface != "none"`` and ``tests_run == 0`` (greedy-filter trap).
3. ``surface != "none"`` and ``exit_code != 0`` (runner failed after retries).
4. ``surface == "none"`` without a ``justification`` AND a ``reason_code`` from
   the closed ``surface_none`` vocabulary.
5. ``surface == "none"`` while the branch diff touches a runnable surface
   (UI, API route, SSE / WebSocket, message contract), re-derived here by
   :mod:`._surface_detect`. A diff that cannot be measured cannot confirm
   ``none`` either, so it fails too.
6. ``surface != "none"`` whose numbers the staged evidence does not back:
   absent, another run's, staged at a revision the verified commit does not
   descend from or that later code commits superseded, missing the surface's
   own report kind, or
   disagreeing with ``tests_run`` / ``exit_code`` (:mod:`._surface_evidence`).
7. ``surface`` other than ``web`` while the diff touches a UI file: a UI
   change is driven in a browser. (Other detected kinds only refuse ``none``;
   an API or contract change may legitimately be driven as ``api`` or ``cli``.)

Precedence: the diff wins over the reason code. ``no-startable-surface`` on a
diff that touches a route is refused like any other code.

A missing or malformed ``shipwright_test_results.json`` at medium+ is itself a
failure: F5 is mandatory and produces it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402
from lib.reason_codes import family_codes, reason_code_error  # noqa: E402

from ._cascade_trigger_inputs import measure_diff  # noqa: E402
from ._entry_details import _no_entry_detail, _wrong_shape_detail  # noqa: E402
from ._iterate_latest import read_iterate_latest, stale_detail  # noqa: E402
from ._surface_detect import detect_surfaces  # noqa: E402
from ._surface_evidence import evidence_problem  # noqa: E402
from ._surface_git import surface_texts  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git, git_context  # noqa: E402

__all__ = ["check_surface_verification"]

CHECK_NAME = "F0.5 surface_verification block valid"
_FAMILY = "surface_none"


def _verified_commit(project_root: Path, commit_hash: str) -> tuple[str, str | None]:
    """``(commit, error)``: the commit F11 verifies, or why there is none."""
    ctx = git_context(project_root)
    if ctx != "work_tree":
        return "", f"{project_root} is not a readable git work tree ({ctx})"
    if commit_hash:
        return commit_hash, None
    rc, out, _ = _run_git(project_root, "rev-parse", "HEAD", timeout=10.0)
    return (out.strip(), None) if rc == 0 and out.strip() else ("", "HEAD is unresolvable")


def _touched(project_root: Path, commit_hash: str) -> tuple[dict[str, list[str]], str, str | None]:
    """``(surfaces touched, base, error)`` for the branch diff merge-base..verified commit."""
    commit, err = _verified_commit(project_root, commit_hash)
    measure = measure_diff(project_root, commit) if commit else None
    if err or measure is None or measure.error:
        why = err or (measure.error if measure else "no commit")
        return {}, "", (f"the diff is unmeasurable ({why}), so F11 cannot re-derive which runnable "
                        "surfaces changed. Make the trunk resolvable (`git fetch origin <trunk>`)")
    texts = surface_texts(project_root, measure.base, commit, measure.paths)
    if texts is None:
        return {}, "", "git could not produce the branch's changed lines and file contents"
    return detect_surfaces(measure.paths, texts), measure.base, None


def _resolve_block(project_root: Path, run_id: str, entry: dict) -> tuple[dict | None, str | None]:
    # Per-run entry FIRST, exactly as the ledger check does: the shared results
    # file is a derived snapshot the F11 integration rewinds to HEAD, so a block
    # found there may belong to whatever run main last committed.
    block = entry.get("surface_verification")
    if block is not None and not isinstance(block, dict):
        return None, _wrong_shape_detail("surface_verification", block)
    if not isinstance(block, dict):
        latest = read_iterate_latest(project_root, run_id)
        if not latest.is_current:
            return None, stale_detail(latest, run_id, "surface_verification")
        block = (latest.block or {}).get("surface_verification")
    if not isinstance(block, dict):
        return None, "iterate_latest.surface_verification missing for medium+ iterate"
    return block, None


def _check_none(project_root: Path, block: dict, commit_hash: str) -> CheckResult:
    justification = str(block.get("justification") or "").strip()
    if not justification:
        return CheckResult(CHECK_NAME, False, "surface=none requires non-empty justification")
    code = block.get("reason_code")
    codes = "|".join(sorted(family_codes(_FAMILY)))
    if code is None:
        return CheckResult(CHECK_NAME, False,
                           "surface=none at medium+ needs a reason_code from the closed "
                           f"{_FAMILY} vocabulary, not only a free-text justification. Re-run "
                           f"F0.5 with `--surface none --reason-code <{codes}> --justification ...`")
    bad = reason_code_error(_FAMILY, code, where="surface_verification.reason_code")
    if bad:
        return CheckResult(CHECK_NAME, False, bad)
    touched, base, why = _touched(project_root, commit_hash)
    if why:
        return CheckResult(CHECK_NAME, False, f"surface=none cannot be confirmed: {why}")
    if touched:
        named = "; ".join(f"{kind}: {', '.join(paths[:3])}" for kind, paths in touched.items())
        return CheckResult(CHECK_NAME, False,
                           f"surface=none ({code}) refused: the diff touches a runnable surface "
                           f"({named}). Drive it through F0.5 with --surface web|api|cli")
    return CheckResult(CHECK_NAME, True,
                       f"surface=none ({code}), justification recorded ({len(justification)} "
                       f"chars), diff vs {base} touches no runnable surface")


def check_surface_verification(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """F0.5 audit; see the module docstring for the seven fail-closed conditions."""
    project_root = Path(project_root)
    entry = find_entry_by_run_id(project_root, run_id)
    if entry is None:
        return CheckResult(CHECK_NAME, False, _no_entry_detail(run_id))
    complexity = entry.get("complexity", "")
    if complexity not in ("medium", "large"):
        return CheckResult(CHECK_NAME, True, f"skipped (complexity={complexity or 'unknown'})",
                           severity=Severity.SKIPPED.value)
    block, problem = _resolve_block(project_root, run_id, entry)
    if block is None:
        return CheckResult(CHECK_NAME, False, problem or "surface_verification missing")

    surface = block.get("surface")
    if surface not in ("web", "cli", "api", "none"):
        return CheckResult(CHECK_NAME, False, f"surface={surface!r} not one of web/cli/api/none")
    if surface == "none":
        return _check_none(project_root, block, commit_hash)

    exit_code = block.get("exit_code")
    tests_run = block.get("tests_run")
    if not isinstance(tests_run, int) or isinstance(tests_run, bool) or tests_run <= 0:
        return CheckResult(CHECK_NAME, False, f"surface={surface}, tests_run={tests_run!r} (must be > 0)")
    if exit_code != 0 or isinstance(exit_code, bool):
        return CheckResult(CHECK_NAME, False,
                           f"surface={surface}, exit_code={exit_code!r} (runner failed after retries)")
    commit, err = _verified_commit(project_root, commit_hash)
    if err:
        return CheckResult(CHECK_NAME, False, f"surface={surface}, tests_run={tests_run}: stale: {err}, "
                           "so the staged evidence cannot be tied to the verified revision")
    touched, _, why = _touched(project_root, commit)
    if why:
        return CheckResult(CHECK_NAME, False, f"surface={surface}, tests_run={tests_run}: {why}")
    if "ui" in touched and surface != "web":
        return CheckResult(CHECK_NAME, False,
                           f"surface={surface}, but the diff touches UI ({', '.join(touched['ui'][:3])}): "
                           "a UI change is driven in a browser. Re-run F0.5 with --surface web")
    bad, summary = evidence_problem(project_root, run_id, commit, block, touched)
    if bad:
        return CheckResult(CHECK_NAME, False, f"surface={surface}, tests_run={tests_run}: {bad}")
    return CheckResult(CHECK_NAME, True, f"surface={surface}, tests_run={tests_run}, exit_code=0; {summary}")
