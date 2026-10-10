"""Required-checks drift for repos adopted before the review scaffold was retired.

Adopt stopped scaffolding ``claude-review*.yml`` (decision 2026-10-10), but a
repo adopted earlier keeps its stage-2 workflow and the ``Claude Code Review``
status it posts. Dropping that context from ``POSTED_STATUS_CONTEXTS`` would make
the drift producer (which runs in every adopted repo) call it a phantom check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.required_checks_drift import (  # noqa: E402
    compare_required_checks,
    workflow_check_sets,
)


@pytest.mark.covers("FR-01.17/AC06")
def test_legacy_adopted_review_context_is_not_a_phantom(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "claude-review-run.yml").write_text(
        "\n".join([
            "name: Claude Review Run", "on:", "  workflow_run:",
            "    workflows: [Claude Review]", "    types: [completed]",
            "jobs:", "  review:", "    runs-on: ubuntu-latest", "    steps: []", "",
        ]),
        encoding="utf-8",
    )
    possible, _candidates = workflow_check_sets(tmp_path)
    assert "Claude Code Review" in possible
    result = compare_required_checks(possible, ["Claude Code Review"])
    assert result["in_sync"]
