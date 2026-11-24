"""The changelog ``phase_completed`` event must ship in the release PR.

Recording it after the merge appended to ``shipwright_events.jsonl`` in the
main checkout and never committed it (webui v0.28.0, monorepo v0.34.0), so
the documented Step 7 order is pinned: record + commit + push, THEN merge. Since unit P4 the record,
the commit and the push are ``release.py record-event``, and the tag push is ``release.py push-tag`` (its chain is proven in ``test_release_p4_cli.py``
and ``test_release_event_real_git.py``); this file pins where the skill calls it.
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
    record = step.index("release.py\" record-event")
    merge = step.index("gh pr merge")
    tag_push = step.index('release.py" push-tag')
    assert create < record < merge < tag_push  # the tag follows the merge (F1b)


@pytest.mark.covers("FR-01.09/AC01")
def test_event_is_recorded_once_per_flow():
    # One call serves the PR flow and the on-main flow (it reads the branch itself); never recorded twice.
    assert _step_7().count("release.py\" record-event") == 1
    assert "record_event.py" not in _step_7()


@pytest.mark.covers("FR-01.09/AC01")
def test_on_main_case_records_before_tag_push_without_its_own_push():
    step = _step_7()
    assert step.index("Omit `--pr-url` on main") < step.index('release.py" push-tag')
    assert "git push origin HEAD" not in step  # the head push is inside `record-event`, on a feature branch only


@pytest.mark.covers("FR-01.09/AC11")
def test_a_guided_release_pushes_only_the_tag_and_only_after_the_merge():
    step = _step_7()
    assert "**after the PR is merged**" in step and "Neither is done before the merge" in step
    assert step.index("run `close-phase` now") < step.index("**after the PR is merged**")  # close first (waiting), tag and page after the merge
    flat = " ".join(step.split())
    assert 'release.py" push-tag' in flat and "never a local trunk" in flat and "`reason: \"waiting_for_merge\"`" in flat
    assert "git push" not in step  # the push, and the decision before it, are `release.py push-tag` (F1a/F1b/F4; proven in test_release_p5.py)
