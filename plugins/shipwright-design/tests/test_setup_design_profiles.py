"""setup-design-session resolves profiles through the stack-profile resolver (campaign S2).

Per-loader table (BRIEF S2 1a), setup-design-session row: reserved sentinel
(``generic`` / ``detecting``, the latter written by the project phase) -> built-in
defaults (empty design_system); no profile in the project config -> the existing
``supabase-nextjs`` default; named but unknown / invalid / too new -> an ERROR.
Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.06")

_PLUGIN = Path(__file__).resolve().parent.parent
_SHARED = _PLUGIN.parent.parent / "shared"
SCRIPT = _PLUGIN / "scripts" / "checks" / "setup-design-session.py"
DESIGN = {"design_system": {"framework": "my-ui"}}


def _project(tmp_path, config=None):
    root = tmp_path / "proj"
    root.mkdir()
    if config is not None:
        (root / "shipwright_project_config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def _profile(root, name, **data):
    path = root / ".shipwright" / "profiles" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name, **data}), encoding="utf-8")
    return path


def _run(root, script=SCRIPT):
    done = subprocess.run([sys.executable, str(script), "--project-root", str(root),
                           "--plugin-root", str(_PLUGIN)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    return done.returncode, json.loads(done.stdout), done.stderr


def test_custom_project_profile_design_system_is_used(tmp_path):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", **DESIGN)
    code, out, err = _run(root)
    assert code == 0 and out["design_system"] == {"framework": "my-ui"}
    assert out["profile_source"] == "project" and "source=project" in err


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_sentinel_means_built_in_defaults_not_an_error(tmp_path, sentinel):
    code, out, _err = _run(_project(tmp_path, {"profile": sentinel}))
    assert code == 0 and out["success"] is True
    assert out["design_system"] == {} and out["profile_source"] == "builtin"


def test_no_profile_in_config_keeps_the_supabase_default(tmp_path):
    for i, config in enumerate((None, {}, {"other": 1})):
        sub = tmp_path / str(i)
        sub.mkdir()
        code, out, _err = _run(_project(sub, config))
        assert code == 0 and out["profile"] == "supabase-nextjs" and out["profile_source"] == "bundled"
        assert out["design_system"]  # the bundled supabase-nextjs design_system, unchanged


def test_unknown_profile_is_an_error_with_remediation(tmp_path):
    code, out, err = _run(_project(tmp_path, {"profile": "no-such-stack"}))
    assert code == 2 and out["success"] is False and out["kind"] == "not_found"
    assert "Searched" in out["error"] and "shipwright_project_config.json" in out["error"]
    assert "set it to generic" in out["error"] and "no-such-stack" in err


def test_corrupt_profile_names_the_file_and_does_not_fall_back_to_bundled(tmp_path):
    root = _project(tmp_path, {"profile": "vite-hono"})
    path = root / ".shipwright" / "profiles" / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    code, out, _err = _run(root)
    assert code == 3 and out["kind"] == "invalid" and str(path) in out["error"]


def test_too_new_schema_version_is_drift(tmp_path):
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", schema_version=99)
    code, out, _err = _run(root)
    assert code == 3 and out["kind"] == "schema_drift"


def test_shadowing_a_bundled_name_warns_on_stderr(tmp_path):
    root = _project(tmp_path, {"profile": "vite-hono"})
    _profile(root, "vite-hono", **DESIGN)
    code, out, err = _run(root)
    assert out["design_system"] == {"framework": "my-ui"}
    assert "shadows the bundled profile 'vite-hono'" in err


def test_resolver_imports_through_the_plugin_cache_layout(tmp_path):
    """Stale-cache rule: <cache>/shipwright/<plugin>/<ver>/scripts/checks -> parents[4]/shared."""
    cache = tmp_path / "cache" / "shipwright"
    plugin = cache / "shipwright-design" / "9.9.9"
    shutil.copytree(_PLUGIN / "scripts", plugin / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    scripts = cache / "shared" / "scripts"
    (scripts / "lib").mkdir(parents=True)
    for name in ("profile_resolver.py", "profile_model.py", "profile_schema_check.py", "profile_consumer.py"):
        shutil.copy(_SHARED / "scripts" / name, scripts / name)
    shutil.copy(_SHARED / "scripts" / "lib" / "planning_discovery.py", scripts / "lib" / "planning_discovery.py")
    shutil.copytree(_SHARED / "schemas", cache / "shared" / "schemas")
    shutil.copytree(_SHARED / "profiles", cache / "shared" / "profiles", ignore=shutil.ignore_patterns("deploy"))
    root = _project(tmp_path, {"profile": "my-stack"})
    _profile(root, "my-stack", **DESIGN)
    code, out, err = _run(root, plugin / "scripts" / "checks" / "setup-design-session.py")
    assert code == 0, err
    assert out["profile_source"] == "project" and out["design_system"] == {"framework": "my-ui"}


def test_mixed_case_sentinel_is_an_error(tmp_path):
    code, out, _err = _run(_project(tmp_path, {"profile": "Detecting"}))
    assert code == 3 and "reserved name" in out["error"]


def test_d6_declared_profile_keys_exist_in_the_schema():
    import importlib.util
    spec = importlib.util.spec_from_file_location("setup_design_session_d6", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    schema = json.loads((_SHARED / "schemas" / "stack_profile.schema.json").read_text(encoding="utf-8"))
    assert mod.PROFILE_KEYS_READ and set(mod.PROFILE_KEYS_READ) <= set(schema["properties"])
