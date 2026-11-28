"""Readers and writers routed off frozen names in R1c-2 find a file in the NEW place (BRIEF 12.2 / 12.10).

Each case puts the file only under ``.shipwright/config/`` (``.shipwright/runtime/`` for the dev server)
and drives the real module function. Before R1c-2 every one of them joined ``root / CONST`` and would see
nothing there. The legacy layout is covered by the rest of the suite, which still writes root files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "scripts"))

import accepted_risks  # noqa: E402
import inline_suppression_baseline  # noqa: E402
import project_facts  # noqa: E402
from dev_server import state as dev_state  # noqa: E402
from lib import adr_collision_baseline, bloat_baseline  # noqa: E402
from lib import config as shared_config  # noqa: E402
from lib import shipwright_paths as sp  # noqa: E402


def _new(root: Path, key: str, text: str) -> Path:
    p = root / sp.new_rel(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.covers("FR-01.11")
def test_config_readers_read_the_new_place(tmp_path):
    _new(tmp_path, "project_config", json.dumps({"marker": "new-project"}))
    _new(tmp_path, "run_config", json.dumps({"marker": "new-run"}))
    assert shared_config.read_config("project", tmp_path) == {"marker": "new-project"}
    assert shared_config.read_all_configs(tmp_path)["run"] == {"marker": "new-run"}
    assert project_facts.read_run_config(tmp_path)["marker"] == "new-run"


@pytest.mark.covers("FR-01.11")
def test_a_baseline_reader_reads_the_new_place(tmp_path):
    _new(tmp_path, "adr_collision_baseline", json.dumps({"entries": {"097": ["097-a.md", "097-b.md"]}}))
    assert adr_collision_baseline.load(tmp_path) == {"97": ["097-a.md", "097-b.md"]}


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("key, locate", [
    ("accepted_risks", accepted_risks.register_path),
    ("inline_suppressions", inline_suppression_baseline.baseline_path),
    ("bloat_baseline", bloat_baseline.baseline_path),
])
def test_path_helpers_point_at_the_new_place(tmp_path, key, locate):
    assert locate(tmp_path) == tmp_path / sp.legacy_rel(key)   # unmigrated: the root, as before
    moved = _new(tmp_path, key, "{}")
    assert locate(tmp_path) == moved


@pytest.mark.covers("FR-01.11")
def test_the_dev_server_state_follows_its_file(tmp_path):
    """D1: runtime state, so its new place is ``.shipwright/runtime/``. A writer keeps the root until R3
    (nothing there yet) and writes the new copy once it exists."""
    dev_state._save_state(tmp_path, {"marker": 1})
    assert (tmp_path / sp.legacy_rel("dev_server")).is_file()
    (tmp_path / sp.legacy_rel("dev_server")).unlink()
    moved = _new(tmp_path, "dev_server", "{}")
    assert moved.parent.name == "runtime"
    dev_state._save_state_atomic(tmp_path, {"marker": 2})   # the production writer
    assert json.loads(moved.read_text(encoding="utf-8")) == {"marker": 2}
    assert not (tmp_path / sp.legacy_rel("dev_server")).exists()


@pytest.mark.covers("FR-01.11")
def test_two_copies_stop_a_routed_reader(tmp_path):
    (tmp_path / sp.legacy_rel("project_config")).write_text("{}", encoding="utf-8")
    _new(tmp_path, "project_config", "{}")
    with pytest.raises(sp.LayoutError) as exc:
        shared_config.read_config("project", tmp_path)
    assert exc.value.code == "both_copies"


@pytest.mark.covers("FR-01.11")
def test_the_session_start_hook_recognises_a_moved_project(tmp_path):
    """Integration: the real SessionStart hook, run as Claude Code runs it (own process, stdin payload),
    finds the run config only in ``.shipwright/config/`` and injects its context."""
    import os
    import subprocess
    _new(tmp_path, "run_config", json.dumps({"status": "complete"}))
    hook = REPO / "shared" / "scripts" / "hooks" / "session_start_using_shipwright.py"
    env = {**os.environ, "SHIPWRIGHT_PROJECT_ROOT": str(tmp_path)}
    out = subprocess.run([sys.executable, str(hook)], input=json.dumps({"session_id": "moved-1"}),
                         capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert out.returncode == 0, out.stderr
    assert "additionalContext" in out.stdout, (out.stdout, out.stderr)
    assert not (tmp_path / sp.legacy_rel("run_config")).exists()


@pytest.mark.covers("FR-01.11")
def test_a_writer_updates_the_new_copy_and_creates_no_root_copy(tmp_path):
    moved = _new(tmp_path, "project_config", json.dumps({"a": 1}))
    shared_config.update_config("project", tmp_path, {"b": 2})
    assert json.loads(moved.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert not (tmp_path / sp.legacy_rel("project_config")).exists()


@pytest.mark.covers("FR-01.11")
def test_the_stack_profile_is_read_from_the_new_place(tmp_path):
    import profile_consumer
    _new(tmp_path, "run_config", json.dumps({"profile": "python-uv"}))
    _new(tmp_path, "project_config", json.dumps({"profile": "generic"}))
    assert profile_consumer.config_profile(tmp_path) == "python-uv"
    assert profile_consumer.config_profile(tmp_path, "project_config") == "generic"
    with pytest.raises(ValueError, match="registry key"):
        profile_consumer.config_profile(tmp_path, sp.legacy_rel("run_config"))   # the pre-R1c-2 calling style


def _security_gate():
    import importlib.util
    f = REPO / "plugins" / "shipwright-compliance" / "scripts" / "lib" / "security_gate.py"
    spec = importlib.util.spec_from_file_location("security_gate_under_test", f)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.covers("FR-01.11")
def test_the_security_gate_reads_the_new_place_and_never_widens_on_two_copies(tmp_path):
    gate = _security_gate()
    cfg = json.dumps({"enforcement": {"allowed_critical_findings": 3}})
    _new(tmp_path, "compliance_config", cfg)
    assert gate.load_threshold(tmp_path) == 3
    (tmp_path / sp.legacy_rel("compliance_config")).write_text(cfg, encoding="utf-8")
    assert gate.load_threshold(tmp_path) == 0   # two copies: zero tolerance, no exception into the fail-open hook
