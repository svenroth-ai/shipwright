"""Prose guards for the R2 worktree-capability wiring (campaign-dag-scheduler
R2). Closes the exact gap external plan review (OpenAI, high) found: the
runner's Input section documented `campaign_worktree`/`state_path` as brief
parameters, but nothing in `campaign-mode.md`'s own spawn line populated
them — so every real campaign brief would have omitted both and the
runner's step-boundary liveness touches would silently never fire.

Not a behavior test (no code runs these docs) — a content guard, same shape
as `test_campaign_step_3f_bis.py`, so a future edit that drops either
mention is caught immediately rather than rediscovered by another external
review pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_prose_harness import CAMPAIGN_DOC, RUNNER_DOC, norm  # noqa: E402


def _step_3c() -> str:
    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = text.index("3c. **Worktree guard")
    rest = text[start:]
    end = rest.index("3d. Wait for terminal marker")
    return norm(rest[:end])


def test_step_3c_spawn_brief_populates_campaign_worktree_and_state_path():
    body = _step_3c()
    assert "campaign_worktree" in body
    assert "state_path" in body
    # Not just mentioned — populated FROM `{project_root}`, the value that
    # actually exists at spawn time (external review's exact finding: a
    # bare mention with no producer is indistinguishable from a promise).
    assert "campaign_worktree (= {project_root}" in body


def test_runner_input_section_documents_both_new_brief_parameters():
    text = norm(RUNNER_DOC.read_text(encoding="utf-8"))
    assert "campaign_worktree" in text
    assert "state_path" in text


def test_runner_lease_touch_uses_project_root_not_campaign_worktree_for_its_own_field():
    """The exact bug external code review (GLM + OpenAI, medium) found: the
    lease's OWN `--worktree` value must be `{project_root}` (the unit's own
    worktree, pre-/post-flip), never `{campaign_worktree}` (which would
    freeze the SHARED worktree into every unit row forever once R5a flips
    `{project_root}`)."""
    text = RUNNER_DOC.read_text(encoding="utf-8")
    start = text.index("check_unit_lease.py")
    snippet = text[start:start + 400]
    assert '--worktree "{project_root}"' in snippet
    assert '--campaign-worktree "{campaign_worktree}"' in snippet
