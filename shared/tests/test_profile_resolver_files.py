"""Stack-profile resolver, explicit files / case rules / read-only (S1 items 11, 13, 18, 19).

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shared.tests.profile_test_fixtures import pr, proj_dir as _proj_dir, write_profile as _write

pytestmark = pytest.mark.covers("FR-01.06")


# (11)(19) load_profile_file --------------------------------------------------------------
def test_load_profile_file_applies_schema_not_name_rules(tmp_path):
    p = tmp_path / "Weird_Name.json"
    p.write_text(json.dumps({"name": "Weird_Name"}), encoding="utf-8")
    res = pr.load_profile_file(p)
    assert res.source == "explicit" and res.custom
    p.write_text(json.dumps({"name": "x", "schema_version": 99}), encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pr.load_profile_file(p)
    assert ei.value.kind == "schema_drift"
    with pytest.raises(ValueError, match="must equal the file name"):
        p.write_text(json.dumps({"name": "x"}), encoding="utf-8")
        pr.load_profile_file(p, expected_name="Weird_Name")


def test_custom_file_named_like_bundled_is_never_bundled(tmp_path):
    p = _write(tmp_path / "elsewhere", "supabase-nextjs", testing={"command": "make test"})
    res = pr.load_profile_file(p)
    assert res.source == "explicit" and res.custom
    assert res.shadows_bundled and any("shadows the bundled" in w for w in res.warnings)
    assert res.data["testing"]["command"] == "make test"


def test_load_profile_file_classifies_against_search_dirs(project, user_dir):
    pp = _write(_proj_dir(project), "vite-hono")
    res = pr.load_profile_file(pp, project_root=project)
    assert res.source == "project" and res.custom and res.shadows_bundled
    bundled = pr.load_profile_file(Path(pr.bundled_dir()) / "vite-hono.json")
    assert bundled.source == "bundled" and not bundled.custom and not bundled.warnings


# (18) case spelling --------------------------------------------------------------------------
def test_wrong_case_entry_is_deterministic_error(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "Vite-Hono.json").write_text(json.dumps({"name": "vite-hono"}), encoding="utf-8")
    with pytest.raises(ValueError, match="lowercase"):
        pr.resolve_profile("vite-hono", project)
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"].lower() == "vite-hono")
    assert row["valid"] is False


def test_case_colliding_pair_is_error(project, monkeypatch):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    real_listdir = os.listdir
    monkeypatch.setattr(
        os, "listdir", lambda p: ["foo.json", "Foo.json"] if str(p) == str(d) else real_listdir(p))
    with pytest.raises(ValueError, match="differ only in case"):
        pr.resolve_profile("foo", project)
    out = pr.list_profiles(project)
    assert any(not r["valid"] and "differ only in case" in r["error"] for r in out["profiles"])


# (13) read-only ------------------------------------------------------------------------------
def test_resolver_modules_never_spawn_or_expand_env():
    for mod in ("profile_resolver", "profile_model", "profile_schema_check"):
        src = (Path(pr.bundled_dir()).parent / "scripts" / f"{mod}.py").read_text(encoding="utf-8")
        assert "subprocess" not in src and "_expand_env" not in src and "os.system" not in src


def test_import_has_no_pathlib_arithmetic_at_module_scope():
    code = ("import sys,pathlib;sys.argv=['x'];"
            "orig=pathlib.Path.home\n"
            "def boom(*a,**k): raise AssertionError('Path.home at import')\n"
            "pathlib.Path.home=boom\n"
            f"sys.path.append({str(Path(pr.bundled_dir()).parent / 'scripts')!r});import profile_resolver")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_directory_or_dangling_symlink_at_winning_path_is_invalid_not_absent(project, tmp_path):
    d = _proj_dir(project)
    (d / "vite-hono.json").mkdir(parents=True)  # a directory where the file should be
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("vite-hono", project)
    assert ei.value.kind == "invalid"  # never falls through to the bundled file
    (d / "vite-hono.json").rmdir()
    try:
        os.symlink(tmp_path / "gone.json", d / "vite-hono.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink privilege missing")
    with pytest.raises(ValueError):
        pr.resolve_profile("vite-hono", project)


def test_unreadable_or_file_typed_project_dir_never_falls_through(project):
    (project / ".shipwright").mkdir()
    (project / ".shipwright" / "profiles").write_text("i am a file", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("vite-hono", project)  # NOT the bundled profile
    assert ei.value.kind == "invalid" and "cannot be read" in str(ei.value)


def test_user_dir_that_is_a_file_is_simply_absent(project, tmp_path, monkeypatch):
    bad = tmp_path / "userfile"
    bad.write_text("x", encoding="utf-8")
    monkeypatch.setenv(pr.USER_DIR_ENV, str(bad))
    assert pr.resolve_profile("vite-hono", project).source == "bundled"


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_sentinel_named_file_is_an_error_in_any_source(project, user_dir, sentinel):
    _write(user_dir, sentinel)
    with pytest.raises(ValueError, match="reserved built-in name"):
        pr.resolve_profile(sentinel, project)


def test_custom_profiles_named_like_deploy_files_are_allowed(project):
    _write(_proj_dir(project), "deploy-profile")
    assert pr.resolve_profile("deploy-profile", project).source == "project"


def test_isolation_fixture_constant_matches_resolver():
    from profile_test_isolation import USER_DIR_ENV
    assert USER_DIR_ENV == pr.USER_DIR_ENV


def test_defective_lower_source_entry_never_blocks_a_valid_winner(project, user_dir):
    _write(_proj_dir(project), "vite-hono")
    (user_dir / "Vite-Hono.json").write_text("{}", encoding="utf-8")  # wrong case, lower source
    res = pr.resolve_profile("vite-hono", project)
    assert res.source == "project" and any(s.endswith("Vite-Hono.json") for s in res.shadows)


def test_upper_case_extension_is_listed_invalid_and_blocks_resolve(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "vite-hono.JSON").write_text(json.dumps({"name": "vite-hono"}), encoding="utf-8")
    with pytest.raises(ValueError, match="lowercase"):
        pr.resolve_profile("vite-hono", project)
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"].lower() == "vite-hono")
    assert row["valid"] is False and row["source"] == "project"


def test_sentinel_scan_does_not_hide_an_unreadable_project_dir(project):
    (project / ".shipwright").mkdir()
    (project / ".shipwright" / "profiles").write_text("file, not dir", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be read"):
        pr.resolve_profile("generic", project)


def test_missing_user_dir_warns_in_list_but_is_absent_for_resolve(project, tmp_path, monkeypatch):
    gone = tmp_path / "no-such-dir"
    monkeypatch.setenv(pr.USER_DIR_ENV, str(gone))
    out = pr.list_profiles(project)
    assert any(str(gone) in w for w in out["warnings"])
    assert pr.resolve_profile("vite-hono", project).source == "bundled"
    assert not [w for w in out["warnings"] if str(project) in w]  # project dir stays silent


def test_search_dirs_override_tuple_and_bare_path_forms(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "dup", description="from a")
    _write(b, "dup", description="from b")
    _write(b, "only-b")
    tuples = [("project", str(a)), ("user", str(b))]
    res = pr.resolve_profile("dup", None, search_dirs=tuples)
    assert res.source == "project" and res.data["description"] == "from a"
    assert res.shadows == [str(b / "dup.json")] and not res.shadows_bundled
    bare = pr.resolve_profile("only-b", None, search_dirs=[str(a), str(b)])
    assert bare.source == "explicit" and bare.path == str(b / "only-b.json")
    with pytest.raises(ValueError) as ei:  # override dirs replace the bundled source
        pr.resolve_profile("vite-hono", None, search_dirs=tuples)
    assert ei.value.kind == "not_found" and str(a) in str(ei.value)
    listed = pr.list_profiles(None, search_dirs=tuples)
    by = {r["name"]: r for r in listed["profiles"]}
    assert set(by) == {"dup", "only-b"} and by["dup"]["source"] == "project"
    assert listed["searched"] == [str(a), str(b)]
    loaded = pr.load_profile_file(b / "dup.json", search_dirs=tuples)
    assert loaded.source == "user" and loaded.shadows == []
    first = pr.load_profile_file(a / "dup.json", search_dirs=tuples)
    assert first.source == "project" and first.shadows == [str(b / "dup.json")]


def test_search_dirs_override_is_strict_for_unreadable_dir(tmp_path):
    f = tmp_path / "file"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be read"):
        pr.resolve_profile("vite-hono", None, search_dirs=[("explicit", str(f))])


def test_symlink_loop_is_invalid_not_a_crash(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    try:
        os.symlink(d / "loop.json", d / "loop.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink privilege missing")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("loop", project)
    assert ei.value.kind == "invalid"
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"] == "loop")
    assert row["valid"] is False


def test_same_directory_listed_twice_is_not_its_own_shadow(project, monkeypatch):
    _write(_proj_dir(project), "twice")
    monkeypatch.setenv(pr.USER_DIR_ENV, str(_proj_dir(project)))
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"] == "twice")
    assert row["shadows"] == []


def test_bare_path_override_ranks_shadows_by_directory_order(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "dup")
    _write(b, "dup")
    loaded = pr.load_profile_file(b / "dup.json", search_dirs=[str(a), str(b)])
    assert loaded.shadows == []  # a ranks higher than b, so it is not a shadow of b's file


def test_resolve_runtime_error_from_symlink_loop_maps_to_invalid(project, monkeypatch):
    """Python 3.11 raises RuntimeError (not OSError) for a loop; simulate it everywhere."""
    _write(_proj_dir(project), "loopy")

    def boom(self, *a, **k):
        raise RuntimeError("Symlink loop from 'x'")

    monkeypatch.setattr(Path, "resolve", boom)
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("loopy", project)
    assert ei.value.kind == "invalid" and "cannot be resolved" in str(ei.value)
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"] == "loopy")
    assert row["valid"] is False


def test_deeply_nested_json_is_invalid_not_a_crash(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "deep.json").write_text("[" * 200000, encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("deep", project)
    assert ei.value.kind == "invalid"
    rows = {r["name"]: r for r in pr.list_profiles(project)["profiles"]}
    assert rows["deep"]["valid"] is False and rows["vite-hono"]["valid"] is True  # list survives


def test_relative_user_dir_env_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv(pr.USER_DIR_ENV, "relative/profiles")
    assert pr.user_dir() is None
    assert [s for s, _ in pr.search_dirs(tmp_path)] == ["project", "bundled"]
