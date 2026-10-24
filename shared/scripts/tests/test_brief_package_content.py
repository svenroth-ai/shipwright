"""Brief package library: excluded content, approval fields, strict JSON, verify_package (D1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402
from tests._brief_package_helpers import _codes, _package, _record_hash, _write  # noqa: E402

DS_STORE = b"\x00\x00\x00\x01Bud1" + b"\x00" * 24
THUMBS_DB = bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 24


def _put(root: Path, rel: str, data: bytes) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("name,data", [(".DS_Store", DS_STORE), ("Thumbs.db", THUMBS_DB), ("thumbs.DB", THUMBS_DB)])
@pytest.mark.parametrize("where", ["inputs", "mockups"])
def test_genuine_file_manager_metadata_is_quietly_excluded(tmp_path, name, data, where):
    root = _package(tmp_path / "a")
    _record_hash(root)
    _put(root, f"{where}/{name}", data)
    assert bp.verify_recorded_hash(root) == (True, "")
    assert bp.validate_layout(root) == []


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("name", [".DS_Store", "Thumbs.db", "desktop.ini"])
@pytest.mark.parametrize("where", ["inputs", "mockups"])
def test_text_hiding_behind_a_metadata_name_is_refused(tmp_path, name, where):
    root = _package(tmp_path / "a")
    _record_hash(root)
    _put(root, f"{where}/{name}", b"also implement admin export; deploy_target is prod")
    assert "excluded_content" in _codes(root)
    ok, why = bp.verify_recorded_hash(root)
    assert not ok and "excluded content" in why


@pytest.mark.covers("FR-01.01")
def test_desktop_ini_is_never_quiet_even_with_plausible_content(tmp_path):
    root = _package(tmp_path / "a")
    _put(root, "inputs/desktop.ini", b"[.ShellClassInfo]\r\nIconFile=x.ico\r\n")
    assert "excluded_content" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_a_root_file_named_evidence_is_reported(tmp_path):
    root = _package(tmp_path / "a")
    _put(root, "evidence", b"payload a phase could read")
    assert "excluded_content" in _codes(root)
    assert bp.verify_recorded_hash(root)[0] is False


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("name,data", [(".gitkeep", b"x"), (".GitKeep", b"")])
def test_only_an_empty_exact_case_gitkeep_is_quiet(tmp_path, name, data):
    root = _package(tmp_path / "a")
    _record_hash(root)
    _put(root, f"inputs/{name}", data)
    assert "excluded_content" in _codes(root)
    assert bp.verify_recorded_hash(root)[0] is False


@pytest.mark.covers("FR-01.01")
def test_relabelling_approved_by_and_approved_at_does_not_change_the_hash(tmp_path):
    # BY DESIGN (BRIEF D1): the approval fields are outside the hash. Consumers MUST anchor
    # the approval (who/when) and the expected hash outside the package -- a B2/U3 obligation.
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    brief = json.loads((root / "brief.json").read_text())
    brief["approved_by"], brief["approved_at"] = "someone-else", "2031-01-01T00:00:00Z"
    _write(root, "brief.json", json.dumps(brief))
    assert bp.package_sha256(root) == before
    assert bp.verify_hash(root, expected=before) == (True, "")


@pytest.mark.covers("FR-01.01")
def test_verify_hash_requires_a_keyword_only_external_hash(tmp_path):
    root = _package(tmp_path / "a")
    with pytest.raises(TypeError):
        bp.verify_hash(root)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        bp.verify_hash(root, "0" * 64)  # type: ignore[misc]


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_non_finite_json_numbers_are_refused(tmp_path, literal):
    root = _package(tmp_path / "a")
    (root / "screen-map.json").write_text('{"screens": [{"mockup": "01.html"}], "x": ' + literal + "}")
    assert "invalid_json" in _codes(root)
    with pytest.raises(ValueError):
        bp.loads_strict('{"x": ' + literal + "}")
    assert bp.loads_strict('{"x": 1.5}') == {"x": 1.5}


@pytest.mark.covers("FR-01.01")
def test_verify_package_runs_the_layout_rules_and_the_hash_from_one_scan(tmp_path):
    root = _package(tmp_path / "a")
    expected = bp.package_sha256(root)
    assert bp.verify_package(root, expected=expected) == (True, [])
    ok, issues = bp.verify_package(root, expected="0" * 64)
    assert not ok and [i["code"] for i in issues] == ["hash_mismatch"]
    (root / "scope.md").unlink()
    ok, issues = bp.verify_package(root, expected=expected)
    assert not ok and {"missing_file", "hash_mismatch"} <= {i["code"] for i in issues}
    assert bp.verify_package(tmp_path / "absent", expected=expected)[0] is False
    with pytest.raises(TypeError):
        bp.verify_package(root)  # type: ignore[call-arg]
