"""tools/record_autonomous_choice.py: the run-23 gate questions an autonomous run settles by rule."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.05/AC05")

_TOOL = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "record_autonomous_choice.py"
_spec = importlib.util.spec_from_file_location("_record_autonomous_choice", _TOOL)
rac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rac)

BRIEF = ("The app must refuse any address other than 127.0.0.1 or localhost.\n"
         "You can use the board on a phone through a tunnel you run yourself.\n")


def _project(root: Path, autonomy: str = "autonomous") -> Path:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"autonomy": autonomy, "brief_dir": "brief"}), encoding="utf-8")
    (root / "brief").mkdir(exist_ok=True)
    (root / "brief" / "brief.md").write_text(BRIEF, encoding="utf-8")
    return root


def _run(root: Path, capsys, *args: str) -> tuple[dict, int]:
    code = rac.main(["--project-root", str(root), *args])
    return json.loads(capsys.readouterr().out), code


def _log(root: Path) -> str:
    return (root / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")


def test_a_hard_requirement_outranks_a_brief_value_and_is_recorded_once(tmp_path, capsys):
    root = _project(tmp_path)
    args = ("--kind", "precedence", "--winner", "hard-requirement", "--loser", "brief",
            "--what", "phone access via a named tunnel",
            "--quote", "must refuse any address other than 127.0.0.1 or localhost")
    out, code = _run(root, capsys, *args)
    assert code == 0 and out["action"] == "recorded" and out["adr"]
    assert "hard-requirement over brief" in _log(root)
    again, code = _run(root, capsys, *args)
    assert code == 0 and again["action"] == "already_recorded"


def test_a_losing_screen_becomes_a_known_difference(tmp_path, capsys):
    root = _project(tmp_path)
    out, code = _run(root, capsys, "--kind", "precedence", "--winner", "brief", "--loser", "approved-screen",
                     "--what", "status line under the title",
                     "--quote", "You can use the board on a phone through a tunnel")
    assert code == 0 and out["kd"]


def test_a_plan_cannot_outrank_the_brief_or_invent_a_quote(tmp_path, capsys):
    root = _project(tmp_path)
    out, code = _run(root, capsys, "--kind", "precedence", "--winner", "plan", "--loser", "brief",
                     "--what", "marker rule")
    assert code == 1 and out["action"] == "ask"
    out, code = _run(root, capsys, "--kind", "precedence", "--winner", "brief", "--loser", "plan",
                     "--what", "marker rule", "--quote", "the marker always moves to the newest hit seen")
    assert code == 1 and "quote" in out["why"]


def test_an_interactive_run_records_nothing(tmp_path, capsys):
    root = _project(tmp_path)
    (root / "shipwright_run_config.json").write_text(json.dumps({"autonomy": "guided"}), encoding="utf-8")
    out, code = _run(root, capsys, "--kind", "routine", "--topic", "changelog-entry")
    assert code == 1 and out["autonomous"] is False


@pytest.mark.parametrize("topic,choice", [("changelog-entry", "readable-list"),
                                          ("tag-uncommitted", "commit-then-tag"),
                                          ("test-screenshots", "ignore-in-git"),
                                          ("decision-log-entry", "add-entry-and-recheck")])
def test_routine_wrap_up_questions_take_their_documented_default(tmp_path, capsys, topic, choice):
    root = _project(tmp_path)
    out, code = _run(root, capsys, "--kind", "routine", "--topic", topic, "--phase", "Changelog")
    assert code == 0 and out["choice"] == choice and out["adr"]


def test_an_unknown_routine_topic_is_an_error(tmp_path, capsys):
    out, code = _run(_project(tmp_path), capsys, "--kind", "routine", "--topic", "delete-everything")
    assert code == 2 and "error" in out
