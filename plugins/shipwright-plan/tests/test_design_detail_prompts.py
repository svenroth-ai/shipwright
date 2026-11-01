"""Plan carries design-defined detail copied from the screen (e2e runs 12-14, check S08).

These are prose pins (the prompts are the product); the batch-script test runs the real generator.
The build's spec-reviewer stops for a person whenever a section contradicts the approved screen.
Runs 12-14 stopped on a breakpoint (768 vs 900), a posted thread's content and an extra field,
all written into the section from memory. The section-writer prompt and the per-section task
prompt now require values copied from the screen; the spec-reviewer accepts a DECLARED extension.
"""
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.05")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
AGENT = (PLUGIN_ROOT / "agents" / "section-writer.md").read_text(encoding="utf-8")
REVIEWER = (PLUGIN_ROOT.parent / "shipwright-build" / "agents" / "spec-reviewer.md").read_text(encoding="utf-8")
SCRIPT = PLUGIN_ROOT / "scripts" / "checks" / "generate-batch-tasks.py"


def test_section_writer_copies_design_values_from_the_screen():
    flat = " ".join(AGENT.split())
    for needle in ("@media", "Per-state content:", "Design extension:", "Design contradiction:",
                   "do NOT pick a side", "without the number", "- Breakpoint:"):
        assert needle in flat, needle


def test_build_spec_reviewer_gate_is_unchanged():
    """The Build gate is deliberately UNCHANGED: no declared line is an exemption."""
    flat = " ".join(REVIEWER.split())
    assert "REJECT with `kind: \"contradiction\"`" in flat
    assert "Design extension" not in flat and "Design contradiction" not in flat
    assert "a person confirms" in " ".join(AGENT.split())


def test_batch_task_prompt_without_mockups_has_no_design_rules(tmp_path, monkeypatch, capsys):
    planning = tmp_path / ".shipwright" / "planning" / "01-x"
    planning.mkdir(parents=True)
    (planning / "plan.md").write_text("<!-- SECTION_MANIFEST\n01-api\nEND_MANIFEST -->\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generate_batch_tasks_nm", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr("sys.argv", ["x", "--planning-dir", str(planning)])
    assert mod.main() == 0
    assert "Design extension" not in json.loads(capsys.readouterr().out)["tasks"][0]["prompt"]


def test_batch_task_prompt_carries_the_rules(tmp_path, monkeypatch, capsys):
    planning = tmp_path / ".shipwright" / "planning" / "01-x"
    planning.mkdir(parents=True)
    (planning / "plan.md").write_text("<!-- SECTION_MANIFEST\n01-board\nEND_MANIFEST -->\n", encoding="utf-8")
    screens = tmp_path / ".shipwright" / "designs" / "screens"
    screens.mkdir(parents=True)
    (screens / "01-board.html").write_text("<html></html>", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("generate_batch_tasks", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr("sys.argv", ["x", "--planning-dir", str(planning)])
    assert mod.main() == 0
    prompt = json.loads(capsys.readouterr().out)["tasks"][0]["prompt"]
    for needle in ("Initial state:", "@media", "Per-state content:", "Design extension:", "Design contradiction:"):
        assert needle in prompt, needle
