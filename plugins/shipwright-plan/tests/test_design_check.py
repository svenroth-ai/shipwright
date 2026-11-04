"""Autonomous design-contradiction resolution: the Plan-phase check and the prompt/Build wiring."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests._check_plan_gates_support import WELL_FORMED, _problems, run_gates

pytestmark = pytest.mark.covers("FR-01.05/AC05")

PLUGIN = Path(__file__).resolve().parent.parent
CLI = str(PLUGIN / "scripts" / "checks" / "check-design-contradictions.py")
BUILD = PLUGIN.parent / "shipwright-build"

SCREEN = (
    '<html><style>@media (max-width: 900px){.x{}}</style><body>'
    '<button aria-label="Previous thread">&lsaquo;</button><h1>Thread board</h1>'
    '<p>Reply drafted</p></body></html>'
)
REF = ("## Design Reference\n- Screen mockup: .shipwright/designs/screens/07-picker.html\n"
       "- Initial state: none\n")


def _section(body):
    return WELL_FORMED.format(name="01-auth", frs="FR-01.01") + "\n" + REF + body


@pytest.fixture
def proj(planning, tmp_path):
    s = tmp_path / ".shipwright" / "designs" / "screens"
    s.mkdir(parents=True)
    (s / "07-picker.html").write_text(SCREEN, encoding="utf-8")
    return tmp_path


def _mode(root, **cfg):
    (root / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _write(planning, body):
    (planning / "sections" / "01-auth.md").write_text(_section(body), encoding="utf-8")


def _cli(planning, root, *extra):
    r = subprocess.run([sys.executable, CLI, "--planning-dir", str(planning), "--project-root", str(root), *extra],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


def test_previous_next_thread_wording_mismatch_fails_autonomous(planning, proj):
    _mode(proj, brief_package={"approved_by": "x"}, autonomy="guided")
    _write(planning, '- the picker buttons read "Thread bord"\n')
    code, out = _cli(planning, proj)
    assert code == 1 and out["autonomous"]
    assert any("text_mismatch" in p for p in out["problems"])


def test_visible_label_vs_aria_only_symbol_is_flagged(planning, proj):
    _mode(proj, autonomy="autonomous")
    _write(planning, '- the button text shows "Previous thread"\n')
    code, out = _cli(planning, proj)
    assert code == 1 and any("visible_vs_attribute" in p for p in out["problems"])


def test_recorded_design_decision_resolves_it(planning, proj):
    _mode(proj, autonomy="autonomous")
    _write(planning, '- the picker buttons read "Thread bord"\n'
                     '- Design decision: "Thread bord" -> "Thread board", screen wins\n')
    code, out = _cli(planning, proj)
    assert code == 0 and out["problems"] == []


def test_breakpoint_mismatch(planning, proj):
    _mode(proj, autonomy="unattended")
    _write(planning, "- the list switches to a picker at the 768px breakpoint\n")
    code, out = _cli(planning, proj)
    assert code == 1 and any("breakpoint_mismatch" in p and "900px" in p for p in out["problems"])
    _write(planning, "- the list switches to a picker at the 900px breakpoint\n")
    assert _cli(planning, proj)[0] == 0


def test_harmless_additions_do_not_stop(planning, proj):
    _mode(proj, autonomy="autonomous")
    _write(planning, '- add an "Export CSV" button and show "Loading spinner shown"\n'
                     "```\nexpect('Whatever text')\n```\n- an unrelated 500px wrapper note\n")
    assert _cli(planning, proj)[0] == 0


def test_undecidable_contradiction_remains_a_stop_for_build(planning, proj):
    _mode(proj, autonomy="autonomous")
    _write(planning, "- Design contradiction: brief says 4 columns vs screen shows 3; rule cannot decide\n")
    assert _cli(planning, proj)[0] == 0  # stays a Build question, not a Plan failure
    _write(planning, "- Design contradiction: brief says 4 columns vs screen shows 3\n")
    code, out = _cli(planning, proj)
    assert code == 1 and any("unresolved_contradiction" in p for p in out["problems"])


def test_interactive_run_is_unchanged(planning, proj, no_e2e_plugin_root):
    _mode(proj, autonomy="guided")
    _write(planning, '- the picker buttons read "Thread bord"\n- Design contradiction: a vs b\n')
    code, out = _cli(planning, proj)
    assert code == 0 and out["problems"] == [] and out["notes"]
    _, gate = run_gates(planning, "sections", project_root=proj, plugin_root=no_e2e_plugin_root)
    assert not any("text_mismatch" in p for p in _problems(gate, "sections"))


def test_gate_sections_fails_autonomous(planning, proj, no_e2e_plugin_root):
    _mode(proj, brief_package={"k": 1})
    _write(planning, '- the picker buttons read "Thread bord"\n')
    _, gate = run_gates(planning, "sections", project_root=proj, plugin_root=no_e2e_plugin_root)
    assert any("text_mismatch" in p for p in _problems(gate, "sections"))


def test_record_decisions_logs_once(planning, proj):
    _mode(proj, autonomy="autonomous")
    _write(planning, "- Design decision: avatars -> two letters, screen wins\n")
    log = proj / ".shipwright" / "agent_docs" / "decision_log.md"
    _cli(planning, proj, "--record-decisions")
    _cli(planning, proj, "--record-decisions")
    assert log.read_text(encoding="utf-8").count("Plan Design Decision") == 1


def test_prompts_and_build_accept_recorded_decision():
    w = " ".join((PLUGIN / "agents" / "section-writer.md").read_text(encoding="utf-8").split())
    assert "Design decision:" in w and "approved screen wins" in w
    assert "rule cannot decide" in w and "interactive run" in w
    sk = (BUILD / "skills" / "build" / "SKILL.md").read_text(encoding="utf-8")
    assert "recorded `Design decision:` line in the section is resolved" in sk
    rev = (BUILD / "agents" / "spec-reviewer.md").read_text(encoding="utf-8")
    assert "Design decision" in rev and "unresolved `Design contradiction:`" in rev


def _load_cli():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_design_contradictions", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_in_process_and_failed_log_write_is_a_problem(planning, proj, monkeypatch, capsys):
    mod = _load_cli()
    _mode(proj, autonomy="autonomous")
    _write(planning, "- Design decision: avatars -> two letters, screen wins\n")

    class R:
        returncode = 7

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr("sys.argv", ["x", "--planning-dir", str(planning), "--project-root", str(proj),
                                     "--record-decisions"])
    assert mod.main() == 1
    out = json.loads(capsys.readouterr().out)
    assert any("decision not logged" in p for p in out["problems"])
