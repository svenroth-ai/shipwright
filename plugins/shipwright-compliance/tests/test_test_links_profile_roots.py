"""A stack profile may declare the folders that hold its tests (GitHub issue #972).

``vite-hono`` keeps tests below ``server/`` and ``client/``; none of the conventional TOP-LEVEL
folders exists, so the collector used to scan nothing. The profile now names the folders, read only
when the project's ``shipwright_compliance_config.json`` sets no ``traceability.test_roots`` itself.
Tiers REPLACE (config, else profile, else defaults), user-level profiles are never consulted, and
profile entries pass the same containment checks as config entries.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PLUGIN = _HERE.parent
sys.path.insert(0, str(_PLUGIN))

from scripts.lib.collectors import _test_links_io as io  # noqa: E402
from scripts.lib.collectors import _test_links_profile_roots as pr_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch, tmp_path):
    io._WARNED_NO_ROOTS.clear()
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", str(tmp_path / "no-user-profiles"))
    yield
    io._WARNED_NO_ROOTS.clear()


def _layout(root: Path) -> None:
    for d in ("server/tests", "server/src", "client/src", "client/e2e"):
        (root / d).mkdir(parents=True)


def _run_config(root: Path, profile) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")


def _project_profile(root: Path, name: str, body: dict) -> None:
    d = root / ".shipwright" / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps({"name": name, **body}), encoding="utf-8")


def _rels(root: Path, paths) -> list[str]:
    return [p.relative_to(root).as_posix() for p in paths]


@pytest.mark.covers("FR-01.10/AC16")
def test_vite_hono_profile_roots_are_used_without_any_config(tmp_path, capsys):
    _layout(tmp_path)
    _run_config(tmp_path, "vite-hono")
    roots = io.configured_test_roots(tmp_path)
    assert _rels(tmp_path, roots) == ["server/tests", "server/src", "client/src", "client/e2e"]
    assert capsys.readouterr().err == ""  # declared folders that do not exist are skipped silently


@pytest.mark.covers("FR-01.10/AC16")
def test_a_tagged_test_in_a_nested_folder_reaches_the_manifest(tmp_path):
    _layout(tmp_path)
    _run_config(tmp_path, "vite-hono")
    spec = tmp_path / ".shipwright" / "planning" / "01-app"
    spec.mkdir(parents=True)
    (spec / "spec.md").write_text(
        "# Spec\n## Functional Requirements\n| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
        "| FR-07.01 | Widget renders | Must | unit |\n", encoding="utf-8")
    (tmp_path / "server" / "tests" / "widget.test.ts").write_text(
        "// @covers FR-07.01\nit('renders', () => {});\n", encoding="utf-8")
    (tmp_path / "client" / "e2e" / "widget.spec.ts").write_text(
        "// @covers FR-07.01\nit('renders in the browser', () => {});\n", encoding="utf-8")
    from scripts.lib.collectors.test_links import build_manifest

    manifest = build_manifest(
        tmp_path, spec_files=io.discover_specs(tmp_path), test_roots=io.configured_test_roots(tmp_path),
        prune_dirs=io.configured_prune_dirs(tmp_path), evidence={}, source_commit="a" * 40,
    )
    linked = [t for node in manifest["requirements"].values() for ts in node["tests"].values() for t in ts]
    paths = {t["path"].split("::")[0] for t in linked}
    assert {"server/tests/widget.test.ts", "client/e2e/widget.spec.ts"} <= paths


@pytest.mark.covers("FR-01.10/AC16")
def test_the_compliance_config_replaces_the_profile(tmp_path):
    _layout(tmp_path)
    _run_config(tmp_path, "vite-hono")
    (tmp_path / "shipwright_compliance_config.json").write_text(
        json.dumps({"traceability": {"test_roots": ["client/e2e"]}}), encoding="utf-8")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["client/e2e"]


@pytest.mark.covers("FR-01.10/AC16")
@pytest.mark.parametrize("profile", [None, "", "generic", "detecting"])
def test_no_usable_profile_keeps_the_defaults_silently(tmp_path, capsys, profile):
    (tmp_path / "tests").mkdir()
    if profile is not None:
        _run_config(tmp_path, profile)
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC16")
def test_a_profile_without_test_roots_keeps_the_defaults(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    _run_config(tmp_path, "supabase-nextjs")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC16")
def test_an_unknown_profile_warns_once_and_uses_the_defaults(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    _run_config(tmp_path, "no-such-stack")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    err = capsys.readouterr().err
    assert err.count("was not found") == 1 and "user-level profiles are not consulted" in err
    assert "traceability.test_roots" in err
    io.configured_test_roots(tmp_path)
    assert capsys.readouterr().err == ""  # once per project root


@pytest.mark.covers("FR-01.10/AC16")
def test_a_user_level_profile_is_never_consulted(tmp_path, capsys, monkeypatch):
    user = tmp_path / "user-profiles"
    user.mkdir()
    (user / "mine.json").write_text(
        json.dumps({"name": "mine", "traceability": {"test_roots": ["x"]}}), encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", str(user))
    project = tmp_path / "proj"
    (project / "tests").mkdir(parents=True)
    _run_config(project, "mine")
    assert _rels(project, io.configured_test_roots(project)) == ["tests"]
    assert "was not found" in capsys.readouterr().err


@pytest.mark.covers("FR-01.10/AC16")
def test_a_corrupt_run_config_degrades_with_one_line(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    (tmp_path / "shipwright_run_config.json").write_text("{ not json", encoding="utf-8")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    assert capsys.readouterr().err.count("shipwright_run_config.json could not be read") == 1


@pytest.mark.covers("FR-01.10/AC16")
def test_a_wrong_typed_profile_degrades_with_one_line(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    _project_profile(tmp_path, "custom", {"traceability": {"test_roots": "server/tests"}})
    _run_config(tmp_path, "custom")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    assert capsys.readouterr().err.count("stack profile 'custom' could not be read") == 1


@pytest.mark.covers("FR-01.10/AC16")
def test_profile_entries_that_escape_the_project_are_dropped(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "proj"
    (project / "ok").mkdir(parents=True)
    _project_profile(project, "custom", {"traceability": {"test_roots": [
        "../outside", str(outside), "**/tests", "", "ok"]}})
    _run_config(project, "custom")
    assert _rels(project, io.configured_test_roots(project)) == ["ok"]


@pytest.mark.covers("FR-01.10/AC16")
def test_declared_folders_that_do_not_exist_warn_and_fall_back(tmp_path, capsys):
    (tmp_path / "app").mkdir()  # a default folder the vite-hono list does not name
    _run_config(tmp_path, "vite-hono")  # server/ and client/ are absent here
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["app"]
    err = capsys.readouterr().err
    assert "'vite-hono'" in err and "none of those folders exists" in err


@pytest.mark.covers("FR-01.10/AC16")
def test_an_empty_declared_list_counts_as_absent(tmp_path, capsys):
    (tmp_path / "tests").mkdir()
    _project_profile(tmp_path, "custom", {"traceability": {"test_roots": []}})
    _run_config(tmp_path, "custom")
    assert _rels(tmp_path, io.configured_test_roots(tmp_path)) == ["tests"]
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC16")
def test_an_unknown_profile_with_no_default_folder_writes_exactly_one_line(tmp_path, capsys):
    _run_config(tmp_path, "no-such-stack")  # no tests/, src/ ... either: the empty-scan warning would also fire
    assert io.configured_test_roots(tmp_path) == []
    err = capsys.readouterr().err
    assert err.count("[test_links]") == 1 and "was not found" in err


@pytest.mark.covers("FR-01.10/AC16")
def test_warn_false_is_silent_for_throwaway_trees(tmp_path, capsys):
    _run_config(tmp_path, "no-such-stack")
    assert io.configured_test_roots(tmp_path, warn=False) == []
    assert capsys.readouterr().err == ""
    other = tmp_path / "other"
    other.mkdir()
    (other / "shipwright_compliance_config.json").write_text(
        json.dumps({"traceability": {"test_roots": "server/tests"}}), encoding="utf-8")
    assert io.configured_test_roots(other, warn=False) == []  # a non-list config value stays quiet too
    assert capsys.readouterr().err == ""


@pytest.mark.covers("FR-01.10/AC16")
def test_without_profile_support_the_lookup_returns_nothing(tmp_path, monkeypatch):
    # Only the `_pc is None` guard; the ImportError branch itself is covered by the subprocess test below.
    monkeypatch.setattr(pr_mod, "_pc", None)
    _run_config(tmp_path, "vite-hono")
    assert pr_mod.profile_test_roots(tmp_path) == ("", [])


@pytest.mark.covers("FR-01.10/AC16")
def test_a_module_placed_where_shared_scripts_does_not_exist_imports_with_no_profile_support(tmp_path):
    src = _PLUGIN / "scripts" / "lib" / "collectors" / "_test_links_profile_roots.py"
    lonely = tmp_path / "a" / "b" / "c" / "d" / "e" / "_probe.py"  # parents[5] has no shared/scripts
    lonely.parent.mkdir(parents=True)
    lonely.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    code = """
import importlib.util, sys
before = list(sys.path)
spec = importlib.util.spec_from_file_location('probe_lonely', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert mod._pc is None, 'profile_consumer must be unreachable here'
assert sys.path == before, 'sys.path changed on the failure path'
assert mod.profile_test_roots(sys.argv[2]) == ('', [])
"""
    proc = subprocess.run([sys.executable, "-I", "-c", code, str(lonely), str(tmp_path)],
                          capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


@pytest.mark.covers("FR-01.10/AC16")
def test_importing_the_module_leaves_sys_path_as_it_found_it(tmp_path):
    shared = str(_PLUGIN.parents[1] / "shared" / "scripts")
    module = str(_PLUGIN / "scripts" / "lib" / "collectors" / "_test_links_profile_roots.py")
    code = """
import importlib.util, sys
shared, module = sys.argv[1], sys.argv[2]

def load(name):
    spec = importlib.util.spec_from_file_location(name, module)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))

sys.path.insert(0, shared)
load('probe_present')
assert sys.path[0] == shared, 'a pre-existing entry was removed'
sys.path.remove(shared)
load('probe_absent')
assert shared not in sys.path, 'the module left its own entry behind'
"""
    proc = subprocess.run([sys.executable, "-I", "-c", code, shared, module],
                          capture_output=True, text=True, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr


@pytest.mark.covers("FR-01.10/AC16")
def test_a_vite_hono_project_keeps_the_links_of_its_top_level_tests_folder(tmp_path):
    # The profile tier REPLACES the defaults, so the list must still reach the conventional top-level
    # folders a vite-hono project may use (the test runner's own tests/integration layout).
    _layout(tmp_path)
    (tmp_path / "tests" / "integration").mkdir(parents=True)
    (tmp_path / "integration-tests").mkdir()
    _run_config(tmp_path, "vite-hono")
    rels = _rels(tmp_path, io.configured_test_roots(tmp_path))
    assert "tests" in rels and "integration-tests" in rels and "client/e2e" in rels
