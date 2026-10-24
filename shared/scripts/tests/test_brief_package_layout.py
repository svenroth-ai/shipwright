"""Brief package library: layout validator, brief.json fields and references (D1)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402
from tests._brief_package_helpers import (  # noqa: E402
    _brief, _codes, _package, _write,
)

@pytest.mark.covers("FR-01.01")
def test_accepts_a_valid_package(tmp_path):
    assert bp.validate_layout(_package(tmp_path / "p")) == []


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("victim,code", [
    ("brief.md", "missing_file"), ("scope.md", "missing_file"), ("screen-map.json", "missing_file"),
    ("visual-guidelines.md", "missing_file"), ("brief.json", "missing_file"),
])
def test_rejects_each_missing_required_file(tmp_path, victim, code):
    root = _package(tmp_path / "p")
    (root / victim).unlink()
    assert code in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_rejects_planted_defects(tmp_path):
    cases = {
        "empty_file": lambda r: (r / "scope.md").write_text("  \n"),
        "invalid_json": lambda r: (r / "screen-map.json").write_text("{nope"),
        "dangling_mockup": lambda r: _write(r, "screen-map.json", json.dumps({"screens": [{"mockup": "x.html"}]})),
        "bad_screen_map": lambda r: _write(r, "screen-map.json", json.dumps({"screens": []})),
        "missing_dir": lambda r: shutil.rmtree(r / "mockups"),
        "bad_version": lambda r: _write(r, "brief.json", json.dumps(_brief(version=1))),
        "bad_value": lambda r: _write(r, "brief.json", json.dumps(_brief(autonomy="yolo"))),
        "bad_brief_dir": lambda r: _write(r, "brief.json", json.dumps(_brief(brief_dir=".shipwright/brief"))),
        "missing_field": lambda r: _write(r, "brief.json", json.dumps({"version": 2})),
        "missing_file": lambda r: _write(r, "brief.json", json.dumps(_brief(ux_shape="chat-first"))),
        "unexpected_file": lambda r: _write(r, "chat-map.json", "{}"),
    }
    for code, plant in cases.items():
        root = _package(tmp_path / code)
        plant(root)
        assert code in _codes(root), code


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("bad", ["/abs", "C:/abs", "../up", "a/../../b", "\\\\share"])
def test_rejects_non_relative_brief_dir(tmp_path, bad):
    root = _package(tmp_path / "p", brief_dir=bad)
    assert "bad_brief_dir" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_missing_directory(tmp_path):
    assert _codes(tmp_path / "absent") == {"missing_dir"}


@pytest.mark.covers("FR-01.01")
def test_non_utf8_required_file_is_a_defect_not_a_crash(tmp_path):
    root = _package(tmp_path / "a")
    (root / "scope.md").write_bytes(b"\xff\xfe\x00bad")
    assert "bad_encoding" in _codes(root)


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("mockup", ["../brief.md", "/etc/hosts", "C:/Windows/win.ini", "sub/../../brief.md", ""])
def test_screen_map_cannot_point_outside_mockups(tmp_path, mockup):
    root = _package(tmp_path / "a")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": mockup}]}))
    assert "dangling_mockup" in _codes(root)


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("bad", ["./.shipwright/x", ".Shipwright/x", "a/.shipwright/b", "", 5, None])
def test_brief_dir_edge_cases(tmp_path, bad):
    root = _package(tmp_path / "a", brief_dir=bad)
    assert "bad_brief_dir" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_brief_dir_with_shipwright_prefix_name_is_fine(tmp_path):
    assert bp.validate_layout(_package(tmp_path / "a", brief_dir=".shipwrightfoo/brief")) == []


@pytest.mark.covers("FR-01.01")
def test_required_fields_and_types(tmp_path):
    for key in ("ui_host", "env_preflight"):
        root = _package(tmp_path / key)
        brief = json.loads((root / "brief.json").read_text())
        del brief[key]
        _write(root, "brief.json", json.dumps(brief))
        assert "missing_field" in _codes(root)
    assert "bad_value" in _codes(_package(tmp_path / "t1", profile=""))
    assert "bad_value" in _codes(_package(tmp_path / "t2", env_preflight="X"))
    assert "dangling_ref" in _codes(_package(tmp_path / "t3", scope="nope.md"))
    assert "dangling_ref" in _codes(_package(tmp_path / "t4", design_system="../x"))


@pytest.mark.covers("FR-01.01")
def test_mockups_with_only_junk_is_not_a_mockup_dir(tmp_path):
    root = _package(tmp_path / "a")
    (root / "mockups" / "01.html").unlink()
    _write(root, "mockups/.gitkeep", "")
    assert "missing_dir" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_colon_in_a_reference_is_refused_it_can_be_a_windows_data_stream(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": "01.html:x"}]}))
    assert "dangling_mockup" in _codes(root)
    assert "dangling_ref" in _codes(_package(tmp_path / "b", scope="scope.md:x"))


@pytest.mark.covers("FR-01.01")
def test_references_must_name_hashed_files(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "evidence/scope.md", "x")
    assert "dangling_ref" in _codes(_package(tmp_path / "b", scope="evidence/scope.md"))
    (root / "mockups" / "01.html").unlink()
    _write(root, "mockups/02.html", "<html></html>")
    _write(root, "mockups/.gitkeep", "")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": ".gitkeep"}]}))
    assert "dangling_mockup" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_duplicate_json_keys_are_refused(tmp_path):
    root = _package(tmp_path / "a")
    text = (root / "brief.json").read_text()
    (root / "brief.json").write_text(text.replace("{", '{"autonomy": "guided", ', 1))
    assert "invalid_json" in _codes(root)
    with pytest.raises(ValueError):
        bp.manifest(root)
    assert bp.verify_recorded_hash(root)[0] is False


@pytest.mark.covers("FR-01.01")
def test_deeply_nested_json_is_a_defect_not_a_crash(tmp_path):
    root = _package(tmp_path / "a")
    (root / "screen-map.json").write_text("[" * 200000)
    assert "invalid_json" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_a_lone_surrogate_is_reported_as_unhashable(tmp_path):
    root = _package(tmp_path / "a")
    brief = (root / "brief.json").read_text().replace('"vite-hono"', '"\\ud800"')
    (root / "brief.json").write_text(brief)
    assert "unhashable_package" in _codes(root)
