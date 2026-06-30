"""D2 (campaign 2026-06-08-triage-outbox-delivery): EMPIRICAL sweep core tests.

The sweep folds the gitignored main-tree outbox into the iterate PR branch under
the canonical triage lock (Codex Q4) and GCs only origin-delivered lines (Codex
unlisted abandoned-branch failure mode). This is the MOST data-loss-sensitive
unit in the campaign — a lost or duplicated triage line is a HARD failure — so
every test here exercises REAL git repos + REAL worktrees + the REAL canonical
``triage._FileLock`` + REAL threads. NOTHING is mocked.

This module: AC2 abandoned-branch GC, AC3 no local-main pollution, AC4
exactly-once after merge=union, AC5 reconcile-parity. The AC1 concurrency +
lock-contention proofs live in ``test_sweep_outbox_concurrency.py``; the guard /
structured-no-op cases in ``test_sweep_outbox_guards.py``.
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
from lib import sweep_outbox  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402

TRIAGE = h.TRIAGE


@pytest.fixture
def repo(git_origin_repo):
    """A main working tree with a bare origin + identity (caller seeds tracked)."""
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


# --------------------------------------------------------------------------- #
# AC5 — identical EOL-normalize + dedup + validate as reconcile
# --------------------------------------------------------------------------- #


def test_sweep_reuses_reconcile_helpers() -> None:
    """The sweep's quarantine pipeline uses the IDENTICAL dedup + validate helpers
    reconcile uses — they moved to ``lib.sweep_quarantine`` but stay single-source."""
    from lib import reconcile_triage, sweep_quarantine
    from lib.churn_merge import dedup_triage_lines, validate_triage_text
    assert sweep_quarantine.dedup_triage_lines is dedup_triage_lines
    assert sweep_quarantine.validate_triage_text is validate_triage_text
    assert reconcile_triage.dedup_triage_lines is dedup_triage_lines
    assert reconcile_triage.validate_triage_text is validate_triage_text


def test_sweep_eol_normalize_matches_reconcile() -> None:
    """The CRLF-absorb + trailing-newline-drop normalization is byte-identical to
    the idiom ``reconcile_main_triage`` runs inline on the tracked log. Rather
    than reimplement reconcile's logic inline (which a shared bug could mask), we
    materialize the SAME raw text through reconcile's real dedup+EOL path and
    compare the resulting bytes (external code review, OpenAI parity gap)."""
    from lib.churn_merge import dedup_triage_lines
    raw = "a\r\nb\nc\r\nb\r\n"  # mixed EOL + a duplicate ("b")

    # Sweep's normalize.
    lines, eol = sweep_outbox._normalize_lines(raw)
    sweep_deduped, _ = dedup_triage_lines(lines)
    sweep_text = (eol.join(sweep_deduped) + eol) if sweep_deduped else ""

    # Reconcile's REAL inline idiom (copied verbatim from reconcile_main_triage).
    r_eol = "\r\n" if "\r\n" in raw else "\n"
    r_lines = [ln[:-1] if ln.endswith("\r") else ln for ln in raw.split("\n")]
    if r_lines and r_lines[-1] == "":
        r_lines = r_lines[:-1]
    r_deduped, _ = dedup_triage_lines(r_lines)
    r_text = (r_eol.join(r_deduped) + r_eol) if r_deduped else ""

    assert sweep_text == r_text, (sweep_text, r_text)
    # CRLF was the dominant EOL → preserved; the duplicate "b" collapsed once.
    assert sweep_text == "a\r\nb\r\nc\r\n"


def test_gc_preserves_outbox_own_eol_not_worktree_eol(repo) -> None:
    """The GC writes survivors back with the OUTBOX's own EOL, NOT the worktree
    triage EOL (external code review, OpenAI). A CRLF outbox + LF worktree must
    keep the surviving outbox line CRLF-terminated after a partial GC."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"), h.item("trg-delivered"))  # LF worktree
    # CRLF outbox: one delivered (GC'd), one fresh (survives CRLF).
    p = work / h.OUTBOX
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("wb") as fh:
        fh.write((h.item("trg-delivered") + "\r\n").encode("utf-8"))
        fh.write((h.item("trg-fresh") + "\r\n").encode("utf-8"))
    wt = h.make_worktree(work, "sweep-eol-gc")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.gc_dropped == 1, result.to_dict()
    survivors_raw = p.read_bytes()
    # The surviving outbox line kept its CRLF (not rewritten to the worktree LF).
    assert b"\r\n" in survivors_raw, survivors_raw
    assert h.item("trg-fresh").encode("utf-8") in survivors_raw


# --------------------------------------------------------------------------- #
# AC3 — sweep commits on the BRANCH; local main gets NO chore(triage) commit
# --------------------------------------------------------------------------- #


def test_sweep_commits_on_branch_not_main(repo) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    main_head_before = h.git(work, "rev-parse", "main").stdout.strip()

    wt = h.make_worktree(work, "sweep-branch")
    h.write_outbox(work, h.item("trg-bbbb"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed", result.to_dict()
    assert result.swept == 1
    assert h.item("trg-bbbb") in h.branch_triage_lines(wt)
    assert h.git(work, "rev-parse", "main").stdout.strip() == main_head_before
    assert "sweep" not in h.git(work, "log", "main", "--format=%s").stdout


def test_sweep_branch_commit_subject(repo) -> None:
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-subject")
    h.write_outbox(work, h.item("trg-bbbb"), h.item("trg-cccc"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed"
    subject = h.git(wt, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "chore(triage): sweep 2 outbox append(s) into branch", subject


def test_header_preserved_first_line_on_branch(repo) -> None:
    """The materialized branch log keeps the schema header as line 1."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-header")
    h.write_outbox(work, h.item("trg-bbbb"))

    sweep_outbox_to_branch(work, wt, default_branch="main")

    first = (wt / TRIAGE).read_text(encoding="utf-8").splitlines()[0]
    assert first == h.HEADER, first


# --------------------------------------------------------------------------- #
# AC2 — abandoned/deleted branch strands NO line (GC keeps un-delivered lines)
# --------------------------------------------------------------------------- #


def test_swept_line_stays_in_outbox_until_origin_delivered(repo) -> None:
    """A just-swept line is on the branch but NOT yet in origin → it must SURVIVE
    in the outbox (so an abandoned branch re-sweeps it)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-survive")
    h.write_outbox(work, h.item("trg-bbbb"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.status == "committed"
    assert result.gc_dropped == 0  # not origin-delivered
    assert h.item("trg-bbbb") in h.outbox_lines(work)


def test_abandoned_branch_resweeps_line(repo) -> None:
    """Real abandoned-branch path: sweep onto a branch, DELETE it unmerged, run
    setup/sweep onto a NEW branch → the line is re-swept and present."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))

    wt1 = h.make_worktree(work, "sweep-abandon-1")
    h.write_outbox(work, h.item("trg-bbbb"))
    r1 = sweep_outbox_to_branch(work, wt1, default_branch="main")
    assert r1.status == "committed"
    assert h.item("trg-bbbb") in h.branch_triage_lines(wt1)
    assert h.item("trg-bbbb") in h.outbox_lines(work)  # not GC'd (not in origin)

    h.git(work, "worktree", "remove", "--force", str(wt1))
    h.git(work, "branch", "-D", "iterate/sweep-abandon-1")

    wt2 = h.make_worktree(work, "sweep-abandon-2")
    r2 = sweep_outbox_to_branch(work, wt2, default_branch="main")
    assert r2.status == "committed", r2.to_dict()
    assert r2.swept == 1, "the abandoned line must be re-swept"
    assert h.item("trg-bbbb") in h.branch_triage_lines(wt2)


def test_origin_delivered_line_is_gced(repo) -> None:
    """Once a line is in origin/main's tracked log, the NEXT sweep's GC drops it
    from the outbox (the merge happened; re-sweeping is no longer needed)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"), h.item("trg-bbbb"))  # merged PR
    h.write_outbox(work, h.item("trg-bbbb"))  # lingering pre-GC outbox copy
    wt = h.make_worktree(work, "sweep-gc")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.gc_dropped == 1, result.to_dict()
    assert h.item("trg-bbbb") not in h.outbox_lines(work)


def test_gc_drops_only_delivered_keeps_undelivered(repo) -> None:
    """Mixed outbox: one line already in origin (GC'd), one not (survives)."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"), h.item("trg-delivered"))
    h.write_outbox(work, h.item("trg-delivered"), h.item("trg-fresh"))
    wt = h.make_worktree(work, "sweep-mixed")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    survivors = h.outbox_lines(work)
    assert h.item("trg-delivered") not in survivors  # in origin → GC'd
    assert h.item("trg-fresh") in survivors          # not in origin → kept
    assert result.gc_dropped == 1


# --------------------------------------------------------------------------- #
# AC4 — exactly-once after PR merge + merge=union
# --------------------------------------------------------------------------- #


def test_swept_line_exactly_once_after_union_merge(repo) -> None:
    """Actually merge the branch (post-sweep) into a divergent origin/main with
    the union driver, then assert the swept line appears EXACTLY once and
    validate passes."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-union")
    h.write_outbox(work, h.item("trg-bbbb"))

    r = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert r.status == "committed"

    # origin/main advances divergently: another append lands on main + push.
    with (work / TRIAGE).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(h.item("trg-cccc") + "\n")
    h.git(work, "commit", "-am", "main appends trg-cccc")
    h.git(work, "push", "origin", "main")

    h.git(wt, "fetch", "origin")
    merge = h.git(wt, "merge", "--no-edit", "origin/main", check=False)
    assert merge.returncode == 0, merge.stderr

    merged_lines = [
        ln for ln in (wt / TRIAGE).read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert sum(1 for ln in merged_lines if h.item("trg-bbbb") == ln.strip()) == 1
    assert sum(1 for ln in merged_lines if h.item("trg-cccc") == ln.strip()) == 1
    from lib.churn_merge import validate_triage_text
    assert validate_triage_text((wt / TRIAGE).read_text(encoding="utf-8")) == []


def test_double_sweep_idempotent(repo) -> None:
    """Sweeping the SAME outbox twice does not duplicate the line on the branch."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))
    wt = h.make_worktree(work, "sweep-twice")
    h.write_outbox(work, h.item("trg-bbbb"))

    r1 = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert r1.status == "committed" and r1.swept == 1
    head_after_first = h.git(wt, "rev-parse", "HEAD").stdout.strip()

    r2 = sweep_outbox_to_branch(work, wt, default_branch="main")
    assert r2.status == "no_change", r2.to_dict()
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == head_after_first
    branch_appends = [ln for ln in h.branch_triage_lines(wt) if '"event":"append"' in ln]
    assert branch_appends.count(h.item("trg-bbbb")) == 1


def test_sweep_collapses_producer_double_append_keep_last(repo) -> None:
    """Regression (trg-60ef91fb): a producer re-appending an UPDATED, non-byte-
    identical version of a finding must NOT return ``invalid`` and wedge the whole
    outbox — the sweep folds the LAST append onto the branch (reader parity)."""
    work, _ = repo
    h.seed_tracked(work)  # header only
    a1 = '{"event":"append","id":"trg-x","ts":"2026-06-09T06:17:00Z","title":"draft","status":"triage"}'
    a2 = '{"event": "append", "id": "trg-x", "ts": "2026-06-09T06:29:00Z", "title": "resolved", "status": "triage"}'
    h.write_outbox(work, a1, a2)
    wt = h.make_worktree(work, "dbl-append")

    res = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert res.status == "committed", res.to_dict()
    branch = h.branch_triage_lines(wt)
    assert [ln for ln in branch if '"append"' in ln and "trg-x" in ln] == [a2]
    assert a1 not in branch
