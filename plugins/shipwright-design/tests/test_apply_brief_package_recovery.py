"""Design takes the Brief package (B3a): reset, foreign-screen and injector edges, driven in-process."""

import sys

import pytest

from .brief_package_helpers import PAGE_A, make_project
from .test_apply_brief_package_inprocess import main_json, tool  # noqa: F401 -- the in-process fixture


@pytest.mark.covers("FR-01.04")
def test_a_foreign_screen_without_its_upload_is_refused_even_when_other_uploads_exist(project, tool, capsys):  # noqa: F811
    main_json(tool, capsys, project)
    designs = project / ".shipwright" / "designs"
    (designs / "uploads" / "02-editor.html").unlink()
    (designs / "screens" / "02-editor.html").write_text("<html>left over from an earlier session</html>", encoding="utf-8")
    (designs / "brief-package-applied.json").unlink()
    code, out = main_json(tool, capsys, project)
    assert code == 1 and [i["code"] for i in out["issues"]] == ["pre_existing_screen"]
    assert not (designs / "uploads" / "02-editor.html").exists()


@pytest.mark.covers("FR-01.04")
def test_an_injection_the_reader_cannot_see_fails_that_screen(project, tool, capsys, monkeypatch):  # noqa: F811
    real = tool._load

    def load(path, name):
        module = real(path, name)
        if "registry" in name:
            module.inject_requirements = lambda data, frs: data  # writes no comment at all
        return module

    monkeypatch.setattr(tool, "_load", load)
    code, out = main_json(tool, capsys, project)
    assert code == 1 and {i["code"] for i in out["issues"]} == {"injection_failed"}


@pytest.mark.covers("FR-01.04")
def test_a_failed_module_load_is_not_left_in_sys_modules(tool, tmp_path):  # noqa: F811
    broken = tmp_path / "broken.py"
    broken.write_text("raise RuntimeError('x')\n", encoding="utf-8")
    with pytest.raises(RuntimeError):
        tool._load(broken, "_t_broken_module")
    assert "_t_broken_module" not in sys.modules


@pytest.mark.covers("FR-01.04")
def test_injection_skips_an_html_tag_inside_a_conditional_comment(tool):  # noqa: F811
    registry = tool._load(tool._HERE.parent / "lib" / "screen_registry.py", "_t_registry_cond")
    page = b'<!--[if IE]><html class="ie"><![endif]--><html lang=en><body></body></html>'
    out = registry.inject_requirements(page, ["FR-01.01"])
    assert out.index(b"<!-- Requirements") > out.index(b"<html lang=en>")
    assert out.count(b"<!-- Requirements") == 1


@pytest.mark.covers("FR-01.04")
def test_a_kept_screen_that_lost_its_ids_is_refused_with_a_remedy(project, tool, capsys):  # noqa: F811
    main_json(tool, capsys, project)
    designs = project / ".shipwright" / "designs"
    (designs / "screens" / "01-notes.html").write_text("<html>retyped, no ids</html>", encoding="utf-8")
    (designs / "brief-package-applied.json").unlink()
    code, out = main_json(tool, capsys, project)
    assert code == 1 and [i["code"] for i in out["issues"]] == ["pre_existing_screen"]
    assert "move that screen away" in out["issues"][0]["message"] and "delete nothing else" in out["issues"][0]["message"]


@pytest.mark.covers("FR-01.04")
def test_an_empty_comment_and_a_leading_bom_do_not_break_injection(tool):  # noqa: F811
    registry = tool._load(tool._HERE.parent / "lib" / "screen_registry.py", "_t_registry_bom")
    out = registry.inject_requirements(b"<!--><html lang=en><body></body></html>", ["FR-01.01"])
    assert out.index(b"<!-- Requirements") > out.index(b"<html lang=en>")
    bom = chr(0xFEFF).encode("utf-8")
    out = registry.inject_requirements(bom + b"<p>fragment</p>", ["FR-01.01"])
    assert out.startswith(bom + b"<!-- Requirements: FR-01.01 -->") and out.count(bom) == 1


@pytest.mark.covers("FR-01.04")
def test_a_pre_existing_differing_guidelines_file_is_kept_and_reported(project, tool, capsys):  # noqa: F811
    guidelines = project / ".shipwright" / "designs" / "visual-guidelines.md"
    guidelines.parent.mkdir(parents=True)
    guidelines.write_text("# mine\n", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 0 and out["kept_existing_differs"] == ["visual-guidelines.md"]
    assert guidelines.read_text(encoding="utf-8") == "# mine\n"
    (project / ".shipwright" / "designs" / "brief-package-applied.json").unlink()
    assert main_json(tool, capsys, project)[1]["kept_existing_differs"] == ["visual-guidelines.md"]


@pytest.mark.covers("FR-01.04")
def test_an_unterminated_comment_hides_a_later_html_tag(tool):  # noqa: F811
    registry = tool._load(tool._HERE.parent / "lib" / "screen_registry.py", "_t_registry_open")
    out = registry.inject_requirements(b"<body><!-- never closed <html class=x>", ["FR-01.01"])
    assert out.startswith(b"<!-- Requirements: FR-01.01 -->")  # the hidden tag was not used


@pytest.mark.covers("FR-01.04")
def test_a_first_apply_lists_material_the_package_did_not_place(project, tool, capsys):  # noqa: F811
    designs = project / ".shipwright" / "designs"
    (designs / "screens").mkdir(parents=True)
    (designs / "screens" / "03-dashboard.html").write_text("<html>mine</html>", encoding="utf-8")
    (designs / "chrome-definition.md").write_text("# chrome\n", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 0 and out["foreign_existing"] == ["screens/03-dashboard.html", "chrome-definition.md"]


@pytest.mark.covers("FR-01.04")
def test_a_minted_fr_that_no_screen_maps_is_listed_as_unmapped(tmp_path, tool, capsys):  # noqa: F811
    root = make_project(tmp_path, [{"id": "notes", "mockup": "01.html", "requirements": ["capture-note"]}], {"01.html": PAGE_A})
    code, out = main_json(tool, capsys, root)
    assert code == 0 and out["unmapped_frs"] == ["FR-01.02", "FR-01.03"]  # informational: the agent stops and reports
