"""`autonomy: unattended` reaches the run config through the CLI (campaign brief-driven-run, B5).
Zero internal imports: the CLI plus the schema file only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ORCH = ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"
SCHEMA = ROOT / "shared" / "schemas" / "run_config.v2.schema.json"

pytestmark = pytest.mark.covers("FR-01.01")


def _write_config(tmp_path, autonomy):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")}
    return subprocess.run(
        [sys.executable, str(ORCH), "write-config", "--scope", "full_app", "--profile", "vite-hono",
         "--autonomy", autonomy, "--project-root", str(tmp_path)],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )


@pytest.mark.parametrize("level", ["guided", "autonomous", "unattended"])
def test_write_config_accepts_every_autonomy_level(tmp_path, level):
    done = _write_config(tmp_path, level)
    assert done.returncode == 0, done.stdout + done.stderr
    cfg = json.loads((tmp_path / "shipwright_run_config.json").read_text(encoding="utf-8"))
    assert cfg["autonomy"] == level


def test_write_config_rejects_an_unknown_autonomy(tmp_path):
    assert _write_config(tmp_path, "yolo").returncode != 0
    assert not (tmp_path / "shipwright_run_config.json").exists()


def test_schema_enum_names_every_level_the_cli_and_adopt_write():
    enum = json.loads(SCHEMA.read_text(encoding="utf-8"))["properties"]["autonomy"]["enum"]
    assert {"guided", "autonomous", "unattended", "supervised"} <= set(enum)
