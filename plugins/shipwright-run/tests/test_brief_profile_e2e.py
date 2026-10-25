"""Wizard brief -> brief_intake -> write-config: the named profile reaches the run config and the
next-step payload (campaign brief-driven-run, B2b). Zero internal imports: CLIs only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INTAKE = ROOT / "shared" / "scripts" / "lib" / "brief_intake.py"
ORCH = ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"

pytestmark = pytest.mark.covers("FR-01.01")


def _env(cwd):
    """The caller's environment minus every SHIPWRIGHT_* variable, with an empty user-profiles dir."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")}
    env["SHIPWRIGHT_USER_PROFILES_DIR"] = str(Path(cwd) / "user-profiles")
    return env


def _run(args, cwd):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=cwd, env=_env(cwd))


def _flow(tmp_path, brief: dict):
    (tmp_path / "wizard-brief.json").write_text(json.dumps(brief), encoding="utf-8")
    took = _run([INTAKE, "--brief", "wizard-brief.json", "--project-root", tmp_path], tmp_path)
    assert took.returncode == 0, took.stdout + took.stderr
    profile = json.loads(took.stdout)["profile"]
    cmd = [ORCH, "write-config", "--scope", "full_app", "--autonomy", "guided", "--project-root", tmp_path]
    wrote = _run(cmd + (["--profile", profile] if profile else []), tmp_path)
    assert wrote.returncode == 0, wrote.stdout + wrote.stderr
    cfg = json.loads((tmp_path / "shipwright_run_config.json").read_text(encoding="utf-8"))
    nxt = _run([ORCH, "get-next-step", "--project-root", tmp_path], tmp_path)
    assert nxt.returncode == 0, nxt.stdout + nxt.stderr
    return cfg, json.loads(nxt.stdout)


def test_named_project_profile_reaches_run_config_and_next_step(tmp_path):
    pdir = tmp_path / ".shipwright" / "profiles"
    pdir.mkdir(parents=True)
    (pdir / "acme-stack.json").write_text(json.dumps({"name": "acme-stack", "description": "acme"}), encoding="utf-8")
    brief = {"description": "A tool", "users": "team", "persistence": "yes", "run_location": "local", "profile": "acme-stack"}
    cfg, step = _flow(tmp_path, brief)
    assert cfg["profile"] == "acme-stack"  # persistence=yes alone would have inferred supabase-nextjs
    assert step["profile"] == "acme-stack"  # the key later phases read from get-next-step


def test_brief_without_profile_keeps_the_inferred_one(tmp_path):
    brief = {"description": "A tool", "users": "team", "persistence": "no", "run_location": "local"}
    cfg, _ = _flow(tmp_path, brief)
    assert cfg["profile"] == "vite-hono"


def test_unknown_profile_stops_at_intake_and_picks_no_fallback(tmp_path):
    brief = {"description": "A tool", "persistence": "yes", "profile": "no-such-stack"}
    (tmp_path / "wizard-brief.json").write_text(json.dumps(brief), encoding="utf-8")
    took = _run([INTAKE, "--brief", "wizard-brief.json", "--project-root", tmp_path], tmp_path)
    out = json.loads(took.stdout)
    assert took.returncode == 3 and out["profile"] is None and out["profile_error"]["code"] == "not_found"
    assert not (tmp_path / "shipwright_run_config.json").exists()  # intake wrote nothing; no fallback profile exists
