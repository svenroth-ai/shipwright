"""Brief package library: layout validator and manifest hash (D1)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402


def _brief(**over) -> dict:
    base = {
        "version": 2, "profile": "vite-hono", "deploy_target": "none", "autonomy": "unattended",
        "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
        "design_system": "visual-guidelines.md", "brief_dir": "brief",
        "allow_parallel_builders": False, "ui_host": "web", "env_preflight": [], "approved_by": "fixture:t", "approved_at": "2026-10-24",
    }
    base.update(over)
    return base


def _write(root: Path, rel: str, text: str, nl: str = "\n") -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(text.replace("\n", nl).encode("utf-8"))


def _package(root: Path, nl: str = "\n", **over) -> Path:
    _write(root, "brief.md", "# B\n\n## a\ntext\n", nl)
    _write(root, "scope.md", "# S\nin\n", nl)
    _write(root, "visual-guidelines.md", "# V\nplain\n", nl)
    _write(root, "mockups/01.html", "<html>\n</html>\n", nl)
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": "01.html"}]}, indent=1) + "\n", nl)
    _write(root, "brief.json", json.dumps(_brief(**over), indent=1) + "\n", nl)
    return root


def _codes(root: Path) -> set[str]:
    return {i["code"] for i in bp.validate_layout(root)}


def test_accepts_a_valid_package(tmp_path):
    assert bp.validate_layout(_package(tmp_path / "p")) == []


@pytest.mark.parametrize("victim,code", [
    ("brief.md", "missing_file"), ("scope.md", "missing_file"), ("screen-map.json", "missing_file"),
    ("visual-guidelines.md", "missing_file"), ("brief.json", "missing_file"),
])
def test_rejects_each_missing_required_file(tmp_path, victim, code):
    root = _package(tmp_path / "p")
    (root / victim).unlink()
    assert code in _codes(root)


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


@pytest.mark.parametrize("bad", ["/abs", "C:/abs", "../up", "a/../../b", "\\\\share"])
def test_rejects_non_relative_brief_dir(tmp_path, bad):
    root = _package(tmp_path / "p", brief_dir=bad)
    assert "bad_brief_dir" in _codes(root)


def test_rejects_symlink(tmp_path, monkeypatch):
    root = _package(tmp_path / "p")
    # Unprivileged Windows cannot create real links; make one path report as a link.
    (root / "link.md").write_text("x")
    real = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self.name == "link.md" or real(self))
    assert "symlink" in _codes(root)
    assert "link.md" not in bp.manifest(root)


def test_missing_directory(tmp_path):
    assert _codes(tmp_path / "absent") == {"missing_dir"}


def test_hash_identical_for_lf_and_crlf(tmp_path):
    lf = bp.package_sha256(_package(tmp_path / "lf"))
    crlf = bp.package_sha256(_package(tmp_path / "crlf", nl="\r\n"))
    assert lf == crlf
    assert bp.manifest(tmp_path / "lf") == bp.manifest(tmp_path / "crlf")


@pytest.mark.parametrize("field,value", [
    ("autonomy", "guided"), ("allow_parallel_builders", True), ("deploy_target", "jelastic-dev"),
])
def test_consent_field_change_changes_hash(tmp_path, field, value):
    before = bp.package_sha256(_package(tmp_path / "a"))
    after = bp.package_sha256(_package(tmp_path / "b", **{field: value}))
    assert before != after


def test_approval_fields_do_not_change_hash(tmp_path):
    a = bp.package_sha256(_package(tmp_path / "a"))
    b = bp.package_sha256(_package(tmp_path / "b", approved_by="someone", approved_at="2030-01-01",
                                   package_sha256="0" * 64))
    assert a == b


def test_content_change_changes_hash(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    (root / "scope.md").write_text("# S\nout\n")
    assert bp.package_sha256(root) != before


def test_excluded_files_do_not_change_hash(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _write(root, "evidence/run.log", "noise")
    _write(root, ".DS_Store", "x")
    _write(root, "mockups/Thumbs.db", "x")
    _write(root, "__MACOSX/._x", "x")
    assert bp.package_sha256(root) == before


def test_manifest_is_posix_nfc_sorted(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/cafe\u0301.md", "x")  # decomposed e + combining accent
    keys = list(bp.manifest(root))
    assert keys == sorted(keys)
    assert "inputs/caf\u00e9.md" in keys
    assert all("\\" not in k for k in keys)


def test_verify_hash_roundtrip(tmp_path):
    root = _package(tmp_path / "a")
    ok, why = bp.verify_hash(root)
    assert not ok and "no package_sha256" in why
    brief = json.loads((root / "brief.json").read_text())
    brief["package_sha256"] = bp.package_sha256(root)
    _write(root, "brief.json", json.dumps(brief))
    assert bp.verify_hash(root) == (True, "")
    brief["autonomy"] = "guided"
    _write(root, "brief.json", json.dumps(brief))
    ok, why = bp.verify_hash(root)
    assert not ok and "mismatch" in why


def test_verify_hash_unreadable_brief(tmp_path):
    root = _package(tmp_path / "a")
    (root / "brief.json").write_text("{bad")
    assert bp.verify_hash(root)[0] is False


def test_nfc_path_collision_is_detected(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/caf\u00e9.md", "x")
    _write(root, "inputs/cafe\u0301.md", "y")
    names = {p.name for p in (root / "inputs").iterdir()}
    if len(names) < 2:
        return  # the filesystem already folds the forms (APFS): nothing can collide
    with pytest.raises(bp.PathCollision):
        bp.manifest(root)
    assert "path_collision" in _codes(root)


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


def test_binary_files_are_hashed_byte_exact(tmp_path):
    a, b = _package(tmp_path / "a"), _package(tmp_path / "b")
    (a / "mockups" / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (b / "mockups" / "x.png").write_bytes(b"\x89PNG\n\x1a\n")
    assert bp.package_sha256(a) != bp.package_sha256(b)


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


def test_text_is_decided_by_content_not_extension(tmp_path):
    a, b = _package(tmp_path / "a"), _package(tmp_path / "b")
    (a / "mockups" / "x.tsx").write_bytes(b"const a = 1;\r\n")
    (b / "mockups" / "x.tsx").write_bytes(b"const a = 1;\n")
    (a / "inputs").mkdir()
    (b / "inputs").mkdir()
    (a / "inputs" / "README").write_bytes(b"hi\r\n")
    (b / "inputs" / "README").write_bytes(b"hi\n")
    assert bp.package_sha256(a) == bp.package_sha256(b)


def test_non_utf8_required_file_is_a_defect_not_a_crash(tmp_path):
    root = _package(tmp_path / "a")
    (root / "scope.md").write_bytes(b"\xff\xfe\x00bad")
    assert "bad_encoding" in _codes(root)


@pytest.mark.parametrize("mockup", ["../brief.md", "/etc/hosts", "C:/Windows/win.ini", "sub/../../brief.md", ""])
def test_screen_map_cannot_point_outside_mockups(tmp_path, mockup):
    root = _package(tmp_path / "a")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": mockup}]}))
    assert "dangling_mockup" in _codes(root)


@pytest.mark.parametrize("bad", ["./.shipwright/x", ".Shipwright/x", "a/.shipwright/b", "", 5, None])
def test_brief_dir_edge_cases(tmp_path, bad):
    root = _package(tmp_path / "a", brief_dir=bad)
    assert "bad_brief_dir" in _codes(root)


def test_brief_dir_with_shipwright_prefix_name_is_fine(tmp_path):
    assert bp.validate_layout(_package(tmp_path / "a", brief_dir=".shipwrightfoo/brief")) == []


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


def test_mockups_with_only_junk_is_not_a_mockup_dir(tmp_path):
    root = _package(tmp_path / "a")
    (root / "mockups" / "01.html").unlink()
    _write(root, "mockups/.gitkeep", "")
    assert "missing_dir" in _codes(root)


def test_case_only_difference_is_a_collision(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "inputs/A.md", "x")
    _write(root, "inputs/a.md", "y")
    if len({p.name for p in (root / "inputs").iterdir()}) < 2:
        return  # case-insensitive filesystem: the two names are one file
    with pytest.raises(bp.PathCollision):
        bp.manifest(root)


def test_colon_in_a_reference_is_refused_it_can_be_a_windows_data_stream(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": "01.html:x"}]}))
    assert "dangling_mockup" in _codes(root)
    assert "dangling_ref" in _codes(_package(tmp_path / "b", scope="scope.md:x"))


def _make_link(target: Path, link: Path) -> None:
    """A real directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_junction_loop_is_reported_not_walked(tmp_path):
    root = _package(tmp_path / "a")
    _make_link(root, root / "loop")
    codes = _codes(root)  # must return, not recurse until MAX_PATH
    assert "symlink" in codes
    assert not any(k.startswith("loop") for k in bp.manifest(root))
    assert bp.verify_hash(root) == (False, "package contains links or junctions")


def test_a_link_to_an_outside_tree_is_not_hashed_or_copied(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("s")
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _make_link(outside, root / "inputs")
    assert "symlink" in _codes(root)
    assert bp.package_sha256(root) == before
    assert not any("secret" in rel for rel, _ in bp.iter_package_files(root))


def test_references_must_name_hashed_files(tmp_path):
    root = _package(tmp_path / "a")
    _write(root, "evidence/scope.md", "x")
    assert "dangling_ref" in _codes(_package(tmp_path / "b", scope="evidence/scope.md"))
    (root / "mockups" / "01.html").unlink()
    _write(root, "mockups/02.html", "<html></html>")
    _write(root, "mockups/.gitkeep", "")
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": ".gitkeep"}]}))
    assert "dangling_mockup" in _codes(root)


def test_evidence_exclusion_is_case_insensitive(tmp_path):
    root = _package(tmp_path / "a")
    before = bp.package_sha256(root)
    _write(root, "Evidence/run.log", "noise")
    assert bp.package_sha256(root) == before


def test_verify_hash_fails_on_a_link_even_when_the_hash_matches(tmp_path):
    root = _package(tmp_path / "a")
    brief = json.loads((root / "brief.json").read_text())
    brief["package_sha256"] = bp.package_sha256(root)
    _write(root, "brief.json", json.dumps(brief))
    assert bp.verify_hash(root) == (True, "")
    _make_link(tmp_path, root / "inputs")
    assert bp.verify_hash(root)[0] is False
