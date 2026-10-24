"""validate_env resolves profiles through the stack-profile resolver (campaign S2).

Per-loader table (BRIEF S2 1a): reserved sentinel -> ``skipped``; run config with no
profile -> skip as before; named but unknown / invalid / too new -> an ERROR result
(``success: false`` / ``action: "error"``) and a non-zero exit - never a silent pass.
Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from shared.scripts import validate_env as ve
from shared.scripts.validate_env import init_env_file, validate

pytestmark = pytest.mark.covers("FR-01.06")

BUILD = {"required_env_vars": {"build": [{"name": "MY_TOKEN", "description": "my token"}]}}


def _project(tmp_path: Path, profile=..., raw: str | None = None) -> Path:
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    if raw is not None:
        (root / "shipwright_run_config.json").write_text(raw, encoding="utf-8")
    elif profile is not ...:
        (root / "shipwright_run_config.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")
    return root


def _profile(root: Path, name: str, **data) -> Path:
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **data}), encoding="utf-8")
    return path


def test_custom_project_profile_is_used_by_validate_and_init(tmp_path):
    root = _project(tmp_path, "my-stack")
    _profile(root, "my-stack", **BUILD)
    res = validate(root, "build")  # no profile_dir: the resolver decides
    assert res["success"] is False and [m["name"] for m in res["missing"]] == ["MY_TOKEN"]
    assert res["profile_source"] == "project"
    out = init_env_file(root, "build")
    assert out["action"] == "created" and out["vars"] == ["MY_TOKEN"]
    assert "MY_TOKEN" in (root / ".env.local").read_text(encoding="utf-8")


def test_corrupt_profile_is_an_error_naming_the_file_and_bundled_is_not_used(tmp_path):
    root = _project(tmp_path, "vite-hono")
    path = root / ".shipwright" / "profiles" / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    res = validate(root, "build")
    assert (res["success"], res["skipped"], res["kind"], res["exit_code"]) == (False, False, "invalid", 3)
    assert str(path) in res["error"]
    out = init_env_file(root, "build")
    assert out["action"] == "error" and out["reason"] == "profile_invalid" and str(path) in out["error"]
    assert not (root / ".env.local").exists()


def test_unknown_profile_error_text_is_remediation_oriented(tmp_path):
    root = _project(tmp_path, "no-such-stack")
    res = validate(root, "build")
    assert res["success"] is False and res["kind"] == "not_found" and res["exit_code"] == 2
    err = res["error"]
    assert "no-such-stack" in err and "Searched" in err and ".shipwright" in err
    assert "fix `profile` in shipwright_run_config.json, add the profile file, or set it to generic" in err
    out = init_env_file(root, "build")
    assert (out["action"], out["reason"], out["kind"]) == ("error", "profile_not_found", "not_found")
    assert "path" not in out and "env_file_path" not in out  # no stale path keys on error


def test_too_new_schema_version_is_drift_for_validate_and_init(tmp_path):
    root = _project(tmp_path, "my-stack")
    _profile(root, "my-stack", schema_version=99, **BUILD)
    assert validate(root, "build")["kind"] == "schema_drift"
    assert init_env_file(root, "build")["reason"] == "profile_schema_drift"


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_sentinels_skip_without_error_or_scaffold(tmp_path, sentinel):
    root = _project(tmp_path, sentinel)
    res = validate(root, "build")
    assert res["success"] is True and res["skipped"] is True and "built-in" in res["skip_reason"]
    out = init_env_file(root, "build", include_framework=True)  # no framework-only scaffold
    assert out["action"] == "skipped" and not (root / ".env.local").exists()


def test_run_config_with_no_profile_stays_a_skip(tmp_path):
    for raw in ("{}", '{"profile": null}', '{"profile": ""}'):
        root = _project(tmp_path, raw=raw)
        assert validate(root, "build")["skipped"] is True
        assert init_env_file(root, "build")["action"] == "skipped"


def test_corrupt_run_config_is_an_error_not_a_traceback(tmp_path):
    root = _project(tmp_path, raw="{nope")
    res = validate(root, "build")
    assert res["success"] is False and res["kind"] == "invalid" and "shipwright_run_config.json" in res["error"]
    assert init_env_file(root, "build")["action"] == "error"


def test_shadowing_a_bundled_name_warns_on_stderr(tmp_path, capsys):
    root = _project(tmp_path, "vite-hono")
    _profile(root, "vite-hono", **BUILD)
    res = validate(root, "build")
    assert res["profile_source"] == "project"
    assert "shadows the bundled profile 'vite-hono'" in capsys.readouterr().err


def test_bundled_profile_still_resolves_by_default(tmp_path, capsys):
    root = _project(tmp_path, "supabase-nextjs")
    res = validate(root, "build")
    assert res["profile_source"] == "bundled" and res["skipped"] is False
    assert "source=bundled" in capsys.readouterr().err


def test_explicit_profile_dir_goes_through_load_profile_file(tmp_path):
    root = _project(tmp_path, "mine")
    d = tmp_path / "dir"
    d.mkdir()
    (d / "mine.json").write_text(json.dumps({"name": "mine", **BUILD}), encoding="utf-8")
    assert validate(root, "build", d)["profile_source"] == "explicit"
    (d / "mine.json").write_text(json.dumps({"name": "mine", "services": "nope"}), encoding="utf-8")
    assert validate(root, "build", d)["kind"] == "schema_drift"  # D5 applies to explicit files
    assert validate(_project(tmp_path, "absent"), "build", d)["kind"] == "not_found"  # no fall-through


def test_main_exit_code_is_non_zero_for_error_and_init_no_longer_exits_zero(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, "no-such-stack")
    for extra in ([], ["--init"]):
        monkeypatch.setattr(sys, "argv", ["validate_env.py", "--project-root", str(root),
                                          "--phase", "build", *extra])
        assert ve.main() == 2
        assert json.loads(capsys.readouterr().out)["kind"] == "not_found"
    _profile(root, "no-such-stack", schema_version=99)
    monkeypatch.setattr(sys, "argv", ["validate_env.py", "--project-root", str(root),
                                      "--phase", "build", "--init"])
    assert ve.main() == 3


def test_main_exit_code_stays_zero_for_skips_and_init_success(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, "my-stack")
    _profile(root, "my-stack", **BUILD)
    for extra in (["--init"], []):
        monkeypatch.setattr(sys, "argv", ["validate_env.py", "--project-root", str(root),
                                          "--phase", "build", *extra])
        assert ve.main() == (0 if extra else 1)  # validate: MY_TOKEN still missing -> 1, as before
        capsys.readouterr()


def test_importing_validate_env_leaves_shared_scripts_off_sys_path():
    """shared/scripts holds a `tools` package that would shadow a plugin's own."""
    scripts = Path(ve.__file__).resolve().parent
    probe = ("import os, sys; sys.path.insert(0, sys.argv[1]); "
             "import shared.scripts.validate_env; "
             "print([p for p in sys.path if os.path.normcase(os.path.abspath(p)) == "
             "os.path.normcase(sys.argv[2])])")
    done = subprocess.run([sys.executable, "-I", "-c", probe, str(scripts.parents[1]), str(scripts)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_mixed_case_sentinel_is_an_error_not_a_skip(tmp_path):
    root = _project(tmp_path, "Generic")
    assert validate(root, "build")["kind"] == "invalid"
    assert init_env_file(root, "build")["action"] == "error"


def test_d6_declared_profile_keys_exist_in_the_schema():
    schema = json.loads((Path(ve.__file__).resolve().parents[1] / "schemas" / "stack_profile.schema.json")
                        .read_text(encoding="utf-8"))
    assert ve.PROFILE_KEYS_READ and set(ve.PROFILE_KEYS_READ) <= set(schema["properties"])
