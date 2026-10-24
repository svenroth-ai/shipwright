"""performance_check resolves profiles through the stack-profile resolver (campaign S2).

Per-loader table (BRIEF S2 1a), performance_check row: sentinel / no profile ->
explicit "no budgets (no profile)" and exit 0; unknown / invalid / too new / a
non-object file -> an ERROR (exit 2/3), never "continue with no budgets" and never
a traceback. Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib import performance_check as pcheck  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

_PLUGIN = Path(__file__).resolve().parent.parent
_SHARED = _PLUGIN.parent.parent / "shared"
PERF = {"enabled": True, "bundle": {"max_kb_gz": 7, "build_output_dir": "dist"}}


def _project(tmp_path, run_config=None):
    root = tmp_path / "proj"
    root.mkdir()
    if run_config is not None:
        (root / "shipwright_run_config.json").write_text(json.dumps(run_config), encoding="utf-8")
    return root


def _profile(root, name, **data):
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **data}), encoding="utf-8")
    return path


def _run(monkeypatch, capsys, root, *argv):
    monkeypatch.setattr(sys, "argv", ["performance_check.py", "--cwd", str(root), *argv])
    code = pcheck.main()
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_custom_project_profile_budgets_are_used_by_name(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", testing={"performance": PERF})
    (root / "dist").mkdir()
    code, out, err = _run(monkeypatch, capsys, root)  # name from the run config
    assert out["profile_source"] == "project" and out["skipped"] is False
    assert out["bundle"]["skip_reason"].startswith("no bundle assets matched")  # budgets were applied
    assert "source=project" in err
    code, out, _ = _run(monkeypatch, capsys, root, "--profile", "my-stack", "--project-root", str(root))
    assert out["profile_source"] == "project"


@pytest.mark.parametrize("run_config", [None, {}, {"profile": "generic"}, {"profile": "detecting"}])
def test_no_profile_or_sentinel_is_an_explicit_skip_with_exit_0(tmp_path, monkeypatch, capsys, run_config):
    root = _project(tmp_path, run_config)
    code, out, _err = _run(monkeypatch, capsys, root)
    assert code == 0 and out["success"] is True and out["skipped"] is True
    assert out["skip_reason"] == "no budgets (no profile)"


def test_corrupt_profile_is_exit_3_naming_the_file_and_not_a_budget_free_run(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    path = root / ".shipwright" / "profiles" / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    code, out, err = _run(monkeypatch, capsys, root, "--profile", "vite-hono")
    assert code == 3 and out["success"] is False and out["kind"] == "invalid"
    assert str(path) in out["error"] and str(path) in err


def test_unknown_profile_is_exit_2_with_remediation(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "no-such-stack"})
    code, out, _err = _run(monkeypatch, capsys, root)
    assert code == 2 and out["kind"] == "not_found"
    assert "fix `profile` in shipwright_run_config.json, add the profile file, or set it to generic" in out["error"]
    code, out, _err = _run(monkeypatch, capsys, root, "--profile", "also-missing")
    assert code == 2 and "--profile" in out["error"]


def test_non_object_profile_file_is_a_clear_error_not_a_traceback(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    bad = tmp_path / "list.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile-path", str(bad))
    assert code == 3 and "must be a JSON object" in out["error"]


def test_too_new_schema_version_is_drift(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", schema_version=99)
    code, out, _err = _run(monkeypatch, capsys, root)
    assert code == 3 and out["kind"] == "schema_drift"


def test_explicit_profile_path_is_classified_explicit_and_validated(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    good = tmp_path / "p.json"
    good.write_text(json.dumps({"name": "supabase-nextjs", "testing": {"performance": {"enabled": False}}}),
                    encoding="utf-8")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile-path", str(good))
    assert code == 0 and out["profile_source"] == "explicit"  # a custom file, never "bundled"


def test_shadowing_a_bundled_name_warns(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _profile(root, "vite-hono", testing={"performance": {"enabled": False}})
    _code, out, err = _run(monkeypatch, capsys, root, "--profile", "vite-hono")
    assert out["profile_source"] == "project" and "shadows the bundled profile 'vite-hono'" in err


def test_bundled_profile_behaviour_is_unchanged(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    code, out, _err = _run(monkeypatch, capsys, root, "--profile", "python-plugin-monorepo")
    assert code == 0 and out["profile_source"] == "bundled" and out["skipped"] is True


def test_resolver_imports_through_the_plugin_cache_layout(tmp_path):
    """Stale-cache rule: <cache>/shipwright/<plugin>/<ver>/scripts/lib -> parents[4]/shared."""
    cache = tmp_path / "cache" / "shipwright"
    lib = cache / "shipwright-test" / "9.9.9" / "scripts" / "lib"
    shutil.copytree(_PLUGIN / "scripts" / "lib", lib, ignore=shutil.ignore_patterns("__pycache__"))
    scripts = cache / "shared" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("profile_resolver.py", "profile_model.py", "profile_schema_check.py", "profile_consumer.py"):
        shutil.copy(_SHARED / "scripts" / name, scripts / name)
    shutil.copytree(_SHARED / "schemas", cache / "shared" / "schemas")
    shutil.copytree(_SHARED / "profiles", cache / "shared" / "profiles", ignore=shutil.ignore_patterns("deploy"))
    root = _project(tmp_path)
    _profile(root, "my-stack", testing={"performance": {"enabled": False}})
    done = subprocess.run([sys.executable, str(lib / "performance_check.py"), "--cwd", str(root),
                           "--profile", "my-stack"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["profile_source"] == "project"


def test_explicit_profile_path_wins_over_profile_name(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    good = tmp_path / "p.json"
    good.write_text(json.dumps({"name": "p", "testing": {"performance": {"enabled": False}}}), encoding="utf-8")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile", "no-such-stack", "--profile-path", str(good))
    assert code == 0 and out["profile_source"] == "explicit"


def test_mixed_case_sentinel_is_an_error(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "Detecting"})
    code, out, _err = _run(monkeypatch, capsys, root)
    assert code == 3 and "reserved name" in out["error"]


def test_corrupt_run_config_is_an_error_not_a_no_profile_skip(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    (root / "shipwright_run_config.json").write_text("{nope", encoding="utf-8")
    code, out, _err = _run(monkeypatch, capsys, root)
    assert code == 3 and "shipwright_run_config.json" in out["error"]


def test_prose_shaped_bundled_profile_path_resolves_by_name(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _profile(root, "vite-hono", testing={"performance": {"enabled": False}})
    bundled = str(_SHARED / "profiles" / "vite-hono.json")
    _code, out, _err = _run(monkeypatch, capsys, root, "--profile", "vite-hono", "--profile-path", bundled)
    assert out["profile_source"] == "project"  # not the bundled file named by the path
    gen = str(_SHARED / "profiles" / "generic.json")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile", "generic", "--profile-path", gen)
    assert code == 0 and out["skip_reason"] == "no budgets (no profile)"


def test_d6_declared_profile_keys_exist_in_the_schema():
    from lib import performance_profile, test_runner
    schema = json.loads((_SHARED / "schemas" / "stack_profile.schema.json").read_text(encoding="utf-8"))
    for mod in (performance_profile, test_runner):
        assert mod.PROFILE_KEYS_READ and set(mod.PROFILE_KEYS_READ) <= set(schema["properties"])


def test_step_3_8_prose_shape_only_a_bundled_profile_path(tmp_path, monkeypatch, capsys):
    """references/step-3.8-performance-budget.md passes ONLY `--profile-path <shared>/profiles/<profile>.json`."""
    root = _project(tmp_path)
    gen = str(_SHARED / "profiles" / "generic.json")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile-path", gen)
    assert code == 0 and out["skip_reason"] == "no budgets (no profile)"  # sentinel: not a missing-file error
    _profile(root, "vite-hono", testing={"performance": {"enabled": False}})
    bundled = str(_SHARED / "profiles" / "vite-hono.json")
    _code, out, err = _run(monkeypatch, capsys, root, "--profile-path", bundled)
    assert out["profile_source"] == "project" and "shadows the bundled profile 'vite-hono'" in err
    (tmp_path / "second").mkdir()
    root2 = _project(tmp_path / "second")
    _code, out, _err = _run(monkeypatch, capsys, root2, "--profile-path", bundled)
    assert out["profile_source"] == "bundled"


def test_prose_path_through_dotdot_or_symlink_and_empty_profile(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    dotdot = str(_PLUGIN / "scripts" / ".." / ".." / ".." / "shared" / "profiles" / "generic.json")
    paths = [dotdot]
    link = tmp_path / "linked-shared"
    try:
        link.symlink_to(_SHARED, target_is_directory=True)
        paths.append(str(link / "profiles" / "generic.json"))
    except (OSError, NotImplementedError):
        pass
    for path in paths:
        code, out, _err = _run(monkeypatch, capsys, root, "--profile-path", path)
        assert code == 0 and out["skip_reason"] == "no budgets (no profile)", path
    # `profile: null` renders an empty name and `<bundled>/.json`: names nothing -> skip, exit 0
    empty = str(_SHARED / "profiles" / ".json")
    code, out, _err = _run(monkeypatch, capsys, root, "--profile", "", "--profile-path", empty)
    assert code == 0 and out["skip_reason"] == "no budgets (no profile)"
    code, out, _err = _run(monkeypatch, capsys, root, "--profile-path", str(_SHARED / "profiles" / "null.json"))
    assert code == 2 and "--profile-path option" in out["error"]
