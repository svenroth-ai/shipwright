"""The F11 check (`check_no_silent_revert`), split out of
``test_silent_revert.py`` at the 300-LOC bloat-baseline threshold (P3.4
tagging backfill: every test in that file already carried the same
``FR-01.11/AC18`` tag, so there was no "newly tagged subset" to extract --
the file's own existing section boundary, "the F11 check", is the split
instead; the pure ``dropped_lines`` detector tests stay in the sibling file).

See ``test_silent_revert.py``'s module docstring for the full PR #463
motivation this check exists to close.
"""

from __future__ import annotations
import pytest

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


@pytest.mark.covers("FR-01.11/AC18")
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


@pytest.mark.covers("FR-01.11/AC18")
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


@pytest.mark.covers("FR-01.11/AC18")
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


@pytest.mark.covers("FR-01.11/AC18")
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


@pytest.mark.covers("FR-01.11/AC18")
def test_a_clean_branch_passes(tmp_path):
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")

    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is True


@pytest.mark.covers("FR-01.11/AC18")
def test_no_default_branch_is_a_visible_skip_not_a_pass(tmp_path):
    """Fail-honest: if the comparison cannot be made, say so rather than
    reporting that nothing was lost."""
    root = _repo(tmp_path)

    result = check_no_silent_revert(root, default_branch="no-such-branch")

    assert result.severity == "skipped"
    assert "no-such-branch" in result.detail


@pytest.mark.covers("FR-01.11/AC18")
def test_a_non_git_tree_skips(tmp_path):
    result = check_no_silent_revert(tmp_path, default_branch="main")
    assert result.severity == "skipped"


@pytest.mark.covers("FR-01.11/AC18")
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
