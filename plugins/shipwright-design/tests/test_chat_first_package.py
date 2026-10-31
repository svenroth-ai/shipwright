"""Chat-first Brief package (B3b): chat-map checks, generated flows, the chip rule and the pinned prose."""

import json
import shutil
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from .brief_package_helpers import _GATES, _REPO, _TOOL, PAGE_A, TWO, bdi, bp, make_project, run

FIXTURE = _REPO / "integration-tests" / "fixtures" / "social-engagement"
REFS = _REPO / "plugins" / "shipwright-design" / "skills" / "design" / "references"
NAMES = ("Fetch new matches", "View the board", "Show a thread", "Draft a reply", "Mark a thread as posted", "Set keywords")
SPEC = ("| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
        + "".join(f"| FR-01.{i:02d} | Desk | {n} | Must | The system SHALL x |\n" for i, n in enumerate(NAMES, 1)))


_VERIFY = ("import sys, json; sys.path.insert(0, sys.argv[1]); from pathlib import Path; "
           "from tools.verifiers.brief_chat_checks import check_brief_chat_first_applied as c; "
           "print(json.dumps([[r.name, r.ok, r.detail] for r in c(Path(sys.argv[2]))]))")


def _check():
    """The verifier in its own interpreter: in-process, ``lib`` would be this plugin's lib (ADR-045)."""
    def check(root: Path) -> list:
        proc = subprocess.run([sys.executable, "-c", _VERIFY, str(_REPO / "shared" / "scripts"), str(root)],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return [SimpleNamespace(name=n, ok=ok, detail=d) for n, ok, d in json.loads(proc.stdout)]
    return check


def _project(tmp_path: Path, monkeypatch, edit=None) -> Path:
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    pkg = tmp_path / "brief"
    shutil.copytree(FIXTURE, pkg)
    if edit:
        edit(pkg)
        brief = json.loads((pkg / "brief.json").read_text(encoding="utf-8"))
        brief["package_sha256"] = bp.package_sha256(pkg)
        (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({"profile": "chat-first-json"}), encoding="utf-8")
    bdi.record(tmp_path, "brief")
    spec = tmp_path / ".shipwright" / "planning" / "01-desk" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(SPEC, encoding="utf-8")
    return tmp_path


def _edit_chat_map(change):
    def edit(pkg: Path) -> None:
        path = pkg / "chat-map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return edit


def _refused(tmp_path, monkeypatch, change, needle):
    root = _project(tmp_path, monkeypatch, _edit_chat_map(change))
    code, out = run(_TOOL, root)
    assert code == 1 and not out["ok"], out
    assert any(i["code"] == "bad_chat_map" and needle in i["message"] for i in out["issues"]), out
    assert not (root / ".shipwright" / "designs").exists()  # all checks run before the first write


@pytest.mark.covers("FR-01.04", "FR-01.04/AC14")
def test_a_capability_without_its_pane_state_screen_stops_the_tool(tmp_path, monkeypatch):
    _refused(tmp_path, monkeypatch, lambda d: d["capabilities"][0].update(screen="nowhere"), "pane-state screen")


@pytest.mark.covers("FR-01.04")
def test_a_capability_whose_screen_does_not_list_its_requirement_stops_the_tool(tmp_path, monkeypatch):
    _refused(tmp_path, monkeypatch, lambda d: d["capabilities"][1].update(screen="keywords"), "does not list")


@pytest.mark.covers("FR-01.04")
def test_a_golden_path_step_on_an_unknown_screen_stops_the_tool(tmp_path, monkeypatch):
    _refused(tmp_path, monkeypatch, lambda d: d["golden_paths"][0]["steps"][0].update(screen="nowhere"), "not a screen-map id")


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("change,needle", [
    (lambda d: d.update(version=2), "version must be"),
    (lambda d: d.update(golden_paths=[]), "golden_paths must be"),
    (lambda d: d["capabilities"].append(dict(d["capabilities"][0])), "repeated"),
    (lambda d: d["golden_paths"][0].update(steps=[]), "steps must be"),
])
def test_other_chat_map_defects_are_issues(tmp_path, monkeypatch, change, needle):
    _refused(tmp_path, monkeypatch, change, needle)


@pytest.mark.covers("FR-01.04")
def test_a_chat_map_that_is_not_an_object_is_an_issue(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch, lambda pkg: (pkg / "chat-map.json").write_text("[]", encoding="utf-8"))
    code, out = run(_TOOL, root)
    assert code == 1 and out["issues"][0]["code"] == "bad_chat_map", out


@pytest.mark.covers("FR-01.04")
def test_reentry_reports_the_shape_and_keeps_flow_edits(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert run(_TOOL, root)[0] == 0
    flow = root / ".shipwright" / "designs" / "flows" / "01-triage-a-thread.html"
    flow.write_text("<html><body>edited in review</body></html>", encoding="utf-8")
    code, out = run(_TOOL, root)
    assert code == 0 and out["already_applied"] and out["ux_shape"] == "chat-first" and out["ui_host"] == "served-pane"
    assert "edited in review" in flow.read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.04")
def test_the_verifier_is_red_without_a_flow_or_a_linked_fr(tmp_path, monkeypatch):
    check = _check()
    root = _project(tmp_path, monkeypatch)
    assert run(_TOOL, root)[0] == 0
    assert check(root)[0].ok is True
    designs = root / ".shipwright" / "designs"
    (designs / "flows" / "02-tune-the-keywords.html").unlink()
    red = check(root)[0]
    assert red.ok is False and "flows/02-tune-the-keywords.html is missing" in red.detail
    screen = designs / "screens" / "05-keywords.html"
    screen.write_text(screen.read_text(encoding="utf-8").replace("FR-01.06", "FR-09.99"), encoding="utf-8")
    assert "does not link ['FR-01.06']" in check(root)[0].detail


@pytest.mark.covers("FR-01.04")
def test_a_classic_package_gets_no_flows_and_no_chat_check(tmp_path):
    check = _check()
    root = make_project(tmp_path, [TWO[0]], {"01-notes.html": PAGE_A})
    code, out = run(_TOOL, root)
    assert code == 0 and out["flows"] == [] and out["ux_shape"] == "classic"
    assert check(root) == []


@pytest.mark.covers("FR-01.04")
def test_a_chip_used_as_navigation_turns_the_chrome_gate_red(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert run(_TOOL, root)[0] == 0
    _, out = run(_GATES, root, "--gate", "chrome")
    assert out["success"] is True
    screen = root / ".shipwright" / "designs" / "screens" / "02-thread-detail.html"
    screen.write_text(screen.read_text(encoding="utf-8").replace('class="chip"', 'class="chip nav-item"', 1), encoding="utf-8")
    code, out = run(_GATES, root, "--gate", "chrome")
    assert code == 1 and "chip used as navigation" in out["gates"][0]["problems"][0], out


@pytest.mark.covers("FR-01.04")
def test_the_chat_first_prose_is_pinned():
    text = (REFS / "chat-first.md").read_text(encoding="utf-8")
    for sentence in (
        "Generate NO screen and NO flow by hand.",
        "Skip Step 3.7",
        "you never type an FR id",
        "Never waive an FR, never write a `## Non-UI FRs` entry or an ADR, never edit `brief/`.",
        "STOP and report the issues (a package defect: the fix is a re-approved package, never an edit of `brief/`)",
        "`design.preview-approval` checkpoint is still a human gate; you never answer it.",
    ):
        assert sentence in text, sentence
    layout = (REFS / "snippets-layout.md").read_text(encoding="utf-8")
    assert "## Layout D: Chat + Pane (chat-first)" in layout and "never `nav-item` / `topnav-link`" in layout
    assert "chat-first.md" in (REFS / "step-4-generate-screens.md").read_text(encoding="utf-8")
    assert "chat-first.md" in (REFS / "upload-mode.md").read_text(encoding="utf-8")
    skill = (REFS.parent / "SKILL.md").read_text(encoding="utf-8")
    assert "references/chat-first.md" in skill and len(skill.splitlines()) <= 300


@pytest.mark.covers("FR-01.04")
def test_reentry_with_a_deleted_flow_is_applied_files_missing_and_repairable(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert run(_TOOL, root)[0] == 0
    designs = root / ".shipwright" / "designs"
    (designs / "flows" / "02-tune-the-keywords.html").unlink()
    code, out = run(_TOOL, root)
    assert code == 1 and out["issues"][0]["code"] == "applied_files_missing", out
    (designs / "brief-package-applied.json").unlink()  # the documented repair: writes only what is missing
    code, out = run(_TOOL, root)
    assert code == 0 and (designs / "flows" / "02-tune-the-keywords.html").is_file(), out


@pytest.mark.covers("FR-01.04")
def test_a_flow_that_was_already_there_and_differs_is_reported(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    flows = root / ".shipwright" / "designs" / "flows"
    flows.mkdir(parents=True)
    (flows / "01-triage-a-thread.html").write_text("<html><body>old run</body></html>", encoding="utf-8")
    code, out = run(_TOOL, root)
    assert code == 0, out
    assert "flows/01-triage-a-thread.html" in out["kept_existing_differs"]


@pytest.mark.covers("FR-01.04")
def test_the_generated_flow_inlines_the_approved_pane_mockup(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    assert run(_TOOL, root)[0] == 0
    flow = (root / ".shipwright" / "designs" / "flows" / "01-triage-a-thread.html").read_text(encoding="utf-8")
    assert flow.count("<iframe sandbox") == 4 and "Added 3 new threads" in flow  # one frame per step, the mockup's own text
