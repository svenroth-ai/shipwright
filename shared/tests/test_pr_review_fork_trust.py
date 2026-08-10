"""A credentialed stage 2 trusts nothing the contributor controls.

@FR-01.17

Sibling module: ``test_pr_review_fail_closed.py`` covers the other half — that
the gate cannot be bypassed by size, crash or waiver. Shared readers live in
``_pr_review_workflows.py``.

``workflow_run`` grants secrets and a writable token to a run whose input is
attacker-influenced, which is the only way a pull request raised from a fork can
be reviewed at all (GitHub withholds secrets from fork-raised ``pull_request``
runs). That trust is also the danger, and the rules below are what make it safe:

1. never check out the PR head — the contributor's code is read, never run;
2. nothing stage 1 emitted is authoritative. ``pull_request`` runs stage 1 FROM
   THE PR HEAD, so the contributor controls its tier decision, its metadata and
   the diff it uploads;
3. identity comes from the trusted ``workflow_run`` event, not the artifact;
4. an ambiguous or moved head fails closed rather than being guessed at.

Rules 2 and 4 are here because the first draft of this change got them wrong.
It honoured an artifact-supplied ``needs_review`` flag — letting a pull request
declare itself exempt and collect a green status, reintroducing the exact
self-exemption FR-01.17 (E)7 forbids — and reviewed the artifact's diff, so a
forged upload would have had benign code reviewed while different code merged.
It also resolved the PR with ``[0]`` from the commit's PR list, and never
re-checked the head before posting. All four were caught in external review
before merge. These tests are what stop them coming back.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _pr_review_workflows import ALL_STAGE2, job_conditions, jobs, load, shell_code, text  # noqa: E402

# --------------------------------------------------------------------------
# 1. Chained to stage 1, and never running the contributor's code
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_is_triggered_by_workflow_run(path: Path) -> None:
    on = load(path).get(True) or load(path).get("on") or {}
    assert "workflow_run" in on, (
        f"{path.name}: stage 2 must be triggered by the completion of stage 1, "
        f"which is what grants it credentials the fork run never had."
    )


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_never_checks_out_contributor_code(path: Path) -> None:
    """The pwn-request rule: read the diff, never run the code."""
    for job in jobs(path).values():
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if "actions/checkout" not in str(step.get("uses") or ""):
                continue
            ref = str((step.get("with") or {}).get("ref") or "")
            assert "workflow_run" not in ref and "head" not in ref.lower(), (
                f"{path.name}: checkout pins {ref!r} — stage 2 holds secrets "
                f"and must check out the base repo only, never the PR head."
            )
            assert (step.get("with") or {}).get("persist-credentials") is False, (
                f"{path.name}: checkout must set `persist-credentials: false` "
                "because this credentialed job never uses git authentication"
            )


# --------------------------------------------------------------------------
# 2. Identity and content come from trusted sources, never the artifact
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_takes_identity_from_the_trusted_event(path: Path) -> None:
    """A forged artifact must not redirect a verdict onto another PR."""
    assert "github.event.workflow_run" in text(path), (
        f"{path.name}: the PR number and head SHA must come from the trusted "
        f"workflow_run event, never from the downloaded artifact."
    )


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_never_reviews_the_artifact(path: Path) -> None:
    """The trust rule, and the reason this module exists.

    If stage 2 reviewed the uploaded diff, a fork could upload a benign diff,
    have that reviewed, and collect a green status for entirely different code.
    """
    code = shell_code(path)
    assert "pr-review-request/pr.diff" not in code, (
        f"{path.name}: reviews the artifact diff — a contributor controls "
        f"stage 1 and can forge it. Fetch the diff from the API instead."
    )
    assert "needs_review" not in code or "gh api" in code, (
        f"{path.name}: a tier decision must be derived from API data here, "
        f"never read from stage 1's artifact (FR-01.17 (E)7)."
    )


# --------------------------------------------------------------------------
# 3. Ambiguity and movement fail closed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_refuses_an_ambiguous_pull_request(path: Path) -> None:
    """One commit can belong to several open PRs.

    Taking the first would let stage 2 review PR A's diff and post a green
    status onto a SHA that satisfies PR B's gate. Ambiguity is
    indistinguishable from an attack, so it must fail closed rather than pick.
    """
    code = shell_code(path)
    assert "head.sha == $sha" in code, (
        f"{path.name}: the resolved PR's head must equal the trusted event SHA"
    )
    assert "-ne 1 " in code, (
        f"{path.name}: must require EXACTLY one match and fail closed on zero "
        f"or many, rather than selecting one"
    )


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_resolves_a_fork_pr_not_just_a_same_repo_one(path: Path) -> None:
    """`commits/{sha}/pulls` is scoped to the queried repo's own commit store.

    A fork PR's head commit lives in the FORK's store, not the base repo's, so
    that endpoint returns an EMPTY list for every fork PR — verified against
    three real open fork PRs on cli/cli: all three returned zero matches from
    `commits/{sha}/pulls` and exactly one from listing the base repo's open
    PRs and matching `head.sha`. The ambiguity guard above then reads "found
    0" and refuses to post a verdict, so a fork PR is not merely
    under-reviewed but permanently blocked with a red required check — the
    exact case this two-stage split exists to fix, inverted into an
    availability regression no same-repo PR would ever reveal.
    (shipwright-webui#338, doubt-reviewer finding 26.)
    """
    code = shell_code(path)
    assert "commits/$HEAD_SHA/pulls" not in code, (
        f"{path.name}: resolves the PR via commits/{{sha}}/pulls, which is "
        f"EMPTY for a fork PR's head commit — list the base repo's open PRs "
        f"and match on head.sha instead"
    )
    # External review (openai, iterate-2026-08-05-pr-review-fork-resolve):
    # two independent substring checks can pass even if pagination, the safe
    # jq argument binding, or the number extraction were dropped or attached
    # to an unrelated call elsewhere in the file. Extract the actual `matches=`
    # assignment and assert its properties are co-located in that ONE block.
    block_match = re.search(r"matches=\$\(gh api(.*?)count=", code, re.DOTALL)
    assert block_match, (
        f"{path.name}: could not find the resolver's `matches=$(gh api ...)` "
        f"assignment — the resolve step's shape changed unexpectedly"
    )
    block = block_match.group(1)
    assert "--paginate" in block and "--slurp" in block, (
        f"{path.name}: the open-PR listing must be paginated and slurped — a "
        f"match beyond page 1 must not read as absent"
    )
    assert "pulls?state=open" in block, (
        f"{path.name}: must resolve identity by listing the base repo's open "
        f"PRs (pulls?state=open) — the only query that also finds a fork PR"
    )
    assert '--arg sha "$HEAD_SHA"' in block, (
        f"{path.name}: the trusted SHA must be bound via a safe jq --arg, "
        f"never interpolated directly into the jq program text"
    )
    # External review (deepseek, iterate-2026-08-05-pr-review-fork-resolve):
    # --slurp wraps each page's array in an outer array, so a jq filter
    # missing the `.[][]` double-flatten would satisfy every check above yet
    # only ever see page 1 (or fail to iterate at all) at runtime.
    assert ".[][]" in block, (
        f"{path.name}: --slurp needs the matching .[][] double-flatten in "
        f"the jq filter, or pages beyond the first are silently dropped"
    )
    assert ".head.sha == $sha" in block and ".number" in block, (
        f"{path.name}: must filter on the safely-bound $sha and extract "
        f".number from the SAME query this test isolated"
    )


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_rechecks_the_head_before_blessing_it(path: Path) -> None:
    """A force-push mid-run means the review describes different code.

    The diff is fetched by PR number (a moving target) while the verdict lands
    on the immutable event SHA. Without a re-check, a later restore of that SHA
    would inherit a green status earned by code that is no longer there.
    """
    assert "head moved during the run" in shell_code(path), (
        f"{path.name}: must re-verify the head SHA before posting success"
    )


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_rejects_any_force_push_since_stage1_started(path: Path) -> None:
    """An A -> B -> A force-push defeats a current-head-only comparison."""
    code = shell_code(path)
    assert "RUN_STARTED_AT" in code
    assert "head_ref_force_pushed" in code
    assert "issues/$PR_NUMBER/timeline" in code
    assert ".created_at >= $t" in code
    assert '[[ "$forced" =~ ^[0-9]+$ ]]' in code


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_refuses_a_second_check_run_claiming_its_context(path: Path) -> None:
    """Stage 1 is contributor-controlled and cannot mint the required name."""
    code = shell_code(path)
    expected = "Claude Code Review" if "claude-review-run" in path.name else "PR Review"
    assert "checks: read" in text(path)
    assert "commits/$HEAD_SHA/check-runs" in code
    assert f'.name == "{expected}"' in code
    assert 'details_url // "") | startswith($run) | not' in code
    assert "second producer is claiming this context" in code


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_silences_cancelled_superseded_runs(path: Path) -> None:
    """A cancelled workflow must not overwrite the newer run's verdict."""
    conditions = job_conditions(path)
    assert "${{ !cancelled() }}" in conditions
    assert "always()" not in conditions


# --------------------------------------------------------------------------
# 4. The verdict reaches the humans who decide — FR-01.17 (E)4
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", ALL_STAGE2)
def test_stage2_posts_the_verdict_onto_the_change(path: Path) -> None:
    """Not left in the log of a run nobody opens."""
    body = text(path)
    assert "statuses" in body, f"{path.name}: must post the commit status"
    assert re.search(r'context="(PR Review|Claude Code Review)"', body), (
        f"{path.name}: must post the required context by name — it is the sole "
        f"producer, and an absent status blocks the merge"
    )
