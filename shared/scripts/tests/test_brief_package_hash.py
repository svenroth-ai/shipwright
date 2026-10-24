"""Brief package library: manifest hash -- line endings, consent fields, text sniffing, collisions (D1)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402
from tests._brief_package_helpers import (  # noqa: E402
    _codes, _package, _record_hash, _write,
)

@pytest.mark.covers("FR-01.01")
def test_hash_identical_for_lf_and_crlf(tmp_path):
    lf = bp.package_sha256(_package(tmp_path / "lf"))
    crlf = bp.package_sha256(_package(tmp_path / "crlf", nl="\r\n"))
    assert lf == crlf
    assert bp.manifest(tmp_path / "lf") == bp.manifest(tmp_path / "crlf")


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("field,value", [
    ("autonomy", "guided"), ("allow_parallel_builders", True), ("deploy_target", "jelastic-dev"),
])
def test_consent_field_change_changes_hash(tmp_path, field, value):
    before = bp.package_sha256(_package(tmp_path / "a"))
    after = bp.package_sha256(_package(tmp_path / "b", **{field: value}))
    assert before != after


@pytest.mark.covers("FR-01.01")
def test_approval_fields_do_not_change_hash(tmp_path):
    a = bp.package_sha256(_package(tmp_path / "a"))
    b = bp.package_sha256(_package(tmp_path / "b", approved_by="someone", approved_at="2030-01-01",
                                   package_sha256="0" * 64))
    assert a == b


@pytest.mark.covers("FR-01.01")
def test_content_change_changes_hash(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    (root / "scope.md").write_text("# S\nout\n")
    assert bp.package_sha256(root) != before


@pytest.mark.covers("FR-01.01")
def test_manifest_is_posix_nfc_sorted(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/cafe\u0301.md", "x")  # decomposed e + combining accent
    keys = list(bp.manifest(root))
    assert keys == sorted(keys)
    assert "inputs/caf\u00e9.md" in keys
    assert all("\\" not in k for k in keys)


@pytest.mark.covers("FR-01.01")
def test_verify_hash_roundtrip(tmp_path):
    root = _package(tmp_path / "a")
    ok, why = bp.verify_hash(root)
    assert not ok and "no package_sha256" in why
    _record_hash(root)
    assert bp.verify_hash(root) == (True, "")
    brief = json.loads((root / "brief.json").read_text())
    brief["autonomy"] = "guided"
    _write(root, "brief.json", json.dumps(brief))
    ok, why = bp.verify_hash(root)
    assert not ok and "mismatch" in why


@pytest.mark.covers("FR-01.01")
def test_verify_hash_unreadable_brief(tmp_path):
    root = _package(tmp_path / "a")
    (root / "brief.json").write_text("{bad")
    assert bp.verify_hash(root)[0] is False


@pytest.mark.covers("FR-01.01")
def test_nfc_path_collision_is_detected(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/caf\u00e9.md", "x")
    _write(root, "inputs/cafe\u0301.md", "y")
    names = {p.name for p in (root / "inputs").iterdir()}
    if len(names) < 2:
        pytest.skip("filesystem folds unicode forms")  # test-hygiene: allow-silent-skip — setup-condition gate: the filesystem normalises names, so the collision cannot be created
    with pytest.raises(bp.PathCollision):
        bp.manifest(root)
    assert "path_collision" in _codes(root)


@pytest.mark.covers("FR-01.01")
def test_rename_and_add_and_remove_change_hash(tmp_path):
    root = _package(tmp_path / "a")
    base = bp.package_sha256(root)
    (root / "scope.md").rename(root / "scope2.md")
    assert bp.package_sha256(root) != base
    (root / "scope2.md").rename(root / "scope.md")
    assert bp.package_sha256(root) == base
    _write(root, "inputs/extra.md", "x")
    assert bp.package_sha256(root) != base
    (root / "inputs" / "extra.md").unlink()
    (root / "inputs").rmdir()
    assert bp.package_sha256(root) == base


@pytest.mark.covers("FR-01.01")
def test_binary_files_are_hashed_byte_exact(tmp_path):
    a, b = _package(tmp_path / "a"), _package(tmp_path / "b")
    (a / "mockups" / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    (b / "mockups" / "x.png").write_bytes(b"\x89PNG\n\x1a\n\x00")
    assert bp.package_sha256(a) != bp.package_sha256(b)


@pytest.mark.covers("FR-01.01")
def test_hash_matches_an_independent_computation(tmp_path):
    import hashlib
    root = tmp_path / "tiny"
    _write(root, "brief.json", json.dumps({"b": 1, "a": "\u00e9", "approved_by": "x"}))
    (root / "scope.md").write_bytes(b"one\r\ntwo\r\n")
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    expected_manifest = (
        '{"brief.json":"' + sha('{"a":"\u00e9","b":1}'.encode("utf-8"))
        + '","scope.md":"' + sha(b"one\ntwo\n") + '"}'
    )
    assert bp.package_sha256(root) == sha(expected_manifest.encode("utf-8"))


@pytest.mark.covers("FR-01.01")
def test_text_is_decided_by_content_not_extension(tmp_path):
    a, b = _package(tmp_path / "a"), _package(tmp_path / "b")
    (a / "mockups" / "x.tsx").write_bytes(b"const a = 1;\r\n")
    (b / "mockups" / "x.tsx").write_bytes(b"const a = 1;\n")
    (a / "inputs").mkdir()
    (b / "inputs").mkdir()
    (a / "inputs" / "README").write_bytes(b"hi\r\n")
    (b / "inputs" / "README").write_bytes(b"hi\n")
    assert bp.package_sha256(a) == bp.package_sha256(b)


@pytest.mark.covers("FR-01.01")
def test_case_only_difference_is_a_collision(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/A.md", "x")
    _write(root, "inputs/a.md", "y")
    if len({p.name for p in (root / "inputs").iterdir()}) < 2:
        pytest.skip("case-insensitive filesystem: names fold")  # test-hygiene: allow-silent-skip — setup-condition gate: the filesystem folds case, so the collision cannot be created
    with pytest.raises(bp.PathCollision):
        bp.manifest(root)


@pytest.mark.covers("FR-01.01")
def test_text_detection_matches_git_not_utf8(tmp_path):
    a, b = _package(tmp_path / "a"), _package(tmp_path / "b")
    (a / "inputs").mkdir()
    (b / "inputs").mkdir()
    (a / "inputs" / "legacy.csv").write_bytes("café\r\n".encode("cp1252"))
    (b / "inputs" / "legacy.csv").write_bytes("café\n".encode("cp1252"))
    assert bp.package_sha256(a) == bp.package_sha256(b)


@pytest.mark.covers("FR-01.01")
def test_verify_hash_against_an_externally_held_hash(tmp_path):
    root = _package(tmp_path / "a")
    actual = bp.package_sha256(root)
    assert bp.verify_hash(root, expected=actual) == (True, "")
    ok, why = bp.verify_hash(root, expected="0" * 64)
    assert not ok and "mismatch" in why
