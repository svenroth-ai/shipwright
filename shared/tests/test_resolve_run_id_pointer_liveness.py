"""AC-11 — an orphaned run pointer must not bind a finished run.

Run pointers are reaped only by ``prune_stale_run_pointers``, which runs only
from ``setup_iterate_worktree`` and only unlinks pointers whose worktree is
already gone. Since this repo RETAINS worktrees after a PR merges, pointers
routinely outlive their runs: measured on the main tree, 64 pointer files
against ~36 live worktrees.

Without a liveness predicate that is a *new* mis-attribution path, not an
inherited one. A session that finishes iterate A and keeps working would
resolve ``run_id = A`` on every later Stop; once A's ledger entry merges into
main, ``has_exact_iterate_entry`` turns True and the guarded checks evaluate
**A's** category against the current tree. Before priority 0 existed the same
Stop resolved a session UUID and SKIPped.

``pointer_run_id`` therefore requires the pointer's ``worktree_path`` to still
be a directory — matching the sibling consumer of this artifact
(``iterate_stop_finalize``), which already refuses a pointer whose worktree is
not live. It bounds staleness rather than eliminating it: a worktree retained
after its PR merges still looks live (trg-276994a4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402

SID = "1ce34d44-0ee1-4c91-871e-d2d52fea7247"
RID = "iterate-2026-08-06-resolve-run-id-seam"
_FALLBACK = "run-id-from-run-config"


@pytest.fixture(autouse=True)
def _no_loop_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID"):
        monkeypatch.delenv(var, raising=False)


def _project(proj: Path, worktree_path: object) -> None:
    """A run config to fall back to, plus a pointer with the given worktree."""
    (proj / "shipwright_run_config.json").write_text(
        json.dumps({"run_id": _FALLBACK}), encoding="utf-8")
    d = proj / ".shipwright" / "iterate_active"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{SID}.json").write_text(
        json.dumps({"run_id": RID, "session_id": SID,
                    "worktree_path": worktree_path}),
        encoding="utf-8")


@pytest.mark.parametrize(
    "worktree_path",
    ["", "   ", None, 42],
    ids=["blank", "whitespace", "null", "non-string"],
)
def test_pointer_without_a_usable_worktree_path_is_rejected(
    tmp_path: Path, worktree_path: object,
) -> None:
    _project(tmp_path, worktree_path)
    assert pq.resolve_run_id(tmp_path, SID) == _FALLBACK


def test_pointer_whose_worktree_was_removed_is_rejected(tmp_path: Path) -> None:
    """The case F11 cleanup produces: ``git worktree remove`` runs, the pointer
    stays behind until some later iterate's setup happens to prune it."""
    gone = tmp_path / ".worktrees" / "already-removed"
    _project(tmp_path, str(gone))

    assert not gone.exists()
    assert pq.resolve_run_id(tmp_path, SID) == _FALLBACK


def test_a_file_at_the_worktree_path_is_not_a_live_worktree(
    tmp_path: Path,
) -> None:
    """``is_dir()``, not ``exists()`` — a leftover file where the worktree used
    to be is not a worktree."""
    impostor = tmp_path / "not-a-dir"
    impostor.write_text("", encoding="utf-8")
    _project(tmp_path, str(impostor))

    assert pq.resolve_run_id(tmp_path, SID) == _FALLBACK


def test_a_live_worktree_still_resolves(tmp_path: Path) -> None:
    """The guard must not over-fire: the ordinary in-flight shape still wins.

    This is what makes the four rejections above meaningful rather than a
    resolver that simply stopped honouring pointers.
    """
    live = tmp_path / ".worktrees" / "resolve-run-id-seam"
    live.mkdir(parents=True)
    _project(tmp_path, str(live))

    assert pq.resolve_run_id(tmp_path, SID) == RID
