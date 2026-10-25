"""Shared helpers for the apply-brief-package tests (B3a): a Brief package builder and the CLI runner."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[3]
_CHECKS = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks"
_TOOL = _CHECKS / "apply-brief-package.py"
_GATES = _CHECKS / "check-design-gates.py"
_BDI_PATH = _REPO / "shared" / "scripts" / "lib" / "brief_dir_intake.py"

_spec = importlib.util.spec_from_file_location("_test_b3a_bdi", _BDI_PATH)
bdi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdi)
bp = bdi._lib("brief_package")

GOOD_GUIDELINES = (
    "# Visual Guidelines\n\n## Typography\n- Inter\n\n## Colors\n| Role | Value |\n|---|---|\n"
    "| Background | #fff |\n\n## Spacing & Layout\n- 4px\n"
)
SPEC = (
    "| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
    "| FR-01.01 | Notes | Capture note | Must | The system SHALL capture a note |\n"
    "| FR-01.02 | Notes | List notes | Must | The system SHALL list notes |\n"
    "| FR-01.03 | Notes | Edit note | Must | The system SHALL edit a note |\n"
)
PAGE_A = "<!doctype html>\r\n<html lang=\"en\">\r\n<head><title>A</title></head><body><h1>A</h1></body></html>\r\n"
PAGE_B = "<!doctype html>\n<html><head><title>B</title></head><body><h1>B</h1></body></html>\n"


def make_project(root: Path, screens: list, pages: dict, guidelines: str = GOOD_GUIDELINES, design_system: str = "visual-guidelines.md") -> Path:
    pkg = root / "brief"
    (pkg / "mockups").mkdir(parents=True)
    for name, text in pages.items():
        (pkg / "mockups" / name).parent.mkdir(parents=True, exist_ok=True)
        (pkg / "mockups" / name).write_bytes(text.encode("utf-8"))
    (pkg / "brief.md").write_text("# Notes\n\n## Capture note\nx\n\n## List notes\ny\n\n## Edit note\nz\n", encoding="utf-8")
    (pkg / "scope.md").write_text("# Scope\n", encoding="utf-8")
    (pkg / "visual-guidelines.md").write_text(guidelines, encoding="utf-8")
    (pkg / "screen-map.json").write_text(json.dumps({"screens": screens}), encoding="utf-8")
    brief = {
        "version": bp.BRIEF_VERSION, "profile": "vite-hono", "deploy_target": "none", "autonomy": "guided",
        "ui_host": "web", "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
        "design_system": design_system, "brief_dir": "brief", "env_preflight": [],
        "allow_parallel_builders": False, "approved_by": "person:test", "approved_at": "2026-10-25T00:00:00Z",
    }
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(json.dumps({"profile": "vite-hono"}), encoding="utf-8")
    bdi.record(root, "brief")
    spec_dir = root / ".shipwright" / "planning" / "01-notes"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(SPEC, encoding="utf-8")
    return root


def run(script: Path, root: Path, *extra: str):
    proc = subprocess.run([sys.executable, str(script), "--project-root", str(root), *extra],
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, json.loads(proc.stdout)


TWO = [
    {"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note", "list-notes"]},
    {"id": "editor", "mockup": "02-editor.html", "requirements": ["edit-note"]},
]
