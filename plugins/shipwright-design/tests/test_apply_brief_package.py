"""Design takes the Brief package (B3a): uploads stay byte-identical, screens carry minted FR ids."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECKS = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks"
_TOOL = _CHECKS / "apply-brief-package.py"
_GATES = _CHECKS / "check-design-gates.py"
_BDI_PATH = _REPO / "shared" / "scripts" / "lib" / "brief_dir_intake.py"

_spec = importlib.util.spec_from_file_location("_test_b3a_bdi", _BDI_PATH)
bdi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdi)
bp = bdi._lib("brief_package")

GOOD_GUIDELINES = (
    "# Visual Guidelines\n\n## Typography\n- Inter\n\n## Colors\n| Role | Value |\n|---|---|\n"
    "| Background | #fff |\n\n## Spacing & Layout\n- 4px\n"
)
SPEC = (
    "| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
    "| FR-01.01 | Notes | Capture note | Must | The system SHALL capture a note |\n"
    "| FR-01.02 | Notes | List notes | Must | The system SHALL list notes |\n"
    "| FR-01.03 | Notes | Edit note | Must | The system SHALL edit a note |\n"
)
PAGE_A = "<!doctype html>\r\n<html lang=\"en\">\r\n<head><title>A</title></head><body><h1>A</h1></body></html>\r\n"
PAGE_B = "<!doctype html>\n<html><head><title>B</title></head><body><h1>B</h1></body></html>\n"


def make_project(root: Path, screens: list, pages: dict, guidelines: str = GOOD_GUIDELINES, design_system: str = "visual-guidelines.md") -> Path:
    pkg = root / "brief"
    (pkg / "mockups").mkdir(parents=True)
    for name, text in pages.items():
        (pkg / "mockups" / name).parent.mkdir(parents=True, exist_ok=True)
        (pkg / "mockups" / name).write_bytes(text.encode("utf-8"))
    (pkg / "brief.md").write_text("# Notes\n\n## Capture note\nx\n\n## List notes\ny\n\n## Edit note\nz\n", encoding="utf-8")
    (pkg / "scope.md").write_text("# Scope\n", encoding="utf-8")
    (pkg / "visual-guidelines.md").write_text(guidelines, encoding="utf-8")
    (pkg / "screen-map.json").write_text(json.dumps({"screens": screens}), encoding="utf-8")
    brief = {
        "version": bp.BRIEF_VERSION, "profile": "vite-hono", "deploy_target": "none", "autonomy": "guided",
        "ui_host": "web", "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
        "design_system": design_system, "brief_dir": "brief", "env_preflight": [],
        "allow_parallel_builders": False, "approved_by": "person:test", "approved_at": "2026-10-25T00:00:00Z",
    }
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(json.dumps({"profile": "vite-hono"}), encoding="utf-8")
    bdi.record(root, "brief")
    spec_dir = root / ".shipwright" / "planning" / "01-notes"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC, encoding="utf-8")
    return root


def run(script: Path, root: Path, *extra: str):
    proc = subprocess.run([sys.executable, str(script), "--project-root", str(root), *extra],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, json.loads(proc.stdout)


TWO = [
    {"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note", "list-notes"]},
    {"id": "editor", "mockup": "02-editor.html", "requirements": ["edit-note"]},
]


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path, TWO, {"01-notes.html": PAGE_A, "02-editor.html": PAGE_B})


@pytest.mark.covers("FR-01.04")
def test_uploads_are_byte_identical_and_screens_carry_minted_frs(project):
    code, out = run(_TOOL, project)
    assert code == 0 and out["ok"], out
    designs = project / ".shipwright" / "designs"
    assert (designs / "uploads" / "01-notes.html").read_bytes() == PAGE_A.encode()
    assert (designs / "uploads" / "02-editor.html").read_bytes() == PAGE_B.encode()
    a = (designs / "screens" / "01-notes.html").read_bytes()
    assert b"<!-- Requirements: FR-01.01, FR-01.02 -->" in a
    assert b"\r\n<!-- Requirements" in a  # the CRLF page keeps its newline style
    assert a.startswith(b"<!doctype html>") and b"<h1>A</h1>" in a
    assert b"<!-- Requirements: FR-01.03 -->" in (designs / "screens" / "02-editor.html").read_bytes()
    assert {s["frs"][0] for s in out["screens"]} == {"FR-01.01", "FR-01.03"}


@pytest.mark.covers("FR-01.04")
def test_gates_pass_once_a_flow_is_added(project):
    run(_TOOL, project)
    flows = project / ".shipwright" / "designs" / "flows"
    flows.mkdir()
    (flows / "main.html").write_text("<html><body>flow</body></html>", encoding="utf-8")
    _, out = run(_GATES, project, "--gate", "all")
    failed = {g["gate"]: g["problems"] for g in out["gates"] if not g["ok"] and g["gate"] != "boundary"}
    assert not failed, failed


@pytest.mark.covers("FR-01.04")
def test_flows_gate_still_demands_a_flow_for_two_screens(project):
    run(_TOOL, project)
    _, out = run(_GATES, project, "--gate", "flows")
    assert out["failed"] == ["flows"]


@pytest.mark.covers("FR-01.04")
def test_manifest_and_visual_guidelines_are_written(project):
    run(_TOOL, project)
    designs = project / ".shipwright" / "designs"
    manifest = (designs / "design-manifest.md").read_text(encoding="utf-8")
    assert "screens/01-notes.html" in manifest and "FR-01.01, FR-01.02" in manifest
    assert (designs / "visual-guidelines.md").read_text(encoding="utf-8") == GOOD_GUIDELINES
    _, out = run(_GATES, project, "--gate", "fr-coverage")
    assert out["success"], out


@pytest.mark.covers("FR-01.04")
def test_rerun_is_idempotent(project):
    run(_TOOL, project)
    code, out = run(_TOOL, project)
    assert code == 0 and out["ok"]


@pytest.mark.covers("FR-01.04")
def test_a_changed_package_is_refused_and_writes_nothing(project):
    (project / "brief" / "mockups" / "01-notes.html").write_text("tampered", encoding="utf-8")
    code, out = run(_TOOL, project)
    assert code == 3 and out["refused"] and out["code"] == "hash_mismatch"
    assert not (project / ".shipwright" / "designs").exists()


@pytest.mark.covers("FR-01.04")
def test_no_recorded_package_is_refused(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    code, out = run(_TOOL, tmp_path)
    assert code == 3 and out["code"] == "no_package"


@pytest.mark.covers("FR-01.04")
def test_a_requirement_without_an_fr_row_stops_everything(tmp_path):
    screens = [{"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note", "share-note"]}]
    root = make_project(tmp_path, screens, {"01-notes.html": PAGE_A})
    code, out = run(_TOOL, root)
    assert code == 1 and not out["ok"]
    assert any("share-note" in i["message"] for i in out["issues"])
    assert not (root / ".shipwright" / "designs").exists()


@pytest.mark.covers("FR-01.04")
def test_a_screen_without_requirements_or_a_non_html_mockup_is_refused(tmp_path):
    screens = [{"id": "notes", "mockup": "01-notes.png", "requirements": []}]
    root = make_project(tmp_path, screens, {"01-notes.png": "x"})
    code, out = run(_TOOL, root)
    assert code == 1
    messages = " ".join(i["message"] for i in out["issues"])
    assert "not an .html" in messages and "no requirements" in messages


@pytest.mark.covers("FR-01.04")
def test_a_differing_existing_screen_is_never_overwritten(project):
    screens = project / ".shipwright" / "designs" / "screens"
    screens.mkdir(parents=True)
    (screens / "01-notes.html").write_text("hand edited", encoding="utf-8")
    code, out = run(_TOOL, project)
    assert code == 1 and out["issues"][0]["code"] == "exists_differs"
    assert (screens / "01-notes.html").read_text(encoding="utf-8") == "hand edited"
    assert not (project / ".shipwright" / "designs" / "uploads").exists()


@pytest.mark.covers("FR-01.04")
def test_injection_replaces_an_old_comment_and_handles_a_bare_fragment():
    from screen_registry import inject_requirements

    old = b"<html>\n<!-- Requirements: FR-09.09 -->\n<body></body></html>\n"
    new = inject_requirements(old, ["FR-01.01"])
    assert new.count(b"Requirements:") == 1 and b"FR-09.09" not in new
    assert inject_requirements(b"<p>x</p>", ["FR-01.01"]).startswith(b"<!-- Requirements: FR-01.01 -->")


@pytest.mark.covers("FR-01.04")
def test_an_ambiguous_slug_and_a_path_like_mockup_name_are_refused(tmp_path):
    screens = [{"id": "notes", "mockup": "sub/01.html", "requirements": ["capture-note"]},
               {"id": "more", "mockup": "02.html", "requirements": ["capture-note"]}]
    root = make_project(tmp_path, screens, {"sub/01.html": PAGE_A, "02.html": PAGE_B})
    spec = root / ".shipwright" / "planning" / "02-more" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("| FR-02.01 | Notes | Capture Note | Must | dup |\n", encoding="utf-8")
    code, out = run(_TOOL, root)
    messages = " ".join(i["message"] for i in out["issues"])
    assert code == 1 and "plain file name" in messages and "ambiguous" in messages
    assert not (root / ".shipwright" / "designs").exists()


@pytest.mark.covers("FR-01.04")
def test_a_rerun_completes_a_partially_applied_package(project):
    run(_TOOL, project)
    designs = project / ".shipwright" / "designs"
    (designs / "screens" / "02-editor.html").unlink()
    (designs / "brief-package-applied.json").unlink()  # the apply never finished: no marker
    code, out = run(_TOOL, project)
    assert code == 0 and (project / ".shipwright" / "designs" / "screens" / "02-editor.html").is_file()


@pytest.mark.covers("FR-01.04")
def test_old_comments_are_all_replaced_even_with_a_gt_inside():
    from screen_registry import inject_requirements

    old = b"<html><!-- Requirements: FR-09.01 (a > b) --><body><!-- Requirements: FR-09.02 --></body></html>"
    new = inject_requirements(old, ["FR-01.01"])
    assert new.count(b"Requirements:") == 1 and b"FR-09" not in new and b"(a > b)" not in new


@pytest.mark.covers("FR-01.04")
def test_duplicate_mockup_and_differing_guidelines_are_refused(tmp_path):
    twice = [{"id": "x", "mockup": "01.html", "requirements": ["capture-note"]},
             {"id": "y", "mockup": "01.html", "requirements": ["list-notes"]}]
    root = make_project(tmp_path / "b", twice, {"01.html": PAGE_A})
    code, out = run(_TOOL, root)
    assert code == 1 and "used by two screens" in out["issues"][0]["message"]
    root = make_project(tmp_path / "c", TWO, {"01-notes.html": PAGE_A, "02-editor.html": PAGE_B})
    designs = root / ".shipwright" / "designs"
    designs.mkdir(parents=True)
    (designs / "visual-guidelines.md").write_text("# other", encoding="utf-8")
    code, out = run(_TOOL, root)
    assert code == 1 and out["issues"][0]["screen"] == "visual-guidelines.md"
    assert not (designs / "screens").exists()


@pytest.mark.covers("FR-01.04")
def test_an_edited_screen_map_is_refused_by_the_hash_before_it_is_read(tmp_path):
    root = make_project(tmp_path, TWO, {"01-notes.html": PAGE_A, "02-editor.html": PAGE_B})
    (root / "brief" / "screen-map.json").write_text("{", encoding="utf-8")
    code, out = run(_TOOL, root)
    assert code == 3 and out["refused"]  # the hash catches the edit first


_SKILL = _REPO / "plugins" / "shipwright-design" / "skills" / "design" / "SKILL.md"


@pytest.mark.covers("FR-01.04")
def test_skill_routes_a_recorded_brief_package_before_a_new_design_session():
    text = _SKILL.read_text(encoding="utf-8")
    brief = text.index("**Brief package** (`shipwright_run_config.json` records `brief_dir`")
    new_session = text.index("**New Design Session**")
    upload = text.index("**Upload Integration**")
    assert brief < new_session < upload  # evaluated first, not nested under --upload
    section = text[brief:new_session]
    assert "apply-brief-package.py" in section and "neither `--upload` nor files" in section


@pytest.mark.covers("FR-01.04")
def test_the_registry_check_accepts_the_tools_manifest(project):
    run(_TOOL, project)
    code = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]);"
        "from tools.verifiers.design_checks import check_design_manifest_screens_exist as c;"
        "r = c(Path(sys.argv[2])); print(r.detail); sys.exit(1 if r.is_failure else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code, str(_REPO / "shared" / "scripts"), str(project)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.fixture
def tool():
    """The hyphenated script loaded in-process (diff coverage sees it). Its shared tools imports
    bind the shared lib package, so the plugin's own lib and tools modules are set aside meanwhile."""
    def is_pkg(n):
        return n in ("lib", "tools") or n.startswith(("lib.", "tools."))

    saved_path = list(sys.path)
    aside = {n: sys.modules.pop(n) for n in [n for n in sys.modules if is_pkg(n)]}
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("_t_apply_brief_package", _TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n in [n for n in sys.modules if is_pkg(n)]:
            del sys.modules[n]
        sys.modules.update(aside)
        sys.path[:] = saved_path


def main_json(tool, capsys, project):
    code = tool.main(["--project-root", str(project)])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.covers("FR-01.04")
def test_in_process_apply_then_reentry_keeps_review_loop_edits(project, tool, capsys):
    code, out = main_json(tool, capsys, project)
    assert code == 0 and out["ok"] and "already_applied" not in out
    designs = project / ".shipwright" / "designs"
    (designs / "screens" / "01-notes.html").write_text("edited in the review loop", encoding="utf-8")
    (designs / "visual-guidelines.md").write_text("# edited", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 0 and out["already_applied"] is True
    assert (designs / "screens" / "01-notes.html").read_text(encoding="utf-8") == "edited in the review loop"
    assert (designs / "visual-guidelines.md").read_text(encoding="utf-8") == "# edited"


@pytest.mark.covers("FR-01.04")
def test_in_process_a_changed_package_after_apply_is_refused(project, tool, capsys):
    main_json(tool, capsys, project)
    (project / "brief" / "mockups" / "01-notes.html").write_text("tampered", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 3 and out["code"] == "hash_mismatch"


@pytest.mark.covers("FR-01.04")
def test_in_process_a_different_applied_hash_is_not_silently_reapplied(project, tool, capsys):
    main_json(tool, capsys, project)
    marker = project / ".shipwright" / "designs" / "brief-package-applied.json"
    marker.write_text(json.dumps({"package_sha256": "0" * 64}), encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "package_changed_since_apply"


@pytest.mark.covers("FR-01.04")
def test_in_process_content_issue_and_refusal_exit_codes(tmp_path, tool, capsys):
    screens = [{"id": "notes", "mockup": "01-notes.html", "requirements": ["share-note"]}]
    root = make_project(tmp_path / "a", screens, {"01-notes.html": PAGE_A})
    code, out = main_json(tool, capsys, root)
    assert code == 1 and "share-note" in out["issues"][0]["message"]
    bare = tmp_path / "b"
    bare.mkdir()
    (bare / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    code, out = main_json(tool, capsys, bare)
    assert code == 3 and out["code"] == "no_package"


@pytest.mark.covers("FR-01.04")
def test_in_process_malformed_entries_of_a_hash_valid_package_are_issues(tmp_path, tool, capsys):
    screens = [{"id": "a", "mockup": "01.html", "requirements": "capture-note"},
               {"id": "b", "mockup": "02.html", "requirements": ["capture-note"]},
               {"id": "c", "mockup": "02.html", "requirements": ["list-notes"]}]
    root = make_project(tmp_path, screens, {"01.html": PAGE_A, "02.html": PAGE_B})
    code, out = main_json(tool, capsys, root)
    messages = " ".join(i["message"] for i in out["issues"])
    assert code == 1 and "list of capability slugs" in messages and "used by two screens" in messages
    assert not (root / ".shipwright" / "designs").exists()


@pytest.mark.covers("FR-01.04")
def test_in_process_an_unreadable_screen_map_is_a_json_issue(project, tool, capsys, monkeypatch):
    real = Path.read_text

    def fail(self, *a, **k):
        if self.name == "screen-map.json":
            raise ValueError("not json")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", fail)
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "unreadable_package"


@pytest.mark.covers("FR-01.04")
def test_in_process_a_marker_that_is_not_a_json_object_is_an_issue(project, tool, capsys):
    main_json(tool, capsys, project)
    (project / ".shipwright" / "designs" / "brief-package-applied.json").write_text("[]", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "bad_marker"
