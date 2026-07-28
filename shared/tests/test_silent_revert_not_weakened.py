"""The filters must not clear a REAL revert
(iterate-2026-07-28-silent-revert-false-positives).

Every one of these was constructed by the Stage-3 adversarial review to disprove
the first version of this change, and every one of them succeeded: against that
version all four returned "nothing was dropped". They are the regression net for
the direction that matters — `test_silent_revert_false_positives.py` proves the
gate stopped crying wolf, and this file proves it can still bite.

Read them as the specification of what the three filters are NOT allowed to
explain away:

* a line the branch never took delivery of, vouched for by a line it wrote
  BEFORE that line existed (D1, D2) — closed by excluding the branch's own
  pre-merge side from the set of possible replacements;
* an unrelated line dragged into the same hunk by a whitespace-only reformat
  (D3) — closed by diffing whitespace-insensitively, so the hunks and the
  findings agree on what "the same line" means;
* a line the default branch merely edited afterwards, where the branch carries
  neither version (D4) — closed by requiring the branch to actually carry what
  superseded it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers.silent_revert import dropped_lines  # noqa: E402

DOC = "docs/notes.md"


def _git(root: Path, *args: str, check=True) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=check).stdout.strip()


def _repo(tmp_path: Path, body: str = "alpha\nbravo\ncharlie\n") -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "merge.conflictStyle", "merge")
    (root / DOC).write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    _git(root, "checkout", "-q", "-b", "work")
    return root


def _write(root: Path, text: str, message: str) -> None:
    (root / DOC).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message, check=False)


def _on_main(root: Path, text: str, message: str) -> None:
    _git(root, "checkout", "-q", "main")
    _write(root, text, message)
    _git(root, "checkout", "-q", "work")


def test_a_branch_line_that_merely_mentions_what_it_discards(tmp_path):
    """D1 — the check's OWN motivating case, with the branch line reworded.

    `test_the_463_shape_is_caught` verbatim, except the branch's line now happens
    to contain the words of the line the merge throws away. The branch wrote it
    BEFORE ever seeing theirs, so it cannot be "the line that replaced" it — but
    the hunk pairing alone could not tell, and cleared a `-s ours` resolution that
    discards documented behaviour while naming it."""
    root = _repo(tmp_path)
    _write(root, "alpha\nbravo\ncharlie\n"
                 "BRANCH LINE - THEIR DOCUMENTED BEHAVIOUR is no longer required\n", "our work")
    _on_main(root, "alpha\nbravo\ncharlie\nTHEIR DOCUMENTED BEHAVIOUR\n", "their work")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge main (ours)")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "THEIR DOCUMENTED BEHAVIOUR" in dropped[DOC]


def test_one_pre_existing_line_cannot_vouch_for_several_deleted_ones(tmp_path):
    """D2 — the same hole at scale. With `-U0` two adjacent deletions and one
    addition share a hunk, so a single long line the branch had all along would
    clear BOTH bullets the default branch added. Nothing was built on anything."""
    root = _repo(tmp_path, "alpha\nzulu\n")
    _write(root, "alpha\n- run the gate in CI only when the label is set\nzulu\n", "our work")
    _on_main(root, "alpha\n- run the gate\n- run the gate in CI\nzulu\n", "two bullets")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert {"- run the gate", "- run the gate in CI"} <= set(dropped[DOC])


def test_a_whitespace_reformat_cannot_widen_a_hunk_into_the_whole_file(tmp_path):
    """D3 — the hunk pairing is only evidence while hunks stay small. Lines are
    compared after `.strip()`, so re-indenting a file produces no finding; git,
    diffing raw bytes, would call every line changed and emit ONE hunk spanning
    the file, inside which any addition vouches for any deletion 28 lines away.
    Diffing whitespace-insensitively keeps the two views of "the same line"
    together."""
    body = "".join(f"  line {i}\n" for i in range(1, 31))
    root = _repo(tmp_path, body)
    _write(root, body + "  always raise Stop\n", "our work")
    _on_main(root, body.replace("  line 3\n", "  line 3\n  raise Stop\n"), "main adds a guard")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")
    assert DOC in dropped_lines(root, "main", "HEAD")      # the finding, before the reformat

    reflowed = "".join(" " + ln.strip() + "\n"
                       for ln in (root / DOC).read_text(encoding="utf-8").splitlines())
    _write(root, reflowed, "reindent the file")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "raise Stop" in dropped[DOC]


def test_a_typo_fix_on_the_default_branch_cannot_erase_a_finding(tmp_path):
    """D4 — "the default branch no longer has this exact line" is true both when
    it superseded the line and when it merely corrected a character in a line this
    branch had really thrown away. Here the branch carries NEITHER version, so
    nothing followed anything and the finding has to stand."""
    root = _repo(tmp_path)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, "alpha\nbravo\ncharlie\nTHEIR LINE is documented here.\n", "their work")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")
    assert DOC in dropped_lines(root, "main", "HEAD")      # the finding, before the typo fix

    _on_main(root, "alpha\nbravo\ncharlie\nTHEIR LINE is documented here!\n", "typo fix")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "THEIR LINE is documented here." in dropped[DOC]
