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

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_module(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_CI_WORKFLOW = _load_module(
    _REPO_ROOT / "shared" / "scripts" / "lib" / "ci_workflow.py",
    "_shipwright_adopt_claude_review_constants",
)
_HELPER = _load_module(
    _REPO_ROOT / "shared" / "scripts" / "lib" / "workflow_scaffold_helper.py",
    "_shipwright_adopt_claude_review_helper",
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
