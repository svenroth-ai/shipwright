"""Snapshot test for the two-stage Tier-3 PR review workflows (B4.5, FR-01.17).

Text-regex based (no PyYAML dep) — guards the tier contract Branch Protection
relies on. A drift here could silently auto-merge an unreviewed external or
sensitive-path PR (Failure Mode "Tier-Logik falsch" in the B4.5 spec).

**The shape changed in iterate-2026-07-27-review-gate-failclosed-fork.** It used
to be one workflow whose `PR Review` job was the required check, guarded by
``head.repo.full_name == github.repository`` so it never ran on a fork. That
guard was the hole: a guarded job is SKIPPED on fork PRs, `review` was skipped
through ``needs:``, and GitHub scores a skipped job as a **successful** required
check — so a fork PR satisfied the gate having been reviewed by nobody.

Now:
  * stage 1 (`pr-review.yml`) runs on every PR including forks, holds NO secret,
    decides the tier, and uploads the diff as an artifact;
  * stage 2 (`pr-review-run.yml`) is triggered by stage 1 completing, holds the
    credentials, never checks out the PR head, and posts the required
    ``PR Review`` context as a COMMIT STATUS.

The required check is therefore a posted status, not a job name — which is what
makes it fail closed: if stage 2 never reports, the context is absent, and an
absent required context is `pending`, which blocks.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE1_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review.yml"
STAGE2_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review-run.yml"


def _read(path: Path) -> str:
    assert path.exists(), f"missing workflow: {path}"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stage1() -> str:
    return _read(STAGE1_PATH)


@pytest.fixture(scope="module")
def stage2() -> str:
    return _read(STAGE2_PATH)


@pytest.fixture(scope="module")
def both() -> str:
    return _read(STAGE1_PATH) + "\n" + _read(STAGE2_PATH)


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

class TestTriggers:

    def test_pull_request_trigger_active(self, stage1):
        active = any(
            line.lstrip().startswith("pull_request:") and not line.lstrip().startswith("#")
            for line in stage1.splitlines()
        )
        assert active, "stage 1 must run on pull_request"

    def test_labeled_event_type_present(self, stage1):
        # A `needs-review` / `skip-pr-review` label added AFTER open must re-trigger.
        assert "labeled" in stage1, "workflow must trigger on the 'labeled' event type"

    def test_stage2_is_chained_to_stage1(self, stage2):
        assert "workflow_run:" in stage2, "stage 2 must trigger on workflow_run"
        assert '"PR Review Prepare"' in stage2, (
            "stage 2's workflow_run filter must name stage 1 exactly — a renamed "
            "stage 1 would silently never trigger the review"
        )


# ---------------------------------------------------------------------------
# Stage 1 — tier logic, no credentials, no fork guard
# ---------------------------------------------------------------------------

class TestStage1:

    def test_fork_guard_absent(self, stage1):
        """The guard that made the gate skip — and skip means pass."""
        # Only `if:` expressions count; the file's own comments explain the
        # history and legitimately mention the old expression.
        conditions = [
            ln for ln in stage1.splitlines()
            if ln.lstrip().startswith("if:") and not ln.lstrip().startswith("#")
        ]
        assert not any("head.repo.full_name" in ln for ln in conditions), (
            "fork-PR guard is back — a guarded job is SKIPPED on fork PRs and "
            "GitHub scores a skipped job as a PASSING required check"
        )

    def test_holds_no_secret(self, stage1):
        assert "secrets." not in stage1, (
            "stage 1 runs on fork PRs; credentials belong to stage 2 "
            "(FR-01.17 (E)5 — an untrusted change is never handed the keys)"
        )

    def test_uploads_the_diff_artifact(self, stage1):
        assert "upload-artifact" in stage1
        assert "pr-review-request" in stage1

    def test_carries_no_policy(self, stage1):
        """Policy here is policy the reviewee can edit.

        `pull_request` runs this file FROM THE PR HEAD. A tier or waiver rule
        living here reads as enforcement while being entirely under the
        contributor's control — worse than no rule, because it looks like one.
        The tier decision lives in stage 2, which runs from the default branch.
        """
        assert "skip-pr-review" not in stage1, \
            "waiver rule must live in stage 2 (default-branch code)"
        assert "svroch" not in stage1, \
            "author-tier rule must live in stage 2 (default-branch code)"


# ---------------------------------------------------------------------------
# Stage 2 — the verdict, and the rules that keep a credentialed run safe
# ---------------------------------------------------------------------------

class TestStage2:

    def test_posts_the_required_context_as_a_status(self, stage2):
        assert 'context="PR Review"' in stage2, (
            "stage 2 must post the required `PR Review` context as a commit "
            "status — it is the sole producer, and an absent status blocks"
        )
        assert "statuses: write" in stage2, "posting the status needs statuses:write"

    def test_never_checks_out_the_pr_head(self, stage2):
        """The pwn-request rule: read the diff, never run the contributor's code."""
        for m in re.finditer(r"uses:\s*actions/checkout@\S+([\s\S]{0,200})", stage2):
            tail = m.group(1)
            block = tail.split("- name:")[0].split("- uses:")[0]
            assert "ref:" not in block, (
                "stage 2 holds secrets — it must check out the base repo only, "
                "never a ref derived from the pull request"
            )

    def test_identity_comes_from_the_trusted_event(self, stage2):
        assert "github.event.workflow_run.head_sha" in stage2, (
            "the head SHA must come from the trusted workflow_run event, never "
            "from the downloaded artifact — a forged artifact must not be able "
            "to redirect a verdict onto another PR"
        )

    def test_calls_custom_script_not_third_party_action(self, stage2):
        assert "plugins/shipwright-security/scripts/tools/pr_review.py" in stage2, \
            "review job must invoke the custom pr_review.py script"
        assert "anthropics/claude-code-action" not in stage2, \
            "must NOT use a 3rd-party Claude action (B4.5 OpenRouter decision)"

    def test_tier_is_decided_here_from_api_data(self, stage2):
        """The tier rules must run in default-branch code, on trusted input."""
        assert re.search(r'gh api "repos/\$REPO/pulls/\$PR_NUMBER"', stage2), \
            "labels must be read from the API, not from stage 1"
        assert "/files" in stage2, \
            "changed paths must be read from the API, not from stage 1"

        assert "review_record_tier.py" in stage2, \
            "the default-branch helper must make the tier decision"
    def test_internal_exemption_requires_review_evidence(self, stage2):
        """A maintainer name never proves that this branch was reviewed."""
        assert "svroch" not in stage2
        assert "dependabot[bot]" not in stage2
        assert "reviews\\.json" in stage2
        assert ".head.repo.full_name" in stage2
        assert 'repos/$head_repo/contents/$review_record_path?ref=$HEAD_SHA' in stage2
        assert 'repos/$REPO/contents/$review_record_path?ref=$HEAD_SHA' not in stage2
    def test_unavailable_pr_head_evidence_falls_back_to_review(self, stage2):
        """Deleted or unreadable evidence must select Tier-3, not break tiering."""
        assert 'if gh api "repos/$head_repo/contents/$review_record_path?ref=$HEAD_SHA" \\' in stage2
        assert ': > "$review_record_file"' in stage2
        assert "review evidence unavailable at the PR head; Tier-3 review is required" in stage2

    def test_waiver_cannot_cover_a_change_to_the_checks(self, stage2):
        """FR-01.17 (E)7 — whoever unlocks a door does not decide it may be."""
        assert "review_record_tier.py" in stage2

    def test_waiver_reads_both_sides_of_a_rename_and_fails_closed_at_api_cap(self, stage2):
        """A suppression moved out of its path is still a suppression change."""
        assert ".previous_filename // empty" in stage2
        assert "sensitive_path_list_truncated" in stage2
        assert "changed-file list is at the API cap" in stage2

    def test_waiver_is_consumed_before_a_later_push_can_reuse_it(self, stage2):
        """A label authorizes one evidence-backed head, never a later synchronize."""
        assert "Consume the one-shot review waiver" in stage2
        assert "if: steps.tier.outputs.needs_review == 'false'" in stage2
    def test_waiver_authorization_is_an_exact_head_approval(self, stage2):
        """A mutable label only starts the waiver; GitHub binds it to this SHA."""
        assert 'pulls/$PR_NUMBER/reviews' in stage2
        assert '.commit_id == $sha' in stage2
        assert 'collaborators/$reviewer/permission' in stage2
        assert '--trusted-head-approval' in stage2

    def test_failed_waiver_consumption_cannot_post_a_green_gate(self, stage2):
        """The sole required status must treat DELETE failure as review-required."""
        assert 'id: consume_waiver' in stage2
        assert 'CONSUME_WAIVER_OUTCOME: ${{ steps.consume_waiver.outcome }}' in stage2
        failure = 'elif [ "$NEEDS_REVIEW" = "false" ] && [ "$CONSUME_WAIVER_OUTCOME" != "success" ]; then'
        green = 'elif [ "$NEEDS_REVIEW" = "false" ] && [ "$CONSUME_WAIVER_OUTCOME" = "success" ]; then'
        assert failure in stage2 and green in stage2
        assert stage2.index(failure) < stage2.index(green)
        assert '"$NEEDS_REVIEW" != "true"' not in stage2


        assert 'gh api --method DELETE "repos/$REPO/issues/$PR_NUMBER/labels/skip-pr-review"' in stage2
        assert "issues: write" in stage2
        assert 'if ! gh api --method DELETE "repos/$REPO/issues/$PR_NUMBER/labels/skip-pr-review" >/dev/null; then' in stage2
        assert "could not consume the one-shot review waiver" in stage2

    def test_does_not_review_the_artifact(self, stage2):
        """A contributor controls stage 1, so its artifact cannot be the input."""
        assert "pr-review-request" not in stage2, (
            "stage 2 must not consume stage 1's artifact — a fork could upload "
            "a benign diff and collect a green status for different code"
        )


# ---------------------------------------------------------------------------
# Secrets + provider invariants
# ---------------------------------------------------------------------------

class TestSecrets:

    def test_openrouter_secret_used(self, stage2):
        assert "secrets.OPENROUTER_API_KEY" in stage2, \
            "review job must read OPENROUTER_API_KEY from secrets"

    def test_no_anthropic_key(self, both):
        assert "ANTHROPIC_API_KEY" not in both, \
            "OpenRouter is the single provider — no ANTHROPIC_API_KEY"

    def test_no_literal_key(self, both):
        assert not re.search(r"sk-or-v1-[A-Za-z0-9]{8,}", both), \
            "hardcoded OpenRouter key literal found — use secrets.OPENROUTER_API_KEY"

    def test_model_env_override(self, stage2):
        assert "SHIPWRIGHT_PR_REVIEW_MODEL" in stage2, \
            "model must be selectable via SHIPWRIGHT_PR_REVIEW_MODEL env"


# ---------------------------------------------------------------------------
# Supply-chain + injection hardening (this PR is itself security-scanned)
# ---------------------------------------------------------------------------

class TestHardening:

    @pytest.mark.parametrize("path", [STAGE1_PATH, STAGE2_PATH])
    def test_third_party_actions_sha_pinned(self, path):
        text = _read(path)
        for m in re.finditer(r"uses:\s*astral-sh/setup-uv@(\S+)", text):
            assert re.fullmatch(r"[0-9a-f]{40}", m.group(1)), \
                f"astral-sh/setup-uv must be SHA-pinned, got {m.group(1)!r}"

    @pytest.mark.parametrize("path", [STAGE1_PATH, STAGE2_PATH])
    def test_no_direct_github_context_in_run_body(self, path):
        # run-shell-injection guard: never interpolate ${{ github.* }} directly
        # inside a `run:` shell body — hoist into env first. Tracks the run-block
        # by indentation so the legitimate `${{ github.* }}` in `env:` blocks is
        # not flagged (only deeper-indented run-block lines count).
        text = _read(path)
        offenders = []
        run_indent = None
        for line in text.splitlines():
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if run_indent is not None:
                if indent > run_indent:
                    if "${{ github." in line:
                        offenders.append(line.strip())
                    continue
                run_indent = None  # block ended (dedent to <= run: indent)
            stripped = line.strip()
            if stripped.startswith("run:"):
                if "${{ github." in line:  # inline run on the same line
                    offenders.append(stripped)
                if stripped in ("run: |", "run: >") or stripped.startswith(("run: |", "run: >")):
                    run_indent = indent
        assert not offenders, f"raw ${{{{ github.* }}}} in run body (injection risk): {offenders}"
