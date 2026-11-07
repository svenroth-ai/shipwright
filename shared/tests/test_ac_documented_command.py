"""The DOCUMENTED Step 2a command line (path-a-feature.md) run in the environments it is documented for: a campaign unit, an attended unit, standalone --autonomous."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from shared.tests.ac_test_helpers import repo as _repo
from lib import ac_hold
from tools import ac_decision as cli

_RUN = "iterate-2026-11-03-documented"
_DOC = Path(__file__).resolve().parents[2] / "plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md"
_UNOWNED = {"items": [{"kind": "add", "new_text": "A saved draft survives a restart"}]}


def _documented(root, tmp_path, *extra, base="HEAD"):
    """The command of path-a-feature.md Step 2a.3 for a campaign unit (no --sub-iterate-id: the documented line never had one)."""
    src = tmp_path / "ac.json"
    src.write_text(json.dumps(_UNOWNED), encoding="utf-8")
    return cli.main(["--project-root", str(root), "--from-json", str(src), "--base-ref", base, "--run-id", _RUN, "--bind-id", "demo--Q1",
                     "--nonce", "2026-11-01T00:00:00Z", "--out", str(tmp_path / "decided.json"), "--no-suggest", *extra])


def _unit_layout(tmp_path):
    root = _repo(tmp_path)
    unit = tmp_path / ".worktrees" / "campaign-demo--Q1"
    (tmp_path / ".worktrees" / "campaign-demo").mkdir(parents=True)
    os.rename(root, unit)
    return unit


@pytest.fixture(autouse=True)
def _no_mode(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_AC_MODE", raising=False)


@pytest.mark.covers("FR-01.11/AC49")
def test_h1_the_documented_command_in_an_unattended_campaign_unit_decides_under_auto_without_a_sub_iterate_id(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
    assert _documented(root, tmp_path) == 0, capsys.readouterr().err
    out = json.loads((tmp_path / "decided.json").read_text(encoding="utf-8"))
    assert out["status"] == "ok" and out["ac_mode"]["mode"] == "auto" and out["unattended"] is True


@pytest.mark.covers("FR-01.11/AC49")
def test_h1_an_ask_that_must_be_escalated_still_needs_the_unit_id(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
    assert _documented(root, tmp_path, "--ac-mode", "ask") == 2
    assert "--sub-iterate-id is required" in capsys.readouterr().err
    assert _documented(root, tmp_path, "--ac-mode", "ask", "--sub-iterate-id", "Q1") == 10


@pytest.mark.covers("FR-01.11/AC49")
def test_h2_an_attended_per_unit_worktree_without_the_loop_environment_asks_and_allows_inline_answers(tmp_path, capsys):
    unit = _unit_layout(tmp_path)
    assert ac_hold.is_unattended(unit) is False
    assert _documented(unit, tmp_path) == 10, capsys.readouterr().err
    out = json.loads((tmp_path / "decided.json").read_text(encoding="utf-8"))
    assert out["unattended"] is False and out["ac_mode"]["mode"] == "ask" and "escalation" not in out


@pytest.mark.covers("FR-01.11/AC49")
def test_h2_the_loop_environment_with_a_unit_id_is_what_makes_a_run_unattended(monkeypatch, tmp_path):
    unit = _unit_layout(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    assert ac_hold.is_unattended(unit) is False                                                       # one variable alone is not the loop
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "Q1")
    assert ac_hold.is_unattended(unit) is True and ac_hold.is_unattended("") is True


@pytest.mark.covers("FR-01.11/AC49")
def test_h3_a_standalone_autonomous_run_with_the_documented_command_defaults_to_auto_and_never_stops(tmp_path, capsys):
    root = _repo(tmp_path)
    assert _documented(root, tmp_path, "--autonomous") == 0, capsys.readouterr().err
    out = json.loads((tmp_path / "decided.json").read_text(encoding="utf-8"))
    assert out["status"] == "ok" and out["ac_mode"]["mode"] == "auto"


@pytest.mark.covers("FR-01.11/AC49")
def test_h3_the_documented_command_line_passes_autonomous_and_the_brief_matches_the_design():
    text = _DOC.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "scripts/tools/ac_decision.py" in ln and "--from-json" in ln)
    assert "--autonomous" in line and "--ac-mode" in text
    brief = (Path(__file__).resolve().parents[2] / ".shipwright/planning/campaigns/2026-11-01-ac-at-start-BRIEF.md").read_text(encoding="utf-8")
    assert "never auto-approves" not in brief and re.search(r"--autonomous.{0,80}default mode is `?auto", brief)


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("base", ["null", "refs/does/not/exist", ""])
def test_m2_a_base_ref_that_cannot_be_resolved_is_skipped_with_a_note_not_an_error(tmp_path, capsys, base):
    root = _repo(tmp_path)
    assert _documented(root, tmp_path, base=base) == 0, capsys.readouterr().err
    out = json.loads((tmp_path / "decided.json").read_text(encoding="utf-8")) if (tmp_path / "decided.json").exists() else json.loads(capsys.readouterr().out)
    assert out["status"] == "skipped" and "base" in out["note"].lower() and "F11" in out["note"]


@pytest.mark.covers("FR-01.11/AC49")
def test_m2_a_skipped_decision_writes_no_stub_lines_and_no_error(tmp_path, capsys, monkeypatch):
    from tools import write_plan_stub as wps
    root = _repo(tmp_path)
    decided = tmp_path / "skipped.json"
    decided.write_text(json.dumps({"status": "skipped", "run_id": _RUN, "note": "x"}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["write_plan_stub.py", "--project-root", str(root), "--run-id", _RUN, "--goal", "g", "--reason", "r", "--ref", "x", "--tiny", "--ac-decision", str(decided)])
    assert wps.main() == 0
    stub = (root / ".shipwright" / "planning" / "iterate" / f"{_RUN}.md")
    assert not (root / ".shipwright" / "planning" / "iterate" / _RUN / "ac-record.jsonl").exists() and "ac-decision" not in capsys.readouterr().err
    assert stub.exists() or any(root.rglob("*.md"))


@pytest.mark.covers("FR-01.11/AC49")
def test_l_a_missing_transport_prints_its_reason_once_on_stderr(monkeypatch, capsys):
    from lib import ac_suggest as su
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    monkeypatch.setattr(su, "default_transport", lambda: (_ for _ in ()).throw(FileNotFoundError("no transport here")))
    monkeypatch.setattr(su, "_WARNED", False, raising=False)
    cat = {"frs": {"FR-01.03"}, "titles": {"FR-01.03": "Saving drafts"}, "acs": {}}
    for _ in range(2):
        assert su.propose("A draft is kept", cat, ".")["source"] == "fallback"
    err = capsys.readouterr().err
    assert err.count("no transport here") == 1
