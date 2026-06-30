"""D2 sweep — guard / structured-no-op cases (real git, no mocks).

Split from ``test_sweep_outbox.py`` (the AC1-5 core) so each module stays under
the 300-LOC guideline. Covers: invalid-materialized-log fail-closed (no commit,
no outbox mutation), CI-without-opt-in skip, op-in-progress + staged-changes
guards in the WORKTREE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402


@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


def test_empty_outbox_is_noop(repo) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-empty")
    before = h.git(wt, "rev-parse", "HEAD").stdout.strip()

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "no_change"
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == before


def test_non_orphan_corruption_does_not_commit_or_clear(repo) -> None:
    """Genuine corruption (an invalid-JSON outbox line) still fails CLOSED:
    ``invalid`` WITHOUT committing or touching the outbox, and no quarantine."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-corrupt")
    before = h.git(wt, "rev-parse", "HEAD").stdout.strip()
    bad_json = '{"event":"status","id":"trg-x" BROKEN'
    h.write_outbox(work, bad_json)

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert result.errors and result.quarantined == 0
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == before  # no commit
    assert bad_json in h.outbox_lines(work)                         # outbox intact
    assert h.quarantine_text(work) == ""                            # nothing quarantined


def test_orphan_status_quarantined_remainder_delivered(repo) -> None:
    """AC1 + AC5 (real-git integration): an outbox orphan-status is QUARANTINED while
    the valid pending append is still delivered to the branch — the sweep no longer
    hard-blocks the whole buffer on one orphan."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-quarantine")
    orphan = h.status("trg-ghost")          # no append anywhere → orphan
    real = h.item("trg-bbbb")               # a genuine pending finding
    h.write_outbox(work, orphan, real)

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.quarantined == 1
    assert real in h.branch_triage_lines(wt)        # real finding delivered
    assert orphan not in h.outbox_lines(work)        # orphan removed from outbox
    assert "trg-ghost" in h.quarantine_text(work)    # orphan preserved for review


def test_mixed_orphan_and_corruption_hard_blocks(repo) -> None:
    """AC3: an orphan-status PLUS genuine corruption → corruption wins → ``invalid``,
    nothing quarantined, outbox untouched (fail-closed for real corruption)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-mixed")
    orphan = h.status("trg-ghost")
    bad_json = '{"event":"append" BROKEN'
    h.write_outbox(work, orphan, bad_json)

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert result.quarantined == 0
    assert orphan in h.outbox_lines(work) and bad_json in h.outbox_lines(work)
    assert h.quarantine_text(work) == ""


def test_orphan_status_in_tracked_log_not_quarantined(repo) -> None:
    """AC4: an orphan-status that lives in the WORKTREE-TRACKED (origin) log — not the
    outbox — is NOT quarantined (the sweep cannot rewrite origin) → ``invalid``."""
    work, _ = repo
    # Seed the tracked log itself with an orphan status (no append for trg-ghost).
    h.seed_tracked(work, h.item("trg-aaaa"), h.status("trg-ghost"))
    wt = h.make_worktree(work, "sweep-tracked-orphan")
    h.write_outbox(work, h.item("trg-bbbb"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "invalid", result.to_dict()
    assert result.quarantined == 0
    assert h.quarantine_text(work) == ""


def test_ci_without_optin_skips(repo, monkeypatch) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-ci")
    h.write_outbox(work, h.item("trg-bbbb"))
    monkeypatch.setenv("CI", "true")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "skipped" and result.reason == "ci_without_optin"
    assert h.item("trg-bbbb") in h.outbox_lines(work)


def test_ci_with_allow_ci_proceeds(repo, monkeypatch) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-ci-optin")
    h.write_outbox(work, h.item("trg-bbbb"))
    monkeypatch.setenv("CI", "true")

    result = sweep_outbox_to_branch(work, wt, default_branch="main", allow_ci=True)

    assert result.status == "committed"
    assert h.item("trg-bbbb") in h.branch_triage_lines(wt)


def test_op_in_progress_in_worktree_skips(repo) -> None:
    """A merge in progress in the WORKTREE makes the sweep a structured no-op."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-merging")
    h.write_outbox(work, h.item("trg-bbbb"))
    git_dir = Path(h.git(wt, "rev-parse", "--absolute-git-dir").stdout.strip())
    head = h.git(wt, "rev-parse", "HEAD").stdout.strip()
    (git_dir / "MERGE_HEAD").write_text(head + "\n", encoding="utf-8")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "skipped" and result.reason == "op_in_progress"
    assert h.item("trg-bbbb") in h.outbox_lines(work)


def test_staged_changes_in_worktree_skips(repo) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-staged")
    h.write_outbox(work, h.item("trg-bbbb"))
    (wt / "other.txt").write_text("wip\n", encoding="utf-8")
    h.git(wt, "add", "--", "other.txt")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "skipped" and result.reason == "staged_changes"
    assert h.item("trg-bbbb") in h.outbox_lines(work)


def test_crlf_outbox_line_swept(repo) -> None:
    """A CRLF-terminated outbox line is normalized + swept (no spurious dup)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-crlf")
    # Write a CRLF-terminated outbox line directly (Windows / human-edited shape).
    p = work / h.OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("ab") as fh:
        fh.write((h.item("trg-crlf") + "\r\n").encode("utf-8"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    # The CRLF was absorbed; the branch line matches the LF-normalized form.
    assert h.item("trg-crlf") in h.branch_triage_lines(wt)
