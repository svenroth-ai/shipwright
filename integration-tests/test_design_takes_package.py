"""B3a acceptance: Design takes A1's classic fixture 1 (mockup byte-identical in uploads/, copy with
Linked FRs, registry / FR-coverage / flows / standalone / chrome / tokens gates pass)."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


import _brief_harness as h

_REPO = Path(__file__).resolve().parents[1]
_CHECKS = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks"
_SPEC = (
    "| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
    "| FR-01.01 | Notes | capture-note | Must | The system SHALL capture a note |\n"
    "| FR-01.02 | Notes | list-notes | Must | The system SHALL list notes |\n"
)


def _bdi():
    spec = importlib.util.spec_from_file_location(
        "_it_b3a_bdi", _REPO / "shared" / "scripts" / "lib" / "brief_dir_intake.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(script: str, project: Path, *extra: str):
    env = {**os.environ, "SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL": "1"}
    proc = subprocess.run([sys.executable, str(_CHECKS / script), "--project-root", str(project), *extra],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.covers("FR-01.04")
def test_design_takes_fixture_1_and_every_gate_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    package = h.build_fixture_1(tmp_path / "pkg")
    project = h.prepare_scratch_project(tmp_path / "proj", package)
    (project / "shipwright_run_config.json").write_text(json.dumps({"profile": "vite-hono"}), encoding="utf-8")
    _bdi().record(project, "brief")
    spec_dir = project / ".shipwright" / "planning" / "01-notes"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(_SPEC, encoding="utf-8")

    code, out = _run("apply-brief-package.py", project)
    assert code == 0 and out["ok"], out

    designs = project / ".shipwright" / "designs"
    original = (package / "mockups" / "01-notes.html").read_bytes()
    assert (designs / "uploads" / "01-notes.html").read_bytes() == original
    screen = next((designs / "screens").glob("01-*.html"))
    assert b"<!-- Requirements: FR-01.01, FR-01.02 -->" in screen.read_bytes()

    code, gates = _run("check-design-gates.py", project, "--gate", "all")
    failed = {g["gate"]: g["problems"] for g in gates["gates"] if not g["ok"] and g["gate"] != "boundary"}
    assert not failed, failed
    assert [g["gate"] for g in gates["gates"]] == [
        "fr-coverage", "tokens", "flows", "chrome", "standalone", "uploads", "iteration", "boundary"]
