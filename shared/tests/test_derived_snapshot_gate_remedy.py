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
