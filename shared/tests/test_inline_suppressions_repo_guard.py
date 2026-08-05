"""Live guard — the inline-suppression ratchet running against THIS repo.

This is what actually fails the build. The scanner and the baseline reader are
libraries; what makes them binding is that this file runs on the path CI
already requires (``shared/tests``). The accepted-risk register shipped its
reconciler with nothing invoking it, and external review correctly called that
out as rebuilding the very defect the register exists to fix — a control nobody
runs is a comment. This follows the fix.

Every assertion reads real repo state, so a failure means this repo has
drifted, not that a fixture is stale. The synthetic negative controls proving
each block FIRES live in ``test_inline_suppressions.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import inline_suppressions as isup  # noqa: E402


def test_no_inline_suppression_has_outgrown_its_baseline():
    """The ratchet itself.

    Asserts on the four BLOCKING classes — deliberately NOT on ``shrunk``. A
    baseline entry whose rule has fewer sites than recorded is an improvement,
    and blocking on it would make removing a suppression break the build
    (external review, DeepSeek #3). ``dead`` is the one reduction that does
    block, and it is its own class rather than a slice of ``shrunk`` so that
    ``reconcile``'s promise ("shrink never affects ok") stays literally true —
    Stage-2 code review caught the earlier version breaking exactly that.
    """
    result = isup.reconcile(REPO_ROOT)
    blocking = (
        result["ratchets"] + result["unrecorded"]
        + result["dead"] + result["unreadable"]
    )
    assert not blocking, (
        "Inline-suppression drift in this repo:\n\n"
        + "\n".join(isup.format_report(result))
        + "\n\nRe-check with: uv run shared/scripts/tools/"
        "inline_suppressions_cli.py check --project-root ."
    )
    assert result["ok"]


def test_the_baseline_is_loadable_and_non_empty():
    """If the baseline ever silently became empty, the guard above would still
    pass for a tree with no suppressions — but this repo HAS them, so an empty
    baseline means the file was truncated, not that the debt was paid."""
    entries = isup.load_baseline(REPO_ROOT)
    assert entries, "this repo has inline suppressions; the baseline must record them"


def test_every_baseline_entry_cites_a_recorded_decision():
    for rule, entry in isup.load_baseline(REPO_ROOT).items():
        assert isup.DECISION_REF_RE.search(entry["rationale_ref"]), rule




def test_the_file_set_comes_from_git_in_this_repo():
    """The walk fallback is broader and less precise. This repo is a git tree,
    so a `walk` result here means `git ls-files` failed and the measurement
    silently changed shape."""
    assert isup.scan(REPO_ROOT)["mode"] == "git"


def test_every_baseline_statement_names_its_own_rules_subject():
    """Rule-specificity, asserted directly rather than through global
    uniqueness. The earlier version required every statement to DIFFER from
    every other, which is a proxy — and a bad one: the two `Popen` rules
    genuinely share a reason at the same two sites, so the test forced an
    artificial rewording of the second entry. Stage-2 code review caught that
    the test had shaped the artifact instead of checking it."""
    for rule, entry in isup.load_baseline(REPO_ROOT).items():
        # Distinctive tokens from the rule id, minus the generic namespace
        # segments every semgrep rule shares.
        generic = {"python", "lang", "security", "audit", "compatibility", ""}
        tokens = {
            # Trailing digits are variant markers (`Popen1`/`Popen2` are one
            # subject), so they must not stop the statement from matching.
            t.rstrip("0123456789")
            for part in rule.split(".") for t in part.split("-")
        }
        tokens = {t for t in tokens if t.lower() not in generic and len(t) > 3}
        statement = entry["statement"].lower()
        assert any(t.lower() in statement for t in tokens), (
            f"{rule}: the statement never names what this rule is about "
            f"(expected one of {sorted(tokens)}) — say why THIS rule is "
            "suppressed, not why suppressions exist in general"
        )
