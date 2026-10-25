"""Stop-guard: the block message tells the agent what is open, what is allowed and a runnable command."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from _stop_guard_helpers import RUN  # noqa: E402
from lib import iterate_stop_guard as guard  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC43")


@pytest.fixture
def reason(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: [])
    text = guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="iterate/demo",
                        autonomous=True, tool_count=1)
    assert text
    return text


def test_the_record_hard_blocker_command_is_a_real_path_not_a_template(reason: str) -> None:
    assert "{shared_root}" not in reason and "{{" not in reason
    path = re.search(r'uv run "([^"]+record_hard_blocker\.py)"', reason)
    assert path, reason
    assert Path(path.group(1)).is_file()  # copy-paste runnable, absolute
    assert Path(path.group(1)).is_absolute()


def test_the_message_says_the_run_is_open_not_that_the_agent_broke_a_contract(reason: str) -> None:
    assert "contract violation" not in reason
    assert RUN in reason and "still open" in reason
    assert "MERGED" in reason  # what finishes it


def test_the_message_says_waiting_on_a_background_task_is_allowed(reason: str) -> None:
    low = reason.lower()
    assert "background" in low and "waiting" in low and "without" in low and "tool call" in low


def test_the_message_keeps_the_next_phase_the_hard_blocker_codes_and_the_kill_switch(reason: str) -> None:
    for code in guard.HARD_BLOCKER_CODES:
        assert code in reason
    assert "SHIPWRIGHT_ITERATE_STOP_GUARD=0" in reason
    assert "Next:" in reason


def test_an_unresolvable_tool_path_never_breaks_the_block(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: [])
    monkeypatch.setattr(guard, "__file__", str(tmp_path / "lib" / "iterate_stop_guard.py"))  # no tools/ beside it
    assert guard._blocker_tool() == "record_hard_blocker.py"
    text = guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="iterate/demo",
                        autonomous=True, tool_count=1)
    assert text and "record_hard_blocker.py" in text  # fail-open: a plain name instead of an exception
