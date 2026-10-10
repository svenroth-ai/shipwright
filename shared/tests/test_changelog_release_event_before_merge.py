"""The release skill records its changelog event BEFORE the release PR is merged.

Root cause (iterate-2026-10-10-release-event-before-merge): the skill wrote the
`phase_completed`/changelog event after the PR merge and tag push, straight into
the main checkout. Nothing committed it, so main stayed dirty, `git pull
--ff-only` aborted once an upstream PR touched the event log, and the release
event never reached the event history. These checks pin the order in the skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL = (Path(__file__).resolve().parents[2] / "plugins" / "shipwright-changelog"
          / "skills" / "changelog" / "SKILL.md")
_RECORD = "scripts/tools/record_event.py"
_FENCE = chr(96) * 3
_NL = chr(10)
_CONT = chr(92) + _NL  # shell line continuation: backslash + newline
# The real command block, not prose that merely mentions the command.
_TAG_PUSH = _FENCE + "bash" + _NL + "git push --tags origin main"
_MERGE = "gh pr merge --merge --delete-branch"


def _text() -> str:
    return _SKILL.read_text(encoding="utf-8").replace(chr(13) + _NL, _NL)


@pytest.mark.covers("FR-01.09")
def test_the_event_is_recorded_exactly_once():
    assert _text().count(_RECORD) == 1


@pytest.mark.covers("FR-01.09")
def test_the_event_is_recorded_before_the_merge_and_the_tag_push():
    text = _text()
    record = text.index(_RECORD)
    assert record < text.index(_MERGE)
    assert record < text.index(_TAG_PUSH)


@pytest.mark.covers("FR-01.09")
def test_the_event_is_committed_by_explicit_pathspec_and_pushed():
    text = _text()
    after = text[text.index(_RECORD):text.index(_MERGE)]
    assert "-- shipwright_events.jsonl" in after
    assert "git push origin HEAD" in after
    assert "git add -A" not in after


@pytest.mark.covers("FR-01.09")
def test_the_steps_are_chained_so_a_failed_record_stops_the_merge():
    text = _text()
    start = text.index(_RECORD)
    block = text[start:text.index(_FENCE, start)]
    assert _CONT + "&& git add shipwright_events.jsonl" in block
    assert _CONT + "&& git commit" in block
    assert _CONT + "&& git push origin HEAD" in block
    # the push is for the PR flow only; the on-main reader is told to omit it
    assert "OMIT this line" in block


@pytest.mark.covers("FR-01.09")
def test_the_on_main_case_records_before_the_one_push():
    text = _text()
    note = text.index("tagged on main")
    assert "drop the " + chr(96) + "git push origin HEAD" + chr(96) in text[note:note + 200]
    assert note < text.index(_TAG_PUSH)
