"""What the derived-snapshot gate SAYS, as opposed to what it sees.

Subject: ``derived_snapshot_gate._remedy`` (trg-d0e4592e, fixed in
iterate-2026-07-31-derived-docs-at-release). Its own file because that is the
card's own seam — ``test_derived_snapshot_gate.py`` owns what the gate catches,
this owns whether an operator can act on it.

The gate always BLOCKED correctly; nothing bad ever shipped. The defect was that
following its printed instruction on a merge HEAD changed nothing, so the next
run failed identically and the operator looped. The decisive test therefore does
not inspect the wording — it RUNS the printed command and re-runs the gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402

_DASH = ".shipwright/compliance/dashboard.md"
_RUN_ID = "iterate-2026-07-31-derived-docs-at-release"
_SOURCE_RE = re.compile(r"--source=(\S+)")


def _merge_head_with_an_offender(git_origin_repo, make_worktree):
    """PR #493's shape: the offender in an earlier commit, a merge on top.

    Returns ``(worktree, head_sha)``.
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-remedy")
    _write(wt, "app.py", "the real change\n")
    _write(wt, _DASH, "a derived view that must not ship\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: something, plus an accident")

    _write(work, "other.py", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves")
    _git(work, "push", "origin", "main")
    _git(wt, "fetch", "origin")
    _git(wt, "merge", "--no-ff", "--no-edit", "origin/main")

    parents = _git(wt, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3, "the fixture must really put a MERGE commit on top"
    return wt, _git(wt, "rev-parse", "HEAD").stdout.strip()


# --- AC-11: the printed command actually clears the gate ---------------------


def test_following_the_printed_remedy_clears_the_gate_on_a_merge_head(
    git_origin_repo, make_worktree,
):
    """The whole card, end to end. Not 'is the wording right' — 'does doing it work'."""
    from tools.verifiers.derived_snapshot_gate import (
        check_no_derived_snapshots_committed,
    )

    wt, head = _merge_head_with_an_offender(git_origin_repo, make_worktree)

    blocked = check_no_derived_snapshots_committed(wt, _RUN_ID, head)
    assert blocked.ok is False
    source = _SOURCE_RE.search(blocked.detail)
    assert source, f"no restore source printed: {blocked.detail}"

    _git(wt, "restore", f"--source={source.group(1)}", "--staged", "--worktree",
         "--", _DASH)
    _git(wt, "commit", "--amend", "--no-edit")

    after = check_no_derived_snapshots_committed(
        wt, _RUN_ID, _git(wt, "rev-parse", "HEAD").stdout.strip())
    assert after.ok is True, (
        "following the gate's own instruction left the gate red — the operator loops"
    )


def test_the_remedy_no_longer_names_head_tilde_one(git_origin_repo, make_worktree):
    """The regression, pinned by name. On a merge HEAD ``HEAD~1`` is the FIRST
    PARENT — the branch's own pre-merge tip, i.e. the commit carrying the
    offending snapshot. Restoring from it writes the offending content over
    itself."""
    from tools.verifiers.derived_snapshot_gate import (
        check_no_derived_snapshots_committed,
    )

    wt, head = _merge_head_with_an_offender(git_origin_repo, make_worktree)
    detail = check_no_derived_snapshots_committed(wt, _RUN_ID, head).detail
    assert "HEAD~1" not in detail


def test_the_printed_source_is_the_merge_base_not_the_first_parent(
    git_origin_repo, make_worktree,
):
    """Pins WHICH commit, so a future edit cannot drift back to something that
    merely happens to work on a non-merge HEAD."""
    from tools.verifiers.derived_snapshot_gate import (
        check_no_derived_snapshots_committed,
    )
    from tools.verifiers.git_helpers import _branch_base_commit

    wt, head = _merge_head_with_an_offender(git_origin_repo, make_worktree)
    detail = check_no_derived_snapshots_committed(wt, _RUN_ID, head).detail
    printed = _SOURCE_RE.search(detail).group(1)

    base = _branch_base_commit(wt, head)
    first_parent = _git(wt, "rev-parse", "HEAD~1").stdout.strip()
    assert base and printed == base[:12]
    assert printed != first_parent[:12]


# --- AC-12: no base, no command ----------------------------------------------


def test_no_resolvable_base_prints_no_source_at_all(
    git_origin_repo, make_worktree, monkeypatch,
):
    """A gate that already misdirected an operator once does not get to guess a
    second commit. Words instead of a command that would be wrong."""
    from tools.verifiers import derived_snapshot_gate as gate

    wt, head = _merge_head_with_an_offender(git_origin_repo, make_worktree)
    monkeypatch.setattr(gate, "_branch_base_commit", lambda root, commit: None)

    detail = gate.check_no_derived_snapshots_committed(wt, _RUN_ID, head).detail
    assert "--source" not in detail
    assert "git restore" not in detail
    assert "forked from" in detail, "it must still say what to do, just not how"


def test_the_finding_itself_survives_an_unresolvable_base(
    git_origin_repo, make_worktree, monkeypatch,
):
    """The remedy degrading must never soften the verdict — this is an ERROR gate
    and the offender is still named."""
    from tools.verifiers import derived_snapshot_gate as gate

    wt, head = _merge_head_with_an_offender(git_origin_repo, make_worktree)
    monkeypatch.setattr(gate, "_branch_base_commit", lambda root, commit: None)

    result = gate.check_no_derived_snapshots_committed(wt, _RUN_ID, head)
    assert result.ok is False
    assert _DASH in result.detail


def test_a_run_written_offender_still_never_gets_worktree(
    git_origin_repo, make_worktree,
):
    """The trg-ad29a709 guard composes with the new source: `--worktree` on
    ``shipwright_test_results.json`` destroys the ledger F5 just wrote, and the
    operator pastes ONE command for all the offenders."""
    from lib.churn_merge import TEST_RESULTS
    from tools.verifiers.derived_snapshot_gate import (
        check_no_derived_snapshots_committed,
    )

    wt, _head = _merge_head_with_an_offender(git_origin_repo, make_worktree)
    _write(wt, TEST_RESULTS, '{"iterate_latest": {"totals": 1}}\n')
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "chore: and the ledger too")

    detail = check_no_derived_snapshots_committed(
        wt, _RUN_ID, _git(wt, "rev-parse", "HEAD").stdout.strip()).detail
    assert "--staged --worktree" not in detail
    assert "--staged" in detail


# --- P2.15: the run-written carve-out, seen from the gate --------------------
#
# `session_handoff.md` left `RESTORABLE_SNAPSHOTS` (trg-01cd6aef) so a mid-run restore
# stops destroying the run's canon marker. Two consequences land here rather than in
# `test_derived_snapshot_gate.py`, which sits at 272 of the 300-line source limit and
# would cross it: what the gate still CATCHES, and what it now TELLS the operator.

def _committed_handoff(git_origin_repo, make_worktree):
    """A branch whose commit carries the note. Returns ``(worktree, head_sha)``."""
    from lib.derived_snapshots import SESSION_HANDOFF

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "seed\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-handoff")
    _write(wt, SESSION_HANDOFF, '---\ncanon_generated: true\nrun_id: "r"\n---\n')
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "a commit that must not be allowed to carry the note")
    return wt, _git(wt, "rev-parse", "HEAD").stdout.strip()


def test_the_gate_still_blocks_the_session_handoff(git_origin_repo, make_worktree) -> None:
    """The carve-out must never read as "so now it may ship".

    Keeping the note out of the PR is what removed the N(N-1)/2 collision class; P2.15
    changed who may RESET it mid-run, nothing about who may COMMIT it. Two adjacent
    registers, one of which moved — worth a test rather than a reader's confidence.
    """
    from lib.derived_snapshots import SESSION_HANDOFF
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    wt, head = _committed_handoff(git_origin_repo, make_worktree)

    result = check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is False, "the derived-snapshot commit gate must still block it"
    assert SESSION_HANDOFF in result.detail


def test_the_remedy_never_offers_to_reset_the_note_on_disk(git_origin_repo, make_worktree) -> None:
    """This file's own subject: what an operator is told to type.

    `_restore_flags` suggests `--staged --worktree` only when every offender is
    re-derivable; a run-written offender narrows it to `--staged`, because `--worktree`
    resets the file on disk to its pre-iterate state. The rule was written for the F5
    ledger (trg-ad29a709) and keys off `RESTORABLE_SNAPSHOTS`, so the note inherited the
    protection the moment it joined the carve-out — following the gate's own printed
    instruction can no longer destroy this run's canon marker.
    """
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    wt, head = _committed_handoff(git_origin_repo, make_worktree)

    detail = check_no_derived_snapshots_committed(wt, _RUN_ID, head).detail

    assert "--staged" in detail, detail
    assert "--worktree" not in detail, (
        "the remedy offered to reset the note on disk, which would destroy the very "
        "marker the carve-out preserves"
    )


def test_the_narrowing_applies_to_EVERY_offender_not_just_the_run_written_one(
    git_origin_repo, make_worktree,
) -> None:
    """The cost of the narrowing, pinned rather than only its benefit.

    `_restore_flags` tests the offender SET, so one run-written path narrows the flags for
    all of them. The realistic trigger for this gate is a stray `git add -A`, which sweeps
    the note in together with its neighbours in the same directory — so after P2.15 that
    commit is told `--staged` alone, and following the instruction leaves the re-derivable
    offenders modified-but-unstaged, which is the state a later `git merge` refuses on.

    Recoverable on the integrate path, where `restore_derived_to_head` cleans them; not on
    a repair branch that never integrates. Splitting the remedy into two commands (one per
    class) is the real fix and is deliberately NOT done here — it rewrites operator-facing
    text well beyond this card. Recording the behaviour is what stops the next reader
    assuming the narrowing is free (Stage-3 doubt review, low).
    """
    from lib.derived_snapshots import SESSION_HANDOFF
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "seed\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-mixed")
    _write(wt, SESSION_HANDOFF, '---\ncanon_generated: true\nrun_id: "r"\n---\n')
    _write(wt, _DASH, "a re-derivable view swept in by the same `git add -A`\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "a stray add -A carried both")
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()

    result = check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is False
    assert SESSION_HANDOFF in result.detail and _DASH in result.detail
    # One run-written offender narrows the flags for the re-derivable one too.
    assert "--staged" in result.detail
    assert "--worktree" not in result.detail, (
        "if this ever flips, the remedy would reset the note on disk and destroy the "
        "run's canon marker — the narrowing must hold for the whole set"
    )
