"""P2.43 — `ensure_current.py`'s `_absorb_dirty_triage_log` guard.

Split out of `test_ensure_current.py` to stay under the 300-line guideline
(same pattern as `test_sweep_outbox_review_cascade2.py` next to
`test_triage_outbox.py`). Imports the shared helpers/fixtures from that sibling
module rather than duplicating them.

A background producer (the compliance-backlog Stop hook) refreshes the tracked
`.shipwright/triage.jsonl` on every Stop hook for an iterate run's whole
duration — not just once — so a finalization spanning more than one Stop can
leave it dirty at exactly the moment F11's `ensure_current` tries to merge
`origin/<default>`, and `git merge` refuses outright ("local changes ... would
be overwritten"). Measured twice in one run and on PR #582 across two
consecutive integration attempts, which had to carry the appends onto the
branch as chore commits by hand. `_absorb_dirty_triage_log` automates exactly
that, scoped to the one path.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins for `tools`

from test_ensure_current import _DASH, _RUN_ID, _fake_regen  # noqa: E402
from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import ensure_current as ec  # noqa: E402
from tools import integrate_main, integrate_merge  # noqa: E402

_TRIAGE = ".shipwright/triage.jsonl"


def test_ensure_current_absorbs_dirty_triage_log_before_merging(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Reproduces the reported failure: a background producer (the compliance
    backlog Stop hook) dirties `.shipwright/triage.jsonl` AFTER the run's own
    commit, and origin ALSO advanced that same path — the exact precondition
    for git's pre-merge refusal ("local changes ... would be overwritten"),
    which is what turned into `ensure_current` exit 6 on PR #582. The guard
    must absorb the dirty log into its own small commit and still integrate,
    rather than fail before the merge even starts."""
    _header = '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}'
    _append1 = '{"event":"append","id":"trg-1","source":"compliance","severity":"low","kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:00Z"}'
    _append_main = '{"event":"append","id":"trg-main","source":"compliance","severity":"low","kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:01Z"}'
    _append_wt = '{"event":"append","id":"trg-worktree","source":"compliance","severity":"low","kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:02Z"}'

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TRIAGE, f"{_header}\n{_append1}\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed triage log")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-triage-absorb")
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")

    # origin advances the SAME triage path -> the worktree goes behind AND the
    # merge would touch a path this worktree also has feelings about.
    _write(work, _TRIAGE, f"{_header}\n{_append1}\n{_append_main}\n")
    _git(work, "commit", "-am", "main appends trg-main")
    _git(work, "push", "origin", "main")

    # The background producer's post-commit refresh: uncommitted, in the worktree.
    _write(wt, _TRIAGE, f"{_header}\n{_append1}\n{_append_wt}\n")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", _fake_regen)

    result = ec.ensure_current(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert result["integrated"] is True, result
    assert "triage-absorbed" in result["steps"], result
    assert not _git(wt, "status", "--porcelain").stdout.strip(), "worktree must end clean"
    # Both sides' appends survive the churn-resolved merge — nothing was dropped
    # by treating the absorb commit as "mine wins".
    merged = (wt / _TRIAGE).read_text(encoding="utf-8")
    assert "trg-main" in merged
    assert "trg-worktree" in merged


def test_ensure_current_absorb_commit_alone_counts_as_integrated(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Regression for the `head_before`/absorb ordering bug (Stage-2 code
    review, medium): if the absorb commit is the ONLY commit that lands —
    `integrate()` turns out to be a genuine no-op, the documented "ancestor by
    merge time" race — `integrated` must still be True, or the caller never
    re-pushes and the absorbed content is lost when F11 tears the worktree
    down."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n')
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard + triage log")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-absorb-only")
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")

    # origin advances -> `behind` reads > 0.
    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main changes dashboard")
    _git(work, "push", "origin", "main")

    # The background producer's dirty write to the ALREADY-TRACKED log,
    # absorbed as a real commit (an untracked triage.jsonl is skipped by
    # design — Stage-3 doubt review, low).
    _write(wt, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n{"event":"append","id":"trg-1","source":"compliance","severity":"low","kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:01Z"}\n')

    # integrate() itself is a no-op this time: the ONLY commit that actually
    # lands is the absorb.
    monkeypatch.setattr(
        integrate_main, "integrate",
        lambda *a, **k: {"status": "ok", "steps": ["already-current-race"]},
    )

    result = ec.ensure_current(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert result["integrated"] is True, result
    assert "triage-absorbed" in result["steps"], result


def test_ensure_current_absorbs_on_the_already_current_path_too(
    git_origin_repo, make_worktree,
) -> None:
    """Stage-3 doubt review, high: `ensure_current` is also invoked when the
    branch is ALREADY current — the delivery ladder's repeat refresh calls —
    which is exactly the state a long finalization's background writes
    accumulate in BETWEEN calls. Absorbing only on the "behind, about to
    merge" path would leave those writes to be silently destroyed when F11
    tears the worktree down: the same failure class the rejected
    outbox-routing alternative was rejected for. The absorb must fire, and
    `integrated` must report True, even though no merge happens at all."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed triage log")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-absorb-when-current")
    # The background producer's dirty write to the tracked log -- nothing else
    # changed, so the branch stays exactly current with origin/main.
    _write(wt, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n{"event":"append","id":"trg-1","source":"compliance","severity":"low","kind":"compliance","title":"t","detail":"d","ts":"2026-08-06T00:00:01Z"}\n')

    result = ec.ensure_current(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert result["action"] == "already-current", result
    assert result["behind"] == 0, result
    assert "triage-absorbed" in result["steps"], result
    assert result["integrated"] is True, result
    assert not _git(wt, "status", "--porcelain").stdout.strip(), "worktree must end clean"


def test_absorb_skips_when_a_merge_is_already_in_progress(git_origin_repo) -> None:
    """Stage-2 code review (final pass): the MERGE_HEAD guard added for the
    prior "unconditional git add" finding needs its own regression test — a
    dirty triage.jsonl while a real conflicting merge is wedged (MERGE_HEAD
    standing) must be left untouched, not staged, or an unmerged `UU` path
    could get silently marked resolved with its conflict markers still in the
    content. Same MERGE_HEAD-leaving recipe as
    test_reconcile_triage_guards.py::test_skip_on_merge_in_progress."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n')
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed triage log")

    _git(work, "checkout", "-b", "side")
    _write(work, "c.txt", "side\n")
    _git(work, "add", "c.txt")
    _git(work, "commit", "-m", "side")
    _git(work, "checkout", "main")
    _write(work, "c.txt", "main\n")
    _git(work, "add", "c.txt")
    _git(work, "commit", "-m", "main")
    _git(work, "merge", "side", check=False)  # conflict -> MERGE_HEAD persists

    _write(work, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n{"event":"append"}\n')

    result = ec._absorb_dirty_triage_log(work)

    assert result == "triage-absorb-skipped-op-in-progress", result
    # No index mutation: nothing got staged.
    assert _TRIAGE not in _git(work, "diff", "--cached", "--name-only").stdout
    assert _git(work, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode == 0, \
        "MERGE_HEAD must still be standing -- confirms the fixture actually wedged the merge"


def test_ensure_current_clean_triage_log_adds_no_absorb_step(
    git_origin_repo, make_worktree, monkeypatch,
) -> None:
    """Sanity/regression: a TRACKED, clean triage.jsonl (not merely an absent
    one — Stage-2 code review, low: an absent file hits the same empty-porcelain
    branch, so this must exercise tracked-and-clean specifically) must not fire
    the absorb step spuriously on an otherwise-ordinary integrate."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _TRIAGE, '{"v":1,"schema":"triage","created":"2026-08-06T00:00:00Z"}\n')
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard + triage log")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-triage-clean")
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")

    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main changes dashboard")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", _fake_regen)

    result = ec.ensure_current(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert "triage-absorbed" not in result["steps"], result
