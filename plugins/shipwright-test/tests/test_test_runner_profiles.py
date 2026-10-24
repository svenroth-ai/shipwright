"""test_runner resolves profiles through the stack-profile resolver (campaign S2).

Per-loader table (BRIEF S2 1a), test_runner row: sentinel -> DEFAULT_COMMANDS; run
config naming nothing -> legacy ``supabase-nextjs``; unknown / invalid / corrupt /
too new -> an ERROR (exit 2 or 3, JSON on stdout, nothing run). D9: the name-keyed
command table follows PROVENANCE, never the name. Tagged to FR-01.06 (see
shared/tests/test_profile_resolver.py for the FR note).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib import test_runner  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

_PLUGIN = Path(__file__).resolve().parent.parent
_SHARED = _PLUGIN.parent.parent / "shared"


def _project(tmp_path, run_config=None, raw=None, name="proj"):
    root = tmp_path / name
    root.mkdir()
    if raw is not None:
        (root / "shipwright_run_config.json").write_text(raw, encoding="utf-8")
    elif run_config is not None:
        (root / "shipwright_run_config.json").write_text(json.dumps(run_config), encoding="utf-8")
    return root


def _profile(root, name, **data):
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **data}), encoding="utf-8")
    return path


def _main(monkeypatch, capsys, root, *argv):
    ran = []
    monkeypatch.setattr(test_runner, "run_tests",
                        lambda cmd, cwd=None: ran.append(cmd) or {"success": True})
    monkeypatch.setattr(sys, "argv", ["test_runner.py", "--cwd", str(root), *argv])
    code = test_runner.main()
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err, ran


def test_custom_project_profile_command_is_used_and_source_reported(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", testing={"unit": {"command": "make check"}})
    code, out, err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
    assert code == 0 and ran == ["make check"] and out["profile_source"] == "project"
    assert "source=project" in err  # D8a


def test_corrupt_profile_is_exit_3_naming_the_file_nothing_runs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "supabase-nextjs"})  # a bundled name
    path = root / ".shipwright" / "profiles" / "supabase-nextjs.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    code, out, err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
    assert code == 3 and ran == [] and out["success"] is False and out["kind"] == "invalid"
    assert str(path) in out["error"] and str(path) in err


def test_unknown_profile_is_exit_2_with_the_remediation_text(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "no-such-stack"})
    code, out, _err, ran = _main(monkeypatch, capsys, root)
    assert code == 2 and ran == [] and out["kind"] == "not_found"
    assert "Searched" in out["error"]
    assert "fix `profile` in shipwright_run_config.json, add the profile file, or set it to generic" in out["error"]


def test_invalid_name_in_run_config_is_an_error_not_supabase_nextjs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "My_Stack"})
    code, out, _err, ran = _main(monkeypatch, capsys, root)
    assert code == 3 and ran == [] and "Invalid profile name" in out["error"]


def test_corrupt_run_config_is_an_error_not_supabase_nextjs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, raw="{nope")
    code, out, _err, ran = _main(monkeypatch, capsys, root)
    assert code == 3 and ran == [] and "shipwright_run_config.json" in out["error"]
    code, out, _err, ran = _main(monkeypatch, capsys, _project(tmp_path, {"profile": 5}, name="b"))
    assert code == 3 and ran == []  # a non-string `profile`


def test_run_config_naming_nothing_keeps_the_legacy_supabase_default(tmp_path, monkeypatch, capsys):
    for i, run_config in enumerate((None, {}, {"profile": None})):
        root = _project(tmp_path, run_config, name=f"p{i}")
        code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
        assert code == 0 and ran == ["npx vitest run"] and out["profile_source"] == "bundled"


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_sentinel_uses_default_commands_from_the_built_in_source(tmp_path, monkeypatch, capsys, sentinel):
    root = _project(tmp_path, {"profile": sentinel})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
    assert code == 0 and ran == ["npm test"] and out["profile_source"] == "builtin"


def test_d9_project_profile_named_like_a_bundled_one_gets_its_own_commands(tmp_path, monkeypatch, capsys):
    """The name-keyed table (npx vitest / playwright) is bundled-only (D9)."""
    root = _project(tmp_path, {"profile": "supabase-nextjs"})
    _profile(root, "supabase-nextjs", testing={"unit": "make mine"})
    code, out, err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
    assert ran == ["make mine"] and out["profile_source"] == "project"
    assert "shadows the bundled profile 'supabase-nextjs'" in err  # D8b
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "pgtap")
    assert out.get("skipped") is True and ran == []  # not `npx supabase test db`


def test_d9_prose_shaped_invocation_passes_name_and_project_root(tmp_path):
    """D8f: `test_runner.py --profile {profile} --cwd {project_root}` resolves natively."""
    root = _project(tmp_path)
    _profile(root, "supabase-nextjs", testing={"unit": "echo custom-unit"})
    script = _PLUGIN / "scripts" / "lib" / "test_runner.py"
    done = subprocess.run([sys.executable, str(script), "--profile", "supabase-nextjs",
                           "--cwd", str(root), "--layer", "unit"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = json.loads(done.stdout)
    assert done.returncode == 0 and out["command"] == "echo custom-unit"
    assert out["profile_source"] == "project"


def test_too_new_schema_version_is_drift_exit_3(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", schema_version=99, testing={"unit": "x"})
    code, out, _err, ran = _main(monkeypatch, capsys, root)
    assert code == 3 and out["kind"] == "schema_drift" and ran == []


def test_explicit_profile_path_is_validated_and_classified_explicit(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    good = tmp_path / "p.json"
    good.write_text(json.dumps({"name": "supabase-nextjs", "testing": {"unit": "make x"}}), encoding="utf-8")
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", str(good), "--layer", "unit")
    assert ran == ["make x"] and out["profile_source"] == "explicit"  # custom: never bundled defaults
    bad = tmp_path / "bad.json"
    bad.write_text("[1]", encoding="utf-8")
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", str(bad))
    assert code == 3 and "JSON object" in out["error"] and ran == []


def test_explicit_command_needs_no_profile(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "no-such-stack"})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--command", "echo hi", "--layer", "unit")
    assert code == 0 and ran == ["echo hi"] and out["profile_source"] is None


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
    shutil.copytree(_SHARED / "profiles", cache / "shared" / "profiles",
                    ignore=shutil.ignore_patterns("deploy"))
    root = _project(tmp_path)
    _profile(root, "my-stack", testing={"unit": "echo from-cache-layout"})
    done = subprocess.run([sys.executable, str(lib / "test_runner.py"), "--profile", "my-stack",
                           "--cwd", str(root), "--layer", "unit"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = json.loads(done.stdout)
    assert done.returncode == 0 and out["profile_source"] == "project"
    assert out["command"] == "echo from-cache-layout"


def test_importing_test_runner_leaves_shared_scripts_off_sys_path():
    shared_scripts = _SHARED / "scripts"
    probe = ("import os, sys; sys.path.insert(0, sys.argv[1]); import test_runner; "
             "print([p for p in sys.path if os.path.normcase(os.path.abspath(p)) == "
             "os.path.normcase(sys.argv[2])])")
    done = subprocess.run([sys.executable, "-I", "-c", probe, str(_PLUGIN / "scripts" / "lib"),
                           str(shared_scripts)], capture_output=True, text=True, encoding="utf-8",
                          timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]"


def test_mixed_case_sentinel_is_an_error_not_a_sentinel(tmp_path, monkeypatch, capsys):
    code, out, _err, ran = _main(monkeypatch, capsys, _project(tmp_path, {"profile": "Generic"}))
    assert code == 3 and ran == [] and "reserved name" in out["error"]


def test_explicit_path_inside_a_project_dir_still_warns_about_shadowing(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    path = _profile(root, "vite-hono", testing={"unit": "make mine"})
    code, out, err, ran = _main(monkeypatch, capsys, root, "--profile-path", str(path), "--layer", "unit")
    assert ran == ["make mine"] and out["profile_source"] == "project"  # classified, not "bundled"
    assert "shadows the bundled profile 'vite-hono'" in err  # D8b on the --profile-path crossing too


def _bundled(name):
    return str(_SHARED / "profiles" / f"{name}.json")


def test_prose_shaped_bundled_profile_path_resolves_by_name(tmp_path, monkeypatch, capsys):
    """`--profile X --profile-path <bundled>/X.json` (skill prose until S4) is the NAME, not a file."""
    root = _project(tmp_path)
    _profile(root, "vite-hono", testing={"unit": "make shadow"})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile", "vite-hono",
                                 "--profile-path", _bundled("vite-hono"), "--layer", "unit")
    assert ran == ["make shadow"] and out["profile_source"] == "project"  # the project shadow wins
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile", "generic",
                                 "--profile-path", _bundled("generic"), "--layer", "unit")
    assert code == 0 and out["profile_source"] == "builtin" and ran == ["npm test"]


def test_custom_profile_without_the_layer_command_is_an_error_not_npx(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", testing={})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "unit")
    assert code == 3 and ran == [] and "defines no unit command" in out["error"]


def test_project_root_flag_drives_the_lookup(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _profile(root, "my-stack", testing={"unit": "make rooted"})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    code, out, _err, ran = _main(monkeypatch, capsys, elsewhere, "--profile", "my-stack",
                                 "--project-root", str(root), "--layer", "unit")
    assert ran == ["make rooted"] and out["profile_source"] == "project"


def test_custom_profile_e2e_command_runs_instead_of_playwright(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", testing={"unit": "make u", "e2e": "make e2e"})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "e2e")
    assert ran == ["make e2e"] and out["profile_source"] == "project"


def test_cli_origin_not_found_hint_names_the_option_not_the_run_config(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "fine"})
    code, out, _err, _ran = _main(monkeypatch, capsys, root, "--profile", "typo-stack")
    assert code == 2 and "--profile option" in out["error"]
    assert "`profile` in shipwright_run_config.json" in out["error"]  # brief item 6: both sources named


def test_step_1_prose_shape_only_a_bundled_profile_path_resolves_by_name(tmp_path, monkeypatch, capsys):
    """The live prose passes ONLY `--profile-path <shared>/profiles/X.json` (no --profile)."""
    root = _project(tmp_path)
    _profile(root, "vite-hono", testing={"unit": "make shadow"})
    code, out, err, ran = _main(monkeypatch, capsys, root, "--profile-path", _bundled("vite-hono"), "--layer", "unit")
    assert ran == ["make shadow"] and out["profile_source"] == "project"
    assert "shadows the bundled profile 'vite-hono'" in err  # D8b reaches the executing loader
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", _bundled("supabase-nextjs"),
                                 "--layer", "unit")
    assert ran == ["npx vitest run"] and out["profile_source"] == "bundled"  # unchanged for bundled
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", _bundled("generic"), "--layer", "unit")
    assert code == 0 and ran == ["npm test"] and out["profile_source"] == "builtin"  # no generic.json needed


def _prose_paths(tmp_path, stem):
    """The bundled path as the prose renders it: un-normalised, and (when allowed) through a symlink."""
    paths = [str(_PLUGIN / "scripts" / ".." / ".." / ".." / "shared" / "profiles" / f"{stem}.json")]
    link = tmp_path / "linked-shared"
    try:
        link.symlink_to(_SHARED, target_is_directory=True)
        paths.append(str(link / "profiles" / f"{stem}.json"))
    except (OSError, NotImplementedError):
        pass  # no symlink privilege here; the un-normalised variant still runs
    return paths


def test_prose_path_through_dotdot_or_symlink_still_resolves_by_name(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    for path in _prose_paths(tmp_path, "generic"):
        code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", path, "--layer", "unit")
        assert code == 0 and out["profile_source"] == "builtin" and ran == ["npm test"], path
    _profile(root, "vite-hono", testing={"unit": "make shadow"})
    for path in _prose_paths(tmp_path, "vite-hono"):
        code, out, err, ran = _main(monkeypatch, capsys, root, "--profile-path", path, "--layer", "unit")
        assert ran == ["make shadow"] and out["profile_source"] == "project", path
        assert "shadows the bundled profile 'vite-hono'" in err


def test_empty_profile_in_prose_falls_through_to_the_run_config_default(tmp_path, monkeypatch, capsys):
    """`profile: null` renders `--profile "" --profile-path <bundled>/.json`: names nothing -> table 1a."""
    root = _project(tmp_path)
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile", "", "--profile-path",
                                 _bundled(""), "--layer", "unit")
    assert code == 0 and ran == ["npx vitest run"] and out["profile_source"] == "bundled"  # legacy default


def test_literal_null_profile_is_not_found_naming_the_path_origin(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--profile-path", _bundled("null"), "--layer", "unit")
    assert code == 2 and ran == [] and "--profile-path option" in out["error"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink semantics: `link/..` is followed, not collapsed")
def test_symlinked_plugin_root_with_dotdot_still_resolves_by_name(tmp_path, monkeypatch, capsys):
    link = tmp_path / "link_to_plugin"
    link.symlink_to(_PLUGIN, target_is_directory=True)  # two levels below the repo root
    path = f"{link}/../../shared/profiles/generic.json"
    code, out, _err, ran = _main(monkeypatch, capsys, _project(tmp_path), "--profile-path", path, "--layer", "unit")
    assert code == 0 and out["profile_source"] == "builtin" and ran == ["npm test"]


def test_custom_profile_declaring_a_layer_without_a_command_is_an_error_not_a_skip(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", testing={"unit": "make u", "e2e": {"framework": "playwright"}})
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "e2e")
    assert code == 3 and ran == [] and "defines no e2e command" in out["error"]
    code, out, _err, ran = _main(monkeypatch, capsys, root, "--layer", "pgtap")  # not declared at all: may skip
    assert code == 0 and out.get("skipped") is True and ran == []
