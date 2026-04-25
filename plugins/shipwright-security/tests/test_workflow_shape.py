"""Snapshot test for .github/workflows/security.yml invariants.

Iterate 2 (`sec-ci-activation`) deliberately leaves auto-triggers DORMANT —
only `workflow_dispatch` is active. This test guards against accidental
uncommenting in future edits, and verifies the SARIF + fork-guard +
permission contract baked into the workflow.

Text-regex based (no PyYAML dep) — the goal is to catch drift on a small
set of invariants, not to validate the full YAML structure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "security.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW_PATH.exists(), f"missing workflow: {WORKFLOW_PATH}"
    return WORKFLOW_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Triggers — must remain DORMANT until Phase B (Go-Live)
# ---------------------------------------------------------------------------

class TestDormantTriggers:

    def test_pull_request_trigger_is_commented(self, workflow_text):
        # Match an UNCOMMENTED `pull_request:` at the top of the `on:` block.
        # Allowed: `# pull_request:` lines (commented).
        # Forbidden: a bare `pull_request:` line at indent level 2 (inside `on:`).
        for line in workflow_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("pull_request:"):
                pytest.fail(
                    "pull_request trigger appears UNCOMMENTED in security.yml. "
                    "Iterate 2 (`sec-ci-activation`) keeps triggers dormant — "
                    "user activates them manually at Phase B / Go-Live."
                )

    def test_schedule_trigger_is_commented(self, workflow_text):
        for line in workflow_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("schedule:"):
                pytest.fail(
                    "schedule trigger appears UNCOMMENTED in security.yml. "
                    "Iterate 2 (`sec-ci-activation`) keeps triggers dormant."
                )

    def test_workflow_dispatch_is_active(self, workflow_text):
        # workflow_dispatch must remain active so the user can trigger manually.
        active_dispatch = any(
            line.strip() == "workflow_dispatch:"
            and not line.lstrip().startswith("#")
            for line in workflow_text.splitlines()
        )
        assert active_dispatch, "workflow_dispatch trigger missing from security.yml"

    def test_dormant_banner_present(self, workflow_text):
        # The banner is what tells humans (and future-Claude) why triggers
        # look weird — keep it intact.
        assert "DORMANT" in workflow_text


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class TestPermissions:

    def test_security_events_write_present(self, workflow_text):
        # Required by github/codeql-action/upload-sarif@v3
        assert re.search(
            r"^\s*security-events:\s*write\b",
            workflow_text,
            re.MULTILINE,
        ), "security-events: write permission missing"

    def test_contents_read_present(self, workflow_text):
        assert re.search(
            r"^\s*contents:\s*read\b",
            workflow_text,
            re.MULTILINE,
        ), "contents: read permission missing"

    def test_pull_requests_write_present(self, workflow_text):
        assert re.search(
            r"^\s*pull-requests:\s*write\b",
            workflow_text,
            re.MULTILINE,
        ), "pull-requests: write permission missing (needed for PR comments)"


# ---------------------------------------------------------------------------
# SARIF upload + fork-PR guards
# ---------------------------------------------------------------------------

class TestSarifAndGuards:

    def test_sarif_generation_step_present(self, workflow_text):
        assert "--sarif-dir" in workflow_text, \
            "SARIF generation step missing (--sarif-dir flag not used)"
        assert "--input-from-cache" in workflow_text, \
            "SARIF generation must use --input-from-cache to avoid double-scan"

    def test_upload_sarif_action_used(self, workflow_text):
        assert "github/codeql-action/upload-sarif@v3" in workflow_text, \
            "upload-sarif action not invoked"

    def test_upload_sarif_fork_guard(self, workflow_text):
        # The upload step must guard against fork PRs (read-only GITHUB_TOKEN).
        # We require the head-repo equality clause to appear near the upload
        # step. The exact `if:` shape:
        #   if: always() && (github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)
        assert (
            "github.event.pull_request.head.repo.full_name == github.repository"
            in workflow_text
        ), "fork-PR guard (head.repo.full_name == github.repository) missing"

    def test_pr_comment_fork_guard(self, workflow_text):
        # The PR comment step must also be guarded — fork PR can't grant
        # pull-requests: write.
        # Look for the PR-comment step's `if:` containing both event check and head-repo check.
        pr_comment_block = re.search(
            r"-\s+name:\s*Post PR comment\s*\n\s*if:\s*([^\n]+)",
            workflow_text,
        )
        assert pr_comment_block, "Post PR comment step missing"
        cond = pr_comment_block.group(1)
        assert "pull_request" in cond, "PR-comment if: must check event_name"
        assert "head.repo.full_name == github.repository" in cond, \
            "PR-comment step missing fork-PR guard"

    def test_sarif_category_set(self, workflow_text):
        # SARIF results land under "shipwright-security" category in the
        # GitHub Security tab — separate from CodeQL's own category.
        assert re.search(
            r"category:\s*shipwright-security\b",
            workflow_text,
        ), "SARIF category 'shipwright-security' missing on upload-sarif step"


# ---------------------------------------------------------------------------
# Critical-finding gate (regression — existing behavior preserved)
# ---------------------------------------------------------------------------

class TestCriticalGate:

    def test_critical_check_present(self, workflow_text):
        assert "critical security findings" in workflow_text, \
            "critical-findings gate missing — workflow no longer blocks on critical"
