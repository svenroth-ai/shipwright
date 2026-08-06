"""The repaired seam, composed end to end over a real git worktree.

``test_resolve_run_id_pointer_seam.py`` pins ``resolve_run_id`` in isolation.
This pins the thing that actually failed in production: the *composition* of
producer -> resolver -> guard -> check. Every piece was individually correct
while the family of checks was inert, because the run pointer written by
``setup_iterate_worktree.py`` lives in the MAIN tree and an iterate's audit runs
from its WORKTREE — so the seam only holds if main-root resolution is part of
the resolver's contract.

It also pins the blast-radius claim itself (AC-10): "this repairs five checks"
is asserted here over all five, not inferred from their names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
import lib.worktree_isolation as wi  # noqa: E402
from tools.verifiers import iterate_compliance as ic  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402

SID = "1ce34d44-0ee1-4c91-871e-d2d52fea7247"
RID = "iterate-2026-08-06-resolve-run-id-seam"
_UNRELATED = "iterate-2026-08-01-someone-elses-run"


@pytest.fixture(autouse=True)
def _no_loop_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SHIPWRIGHT_LOOP_ID", "SHIPWRIGHT_LOOP_UNIT_ID"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def would_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub S9/S10's git reads to the exact state both checks WARN on.

    With git pinned to the would-warn state, a surviving SKIP is unambiguous
    evidence the run_id guard fired — and a WARN is unambiguous evidence it
    did not. That is what makes this test falsifiable rather than decorative.
    """
    monkeypatch.setattr(sc, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(sc, "_is_ui_facing_iterate", lambda root: True)
    monkeypatch.setattr(sc, "_readme_touched_recently", lambda root: False)
    monkeypatch.setattr(sc, "_new_top_level_dirs", lambda root: ["brandnewdir"])
    monkeypatch.setattr(sc, "_claude_md_touched_recently", lambda root: False)


def _history(proj: Path, entries: list[dict]) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": entries}), encoding="utf-8")


# --- AC-2 / AC-7: the composed seam over a real linked worktree -----------

def test_a_worktree_audit_resolves_the_pointer_from_the_main_tree(
    git_origin_repo: tuple[Path, Path], make_worktree: Any,
) -> None:
    """AC-2, the case the repair exists for.

    The producer writes the pointer into the MAIN tree; the iterate's audit
    runs with ``project_root`` = the linked worktree. Resolution therefore has
    to cross that boundary, and a resolver that only looked beside
    ``project_root`` would find nothing.
    """
    work, _ = git_origin_repo
    wt = make_worktree(work, "resolve-run-id-seam")
    wi.write_run_pointer(
        work, run_id=RID, slug="resolve-run-id-seam",
        branch="iterate/resolve-run-id-seam", worktree_path=wt, session_id=SID)

    assert not (wt / ".shipwright" / "iterate_active").exists()
    assert pq.resolve_run_id(wt, SID) == RID


def test_a_plain_checkout_audit_resolves_its_own_pointer(
    git_origin_repo: tuple[Path, Path],
) -> None:
    """AC-2: in a non-worktree checkout, main-root resolution is the identity,
    so the same single code path serves both shapes."""
    work, _ = git_origin_repo
    wt = work / ".worktrees" / "s"
    wt.mkdir(parents=True)
    wi.write_run_pointer(
        work, run_id=RID, slug="s", branch="b",
        worktree_path=wt, session_id=SID)

    assert pq.resolve_run_id(work, SID) == RID


def test_s9_and_s10_stop_skipping_once_the_seam_is_repaired(
    git_origin_repo: tuple[Path, Path], make_worktree: Any, would_warn: None,
) -> None:
    """AC-7 — the whole point of the change, asserted as one composition.

    Producer (real ``write_run_pointer``) -> resolver (``resolve_run_id``) ->
    guard (``unresolvable_run_id_skip``) -> checks (S9/S10). Before the repair
    the resolver handed the guard a session UUID, the guard correctly refused
    to let an unrelated run's category decide the verdict, and both checks
    SKIPped. The unrelated entry is left in history on purpose: the verdict
    must now come from THIS run's own entry, not from that one.
    """
    work, _ = git_origin_repo
    wt = make_worktree(work, "resolve-run-id-seam")
    wi.write_run_pointer(
        work, run_id=RID, slug="resolve-run-id-seam",
        branch="iterate/resolve-run-id-seam", worktree_path=wt, session_id=SID)
    _history(wt, [
        {"run_id": _UNRELATED, "type": "chore", "complexity": "medium"},
        {"run_id": RID, "type": "feature", "complexity": "medium"},
    ])

    resolved = pq.resolve_run_id(wt, SID)
    assert resolved == RID

    for check in (sc.check_s9_readme_freshness, sc.check_s10_claude_md_sync):
        finding = check(wt, resolved)
        assert finding["status"] == pq.STATUS_WARN, finding["evidence"]
        assert "not a resolvable iterate run" not in finding["evidence"]


def test_the_main_root_audit_still_skips_before_the_run_merges(
    git_origin_repo: tuple[Path, Path], make_worktree: Any, would_warn: None,
) -> None:
    """The repair's honest boundary, pinned so it cannot be misremembered.

    Audited from the MAIN root, the run_id now resolves, but the run's own
    ledger entry lives in the unmerged worktree — so the guard still SKIPs.
    That is fail-safe (never a false FAIL) and is the documented limit of this
    change: it does not relocate the per-run ledger.
    """
    work, _ = git_origin_repo
    wt = make_worktree(work, "resolve-run-id-seam")
    wi.write_run_pointer(
        work, run_id=RID, slug="resolve-run-id-seam",
        branch="iterate/resolve-run-id-seam", worktree_path=wt, session_id=SID)
    _history(work, [{"run_id": _UNRELATED, "type": "feature",
                     "complexity": "medium"}])

    resolved = pq.resolve_run_id(work, SID)
    assert resolved == RID

    finding = sc.check_s9_readme_freshness(work, resolved)
    assert finding["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in finding["evidence"]


# --- AC-10: all five checks really do route through the shared guard ------

_GUARDED_CHECKS = [
    pytest.param(sc, sc.check_s2_iterate_spec, "S2", id="S2"),
    pytest.param(sc, sc.check_s3_iterate_miniplan, "S3", id="S3"),
    pytest.param(sc, sc.check_s9_readme_freshness, "S9", id="S9"),
    pytest.param(sc, sc.check_s10_claude_md_sync, "S10", id="S10"),
    pytest.param(ic, ic.check_w2_external_review_marker, "W2", id="W2"),
]


@pytest.mark.parametrize("module,check,check_id", _GUARDED_CHECKS)
def test_every_affected_check_is_gated_by_the_shared_run_id_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, would_warn: None,
    module: Any, check: Any, check_id: str,
) -> None:
    """AC-10 — the blast-radius claim, asserted rather than inferred.

    "The seam repairs five checks" is only true while all five are gated by
    ``unresolvable_run_id_skip``. Spying on the guard in each check's OWN
    module namespace (both import it by name) turns a future bypass into a
    failing test instead of a silently narrower fix.
    """
    _history(tmp_path, [{"run_id": _UNRELATED, "type": "feature",
                         "complexity": "medium"}])
    seen: list[str] = []
    real = module.unresolvable_run_id_skip

    def _spy(project_root: Path, run_id: str, candidates: Any,
             cid: str, name: str, **kw: Any) -> Any:
        seen.append(cid)
        return real(project_root, run_id, candidates, cid, name, **kw)

    monkeypatch.setattr(module, "unresolvable_run_id_skip", _spy)

    finding = check(tmp_path, "unknown")

    assert seen == [check_id]
    assert finding["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in finding["evidence"]
