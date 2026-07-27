"""A branch must not quietly drop work that landed while it was open
(iterate-2026-07-27-no-silent-revert).

PR #463 rewrote `docs/hooks-and-pipeline.md` from a stale base: 10 insertions,
83 deletions, silently reverting documentation from four already-merged PRs
(#443, #454/#460, #456, #459). Nothing caught it. The repo already requires
branches to be up to date, which is what *forces* the integration in which the
bad resolution happens; `ensure_current` correctly refuses a non-churn conflict
and hands over to a human; and then:

  - `PR Review` (the LLM gate that saw the whole diff) returned SUCCESS,
  - `Anti-ratchet` only ever looks at files GROWING past a baseline,
  - the squash-merge flattened the branch, so the resolution left no trace.

The question this check asks is narrow and decidable: **every line `main` gained
since this branch forked must still be present in the branch's result.** A line
that main has, that arrived after the fork, and that the branch's tree no longer
contains, is work being thrown away — either deliberately (say so) or by a
conflict resolved in favour of one side without reading the other.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers.silent_revert import (  # noqa: E402
    check_no_silent_revert,
    dropped_lines,
)

DOC = "docs/notes.md"


def _git(root: Path, *args: str, check=True) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=check).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    """A tiny repo shaped like ours: a `main`, and a branch forked off it."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "docs").mkdir()
    (root / DOC).write_text("alpha\nbravo\ncharlie\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _write(root: Path, text: str, message: str) -> None:
    (root / DOC).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message)


def _fork(root: Path, name: str = "work") -> None:
    _git(root, "checkout", "-q", "-b", name)


def _main_gains(root: Path, text: str) -> None:
    """Someone else's PR lands on main while our branch is open."""
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _git(root, "checkout", "-q", "main")
    _write(root, text, "someone else's merged work")
    _git(root, "checkout", "-q", current)


# --- the pure detector --------------------------------------------------------

def test_the_463_shape_is_caught(tmp_path):
    """The motivating case: the branch integrates main, resolves the conflict in
    favour of its own copy, and main's newer content disappears."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR DOCUMENTED BEHAVIOUR\n")
    # Resolve "by hand" in favour of ours — their line is gone.
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "THEIR DOCUMENTED BEHAVIOUR" in dropped[DOC]


def test_a_clean_integration_drops_nothing(tmp_path):
    """The normal case: both sides' content survives the merge."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", check=False)
    # Simulate a correct union resolution.
    (root / DOC).write_text("alpha\nbravo\ncharlie\nBRANCH LINE\nTHEIR LINE\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "merge main (union)", check=False)

    assert dropped_lines(root, "main", "HEAD") == {}


def test_a_branch_that_never_integrated_is_not_accused(tmp_path):
    """A branch that simply has not merged main yet is BEHIND, not reverting.
    Accusing it would fire on every branch the moment anything lands on main."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")

    assert dropped_lines(root, "main", "HEAD") == {}


def test_editing_a_line_that_existed_before_is_not_a_drop(tmp_path):
    """An edit to a line that predates the fork is nobody else's work."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", check=False)
    (root / DOC).write_text("alpha\nEDITED\ncharlie\nBRANCH LINE\nTHEIR LINE\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "merge + edit our own line", check=False)

    assert dropped_lines(root, "main", "HEAD") == {}


def test_overwriting_a_line_main_itself_changed_IS_reported(tmp_path):
    """The one case that is genuinely undecidable from content, pinned honestly.

    Main changed a line; this branch then changed that same line again. Whether
    that is "I built on their change" or "I threw their change away" cannot be
    read off the text — and it is precisely the #463 shape at line granularity,
    where a whole file was replaced with an older copy. So the check reports it
    and asks, rather than guessing. The declaration is the answer: say what you
    are removing and why. Named after the external-review finding that the
    earlier version of this test did not actually exercise the condition.
    """
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nTHEIR VERSION OF BRAVO\ncharlie\n")
    _git(root, "merge", "-q", "main", check=False)
    (root / DOC).write_text("alpha\nOUR VERSION OF BRAVO\ncharlie\nBRANCH LINE\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "merge, then take our wording", check=False)

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "THEIR VERSION OF BRAVO" in dropped[DOC]
    # ...and the declared-removal path is how an operator settles it.
    result = check_no_silent_revert(
        root, default_branch="main",
        declared_removals=[{"path": DOC, "reason": "their wording superseded here"}],
    )
    assert result.ok is True


def test_deleting_a_file_after_taking_their_work_is_reported(tmp_path):
    """Losing a whole file counts the same as losing lines inside one."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")  # a real merge, not a fast-forward
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")
    (root / DOC).unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "drop the file")

    assert DOC in dropped_lines(root, "main", "HEAD")


def test_a_branch_that_never_integrated_is_not_this_checks_business(tmp_path):
    """The boundary, stated on purpose. Without an integration there are no two
    sides to compare, so a deletion is simply the branch's own change — visible
    in its own diff and reviewed as such. This check exists for losses that hide
    INSIDE a merge, which is exactly where they stop being visible."""
    root = _repo(tmp_path)
    _fork(root)
    (root / DOC).unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "our own deletion")

    assert dropped_lines(root, "main", "HEAD") == {}


def test_blank_and_whitespace_lines_are_ignored(tmp_path):
    """Formatting churn must not read as lost work."""
    root = _repo(tmp_path)
    _fork(root)
    _main_gains(root, "alpha\nbravo\ncharlie\n\n   \n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")

    assert dropped_lines(root, "main", "HEAD") == {}


# --- the F11 check ------------------------------------------------------------

def test_the_check_blocks_and_names_the_file(tmp_path):
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR DOCUMENTED BEHAVIOUR\n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is False
    assert result.severity != "warning"          # has teeth
    assert DOC in result.detail
    assert "THEIR DOCUMENTED BEHAVIOUR" in result.detail   # shows WHAT is being lost


def test_a_declared_removal_passes(tmp_path):
    """Deliberately removing something main just added is legitimate — it just
    has to be said out loud, the same shape as every other disposition here."""
    root = _repo(tmp_path)
    _fork(root)
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    declared = [{"path": DOC, "reason": "superseded by the rewrite in this change"}]
    result = check_no_silent_revert(root, default_branch="main", declared_removals=declared)

    assert result.ok is True
    assert "declared" in result.detail.lower()


def test_a_declaration_without_a_reason_does_not_count(tmp_path):
    """An escape hatch that takes no argument is not a disposition."""
    root = _repo(tmp_path)
    _fork(root)
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    result = check_no_silent_revert(
        root, default_branch="main", declared_removals=[{"path": DOC, "reason": "  "}],
    )

    assert result.ok is False


def test_a_declaration_for_another_file_does_not_cover_this_one(tmp_path):
    root = _repo(tmp_path)
    _fork(root)
    _main_gains(root, "alpha\nbravo\ncharlie\nTHEIR LINE\n")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    result = check_no_silent_revert(
        root, default_branch="main",
        declared_removals=[{"path": "docs/other.md", "reason": "unrelated"}],
    )

    assert result.ok is False


def test_a_clean_branch_passes(tmp_path):
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")

    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is True


def test_no_default_branch_is_a_visible_skip_not_a_pass(tmp_path):
    """Fail-honest: if the comparison cannot be made, say so rather than
    reporting that nothing was lost."""
    root = _repo(tmp_path)

    result = check_no_silent_revert(root, default_branch="no-such-branch")

    assert result.severity == "skipped"
    assert "no-such-branch" in result.detail


def test_a_non_git_tree_skips(tmp_path):
    result = check_no_silent_revert(tmp_path, default_branch="main")
    assert result.severity == "skipped"


def test_derived_churn_artifacts_are_excluded(tmp_path):
    """Found by running this check against its own branch: all eleven files it
    flagged were CHURN_ALLOWLIST artifacts and none was authored content.

    Those files are regenerated from the merged tree rather than merged line by
    line, so their content legitimately changes wholesale at every integration.
    Comparing them would fire on every iterate — a gate nobody would keep.
    """
    from lib.churn_merge import CHURN_ALLOWLIST

    churn = "shipwright_test_results.json"
    assert churn in CHURN_ALLOWLIST

    root = _repo(tmp_path)
    (root / churn).write_text('{"a": 1}\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add a derived artifact")
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    # Main regenerates the derived artifact...
    _git(root, "checkout", "-q", "main")
    (root / churn).write_text('{"a": 2, "regenerated": true}\n', encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "main regenerates it")
    _git(root, "checkout", "-q", "work")
    # ...and we take ours wholesale, exactly as the churn resolver does.
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    assert dropped_lines(root, "main", "HEAD") == {}
