"""The release CLI's layout constant, its import boundary, and the run state across separate processes (unit P3).

* ``orchestrator.py`` of the run plugin is reached through ``release_paths`` only; each layout the plugin ships in is built
  as a real tree and resolved (the precedent is ``shipwright-run/tests/test_phase_gate_cache_layouts.py``).
* The CLI's own modules are ``lib.release_*``; no shared module is imported as ``lib.<x>`` (ADR-045, programme P16).
* F14: ``SHIPWRIGHT_RUN_ID`` does not survive separate shell calls, so the run id and the release date ``prepare`` stored are
  what ``aggregate`` reads in ANOTHER process (the old way: the model exported a variable and typed a date).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
pytestmark = pytest.mark.covers("FR-01.09/AC01")  # the tests prove the release steps behave as the requirement says; finer tags where a test names its AC

from lib import release_paths

PLUGIN = Path(__file__).resolve().parents[1]
CLI = PLUGIN / "scripts" / "release.py"
REL = Path(*release_paths.ORCHESTRATOR)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# orchestrator\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("layout", ["checkout", "mirror", "installed", "installed-old-versions", "codex"])
def test_the_orchestrator_resolves_in_every_layout_the_plugin_ships_in(tmp_path, layout):
    if layout == "checkout":
        plugin, want = tmp_path / "plugins" / "shipwright-changelog", tmp_path / "plugins" / "shipwright-run" / REL
    elif layout == "mirror":
        plugin, want = tmp_path / "cache" / "shipwright" / "plugins" / "shipwright-changelog", tmp_path / "cache" / "shipwright" / "plugins" / "shipwright-run" / REL
    elif layout == "codex":
        plugin, want = tmp_path / "bundle" / "0.9.0" / "origin" / "shipwright-changelog", tmp_path / "bundle" / "0.9.0" / "origin" / "shipwright-run" / REL
    else:
        cache = tmp_path / "cache" / "shipwright"
        plugin = cache / "shipwright-changelog" / "0.2.1"
        for old in (["0.9.0", "0.10.0"] if layout == "installed-old-versions" else ["0.36.0"]):
            want = _touch(cache / "shipwright-run" / old / REL)
        if layout == "installed-old-versions":
            want = cache / "shipwright-run" / "0.10.0" / REL  # newest first, numerically: 0.10.0 beats 0.9.0
    plugin.mkdir(parents=True, exist_ok=True)
    _touch(want)
    assert release_paths.orchestrator_path(plugin) == want.resolve()
    assert release_paths.shared_root(plugin) == plugin.resolve().parents[1] / "shared"


def test_an_absent_run_plugin_is_none_not_a_guess(tmp_path):
    plugin = tmp_path / "plugins" / "shipwright-changelog"
    plugin.mkdir(parents=True)
    assert release_paths.orchestrator_path(plugin) is None


def test_this_checkout_finds_the_real_orchestrator_and_shared_tree():
    assert release_paths.orchestrator_path(PLUGIN).is_file() and (release_paths.shared_root(PLUGIN) / "scripts" / "tools").is_dir()


def test_importing_the_cli_pulls_in_no_shared_module_as_lib():
    probe = ("import sys; sys.argv=['x']; sys.path.insert(0, %r); import release, lib; "
             "bad=[m for m in sys.modules if m.startswith('lib.') and 'release' not in m and m not in ('lib',)]; "
             "print(lib.__file__); print(sorted(bad))" % str(PLUGIN / "scripts"))
    done = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    lib_file, bad = done.stdout.strip().splitlines()
    assert Path(lib_file).resolve().parent == (PLUGIN / "scripts" / "lib").resolve() and bad == "[]"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, encoding="utf-8")


def _cli(repo: Path, *args: str) -> tuple[int, dict]:
    done = subprocess.run(["uv", "run", str(CLI), *args, "--project-root", str(repo)], capture_output=True, text=True, encoding="utf-8")
    return done.returncode, json.loads(done.stdout) if done.stdout.strip() else {}


@pytest.mark.covers("FR-01.09/AC07")
def test_aggregate_in_another_process_reads_the_date_and_run_id_prepare_stored(git_repo_with_tag, monkeypatch):
    """Boundary + F14: two real processes, the second sees only the file the first wrote."""
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    repo = git_repo_with_tag
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n- first\n", encoding="utf-8")
    _git(repo, "add", "."), _git(repo, "commit", "-m", "docs: changelog")
    (repo / "CHANGELOG-unreleased.d" / "Added").mkdir(parents=True)
    (repo / "CHANGELOG-unreleased.d" / "Added" / "run_001.md").write_text("A pending entry\n", encoding="utf-8")
    code, prepared = _cli(repo, "prepare")
    assert code == 0 and prepared["status"] == "ok", prepared
    state_file = Path(prepared["release"]["state_file"])
    assert state_file.is_absolute() and ".git" in state_file.parts and not (repo / ".shipwright" / "runtime").exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["release_date"] = "2026-01-15"  # "prepare ran on this day": only the file carries it to the next process
    state_file.write_text(json.dumps(state), encoding="utf-8")
    code, agg = _cli(repo, "aggregate", "--version", prepared["version"])
    assert code == 0 and agg["status"] == "ok", agg
    assert agg["release"] == {"date": "2026-01-15", "run_id": prepared["release"]["run_id"], "state_file": prepared["release"]["state_file"]}
    assert f"## [{prepared['version']}] - 2026-01-15" in (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert prepared["gates"] == {"version": "ask", "preview": "ask", "out_of_sequence": "ask"}
    assert prepared["upgrade_notes"]["status"] == "none_changed" and prepared["paths"]["orchestrator"].endswith("orchestrator.py")
