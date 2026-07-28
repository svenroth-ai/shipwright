"""The predicates that decide what is NOT a loss
(iterate-2026-07-28-silent-revert-false-positives).

`test_silent_revert_false_positives.py` covers the behaviour end to end. These
are the surfaces where a quiet mis-read turns straight into a suppressed
finding, so they are exercised directly rather than through the detector: the
containment predicate, the `-U0` hunk parser, and the rule that a git failure
must never be mistaken for "there was nothing there".

Stage-2 code review asked for these — every one of them would have stayed green
with the guard it pins deleted.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers import silent_revert_filters as f  # noqa: E402
from verifiers import silent_revert_reading as r  # noqa: E402
from verifiers.silent_revert import check_no_silent_revert  # noqa: E402

DOC = "docs/notes.md"


def _git(root: Path, *args: str, check=True) -> str:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=check).stdout.strip()


def _repo(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / DOC).write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


# --- tokens_in_order ----------------------------------------------------------

def test_an_empty_needle_never_counts_as_carried_forward():
    """The vacuous truth would be the worst possible answer: 'nothing survived'
    must not read as 'everything survived'. Cannot occur — blank lines are
    dropped before they reach here — but it is not left resting on that."""
    assert r.tokens_in_order("", "anything at all") is False
    assert r.tokens_in_order("   ", "anything at all") is False


def test_a_longer_needle_cannot_hide_in_a_shorter_line():
    assert r.tokens_in_order("a b c", "a b") is False


def test_order_is_required():
    assert r.tokens_in_order("a b", "x a y b z") is True
    assert r.tokens_in_order("b a", "x a y b z") is False


def test_tokens_match_whole_not_as_substrings():
    """`foo` inside `foobar` is a different word. Substring matching here would
    let an unrelated longer line vouch for a deleted one."""
    assert r.tokens_in_order("foo", "foobar baz") is False
    assert r.tokens_in_order("foo", "bar foo baz") is True


def test_a_repeated_token_is_consumed_once_per_occurrence():
    assert r.tokens_in_order("a a", "a b a") is True
    assert r.tokens_in_order("a a", "a b c") is False


def test_the_accepted_blind_spot_is_pinned_not_implied():
    """Recorded decision, not an oversight (Stage-2 review). Containment proves
    main's WORDS survive in the replacing line, never their meaning: a negation
    or a qualifier inserted into their line keeps every token in order. The
    trade is deliberate — the result is one `-`/`+` pair in the PR diff, the most
    reviewable shape there is, whereas the alternative is the state this change
    exists to end. If that ever stops being acceptable, this test is the place
    the decision was written down."""
    assert r.tokens_in_order("the gate blocks on X", "the gate no longer blocks on X") is True


# --- replacement_hunks --------------------------------------------------------

def test_a_deleted_horizontal_rule_is_not_read_as_the_diff_header(tmp_path):
    """`---` deleted from a markdown file renders as `----` in the diff, which
    starts with the same three characters as the diff's own `--- a/path` header.
    Parsing only after the first `@@` is what keeps them apart; without it the
    rule would be lost and the hunk pairing would silently lose a deletion."""
    root = _repo(tmp_path, "alpha\n---\n+++\ncharlie\n")
    (root / DOC).write_text("alpha\ncharlie\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "drop the rules")

    hunks = r.replacement_hunks(root, "HEAD~1", "HEAD", DOC)
    deleted = set().union(*(d for d, _ in hunks)) if hunks else set()

    assert "---" in deleted
    assert "+++" in deleted


def test_a_file_with_no_diff_yields_no_hunks_and_so_suppresses_nothing(tmp_path):
    root = _repo(tmp_path, "alpha\nbravo\n")

    assert r.replacement_hunks(root, "HEAD", "HEAD", DOC) == []


def test_an_unreadable_path_yields_no_hunks(tmp_path):
    """Filters may only ever REMOVE findings, so every failure path in them has to
    return the value that removes nothing."""
    root = _repo(tmp_path, "alpha\n")

    assert r.replacement_hunks(root, "no-such-ref", "HEAD", DOC) == []


def test_a_binary_file_yields_no_hunks(tmp_path):
    root = _repo(tmp_path, "alpha\n")
    (root / "docs" / "blob.bin").write_bytes(bytes(range(256)))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add a binary")
    (root / "docs" / "blob.bin").write_bytes(bytes(range(255, -1, -1)))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "change it")

    assert r.replacement_hunks(root, "HEAD~1", "HEAD", "docs/blob.bin") == []


# --- absence is not failure ---------------------------------------------------

def test_an_absent_path_and_an_unreadable_one_are_told_apart(tmp_path):
    root = _repo(tmp_path, "alpha\nbravo\n")

    assert r.tip_state(root, "HEAD", DOC)[0] == "present"
    assert r.tip_state(root, "HEAD", "docs/never-existed.md")[0] == "absent"
    assert r.tip_state(root, "no-such-ref", DOC)[0] == "unreadable"


def test_a_side_that_cannot_be_read_suppresses_nothing(tmp_path):
    """The path filter clears a whole file on AGREEMENT. If a git failure took the
    same branch, an unanswerable question would come back as a green pass — the
    exact silence this check exists to remove, and the reason the detector already
    turns an unresolvable merge base into a visible SKIP."""
    root = _repo(tmp_path, "alpha\n")
    problems: list[str] = []

    assert f.matches_default(root, "no-such-ref", "HEAD", DOC, {}, problems) is False
    assert problems               # and the caller is told why


def _a_branch_that_really_dropped_a_line(tmp_path) -> Path:
    root = _repo(tmp_path, "alpha\nbravo\n")
    _git(root, "checkout", "-q", "-b", "work")
    (root / DOC).write_text("alpha\nbravo\nBRANCH LINE\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "our work")
    _git(root, "checkout", "-q", "main")
    (root / DOC).write_text("alpha\nbravo\nTHEIR LINE\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "their work")
    _git(root, "checkout", "-q", "work")
    _git(root, "merge", "-q", "main", "-s", "ours", "-m", "merge (ours)")
    return root


def test_an_unreadable_path_does_not_swallow_a_real_finding(tmp_path, monkeypatch):
    """Stage-3 review: a SKIP is ok=True and blocks nothing, so returning one the
    moment ANY path is unreadable let a single unreadable file convert a real
    block over every other path into a pass that named none of them. Findings win;
    the incomplete comparison is reported alongside them, not instead of them."""
    root = _a_branch_that_really_dropped_a_line(tmp_path)

    assert check_no_silent_revert(root, default_branch="main").ok is False   # baseline

    real = f.tip_state

    def flaky(project_root, ref, path, *a, **k):
        return ("unreadable", None) if ref.startswith("main") else real(project_root, ref, path)

    monkeypatch.setattr(f, "tip_state", flaky)
    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is False                     # the finding survives...
    assert DOC in result.detail
    assert "incomplete" in result.detail          # ...and the doubt is disclosed


def test_the_message_names_the_ref_that_was_actually_compared(tmp_path):
    """Stage-2 review: the detector rebound its ref but every operator-facing
    string still named the one it was ASKED about. This run exists because an
    operator was handed four findings they could not verify — pointing them at a
    ref the comparison did not use is that failure in miniature."""
    root = _a_branch_that_really_dropped_a_line(tmp_path)
    _git(root, "update-ref", "refs/remotes/origin/main", _git(root, "rev-parse", "main"))
    _git(root, "branch", "-f", "main", _git(root, "rev-parse", "main~1"))

    result = check_no_silent_revert(root, default_branch="main")

    assert result.ok is False
    assert "origin/main" in result.detail


def test_an_unreadable_delivered_side_is_disclosed_not_inferred(tmp_path, monkeypatch):
    """External code review: the detector reads four sides, and only the tip was
    fail-honest. An unreadable merged-in parent read as 'they deleted it too' and
    dropped the path from the comparison silently — a suppression nobody is told
    about, which is the one thing this check may never do."""
    root = _a_branch_that_really_dropped_a_line(tmp_path)
    real = r.tip_state

    def unreadable_delivered(project_root, ref, path, *a, **k):
        # Fail only the merged-in parent (a sha), never a branch name.
        return ("unreadable", None) if len(ref) == 40 else real(project_root, ref, path)

    monkeypatch.setattr(r, "tip_state", unreadable_delivered)
    problems: list[str] = []
    from verifiers.silent_revert import dropped_lines

    dropped_lines(root, "main", "HEAD", problems=problems)

    assert problems, "an unreadable side was inferred as an absence"


def test_an_unreadable_path_with_no_findings_is_a_visible_skip(tmp_path, monkeypatch):
    """With nothing to report, an unanswerable comparison must still not read as
    'nothing was lost'."""
    root = _repo(tmp_path, "alpha\nbravo\n")
    _git(root, "checkout", "-q", "-b", "work")

    monkeypatch.setattr(
        "verifiers.silent_revert.dropped_lines",
        lambda *a, **k: (k["problems"].append("cannot read x at main"), {})[1],
    )
    result = check_no_silent_revert(root, default_branch="main")

    assert result.severity == "skipped"
    assert "could not be made" in result.detail
