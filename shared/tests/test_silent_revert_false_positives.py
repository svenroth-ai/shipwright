"""The revert check must not accuse an edit, or a deletion main itself made
(iterate-2026-07-28-silent-revert-false-positives).

`check_no_silent_revert` shipped in #477 and reported **four** findings in the
very next long-running iterate — every one of them wrong, every one cleared
through `declared_removals`. An escape hatch in weekly use is a gate on its way
to being decoration, so the two false-positive shapes are closed here:

* **(A)** the default branch deleted or rewrote the text *itself* after the merge
  that delivered it, so the branch correctly no longer carries it;
* **(B)** the branch *edited* a line in place — whole-line set subtraction cannot
  tell "changed" from "discarded".

Both are decided by evidence, never by a similarity threshold: (A) by asking
whether the default branch's own tip still carries the line, (B) by requiring the
replacement to sit in the **same minimal diff hunk** as the deletion.

The cases live in their own file because `test_silent_revert.py` is at the
300-line cap; its sixteen tests are the true-positive contract and stay
untouched — that they keep passing is this change's real acceptance criterion.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers.silent_revert import (  # noqa: E402
    _resolve_default_ref,
    check_no_silent_revert,
    dropped_lines,
)

DOC = "docs/notes.md"
OTHER = "docs/extra.md"


def _git(root: Path, *args: str, check=True) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=check).stdout.strip()


def _repo(tmp_path: Path, body: str = "alpha\nbravo\ncharlie\n") -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    # Pin the conflict style: a contributor with a global `diff3`/`zdiff3` would
    # otherwise get an extra base section in any fixture that leaves a conflict,
    # and the fixture — not the code — would decide the assertion.
    _git(root, "config", "merge.conflictStyle", "merge")
    (root / "docs").mkdir()
    (root / DOC).write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", message, check=False)


def _write(root: Path, text: str, message: str, path: str = DOC) -> None:
    (root / path).write_text(text, encoding="utf-8")
    _commit(root, message)


def _on_main(root: Path, fn) -> None:
    """Run `fn(root)` as a commit on main, then come back."""
    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _git(root, "checkout", "-q", "main")
    fn(root)
    _git(root, "checkout", "-q", current)


def _fork(root: Path, name: str = "work") -> None:
    _git(root, "checkout", "-q", "-b", name)


# --- (A) the default branch removed it itself -------------------------------

def test_a_line_main_itself_deleted_later_is_not_a_drop(tmp_path):
    """AC1. Merge 1 delivers a line; a later main commit replaces it. The branch
    integrates again and correctly no longer carries it. Scoring merge 1 against
    HEAD still reads that as a loss — but main does not have the line either, so
    there is nothing this branch could be reverting. Three of the four real
    findings on `iterate/checks-that-gate-nothing` were exactly this."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(r, "alpha\nbravo\ncharlie\nTHEIR TEMP LINE\n", "temp"))
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge 1 (ours)")
    _on_main(root, lambda r: _write(r, "alpha\nbravo\ncharlie\nTHEIR FINAL LINE\n", "main rewrites it"))
    _git(root, "merge", "-q", "main", check=False)
    # Resolve merge 2 explicitly as a union. Letting the conflict be committed
    # would leave markers in the tree, and the assertions below would then pass
    # on text inside a marker block rather than on a real integration.
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\nTHEIR FINAL LINE\n", "merge 2 (union)")

    body = (root / DOC).read_text(encoding="utf-8")
    assert "<<<<<<<" not in body
    assert "THEIR TEMP LINE" not in body
    assert "THEIR FINAL LINE" in body
    assert dropped_lines(root, "main", "HEAD") == {}


def test_a_file_main_itself_deleted_later_is_not_a_drop(tmp_path):
    """AC1b. The whole path is gone from main's tip, so main carries none of it.
    Reading 'file absent at the tip' as 'keep every candidate' would have left
    this shape reporting forever (external plan review, high)."""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(r, "THEIR WHOLE FILE\n", "main adds a file", OTHER))
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge 1 (ours)")

    assert OTHER in dropped_lines(root, "main", "HEAD")   # today's behaviour, still right

    _on_main(root, lambda r: (r / OTHER).unlink() or _commit(r, "main deletes it"))
    _git(root, "merge", "-q", "main", check=False)
    _commit(root, "merge 2")

    assert not (root / OTHER).exists()
    assert dropped_lines(root, "main", "HEAD") == {}


# --- (B) the branch edited the line ------------------------------------------

def test_extending_a_line_main_added_is_not_a_drop(tmp_path):
    """AC2. The real fourth finding: one table row in `docs/hooks-and-pipeline.md`
    gained a sentence *in the middle*, so main's row was not even a substring of
    ours. Every word main wrote survives, in order, in the line that replaced it."""
    root = _repo(tmp_path, "alpha\n| row | one |\ncharlie\n")
    _fork(root)
    _write(root, "alpha\n| row | one |\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(r, "alpha\n| row | one | two |\ncharlie\n", "main extends the row"))
    _git(root, "merge", "-q", "main", check=False)
    _write(root, "alpha\n| row | one | inserted | two |\ncharlie\nBRANCH LINE\n",
           "we extend the same row")

    assert dropped_lines(root, "main", "HEAD") == {}


def test_restoring_the_pre_merge_version_is_still_reported(tmp_path):
    """AC3. The loophole the (b) guard closes. Main NARROWS a line
    (`do X and Y` -> `do X`); the branch puts the wide version back. That sits in
    the same hunk and main's line is a token subsequence of ours — so the hunk
    pairing alone would clear it. It is a real revert, and the base guard keeps
    it reported: our line is the pre-merge text, not something we authored."""
    root = _repo(tmp_path, "alpha\ndo X and Y\ncharlie\n")
    _fork(root)
    _write(root, "alpha\ndo X and Y\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(r, "alpha\ndo X\ncharlie\n", "main narrows the line"))
    _git(root, "merge", "-q", "main", check=False)
    _write(root, "alpha\ndo X and Y\ncharlie\nBRANCH LINE\n", "we put the old wording back")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "do X" in dropped[DOC]


def test_a_match_in_a_different_hunk_does_not_carry_the_line_forward(tmp_path):
    """AC4. Raised by the external plan review (Gemini): a short line main added
    (`break`) would be silenced by any newly authored line containing that token
    anywhere in the file. The answer is positional rather than a minimum-token
    threshold — the replacement must be in the SAME minimal hunk as the deletion.
    Here `break` is dropped near the top and `if error: break` is authored twenty
    lines away, so nothing carries it forward."""
    body = "\n".join(f"line {i}" for i in range(1, 21)) + "\n"
    root = _repo(tmp_path, body)
    _fork(root)
    _on_main(root, lambda r: _write(
        r, body.replace("line 2\n", "line 2\nbreak\n"), "main adds a short line"))
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")
    _write(root, body.replace("line 19\n", "line 19\nif error: break\n"),
           "we author an unrelated line that happens to contain the token")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "break" in dropped[DOC]


def test_deleting_a_file_main_still_has_is_reported(tmp_path):
    """AC4b. Losing a whole file that main still carries stays a finding — neither
    filter may explain it away. (The `ours is not None` guard at the call site
    only skips a pointless git call: with our side absent the diff holds nothing
    but deletions, so nothing would be paired either way. Stage-2 review corrected
    an earlier claim here that the guard prevented a crash; it does not.)"""
    root = _repo(tmp_path)
    _fork(root)
    _write(root, "alpha\nbravo\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(r, "alpha\nbravo\ncharlie\nTHEIR LINE\n", "their work"))
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")
    (root / DOC).unlink()
    _commit(root, "drop the file")

    dropped = dropped_lines(root, "main", "HEAD")

    assert DOC in dropped
    assert "THEIR LINE" in dropped[DOC]


# --- the ref the comparison is anchored to -----------------------------------

def test_default_ref_prefers_origin_when_the_local_ref_is_behind(tmp_path):
    """AC5. Branches are integrated from `origin/<default>` (`ensure_current`
    merges that ref), but the check took the LOCAL branch. When it lags, every
    integration of newer content fails `merge-base --is-ancestor` and the whole
    merge is skipped: measured 6 -> 2 -> 1 merges seen on the real branch as the
    ref was walked back. A gate that quietly shrinks is the disease this fix is
    treating, so the comparison follows the ref the branch actually merges."""
    root = _repo(tmp_path)
    behind = _git(root, "rev-parse", "HEAD")
    _git(root, "update-ref", "refs/remotes/origin/main", behind)
    _write(root, "alpha\nbravo\ncharlie\nmain moves on\n", "main moves on")

    # origin/main is BEHIND local main -> local wins, nothing is lost.
    assert _resolve_default_ref(root, "main") == "main"

    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    _git(root, "checkout", "-q", "--detach")          # `branch -f` refuses the checked-out branch
    _git(root, "branch", "-f", "main", behind)

    # local main is behind origin/main -> the remote ref is the honest tip.
    assert _resolve_default_ref(root, "main") == "origin/main"


def test_default_ref_falls_back_when_there_is_no_remote(tmp_path):
    """AC5. Every repo in this suite is remote-less; the fallback is what keeps
    the sixteen true-positive tests meaning exactly what they meant before."""
    root = _repo(tmp_path)

    assert _resolve_default_ref(root, "main") == "main"
    assert _resolve_default_ref(root, "no-such-branch") == "no-such-branch"


def test_a_diverged_origin_keeps_the_local_ref(tmp_path):
    """AC5. Neither ref contains the other, so there is no 'more current' one to
    prefer. Guessing would move the comparison target on a repository whose state
    we do not understand; keeping the local ref changes nothing."""
    root = _repo(tmp_path)
    forked = _git(root, "rev-parse", "HEAD")
    _write(root, "alpha\nbravo\ncharlie\nlocal only\n", "local main")
    _git(root, "checkout", "-q", "-b", "tmp", forked)
    _write(root, "alpha\nbravo\ncharlie\nremote only\n", "remote main")
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "HEAD"))
    _git(root, "checkout", "-q", "main")
    _git(root, "branch", "-qD", "tmp")

    assert _resolve_default_ref(root, "main") == "main"


# --- the check as F11 calls it -----------------------------------------------

def test_the_check_passes_once_the_false_positives_are_gone(tmp_path):
    """The end-to-end shape of the four real findings: a rewritten line and an
    edited one, on a branch that integrated twice. Before this change the run
    needed four `declared_removals` entries to hand over; now it needs none."""
    root = _repo(tmp_path, "alpha\n| row | one |\ncharlie\n")
    _fork(root)
    _write(root, "alpha\n| row | one |\ncharlie\nBRANCH LINE\n", "our work")
    _on_main(root, lambda r: _write(
        r, "alpha\n| row | one | two |\ncharlie\nTHEIR TEMP LINE\n", "their work"))
    _git(root, "merge", "-q", "main", check=False)
    _write(root, "alpha\n| row | one | inserted | two |\ncharlie\nTHEIR TEMP LINE\nBRANCH LINE\n",
           "integrate, extending their row")
    _on_main(root, lambda r: _write(
        r, "alpha\n| row | one | two |\ncharlie\nTHEIR FINAL LINE\n", "main rewrites its own line"))
    _git(root, "merge", "-q", "main", check=False)
    _write(root, "alpha\n| row | one | inserted | two |\ncharlie\nTHEIR FINAL LINE\nBRANCH LINE\n",
           "integrate again")

    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is True, result.detail
    assert "declared" not in result.detail.lower()
