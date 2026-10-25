"""Design takes the Brief package (B3a): the script driven in-process, so diff coverage sees it."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from .brief_package_helpers import _REPO, _TOOL, PAGE_A, PAGE_B, make_project


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
    assert not (root / ".shipwright" / "designs").exists()  # a content issue writes nothing
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



@pytest.mark.covers("FR-01.04")
def test_in_process_a_marker_with_invalid_json_is_an_issue(project, tool, capsys):
    main_json(tool, capsys, project)
    (project / ".shipwright" / "designs" / "brief-package-applied.json").write_text("{", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "bad_marker"


@pytest.mark.covers("FR-01.04")
def test_in_process_a_crash_mid_write_leaves_no_truncated_file_and_the_rerun_completes(project, tool, capsys, monkeypatch):
    import os

    real, calls = os.replace, []

    def flaky(src, dst, *a, **k):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", flaky)
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "unreadable_package"
    designs = project / ".shipwright" / "designs"
    assert not (designs / "brief-package-applied.json").exists()
    assert not list(designs.rglob("*.tmp")) and all(f.stat().st_size > 0 for f in designs.rglob("*.html"))
    monkeypatch.setattr(os, "replace", real)
    code, out = main_json(tool, capsys, project)
    assert code == 0 and out["ok"] and (designs / "brief-package-applied.json").is_file()


@pytest.mark.covers("FR-01.04")
def test_in_process_already_applied_notices_a_deleted_screen_and_an_edited_upload(project, tool, capsys):
    main_json(tool, capsys, project)
    designs = project / ".shipwright" / "designs"
    (designs / "screens" / "02-editor.html").unlink()
    code, out = main_json(tool, capsys, project)
    assert code == 1 and out["issues"][0]["code"] == "applied_files_missing"
    (designs / "brief-package-applied.json").unlink()  # the documented reset path
    code, out = main_json(tool, capsys, project)
    assert code == 0 and (designs / "screens" / "02-editor.html").is_file()
    (designs / "uploads" / "01-notes.html").write_text("edited", encoding="utf-8")
    code, out = main_json(tool, capsys, project)
    assert code == 1 and "byte-identical" in out["issues"][0]["message"]
