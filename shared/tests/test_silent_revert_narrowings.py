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


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
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
    _commit(clone, "a.md", "one\ntwo\n")   # local main ahead of origin/main

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
