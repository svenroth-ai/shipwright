"""The changelog ``phase_completed`` event must ship in the release PR.

Recording it after the merge appended to ``shipwright_events.jsonl`` in the
main checkout and never committed it (webui v0.28.0, monorepo v0.34.0), so
the documented Step 7 order is pinned: record + commit + push, THEN merge.
"""

from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
)


def _step_7() -> str:
    text = SKILL_PATH.read_text(encoding="utf-8")
    return text[text.index("## Step 7: Create PR") :]


@pytest.mark.covers("FR-01.09/AC01")
def test_event_is_recorded_and_committed_before_merge():
    step = _step_7()
    create = step.index("gh pr create")
    record = step.index("scripts/tools/record_event.py")
    guard = step.index("git diff --quiet HEAD -- shipwright_events.jsonl ||")
    commit = step.index("record changelog event for v")
    push = step.index("git push origin HEAD")
    merge = step.index("gh pr merge")
    assert create < record < guard < commit < push < merge


@pytest.mark.covers("FR-01.09/AC01")
def test_event_is_recorded_once():
    assert _step_7().count("scripts/tools/record_event.py") == 1


@pytest.mark.covers("FR-01.09/AC01")
def test_on_main_case_records_before_tag_push():
    step = _step_7()
    assert "tagged on main" in step
    assert step.index("tagged on main") < step.index("git push --tags origin main")
    assert "before `git push --tags origin main`" in step
