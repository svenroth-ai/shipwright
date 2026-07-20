"""Scaffold the GitHub Actions Claude-Review workflow into adopted target repos.

The Claude-Review workflow runs an independent Claude Code review pass on
pull requests — separate session from the one that authored the code, per
the Anthropic Architect Certification "review-in-a-different-session"
best practice (commit `8aac61d`).

This scaffolder is profile-agnostic: a single template lands at the
canonical path (`.github/workflows/claude-review.yml`). The workflow is
NOT dormant — it fires on `pull_request` by design, because that is its
entire purpose. The Phase-B activation discipline applies only to the
test/security workflows.

External-review #O11: shares the `workflow_scaffold_helper.copy_template_if_absent`
helper with `ci_workflow_scaffolder` so the idempotency + parent-dir +
ScaffoldResult logic lives in one place.
"""

from __future__ import annotations

from pathlib import Path

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

_REPO_ROOT = Path(__file__).resolve().parents[4]

_CI_WORKFLOW = load_shared_module(
    "scripts/lib/ci_workflow.py", "_shipwright_adopt_claude_review_constants"
)
_HELPER = load_shared_module(
    "scripts/lib/workflow_scaffold_helper.py", "_shipwright_adopt_claude_review_helper"
)

CLAUDE_REVIEW_TEMPLATE_PATH: str = _CI_WORKFLOW.CLAUDE_REVIEW_TEMPLATE_PATH
CLAUDE_REVIEW_WORKFLOW_PATH: str = _CI_WORKFLOW.CLAUDE_REVIEW_WORKFLOW_PATH
ScaffoldResult = _HELPER.ScaffoldResult


def scaffold_claude_review_workflow(project_root: Path) -> ScaffoldResult:
    """Write the Claude-Review workflow into ``project_root``.

    Returns a structured result so the adopt handoff banner can render
    the "installed" vs "preserved" line without re-checking the
    filesystem.

    Reason codes:
    - ``scaffolded`` — wrote=True; template copied to target.
    - ``already_exists`` — wrote=False; pre-existing target preserved.
    """
    target = project_root / CLAUDE_REVIEW_WORKFLOW_PATH
    template = _REPO_ROOT / CLAUDE_REVIEW_TEMPLATE_PATH
    return _HELPER.copy_template_if_absent(
        template_path=template,
        target_path=target,
    )
