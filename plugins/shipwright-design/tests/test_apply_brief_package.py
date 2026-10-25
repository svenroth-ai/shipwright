"""Design takes the Brief package (B3a): the tool and the real gates, run as subprocesses."""

import subprocess
import sys

import pytest

from .brief_package_helpers import (
    GOOD_GUIDELINES, _GATES, _REPO, _TOOL, PAGE_A, PAGE_B, TWO, make_project, run,
)



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
def test_a_changed_package_is_refused_and_writes_nothing(project):
    (project / "brief" / "mockups" / "01-notes.html").write_text("tampered", encoding="utf-8")
    code, out = run(_TOOL, project)
    assert code == 3 and out["refused"] and out["code"] == "hash_mismatch"
    assert not (project / ".shipwright" / "designs").exists()


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
