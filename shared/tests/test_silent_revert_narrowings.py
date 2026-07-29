"""AC-5 / AC-6 / AC-7 — the three narrowings deferred from #488 (`trg-ffddd6b9`).

None was a false negative in the gate's blocking direction, which is why they
were recorded rather than rushed. Each is small, independent, and about the
detector agreeing with itself.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.churn_merge import CHURN_ALLOWLIST, classify, is_derived_churn  # noqa: E402
from tools.verifiers.silent_revert_reading import (  # noqa: E402
    file_lines,
    normalize_line,
    replacement_hunks,
    resolve_default_ref,
)

CAMPAIGN_STATUS = ".shipwright/planning/iterate/campaigns/some-slug/status.json"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", check=False)


def _identify(root: Path) -> None:
    """Give the repo its own committer identity.

    A CLONE does not inherit the origin's LOCAL config, and a CI runner has no
    global one — so `git commit` there fails, the "local is ahead" setup never
    happens, and the assertion reads the unmoved ref. Green on a dev box with a
    global identity, red on CI: caught by CI on this run's first push.
    """
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _identify(root)
    return root


def _commit(root: Path, rel: str, body: str, message: str = "c") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", message)


# --- AC-5: one definition of "derived" --------------------------------------

def test_the_resolver_and_the_verifier_share_one_predicate():
    """A campaign status.json used to be regenerated churn to `classify` and
    authored content to the silent-revert filter."""
    assert is_derived_churn(CAMPAIGN_STATUS)
    resolvable, blocking = classify([CAMPAIGN_STATUS])
    assert resolvable == [CAMPAIGN_STATUS] and blocking == []


def test_the_predicate_and_classify_agree_on_every_input():
    probes = [
        *sorted(CHURN_ALLOWLIST),
        CAMPAIGN_STATUS,
        ".shipwright/planning/iterate/campaigns/a/b/status.json",   # too deep
        ".shipwright/planning/iterate/campaigns/x/other.json",
        "shared/scripts/lib/churn_merge.py",
        ".shipwright/agent_docs/architecture.md",                   # curated prose
    ]
    resolvable, blocking = classify(probes)
    assert sorted(p for p in probes if is_derived_churn(p)) == resolvable
    assert sorted(p for p in probes if not is_derived_churn(p)) == blocking


def test_the_predicate_normalises_windows_separators():
    assert is_derived_churn(CAMPAIGN_STATUS.replace("/", "\\"))


# --- AC-6: a resolvable remote beats an unresolvable local ref --------------

def test_the_remote_is_used_when_the_local_ref_does_not_resolve(tmp_path):
    origin = _repo(tmp_path / "o")
    _commit(origin, "a.md", "one\n")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(origin), str(clone)],
                   capture_output=True, check=False)
    _identify(clone)
    _git(clone, "checkout", "-q", "-b", "work")
    _git(clone, "branch", "-q", "-D", "main")
    assert _git(clone, "rev-parse", "--verify", "main^{commit}").returncode != 0

    assert resolve_default_ref(clone, "main") == "origin/main"


def test_a_resolvable_local_ref_is_still_preferred_when_it_is_ahead(tmp_path):
    origin = _repo(tmp_path / "o")
    _commit(origin, "a.md", "one\n")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(origin), str(clone)],
                   capture_output=True, check=False)
    _identify(clone)
    _commit(clone, "a.md", "one\ntwo\n")   # local main ahead of origin/main
    # Assert the SETUP before the subject. Without an identity the commit fails
    # silently, main never moves, and the test would "pass" by measuring nothing
    # — which is exactly how it went green locally and red on CI.
    assert (_git(clone, "rev-parse", "main").stdout.strip()
            != _git(clone, "rev-parse", "origin/main").stdout.strip())

    assert resolve_default_ref(clone, "main") == "main"


def test_no_remote_keeps_the_local_ref(tmp_path):
    root = _repo(tmp_path)
    _commit(root, "a.md", "one\n")
    assert resolve_default_ref(root, "main") == "main"


# --- AC-7: "the same line" means one thing ----------------------------------

def test_normalisation_collapses_internal_whitespace():
    assert normalize_line("  a   b\tc  ") == "a b c"
    assert normalize_line("a b") == normalize_line("a     b")
    assert normalize_line("ab") != normalize_line("a b"), "tokens must still differ"


def test_the_finder_and_the_hunk_pairer_agree_on_internal_whitespace(tmp_path):
    """A pure reformat is not a finding, and needs no hunk to answer one."""
    root = _repo(tmp_path)
    _commit(root, "a.md", "alpha beta gamma\n")
    _commit(root, "a.md", "alpha    beta\tgamma\n", "reformat")

    assert replacement_hunks(root, "HEAD~1", "HEAD", "a.md") == []
    assert file_lines(root, "HEAD~1", "a.md") == file_lines(root, "HEAD", "a.md")


def test_a_real_token_change_is_still_a_change(tmp_path):
    root = _repo(tmp_path)
    _commit(root, "a.md", "alpha beta gamma\n")
    _commit(root, "a.md", "alpha beta delta\n", "real edit")

    assert file_lines(root, "HEAD~1", "a.md") != file_lines(root, "HEAD", "a.md")


def test_a_token_merge_produces_a_hunk_the_finding_can_pair_with(tmp_path):
    """The row that makes `-b` the right partner and `-w` the wrong one.

    Merging two tokens changes content, so `normalize_line` reports it. Under
    `-w` the pairer saw NOTHING — git ignores whitespace entirely, so
    ``alpha beta`` and ``alphabeta`` were one line to it — leaving a finding no
    hunk could ever answer, which is precisely the asymmetry `trg-ffddd6b9` (3)
    names.

    **This test fails under `-w` and passes under `-b`**, which is the whole
    reason it exists. An earlier version asserted only on `file_lines`, so the
    production diff flag could have been reverted silently and every AC-7 test
    would still have gone green (external code review, openai #3 — verified by
    flipping the flag and watching this file stay green, which is how the gap
    was confirmed rather than argued).
    """
    root = _repo(tmp_path)
    _commit(root, "a.md", "alpha beta\n")
    _commit(root, "a.md", "alphabeta\n", "merge two tokens")

    hunks = replacement_hunks(root, "HEAD~1", "HEAD", "a.md")

    assert hunks, "no hunk: the finder reports a change the pairer cannot see"
    deleted, added = hunks[0]
    assert normalize_line("alpha beta") in deleted
    assert normalize_line("alphabeta") in added


def test_the_pairer_and_the_finder_share_one_equivalence_relation(tmp_path):
    """Table-driven over every whitespace shape: the two halves must never
    disagree in the DANGEROUS direction — finder says changed, pairer says
    unchanged, so the finding is unanswerable by construction.

    The de-indent row is the one allowed divergence and it goes the other way:
    a hunk with nothing to pair, which suppresses nothing.
    """
    cases = [
        ("run",       "a b\n",     "a    b\n"),
        ("tab",       "a b\n",     "a\tb\n"),
        ("reindent",  "    a b\n", "        a b\n"),
        ("merge",     "a b\n",     "ab\n"),
        ("deindent",  "    a b\n", "a b\n"),
        ("realedit",  "a b\n",     "a c\n"),
    ]
    for label, before, after in cases:
        root = _repo(tmp_path / label)
        _commit(root, "a.md", before)
        _commit(root, "a.md", after, label)

        finder_sees_change = (
            file_lines(root, "HEAD~1", "a.md") != file_lines(root, "HEAD", "a.md")
        )
        pairer_has_hunk = bool(replacement_hunks(root, "HEAD~1", "HEAD", "a.md"))

        assert not (finder_sees_change and not pairer_has_hunk), (
            f"{label}: the finder reports a change the pairer cannot see"
        )


def test_a_de_indent_between_two_regions_cannot_vouch_across_them(tmp_path):
    """Stage-3 doubt: `-b` widens hunks, and under `-U0` a changed line JOINS
    two hunks that an unchanged one separates.

    A de-indent to column 0 is unchanged under `-w` and changed under `-b`, so
    with `-b` alone the region above and the region below collapse into ONE
    hunk — and `unexplained_by_edit` would let the long added line in region B
    vouch for the deleted line in region A, which it has nothing to do with.
    That is the unbounded matching `replacement_hunks`' own docstring rejects,
    re-entered through hunk boundaries rather than line equality.

    Requiring BOTH pairings to explain a line keeps the narrower `-w`
    boundaries in charge of suppression.
    """
    from tools.verifiers.silent_revert_filters import unexplained_by_edit

    root = _repo(tmp_path)
    _commit(root, "a.md", "keep alpha beta\n    indented\ntail\n")
    # Region A drops the line; the middle de-indents; region B gains a longer
    # line that CONTAINS region A's tokens in order.
    _commit(root, "a.md", "indented\nkeep alpha beta and more\n", "three regions")

    survivors = unexplained_by_edit(
        root, "HEAD~1", "HEAD", "a.md",
        lines={"tail"}, excluded=set(), cache={})

    # `tail` has no replacement carrying its tokens anywhere — it must survive.
    assert survivors == {"tail"}


def test_a_genuine_in_place_rewrite_is_still_explained(tmp_path):
    """The control: requiring both pairings must not stop the filter working."""
    from tools.verifiers.silent_revert_filters import unexplained_by_edit

    root = _repo(tmp_path)
    _commit(root, "a.md", "the quick fox\n")
    _commit(root, "a.md", "the quick brown fox jumps\n", "in-place rewrite")

    survivors = unexplained_by_edit(
        root, "HEAD~1", "HEAD", "a.md",
        lines={"the quick fox"}, excluded=set(), cache={})

    assert survivors == set(), "an in-place rewrite that keeps every token must explain the line"
