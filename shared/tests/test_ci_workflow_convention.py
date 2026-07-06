"""Drift test pinning the CI + Claude-Review workflow templates to the constants.

The convention lock at ``shared/scripts/lib/ci_workflow.py`` is consumed by:

- ``ci_workflow_scaffolder.py`` — writes the profile-specific CI template into
  target repos at ``WORKFLOW_PATH``.
- ``claude_review_workflow_scaffolder.py`` — writes the Claude-Review template
  into target repos at ``CLAUDE_REVIEW_WORKFLOW_PATH``.

Without this test the constants module is a lie: a template could lose its
cross-platform matrix block, accidentally activate auto-triggers, or drop
the explicit-permissions floor — and nobody would notice until an adopted
repo hits the gap in production CI.

Failure modes deliberately covered (external-review findings #5 + #6):

1. Template path declared in ``TEMPLATE_BY_PROFILE`` but file missing on disk.
2. CI template missing the canonical cross-platform matrix block
   (``os: [ubuntu-latest, windows-latest]`` + ``fail-fast: false``).
3. CI template's runtime triggers (``push``, ``pull_request``) ACTIVE — those
   must be absent from parsed YAML so adopted repos don't auto-fire before
   the user has reviewed Phase-B activation. (PyYAML cannot distinguish
   "commented" from "absent" — we require absent to make the contract
   PyYAML-testable per external-review #5.)
4. Explicit ``permissions:`` block missing — implicit token permissions
   are org-policy-dependent and surface as silent CI failures
   (external-review #G3 + #O13).
5. Claude-Review template missing the convention-locked permissions
   (``contents: read``, ``pull-requests: write``) — needed to read the diff
   and post the review comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance deps

from lib.ci_workflow import (  # noqa: E402
    CLAUDE_REVIEW_TEMPLATE_PATH,
    CLAUDE_REVIEW_WORKFLOW_PATH,
    MATRIX_FAIL_FAST,
    MATRIX_OS_VALUES,
    TEMPLATE_BY_PROFILE,
    WORKFLOW_PATH,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Path-constant sanity
# ---------------------------------------------------------------------------


class TestWorkflowPathConstants:
    """Deployed-file path constants must match GitHub Actions conventions."""

    @pytest.mark.parametrize("path", [WORKFLOW_PATH, CLAUDE_REVIEW_WORKFLOW_PATH])
    def test_workflow_path_under_dot_github(self, path: str) -> None:
        assert path.startswith(".github/workflows/"), (
            f"WORKFLOW_PATH={path!r} is not under .github/workflows/ — "
            f"GitHub Actions only resolves workflows from that directory."
        )
        assert path.endswith(".yml") or path.endswith(".yaml"), (
            "Workflow path must end in .yml or .yaml for GitHub to load it."
        )


# ---------------------------------------------------------------------------
# Every registered template resolves to a file
# ---------------------------------------------------------------------------


class TestTemplateRegistryResolves:
    """``TEMPLATE_BY_PROFILE`` is the SSoT — every value must be a real file."""

    @pytest.mark.parametrize("profile,template_rel", list(TEMPLATE_BY_PROFILE.items()))
    def test_profile_template_exists(self, profile: str, template_rel: str) -> None:
        template = REPO_ROOT / template_rel
        assert template.exists(), (
            f"profile {profile!r}: template at {template} declared in "
            f"TEMPLATE_BY_PROFILE but does not exist on disk.\n"
            f"  Either author the template or unregister the profile."
        )

    def test_claude_review_template_exists(self) -> None:
        template = REPO_ROOT / CLAUDE_REVIEW_TEMPLATE_PATH
        assert template.exists(), (
            f"Claude-Review template at {template} declared in "
            f"CLAUDE_REVIEW_TEMPLATE_PATH but does not exist on disk."
        )


# ---------------------------------------------------------------------------
# CI templates: cross-platform matrix block
# ---------------------------------------------------------------------------


def _parsed_ci_templates() -> list[tuple[str, dict]]:
    """Load every CI template + return (profile, parsed_yaml) tuples.

    Skips entries whose file doesn't exist — TestTemplateRegistryResolves
    catches those independently with a clearer failure message.
    """
    out: list[tuple[str, dict]] = []
    for profile, template_rel in TEMPLATE_BY_PROFILE.items():
        template = REPO_ROOT / template_rel
        if not template.exists():
            continue
        out.append((profile, yaml.safe_load(template.read_text(encoding="utf-8"))))
    return out


class TestCITemplatesCrossPlatformMatrix:
    """Every job tagged for cross-platform coverage must carry the matrix.

    Convention (external-review #O6): job-name suffixes ``-checks`` and
    ``-test``/``-tests`` mark cross-platform jobs. Jobs named ``security``,
    ``deploy``, ``diff-coverage`` are explicitly Linux-only by design.
    """

    PLATFORM_AGNOSTIC_JOB_PATTERNS = ("security", "deploy", "release", "publish", "diff-coverage")

    def _is_matrixed_job(self, job_name: str) -> bool:
        """Return True if this job is expected to use the OS matrix."""
        name = job_name.lower()
        for pat in self.PLATFORM_AGNOSTIC_JOB_PATTERNS:
            if name.startswith(pat) or name == pat:
                return False
        return True

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_template_has_matrix_jobs(self, profile: str, parsed: dict) -> None:
        jobs = parsed.get("jobs") or {}
        matrixed_jobs = [
            (name, job)
            for name, job in jobs.items()
            if isinstance(job, dict) and self._is_matrixed_job(name)
        ]
        assert matrixed_jobs, (
            f"profile {profile!r}: no platform-aware jobs found in template "
            f"(jobs: {list(jobs.keys())!r}). At least one test/check job per "
            f"template must use the cross-platform matrix."
        )

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_matrixed_jobs_declare_matrix(self, profile: str, parsed: dict) -> None:
        jobs = parsed.get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or not self._is_matrixed_job(job_name):
                continue
            strategy = job.get("strategy") or {}
            matrix = strategy.get("matrix") or {}
            os_values = matrix.get("os")
            assert os_values == MATRIX_OS_VALUES, (
                f"profile {profile!r}, job {job_name!r}: "
                f"strategy.matrix.os={os_values!r}, expected "
                f"{MATRIX_OS_VALUES!r}.\n"
                f"  Cross-platform matrix is the non-negotiable invariant — "
                f"the webui v0.8.5 regression that motivated this iterate "
                f"would still slip through without it."
            )

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_matrixed_jobs_fail_fast_off(self, profile: str, parsed: dict) -> None:
        jobs = parsed.get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or not self._is_matrixed_job(job_name):
                continue
            strategy = job.get("strategy") or {}
            assert strategy.get("fail-fast") is MATRIX_FAIL_FAST, (
                f"profile {profile!r}, job {job_name!r}: "
                f"strategy.fail-fast={strategy.get('fail-fast')!r}, expected "
                f"{MATRIX_FAIL_FAST!r}.\n"
                f"  Diagnostic visibility (both OS results visible in run "
                f"summary) outweighs the Windows-minutes cost for an OSS "
                f"framework. See ci_workflow.py module docstring for the "
                f"rationale; flip this with explicit ADR if you disagree."
            )

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_matrixed_jobs_use_matrix_runs_on(self, profile: str, parsed: dict) -> None:
        jobs = parsed.get("jobs") or {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict) or not self._is_matrixed_job(job_name):
                continue
            runs_on = job.get("runs-on")
            assert runs_on == "${{ matrix.os }}", (
                f"profile {profile!r}, job {job_name!r}: "
                f"runs-on={runs_on!r}, expected '${{{{ matrix.os }}}}'.\n"
                f"  Without the matrix-driven runs-on, the strategy.matrix "
                f"block is declarative-only and the job actually runs on "
                f"whatever single host is set."
            )


# ---------------------------------------------------------------------------
# CI templates: dormant-trigger contract
# ---------------------------------------------------------------------------


class TestCITemplatesDormantTriggers:
    """Adopted CI templates must NOT fire automatically.

    Same Phase-B activation discipline as the security workflow: the user
    reviews Code Scanning / branch protections / secrets BEFORE flipping
    auto-triggers. The template ships with only ``workflow_dispatch:``
    active.

    External-review #O5: PyYAML loses comments, so we cannot distinguish
    "commented out" from "absent". Make the contract PyYAML-testable by
    requiring absent.
    """

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_workflow_dispatch_active(self, profile: str, parsed: dict) -> None:
        # PyYAML quirk: bare `on:` parses as Python literal True (YAML 1.1
        # "truthy" string). Look it up under both keys.
        triggers = parsed.get("on") or parsed.get(True) or {}
        assert isinstance(triggers, dict), (
            f"profile {profile!r}: `on:` block is not a mapping "
            f"(got {type(triggers).__name__}). Cannot resolve triggers."
        )
        assert "workflow_dispatch" in triggers, (
            f"profile {profile!r}: workflow_dispatch trigger missing — "
            f"user has no manual handle to fire the workflow before "
            f"activating auto-triggers."
        )

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_no_active_pull_request_trigger(self, profile: str, parsed: dict) -> None:
        triggers = parsed.get("on") or parsed.get(True) or {}
        if isinstance(triggers, dict):
            assert "pull_request" not in triggers, (
                f"profile {profile!r}: pull_request trigger is ACTIVE in "
                f"template — adopted repos would auto-fire the workflow on "
                f"every PR before Phase-B prerequisites are confirmed. The "
                f"trigger must be absent from parsed YAML (header comments "
                f"in raw text are fine — operators can uncomment after "
                f"reviewing activation guidance)."
            )

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_no_active_push_trigger(self, profile: str, parsed: dict) -> None:
        triggers = parsed.get("on") or parsed.get(True) or {}
        if isinstance(triggers, dict):
            assert "push" not in triggers, (
                f"profile {profile!r}: push trigger is ACTIVE in template — "
                f"adopted repos would auto-fire on every commit before "
                f"Phase-B activation. The trigger must be absent from "
                f"parsed YAML; uncomment after activation."
            )


# ---------------------------------------------------------------------------
# Explicit permissions floor (external-review #G3 + #O13)
# ---------------------------------------------------------------------------


class TestCITemplatesExplicitPermissions:
    """Every workflow must declare an explicit ``permissions:`` block.

    Implicit GITHUB_TOKEN permissions are org-policy-dependent: a repo
    moved into an org with restricted defaults silently loses access; a
    permissive org over-grants every workflow. Explicit floor is correct
    for shipped templates.
    """

    @pytest.mark.parametrize("profile,parsed", _parsed_ci_templates())
    def test_ci_template_has_explicit_permissions(
        self, profile: str, parsed: dict
    ) -> None:
        permissions = parsed.get("permissions")
        assert permissions is not None, (
            f"profile {profile!r}: no top-level `permissions:` block. "
            f"Add `permissions: {{ contents: read }}` minimum so org-default "
            f"changes can't silently break the workflow."
        )
        assert isinstance(permissions, dict), (
            f"profile {profile!r}: `permissions:` must be a mapping, "
            f"not {type(permissions).__name__}."
        )
        assert permissions.get("contents") == "read", (
            f"profile {profile!r}: permissions.contents != 'read' — "
            f"actions/checkout@v4 needs this to fetch the repo."
        )


class TestClaudeReviewTemplate:
    """Claude-Review template invariants — separate from CI per AC-2.

    The Claude-Review workflow:
    - Runs only on pull_request (active trigger by design — independent
      review fires on PR events).
    - Is profile-agnostic (no matrix, single runner).
    - Needs explicit permissions: contents:read + pull-requests:write.
    """

    @pytest.fixture(scope="class")
    def parsed(self) -> dict:
        template = REPO_ROOT / CLAUDE_REVIEW_TEMPLATE_PATH
        return yaml.safe_load(template.read_text(encoding="utf-8"))

    def test_pull_request_trigger_active(self, parsed: dict) -> None:
        # Claude-Review is the one workflow where pull_request is the
        # intended trigger — it fires on PRs by design.
        triggers = parsed.get("on") or parsed.get(True) or {}
        assert "pull_request" in triggers, (
            "claude-review template: pull_request trigger missing — "
            "this workflow has no purpose without PR events."
        )

    def test_has_explicit_permissions(self, parsed: dict) -> None:
        permissions = parsed.get("permissions") or {}
        assert isinstance(permissions, dict), (
            "claude-review template: permissions must be a mapping."
        )
        # contents:read for checkout, pull-requests:write to post the
        # review comment.
        assert permissions.get("contents") == "read", (
            "claude-review template: permissions.contents != 'read' — "
            "actions/checkout@v4 needs this."
        )
        assert permissions.get("pull-requests") == "write", (
            "claude-review template: permissions.pull-requests != 'write' "
            "— review comment cannot be posted without it."
        )
