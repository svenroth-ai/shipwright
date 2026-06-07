"""Drift test pinning the security-workflow template to the constants module.

The convention lock at ``shared/scripts/lib/security_workflow.py`` is consumed
by two independent code paths:

- ``/shipwright-adopt`` writes the template into target repos at
  ``WORKFLOW_PATH``.
- ``/shipwright-compliance`` Group A5 audits the deployed file using the same
  constants.

Without this test the constants module is a lie: adopt could ship a template
whose step id, permissions, or SARIF category disagree with what compliance
checks for, and nobody would notice until a real audit fires on a real
adopted repo.

Failure modes deliberately covered:

1. Template missing — adopt would scaffold an empty file.
2. Step id renamed in template — A5 audit would not find the gate step.
3. Required permission dropped from template — adopted workflows silently
   lose SARIF upload capability the moment GitHub flips unlisted permissions
   to ``none``.
4. SARIF category renamed — findings land in a different Security-tab bucket
   than the audit expects.
5. Triggers activated in the template — adopted repos would auto-fire the
   workflow on every PR before the user has reviewed Phase B prerequisites
   (Code Scanning enabled, secrets configured, etc.).
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance deps

from lib.security_workflow import (  # noqa: E402  (deferred so pytest.importorskip wins)
    CRITICAL_GATE_STEP_ID,
    REQUIRED_PERMISSIONS,
    SARIF_CATEGORY,
    SARIF_UPLOAD_USES_PREFIX,
    TEMPLATE_PATH,
    WORKFLOW_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_FILE = REPO_ROOT / TEMPLATE_PATH


@pytest.fixture(scope="module")
def template_text() -> str:
    if not TEMPLATE_FILE.exists():
        pytest.fail(
            f"security workflow template missing at {TEMPLATE_FILE}.\n"
            f"  Convention lock (shared/scripts/lib/security_workflow.py) declares "
            f"TEMPLATE_PATH={TEMPLATE_PATH!r} but the file is absent.\n"
            f"  Either author the template or update the constant."
        )
    return TEMPLATE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template_yaml(template_text):
    """Parse the template as YAML.

    GitHub Actions YAML uses bare ``on:`` which PyYAML happily parses as the
    Python literal ``True`` (because YAML 1.1 truthy strings include ``on``).
    The downstream tests address that quirk with explicit lookups.
    """
    return yaml.safe_load(template_text)


# ---------------------------------------------------------------------------
# Constants <-> template alignment
# ---------------------------------------------------------------------------


class TestCriticalGateStep:
    """The merge-blocking gate step must carry the canonical id so A5 finds it."""

    def test_critical_gate_step_id_present(self, template_yaml):
        steps = _all_steps(template_yaml)
        ids = [s.get("id") for s in steps if isinstance(s, dict)]
        assert CRITICAL_GATE_STEP_ID in ids, (
            f"no step in template carries id={CRITICAL_GATE_STEP_ID!r}.\n"
            f"  Found ids: {[i for i in ids if i]!r}.\n"
            f"  Adopt + A5 audit cannot agree without this id."
        )


class TestRequiredPermissions:
    """Every permission in REQUIRED_PERMISSIONS must be present in the template."""

    @pytest.mark.parametrize("perm,value", list(REQUIRED_PERMISSIONS.items()))
    def test_required_permission_present(self, template_yaml, perm, value):
        permissions = template_yaml.get("permissions") or {}
        assert isinstance(permissions, dict), (
            "template `permissions` block is not a mapping — once explicit, "
            "GitHub silently drops every unlisted permission to `none`."
        )
        assert permissions.get(perm) == value, (
            f"required permission {perm!r}: {value!r} missing from template.\n"
            f"  Found: {permissions!r}.\n"
            f"  Without it the workflow loses SARIF upload (or checkout, or "
            f"scope to attach SARIF blobs) the moment it runs in CI."
        )


class TestSarifCategory:
    """SARIF results must land under the canonical category."""

    def test_sarif_category_used(self, template_text):
        # Plain substring is sufficient — the upload-sarif step is one of
        # very few places a literal `category:` ever appears in the file.
        assert f"category: {SARIF_CATEGORY}" in template_text, (
            f"SARIF category {SARIF_CATEGORY!r} missing from upload-sarif step.\n"
            f"  Compliance audit looks for findings under this exact category — "
            f"a rename without updating the constant routes findings to a "
            f"different Security-tab bucket."
        )


class TestSarifUploadUsesPrefix:
    """A5 audit identifies the SARIF upload step by ``uses:`` prefix —
    the template must reference an action under that prefix."""

    def test_template_has_step_using_canonical_action(self, template_yaml):
        steps = _all_steps(template_yaml)
        uses_values = [
            s.get("uses", "") for s in steps if isinstance(s, dict)
        ]
        matching = [u for u in uses_values if isinstance(u, str)
                    and u.startswith(SARIF_UPLOAD_USES_PREFIX)]
        assert matching, (
            f"no step uses an action starting with "
            f"{SARIF_UPLOAD_USES_PREFIX!r}.\n"
            f"  Found uses: {[u for u in uses_values if u]!r}.\n"
            f"  A5 audit identifies the SARIF upload step by this prefix; "
            f"renaming or replacing the action without updating the constant "
            f"makes the audit unable to find the SARIF upload step."
        )


class TestDormantTriggers:
    """Adopt-shipped templates must NOT auto-fire on PRs / schedule.

    The repo Adopt scaffolds into may not have Code Scanning enabled yet, may
    not have the right secrets, and the user needs Phase B sign-off (see
    docs/security-ci-setup.md / project_sec_v030_done.md) before turning the
    auto-triggers on. The template must therefore ship dormant — only
    workflow_dispatch active — and matching ``# pull_request:`` /
    ``# schedule:`` lines preserved as a hint for the user.
    """

    def test_workflow_dispatch_active(self, template_text):
        # An ACTIVE (uncommented) `workflow_dispatch:` line at the top of `on:`.
        active = any(
            line.strip() == "workflow_dispatch:"
            and not line.lstrip().startswith("#")
            for line in template_text.splitlines()
        )
        assert active, (
            "workflow_dispatch trigger missing — user has no manual handle "
            "to fire the workflow before activating the auto-triggers."
        )

    def test_pull_request_trigger_commented(self, template_text):
        # If a bare `pull_request:` appears in `on:` block, it would auto-fire.
        for line in template_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("pull_request:"):
                pytest.fail(
                    "pull_request trigger uncommented in template — adopted "
                    "repos would fire the workflow on every PR before Phase B "
                    "prerequisites are confirmed."
                )

    def test_schedule_trigger_commented(self, template_text):
        for line in template_text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("schedule:"):
                pytest.fail(
                    "schedule trigger uncommented in template — adopted repos "
                    "would run weekly scans before the user has activated."
                )


class TestWorkflowPathConstant:
    """The deployed-file path constant must match the shipped GitHub convention."""

    def test_workflow_path_under_dot_github(self):
        assert WORKFLOW_PATH.startswith(".github/workflows/"), (
            f"WORKFLOW_PATH={WORKFLOW_PATH!r} is not under .github/workflows/ — "
            f"GitHub Actions only resolves workflows from that directory."
        )
        assert WORKFLOW_PATH.endswith(".yml") or WORKFLOW_PATH.endswith(".yaml"), (
            "WORKFLOW_PATH must end in .yml or .yaml for GitHub to load it."
        )


class TestSupplyChainHardening:
    """The adopt-shipped security.yml.template must carry the same supply-chain
    hardening the monorepo's own security.yml already has."""

    def test_gitleaks_download_is_sha256_verified(self, template_text):
        # Download-to-disk + `sha256sum -c` before extract — not an unverified
        # `wget | tar` pipe. Mirrors .github/workflows/security.yml.
        assert "GITLEAKS_SHA256" in template_text, (
            "gitleaks install in the template is not SHA256-pinned — an "
            "unverified tarball is piped straight into extraction."
        )
        assert "sha256sum -c" in template_text, (
            "gitleaks tarball is downloaded but its checksum is never verified "
            "before extraction."
        )

    def test_comment_action_pinned_to_commit_sha(self, template_text):
        assert (
            "peter-evans/create-or-update-comment@"
            "71345be0265236311c031f5c7866368bd1eff043" in template_text
        ), (
            "peter-evans/create-or-update-comment must be pinned to its commit "
            "SHA (supply-chain hardening), not a mutable tag."
        )
        assert "peter-evans/create-or-update-comment@v4" not in template_text, (
            "peter-evans action still references the mutable @v4 tag — a "
            "compromised tag could inject arbitrary code into the PR-comment step."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_steps(workflow: dict) -> list[dict]:
    """Flatten every job's `steps:` list."""
    jobs = workflow.get("jobs") or {}
    steps: list[dict] = []
    for job in jobs.values():
        if isinstance(job, dict):
            steps.extend(job.get("steps") or [])
    return steps
