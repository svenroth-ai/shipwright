"""The sameness predicate for the F11 non-converging halt (trg-ac24ec5b, PR #690).

Two dimensions, both required for the predicate to be trusted:

* **Real wording fires it.** ``test_pr690_round1_and_round2_recur`` replays the
  actual first two `PR Review` BLOCK comments GitHub posted on PR #690 — not
  paraphrased, not tuned to the matcher — and asserts the loose claim-overlap
  matcher recognises them as the same recurring concern on the file both
  rounds actually blocked.
* **Genuinely distinct findings do not fire it.** A count-based "stop after N"
  predicate could not tell a converging run (a fresh, real defect each round —
  the common, good case) from a stuck one; the sameness predicate must, so
  ``test_two_genuinely_different_blocks_do_not_recur`` is the other half of
  the acceptance bar this unit's brief asks for.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

from lib.pr_review_convergence import (  # noqa: E402
    claim_overlap,
    extract_blocking_findings,
    findings_recur,
    is_block_verdict,
    non_converging,
    normalized_tokens,
    two_most_recent_block_verdicts,
)

from _pr690_review_fixtures import (  # noqa: E402
    ROUND1_BODY,
    ROUND2_BODY,
    ROUND2_COMMIT_SHA,
    round1_comment,
    round2_comment,
    round_commits,
    round_reviews,
)


def _block_comment(body: str, *, created_at: str, url: str = "https://x/1") -> dict:
    return {"author": {"login": "github-actions"}, "createdAt": created_at,
            "url": url, "body": body}


APPROVE_BODY = "## \U0001F916 Shipwright PR Review\n\n**Decision: ✅ APPROVE**\n\nLooks fine.\n"


# --- extract_blocking_findings / normalized_tokens / claim_overlap -------------

def test_extract_blocking_findings_reads_only_the_blocking_section():
    body = (
        "## \U0001F916 Shipwright PR Review\n\n**Decision: \U0001F534 BLOCK**\n\nSummary.\n\n"
        "### \U0001F6AB Blocking issues\n"
        "- foo/bar.py:10 — missing null check on `x`, add a guard\n"
        "- foo/baz.py:20 — SQL built via string concat, use a parameterised query\n\n"
        "### Comments\n"
        "- foo/bar.py:11 — consider renaming `x`\n"
    )
    findings = extract_blocking_findings(body)
    assert len(findings) == 2
    assert findings[0]["files"] == frozenset({"foo/bar.py"})
    assert findings[1]["files"] == frozenset({"foo/baz.py"})


def test_extract_blocking_findings_empty_on_approve():
    assert extract_blocking_findings(APPROVE_BODY) == []


def test_extract_blocking_findings_tolerates_the_backtick_wrapped_render_shape():
    """`pr_review_render.render_comment` (PR #694, iterate-2026-09-09-pr-review-dict-finding-render)
    now wraps every blocking item's rendered text in a code span — `- {bullet}`
    became `` - `{bullet}` `` — after this predicate's own canary was written
    against the older, unwrapped shape (main-repair of 106c01c69986). `_BULLET_RE`
    captures the whole rest of the line including the wrapping backticks, and
    `_FILE_RE`'s optional leading backtick still finds the path inside it, so
    parsing must be unaffected — this is the proof, not an assumption."""
    body = (
        "## \U0001F916 Shipwright PR Review\n\n**Decision: \U0001F534 BLOCK**\n\nSummary.\n\n"
        "### \U0001F6AB Blocking issues\n"
        "- `foo/bar.py:10 — missing null check on x, add a guard`\n"
    )
    findings = extract_blocking_findings(body)
    assert len(findings) == 1
    assert findings[0]["files"] == frozenset({"foo/bar.py"})
    assert "guard" in findings[0]["tokens"]


def test_normalized_tokens_strips_file_paths_digits_and_stopwords():
    tokens = normalized_tokens(
        "shared/scripts/tools/foo.py:12-19 — the fingerprint is not bound to the "
        "current manifest revision, so add a check")
    assert "shared" not in tokens          # the file path itself is not a claim token
    assert "foo" not in tokens
    assert "the" not in tokens             # stopword
    assert "fingerprint" in tokens
    assert "manifest" in tokens
    assert "revision" in tokens


def test_claim_overlap_is_zero_on_no_shared_vocabulary():
    a = normalized_tokens("hardcoded secret in the config, rotate the credential")
    b = normalized_tokens("missing await on the async database call, add it")
    assert claim_overlap(a, b) == 0.0


def test_claim_overlap_uses_the_smaller_claims_own_vocabulary():
    small = frozenset({"fingerprint", "manifest", "current"})
    large = frozenset({"fingerprint", "manifest", "current", "coverage", "tests",
                       "promotion", "entry", "revision", "commit", "identity"})
    assert claim_overlap(small, large) == 1.0


# --- findings_recur: file strict, claim loose -----------------------------------

def test_findings_recur_requires_the_same_file():
    cur = [{"files": frozenset({"a.py"}), "tokens": normalized_tokens(
        "fingerprint drift is not checked before promotion, evidence coverage tests")}]
    prev = [{"files": frozenset({"b.py"}), "tokens": normalized_tokens(
        "fingerprint drift is not checked before promotion, evidence coverage tests")}]
    assert findings_recur(cur, prev) is None


def test_findings_recur_tolerates_reworded_claims_on_the_same_file():
    cur = [{"files": frozenset({"promote.py"}), "tokens": normalized_tokens(
        "the fingerprint covers only coverage and tests JSON and is not bound to an "
        "authenticated CI result or the current source revision, include the commit "
        "SHA and manifest revision before applying the promotion")}]
    prev = [{"files": frozenset({"promote.py"}), "tokens": normalized_tokens(
        "make fingerprint drift a decision-enforced condition: when the latest "
        "promoted entry's fingerprint differs from the current manifest evidence, "
        "add a regression test that changes coverage and tests after promotion")}]
    match = findings_recur(cur, prev)
    assert match is not None


def test_findings_recur_none_when_vocabulary_genuinely_differs():
    cur = [{"files": frozenset({"shared.py"}), "tokens": normalized_tokens(
        "hardcoded API secret committed in plaintext, move it to an environment "
        "variable and rotate the leaked credential immediately")}]
    prev = [{"files": frozenset({"shared.py"}), "tokens": normalized_tokens(
        "missing await before the async database call causes an unhandled "
        "promise rejection under concurrent load")}]
    assert findings_recur(cur, prev) is None


# --- two_most_recent_block_verdicts / is_block_verdict --------------------------

def test_is_block_verdict_true_only_for_shipwright_block():
    assert is_block_verdict(ROUND1_BODY) is True
    assert is_block_verdict(APPROVE_BODY) is False
    assert is_block_verdict("some unrelated PR comment mentioning BLOCK") is False


def test_two_most_recent_block_verdicts_ignores_non_block_comments_between():
    """An APPROVE in between two BLOCKs does not reset the pair — the question is
    always "do the last two BLOCKs agree", not "are they adjacent in the thread"."""
    comments = [
        _block_comment(ROUND1_BODY, created_at="2026-01-01T00:00:00Z"),
        _block_comment(APPROVE_BODY, created_at="2026-01-01T01:00:00Z"),
        _block_comment(ROUND2_BODY, created_at="2026-01-01T02:00:00Z"),
    ]
    pair = two_most_recent_block_verdicts(comments)
    assert pair is not None
    previous, current = pair
    assert previous["body"] == ROUND1_BODY
    assert current["body"] == ROUND2_BODY


def test_two_most_recent_block_verdicts_none_below_two():
    assert two_most_recent_block_verdicts([_block_comment(ROUND1_BODY, created_at="t")]) is None
    assert two_most_recent_block_verdicts([]) is None


# --- non_converging: the public entrypoint --------------------------------------

def test_pr690_round1_and_round2_recur():
    """The acceptance fixture: real bytes from PR #690, not invented text. Both
    rounds block on `shared/scripts/tools/promote_required_layers.py` (different
    line ranges — the code moved between pushes) with reworded but overlapping
    claims about the same underlying trust-boundary gap. Bound via `reviews` —
    PR #690's own real `CHANGES_REQUESTED` reviews and their GitHub-stamped
    `commit.oid` — the authoritative path, not the `commits[]` fallback."""
    match = non_converging([round1_comment(), round2_comment()],
                          reviews=round_reviews(), head_sha=ROUND2_COMMIT_SHA)
    assert match is not None
    assert match["previous_comment"]["createdAt"] == "2026-09-08T08:19:23Z"
    assert match["current_comment"]["createdAt"] == "2026-09-08T09:13:44Z"
    shared_file = match["previous_finding"]["files"] & match["current_finding"]["files"]
    assert "shared/scripts/tools/promote_required_layers.py" in shared_file


def test_non_converging_fails_open_without_commit_binding_data():
    """The same recurring pair, with no `commits`/`head_sha` supplied — the
    predicate cannot verify the two verdicts are for distinct, current code,
    so it must fail OPEN rather than escalate on trust. This is the caller
    contract: `deliver_pr_non_converging` must always supply both."""
    assert non_converging([round1_comment(), round2_comment()]) is None


def test_non_converging_none_when_verdicts_share_the_same_commit():
    """A stage-1 re-run (the documented remedy for the GLM JSON-parse flake)
    posts a second BLOCK for the SAME commit — two reviews of unchanged code
    naturally restate the same finding, and that must not read as
    "re-pushing did not help" when nothing was re-pushed at all."""
    same_commit = [{"oid": ROUND2_COMMIT_SHA, "committedDate": "2026-09-08T08:00:00Z"}]
    match = non_converging([round1_comment(), round2_comment()],
                          commits=same_commit, head_sha=ROUND2_COMMIT_SHA)
    assert match is None


def test_non_converging_none_when_current_verdict_is_stale():
    """The current BLOCK does not review the PR's actual head — e.g. a
    transient `PR Review` failure left an old verdict as "most recent". Must
    not escalate against code that is not what HEAD is actually on."""
    match = non_converging([round1_comment(), round2_comment()],
                          commits=round_commits(), head_sha="deadbeef" * 5)
    assert match is None


def test_non_converging_ignores_forged_non_bot_comments():
    """A BLOCK-shaped comment from anyone but the real reviewer is not a
    verdict — otherwise any PR contributor could forge a terminal halt."""
    forged1 = dict(round1_comment())
    forged1["author"] = {"login": "some-contributor"}
    forged2 = dict(round2_comment())
    forged2["author"] = {"login": "some-contributor"}
    match = non_converging([forged1, forged2],
                          commits=round_commits(), head_sha=ROUND2_COMMIT_SHA)
    assert match is None


def test_non_converging_ignores_edited_comments_even_from_the_real_bot():
    """A matching `author.login` is not proof the BODY is what the bot wrote —
    a user with write access can edit another author's comment on GitHub. Same
    denial-of-delivery risk as a forged author, from a higher-privileged
    actor (code-reviewer, Stage 2)."""
    edited1 = dict(round1_comment())
    edited1["includesCreatedEdit"] = True
    edited2 = dict(round2_comment())
    edited2["includesCreatedEdit"] = True
    match = non_converging([edited1, edited2],
                          commits=round_commits(), head_sha=ROUND2_COMMIT_SHA)
    assert match is None


def test_two_genuinely_different_blocks_do_not_recur():
    """The acceptance counterpart: two real-shaped BLOCK verdicts whose findings
    do not overlap must leave the ordinary checks_failed/exit-2 path alone —
    the whole point of matching on SAMENESS rather than a push count."""
    first = (
        "## \U0001F916 Shipwright PR Review\n\n**Decision: \U0001F534 BLOCK**\n\nSummary.\n\n"
        "### \U0001F6AB Blocking issues\n"
        "- shared/scripts/tools/export_report.py:22 — the API key is hardcoded in "
        "plaintext; move it to an environment variable and rotate the leaked "
        "credential before merge\n"
    )
    second = (
        "## \U0001F916 Shipwright PR Review\n\n**Decision: \U0001F534 BLOCK**\n\nSummary.\n\n"
        "### \U0001F6AB Blocking issues\n"
        "- shared/scripts/tools/export_report.py:57 — the retry loop has no upper "
        "bound and can spin forever on a persistent 500; add a max-attempts cap "
        "with backoff\n"
    )
    comments = [
        _block_comment(first, created_at="2026-01-01T00:00:00Z", url="https://x/1"),
        _block_comment(second, created_at="2026-01-01T01:00:00Z", url="https://x/2"),
    ]
    # Commit-binding data that WOULD satisfy `verdicts_span_distinct_commits`
    # (a real commit between the two, the second bound to `head`) is supplied
    # deliberately: without it, this negative test would pass even if the
    # sameness matcher regressed and wrongly matched the two findings, since
    # `non_converging` would return `None` on the unrelated fail-open path
    # instead (code-reviewer). Only the text predicate is under test here.
    commits = [{"oid": "aaa", "committedDate": "2025-12-31T12:00:00Z"},
              {"oid": "head", "committedDate": "2026-01-01T00:30:00Z"}]
    assert non_converging(comments, commits=commits, head_sha="head") is None


def test_non_converging_none_on_a_single_block():
    assert non_converging([round1_comment()]) is None


def test_non_converging_none_when_a_block_has_no_parseable_blocking_section():
    comments = [
        _block_comment("## \U0001F916 Shipwright PR Review\n\n**Decision: \U0001F534 BLOCK**\n\n"
                       "Nothing was reviewed.\n", created_at="2026-01-01T00:00:00Z"),
        round1_comment(),
    ]
    assert non_converging(comments) is None
