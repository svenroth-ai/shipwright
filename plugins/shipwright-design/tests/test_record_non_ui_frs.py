"""record-non-ui-frs: an autonomous run records the brief's own non-UI capabilities without asking.

The package says which capabilities have no screen with an explicit `UI: none` line in their brief.md section.
A capability without it (a Source line naming no Mockup is not enough), or whose section names a Mockup that was never mapped, stays a question.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from .brief_package_helpers import _GATES, _REPO, _TOOL, PAGE_A, bdi, bp, make_project, run

_SCRIPT = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks" / "record-non-ui-frs.py"
_spec = importlib.util.spec_from_file_location("_test_record_non_ui", _SCRIPT)
rec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rec)

pytestmark = pytest.mark.covers("FR-01.04")

BRIEF = (
    "# Notes\n\n"
    "## Capture note\nRequirement: x\nSource: REA; Mockup `01-notes.html`.\n\n"
    "## List notes\nRequirement: y\nUI: none\nSource: Interview (backend store only).\n\n"
    "## Edit note\nRequirement: z\nSource: REA; Mockup `02-editor.html`.\n"
)
MANIFEST = (
    "# Design Manifest\n\n## Screens\n\n| # | Screen | File | Status | Linked FRs |\n|---|---|---|---|---|\n"
    "| 01 | notes | screens/01-notes.html | complete | FR-01.01 |\n\n## Non-UI FRs\n\n"
    "> placeholder text\n\n- FR-XX.YY — ADR-NNN (background job) — replace with a real FR id\n\n## User Flows\n\nnone\n"
)


def rebuild(root: Path, brief_md: str):
    pkg = root / "brief"
    (pkg / "brief.md").write_text(brief_md, encoding="utf-8")
    brief = json.loads((pkg / "brief.json").read_text(encoding="utf-8"))
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    cfg_path = root / "shipwright_run_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg.pop("brief_package", None)
    cfg.pop("brief_dir", None)  # the recorded hash is of the old package: record the edited one afresh
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    bdi.record(root, "brief")


def applied_project(tmp_path, brief_md):
    screens = [{"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note"]}]
    root = make_project(tmp_path, screens, {"01-notes.html": PAGE_A})
    rebuild(root, brief_md)
    code, out = run(_TOOL, root)
    assert code == 0 and out["unmapped_frs"] == ["FR-01.02", "FR-01.03"], out
    (root / ".shipwright" / "designs" / "design-manifest.md").write_text(MANIFEST, encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _in_process_adr(monkeypatch):
    """The in-process tests cannot run the real decision-log writer (it binds the shared ``lib``, ADR-045); the subprocess tests do."""
    monkeypatch.setattr(rec, "_log_decision", lambda _root, _frs: "ADR-900")
    real_load = rec._load

    def load(path, name):
        if name == "_shipwright_design_apply_brief_package":  # apply() imports the shared ``lib`` too: stub its already-applied verdict
            return types.SimpleNamespace(apply=lambda root: {"ok": True, "already_applied": True, "unmapped_frs": ["FR-01.02", "FR-01.03"]})
        if name == "_shipwright_design_brief_design_plan":  # same collision (the grill tools bind ``tools``)
            return types.SimpleNamespace(fr_ids_by_slug=lambda root: {"capture-note": ["FR-01.01"], "list-notes": ["FR-01.02"], "edit-note": ["FR-01.03"]})
        return real_load(path, name)
    monkeypatch.setattr(rec, "_load", load)


@pytest.fixture
def project(tmp_path):
    return applied_project(tmp_path, BRIEF)


def manifest(root):
    return (root / ".shipwright" / "designs" / "design-manifest.md").read_text(encoding="utf-8")


def test_the_brief_declared_non_ui_fr_is_recorded_and_the_other_stays_a_question(project):
    code, out = run(_SCRIPT, project)
    assert code == 1 and out["action"] == "recorded" and out["autonomous"] is True
    assert [r["fr"] for r in out["recorded"]] == ["FR-01.02"]
    assert [a["fr"] for a in out["ask"]] == ["FR-01.03"] and "refers to a mockup" in out["ask"][0]["why"]
    text = manifest(project)
    assert f"- FR-01.02 — {out['adr']} (no screen:" in text and "replace with a real FR id" not in text
    assert text.index("FR-01.02 —") < text.index("## User Flows")
    log = (project / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    assert f"### {out['adr']}:" in log and "FR-01.02" in log


def test_the_real_baseline_brief_has_every_unmapped_capability_marked_and_none_contradicted():
    fixture = _REPO / "integration-tests" / "fixtures" / "social-engagement-baseline"
    sections = rec.brief_sections((fixture / "brief.md").read_text(encoding="utf-8-sig"))
    mapped = {r for s in json.loads((fixture / "screen-map.json").read_text(encoding="utf-8"))["screens"] for r in s["requirements"]}
    caps = {slug: body for slug, body in sections.items() if "Requirement:" in body}
    unmapped = {slug: body for slug, body in caps.items() if slug not in mapped}
    assert len(unmapped) == 10
    assert all(rec.non_ui_verdict(body)[0] for body in unmapped.values()), {s: rec.non_ui_verdict(b) for s, b in unmapped.items()}
    assert not any(rec.non_ui_verdict(body)[0] for slug, body in caps.items() if slug in mapped)  # a screen-mapped capability is never non-UI


def test_the_decision_log_entry_states_the_explicit_marker_rule(project):
    run(_SCRIPT, project)
    log = (project / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    assert "states `UI: none` on a line of its own" in log and "names no mockup" not in log


@pytest.mark.parametrize("line", ["Screen: none", "UI: no", "screen: no", "UI:\n\nnone"])
def test_only_the_documented_marker_counts(line):
    assert rec.non_ui_verdict(f"Requirement: x\n{line}\nSource: REA.\n")[0] is False


def test_with_the_open_one_resolved_by_a_note_everything_is_recorded_and_the_gate_goes_green(tmp_path):
    project = applied_project(tmp_path, BRIEF.replace("Source: REA; Mockup `02-editor.html`.", "UI: none\nSource: REA."))
    code, out = run(_SCRIPT, project)
    assert code == 0, out
    assert [r["fr"] for r in out["recorded"]] == ["FR-01.02", "FR-01.03"] and out["ask"] == []
    _, gates = run(_GATES, project, "--gate", "fr-coverage")
    assert next(g for g in gates["gates"] if g["gate"] == "fr-coverage")["ok"], gates


def test_a_second_run_changes_nothing(project):
    run(_SCRIPT, project)
    before, log = manifest(project), (project / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    code, out = run(_SCRIPT, project)
    assert out["recorded"] == [] and out["adr"] is None and manifest(project) == before
    assert (project / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8") == log


def test_an_interactive_run_is_not_touched(project):
    cfg = json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    cfg.pop("brief_package")
    (project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    code, out = run(_SCRIPT, project)
    assert code == 0 and out == {"autonomous": False, "action": "ask", "recorded": [], "ask": [], "adr": None}
    assert manifest(project) == MANIFEST and not (project / ".shipwright" / "agent_docs" / "decision_log.md").exists()


def test_it_cannot_run_before_the_package_is_applied_or_the_manifest_exists(tmp_path):
    root = make_project(tmp_path, [{"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note"]}], {"01-notes.html": PAGE_A})
    code, out = run(_SCRIPT, root)
    assert code == 2 and "must have run first" in out["error"]


@pytest.mark.parametrize("section,expected", [
    (None, False),
    ("Requirement: x\nSource: REA; Mockup `01.html`.\n", False),
    ("Requirement: x\nSource: Interview.\n", False),  # a Source line without a mockup is not a statement that there is no screen
    ("Requirement: x\n- UI: none\n", True),
    ("Requirement: x\n", False),
    ("Requirement: x\nUI: none\nSource: REA; Mockup `01-home.html`.\n", False),  # contradicts itself: a person decides
    ("Requirement: Store screen capture events\nUI: none\n", True),  # prose saying "screen" does not veto an explicit UI: none
])
def test_non_ui_verdict(section, expected):
    assert rec.non_ui_verdict(section)[0] is expected


def test_brief_sections_are_keyed_by_the_fr_slug():
    secs = rec.brief_sections(BRIEF)
    assert set(secs) == {"capture-note", "list-notes", "edit-note"} and "backend store" in secs["list-notes"]


def test_slugify_parity_with_the_shared_one():
    import subprocess
    import sys
    names = ["Use the board on a phone", "Store the agent's drafts as a run", "  Mixed -- CASE & 9 symbols! "]
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from tools.grill_trace_fr_coverage import slugify; "
            "import json; print(json.dumps([slugify(n) for n in json.loads(sys.argv[2])]))")
    out = subprocess.run([sys.executable, "-c", code, str(_REPO / "shared" / "scripts"), json.dumps(names)],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert json.loads(out) == [rec.slugify(n) for n in names]


def test_an_fr_listed_without_an_adr_is_still_recorded(project):
    text = manifest(project).replace("- FR-XX.YY — ADR-NNN (background job) — replace with a real FR id", "- FR-01.02 (listed, but no ADR: fr-coverage ignores it)")
    (project / ".shipwright" / "designs" / "design-manifest.md").write_text(text, encoding="utf-8")
    _, out = run(_SCRIPT, project)
    assert [r["fr"] for r in out["recorded"]] == ["FR-01.02"]


@pytest.mark.parametrize("section", [
    "Requirement: x\nSource: Interview.\nMockup: 05-settings.html\n",
    "Requirement: x\nSource: Interview; wireframe 05.\n",
    "Requirement: x\nSource: REA; screen 05.\n",
])
def test_a_screen_reference_anywhere_or_a_loose_ui_none_is_not_a_non_ui_note(section):
    assert rec.non_ui_verdict(section)[0] is False


def test_ui_none_must_be_the_whole_line():
    assert rec._UI_NONE_RE.search("UI: no changes to the header, but a new pane") is None
    assert rec._UI_NONE_RE.search("- UI: none.") is not None


# In-process twins of the subprocess tests above: diff coverage cannot see a child process.

def test_in_process_recorded_then_second_run_is_a_no_op(project):
    out, code = rec.run(project)
    assert code == 1 and out["action"] == "recorded" and [r["fr"] for r in out["recorded"]] == ["FR-01.02"]
    assert f"- FR-01.02 — {out['adr']} (no screen:" in manifest(project)
    before = manifest(project)
    out2, code2 = rec.run(project)
    assert out2["recorded"] == [] and out2["adr"] is None and manifest(project) == before and code2 == 1


def test_in_process_interactive_run_is_not_touched(project):
    cfg = json.loads((project / "shipwright_run_config.json").read_text(encoding="utf-8"))
    cfg.pop("brief_package")
    (project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    out, code = rec.run(project)
    assert code == 0 and out["autonomous"] is False and manifest(project) == MANIFEST


def test_in_process_before_apply_is_an_error(tmp_path):
    root = make_project(tmp_path, [{"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note"]}], {"01-notes.html": PAGE_A})
    out, code = rec.run(root)
    assert code == 2 and "must have run first" in out["error"]


def test_an_unwritable_manifest_stops_before_any_adr_exists(project, monkeypatch):
    def refuse(*_a, **_k):
        raise PermissionError("read-only")
    monkeypatch.setattr(rec, "open", refuse, raising=False)
    out, code = rec.run(project)
    assert code == 2 and "cannot be written" in out["error"]
    assert not (project / ".shipwright" / "agent_docs" / "decision_log.md").exists()


def test_main_prints_the_result_and_returns_the_exit_code(project, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["record-non-ui-frs.py", "--project-root", str(project)])
    assert rec.main() == 1
    assert json.loads(capsys.readouterr().out)["action"] == "recorded"
