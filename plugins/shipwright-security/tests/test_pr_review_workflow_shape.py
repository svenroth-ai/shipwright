"""Snapshot test for .github/workflows/pr-review.yml invariants (B4.5 Tier-3).

Text-regex based (no PyYAML dep) — guards the tier contract that Branch
Protection relies on: the required status check is the `PR Review` job, the
tier filter lives in a `decide` job, and only Tier-3 PRs reach the OpenRouter
custom script. A drift here could silently auto-merge an unreviewed external or
sensitive-path PR (Failure Mode "Tier-Logik falsch" in the B4.5 spec).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "pr-review.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"missing workflow: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Trigger + concurrency
# ---------------------------------------------------------------------------

class TestTriggers:

    def test_pull_request_trigger_active(self, workflow_text):
        active = any(
            line.lstrip().startswith("pull_request:") and not line.lstrip().startswith("#")
            for line in workflow_text.splitlines()
        )
        assert active, "pr-review.yml must run on pull_request"

    def test_labeled_event_type_present(self, workflow_text):
        # A `needs-review` / `skip-pr-review` label added AFTER open must re-trigger.
        assert "labeled" in workflow_text, "workflow must trigger on the 'labeled' event type"


# ---------------------------------------------------------------------------
# Fork-PR guard + decide-job tier logic
# ---------------------------------------------------------------------------

class TestDecideJob:

    def test_fork_pr_guard_present(self, workflow_text):
        assert (
            "github.event.pull_request.head.repo.full_name == github.repository"
            in workflow_text
        ), "fork-PR guard (head.repo.full_name == github.repository) missing"

    def test_skip_label_rule(self, workflow_text):
        assert "skip-pr-review" in workflow_text, "skip-pr-review label override missing"

    def test_needs_review_label_rule(self, workflow_text):
        assert "needs-review" in workflow_text, "needs-review label override missing"

    def test_sensitive_paths_rule(self, workflow_text):
        # The decide job must classify hooks/skills/agents + workflows as sensitive.
        assert "hooks" in workflow_text and "skills" in workflow_text and "agents" in workflow_text, \
            "sensitive-path tier rule (hooks/skills/agents) missing"
        assert ".github/workflows/" in workflow_text, \
            "sensitive-path tier rule (.github/workflows/) missing"

    def test_external_author_rule(self, workflow_text):
        # External = not Sven and not dependabot.
        assert "svroch" in workflow_text, "external-author tier rule must reference the maintainer login"
        assert re.search(r"needs_review=true", workflow_text), \
            "decide job must be able to emit needs_review=true"


# ---------------------------------------------------------------------------
# Review job — required check name + gating
# ---------------------------------------------------------------------------

class TestReviewJob:

    def test_job_name_is_pr_review(self, workflow_text):
        # Branch Protection's required check matches the job NAME exactly.
        assert re.search(r"^\s*name:\s*PR Review\s*$", workflow_text, re.MULTILINE), \
            "review job name must be exactly 'PR Review' (Branch-Protection required check)"

    def test_needs_decide_with_gate(self, workflow_text):
        assert re.search(r"^\s*needs:\s*decide\b", workflow_text, re.MULTILINE), \
            "review job must declare `needs: decide`"
        assert "needs.decide.outputs.needs_review == 'true'" in workflow_text, \
            "review job must gate on needs.decide.outputs.needs_review == 'true'"

    def test_calls_custom_script_not_third_party_action(self, workflow_text):
        assert "plugins/shipwright-security/scripts/tools/pr_review.py" in workflow_text, \
            "review job must invoke the custom pr_review.py script"
        # No marketplace LLM-review action (OpenRouter-only, control-our-own-code).
        assert "anthropics/claude-code-action" not in workflow_text, \
            "must NOT use a 3rd-party Claude action (B4.5 OpenRouter decision)"


# ---------------------------------------------------------------------------
# Secrets + provider invariants
# ---------------------------------------------------------------------------

class TestSecrets:

    def test_openrouter_secret_used(self, workflow_text):
        assert "secrets.OPENROUTER_API_KEY" in workflow_text, \
            "review job must read OPENROUTER_API_KEY from secrets"

    def test_no_anthropic_key(self, workflow_text):
        assert "ANTHROPIC_API_KEY" not in workflow_text, \
            "OpenRouter is the single provider — no ANTHROPIC_API_KEY"

    def test_no_literal_key(self, workflow_text):
        # No hardcoded OpenRouter/sk- key literal — must come from secrets.
        assert not re.search(r"sk-or-v1-[A-Za-z0-9]{8,}", workflow_text), \
            "hardcoded OpenRouter key literal found — use secrets.OPENROUTER_API_KEY"

    def test_model_env_override(self, workflow_text):
        assert "SHIPWRIGHT_PR_REVIEW_MODEL" in workflow_text, \
            "model must be selectable via SHIPWRIGHT_PR_REVIEW_MODEL env"


# ---------------------------------------------------------------------------
# Supply-chain + injection hardening (this PR is itself security-scanned)
# ---------------------------------------------------------------------------

class TestHardening:

    def test_third_party_actions_sha_pinned(self, workflow_text):
        # setup-uv is third-party → must be pinned to a 40-char commit SHA.
        for m in re.finditer(r"uses:\s*astral-sh/setup-uv@(\S+)", workflow_text):
            assert re.fullmatch(r"[0-9a-f]{40}", m.group(1)), \
                f"astral-sh/setup-uv must be SHA-pinned, got {m.group(1)!r}"

    def test_no_direct_github_context_in_run_body(self, workflow_text):
        # run-shell-injection guard: never interpolate ${{ github.* }} directly
        # inside a `run:` shell body — hoist into env first. Tracks the run-block
        # by indentation so the legitimate `${{ github.* }}` in `env:` blocks is
        # not flagged (only deeper-indented run-block lines count).
        offenders = []
        run_indent = None
        for line in workflow_text.splitlines():
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
