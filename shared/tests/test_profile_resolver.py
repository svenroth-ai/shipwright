"""Stack-profile resolver (campaign stack-profile-resolver, S1): lookup, names, validation.

Brief S1 acceptance items are tagged ``(n)``. Tagged to FR-01.06 (the test phase
is the first consumer of a resolved profile); the capability FR is minted when
the loaders switch over (S2-S5), per the FR-authoring MINT-vs-FOLD rule.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_resolver as pr  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir as _proj_dir, write_profile as _write  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401  (module-local fixtures: "project", "user_dir")

pytestmark = pytest.mark.covers("FR-01.06")


# (1) project > user > bundled ------------------------------------------------
def test_precedence_project_over_user_over_bundled(project, user_dir):
    assert pr.resolve_profile("vite-hono", project).source == "bundled"
    _write(user_dir, "vite-hono")
    assert pr.resolve_profile("vite-hono", project).source == "user"
    _write(_proj_dir(project), "vite-hono")
    assert pr.resolve_profile("vite-hono", project).source == "project"


def test_user_only_and_project_only_names(project, user_dir):
    _write(user_dir, "my-user")
    _write(_proj_dir(project), "my-proj")
    assert pr.resolve_profile("my-user", project).source == "user"
    assert pr.resolve_profile("my-proj", project).source == "project"
    assert not pr.resolve_profile("my-proj", project).shadows


# (2) shadows -----------------------------------------------------------------
def test_shadows_reported_and_bundled_shadow_warns(project, user_dir):
    up = _write(user_dir, "vite-hono")
    pp = _write(_proj_dir(project), "vite-hono")
    res = pr.resolve_profile("vite-hono", project)
    assert res.path == str(pp)
    assert str(up) in res.shadows
    assert any(s.endswith("vite-hono.json") for s in res.shadows)
    assert res.shadows_bundled
    assert any("shadows the bundled" in w for w in res.warnings)
    assert any(line.startswith("shadows:") for line in pr.provenance_lines(res))


def test_no_shadow_warning_when_not_shadowing_bundled(project, user_dir):
    _write(user_dir, "same")
    _write(_proj_dir(project), "same")
    res = pr.resolve_profile("same", project)
    assert res.shadows and not res.shadows_bundled and not res.warnings


# (3) corrupt winner never falls through ---------------------------------------
def test_corrupt_winning_file_raises_and_does_not_use_bundled(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "vite-hono.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("vite-hono", project)
    assert ei.value.kind == "invalid" and ei.value.exit_code == 3
    assert "vite-hono.json" in str(ei.value)


def test_bom_is_tolerated_and_non_object_rejected(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "bom.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"name": "bom"}).encode())
    assert pr.resolve_profile("bom", project).name == "bom"
    (d / "arr.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        pr.resolve_profile("arr", project)


def test_name_must_match_file_stem(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "foo.json").write_text(json.dumps({"name": "bar"}), encoding="utf-8")
    with pytest.raises(ValueError, match="must equal the file name"):
        pr.resolve_profile("foo", project)


# (4) schema drift -------------------------------------------------------------
@pytest.mark.parametrize("version", [99, 0, "2", True])
def test_schema_version_drift(project, version):
    _write(_proj_dir(project), "drifty", schema_version=version)
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("drifty", project)
    assert ei.value.kind == "schema_drift" and ei.value.exit_code == 3
    msg = str(ei.value)
    assert "drifty.json" in msg and "schema_version 1" in msg
    assert "copy the bundled profile" in msg


def test_wrong_typed_key_is_drift(project):
    _write(_proj_dir(project), "typo", services="not-a-list")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("typo", project)
    assert ei.value.kind == "schema_drift"


def test_missing_name_key_is_invalid(project):
    d = _proj_dir(project)
    d.mkdir(parents=True)
    (d / "anon.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("anon", project)
    assert ei.value.kind == "invalid"


# (5) unknown name -------------------------------------------------------------
def test_unknown_name_lists_searched_paths(project):
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("nope", project)
    assert ei.value.kind == "not_found" and ei.value.exit_code == 2
    msg = str(ei.value)
    assert str(_proj_dir(project)) in msg and pr.bundled_dir() in msg


# (6) sentinels ------------------------------------------------------------------
@pytest.mark.parametrize("name", ["generic", "detecting"])
def test_sentinels_are_builtin_without_reading_files(project, name, monkeypatch):
    monkeypatch.setattr(pr, "_read_json", lambda *a: pytest.fail("no file may be read"))
    res = pr.resolve_profile(name, project)
    assert res.source == "builtin" and res.path is None and res.data == {}
    assert not res.custom


# (7) names ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    ["../x", "A_B", "Generic", "DETECTING", "/etc/passwd", "C:\\x", "..\\x", "con", "CON",
     "nul", "aux", "prn", "com1", "lpt9", "a/b", "a\\b", "\\\\server\\share", "a.b", "a b", "", "-lead", "x" + "\x00", "foo\n"],
)
def test_bad_names_rejected(project, name):
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile(name, project)
    assert ei.value.kind == "invalid"


def test_symlink_leaving_directory_rejected(project, tmp_path):
    outside = _write(tmp_path / "outside", "evil")
    d = _proj_dir(project)
    d.mkdir(parents=True)
    try:
        os.symlink(outside, d / "evil.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink privilege missing")
    with pytest.raises(ValueError, match="outside"):
        pr.resolve_profile("evil", project)


# (8) non-profile files ------------------------------------------------------------
@pytest.mark.parametrize("name", ["reducibility-idioms", "deploy-profile.schema", "deploy-profile-schema"])
def test_non_profile_files_not_resolvable(project, name):
    with pytest.raises(ValueError):
        pr.resolve_profile(name, project)


def test_non_profile_files_never_listed(project):
    names = {p["name"] for p in pr.list_profiles(project)["profiles"]}
    assert names == {"supabase-nextjs", "vite-hono", "python-plugin-monorepo", "chat-first-json"}


def test_non_profile_registry_matches_bundled_dir():
    shipped = {p.name for p in Path(pr.bundled_dir()).iterdir() if p.is_file()}
    stack = {n + ".json" for n in pr.bundled_names()}
    assert shipped == stack | set(pr.NON_PROFILE_FILES)
    assert set(pr.NON_PROFILE_FILES) <= shipped  # both directions


# (9) list ---------------------------------------------------------------------------
def test_list_shape_and_invalid_entries(project, user_dir):
    _write(_proj_dir(project), "good")
    (_proj_dir(project) / "broken.json").write_text("{", encoding="utf-8")
    out = pr.list_profiles(project)
    assert out["contract_version"] == 1
    assert set(out) == {"contract_version", "profiles", "warnings", "searched"}
    rows = {r["name"]: r for r in out["profiles"]}
    assert rows["good"]["valid"] is True and rows["good"]["source"] == "project"
    assert rows["broken"]["valid"] is False and "not valid JSON" in rows["broken"]["error"]
    assert set(rows["good"]) == {"name", "source", "path", "valid", "error", "kind",
                                 "schema_version", "description", "shadows"}


def test_invalid_candidate_keeps_ownership_of_its_name(project):
    (_proj_dir(project)).mkdir(parents=True)
    (_proj_dir(project) / "vite-hono.json").write_text("{", encoding="utf-8")
    row = next(r for r in pr.list_profiles(project)["profiles"] if r["name"] == "vite-hono")
    assert row["source"] == "project" and row["valid"] is False
    assert any(s.endswith("vite-hono.json") for s in row["shadows"])


def test_unreadable_user_dir_is_a_warning_and_absent_for_resolve(project, tmp_path, monkeypatch):
    not_a_dir = tmp_path / "file-not-dir"
    not_a_dir.write_text("x", encoding="utf-8")
    monkeypatch.setenv(pr.USER_DIR_ENV, str(not_a_dir))
    out = pr.list_profiles(project)
    assert any(str(not_a_dir) in w for w in out["warnings"])
    assert pr.resolve_profile("vite-hono", project).source == "bundled"


# (10) user dir env / missing home -------------------------------------------------------
def test_user_dir_env_and_default_and_missing_home(monkeypatch, tmp_path):
    monkeypatch.setenv(pr.USER_DIR_ENV, str(tmp_path / "u"))
    assert pr.user_dir() == str(tmp_path / "u")
    monkeypatch.delenv(pr.USER_DIR_ENV)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p)  # home undeterminable
    assert pr.user_dir() is None
    assert [s for s, _ in pr.search_dirs(tmp_path)] == ["project", "bundled"]
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home"))
    assert pr.user_dir() == os.path.join(str(tmp_path / "home"), ".shipwright", "profiles")
    assert [s for s, _ in pr.search_dirs(tmp_path)] == ["project", "user", "bundled"]
