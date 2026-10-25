"""Design brief-mode check ``brief_design_applied`` (campaign brief-driven-run, B3a; BRIEF D8)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import bdi, bp, build_package, write_config  # noqa: E402
from tools.verifiers.brief_design_checks import check_brief_design_applied  # noqa: E402
from tools.verifiers.design_checks import run_design_checks  # noqa: E402

TOOL = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-design" / "scripts" / "checks" / "apply-brief-package.py"
SPEC = (
    "| ID | Area | Name | Priority | Requirement |\n|---|---|---|---|---|\n"
    "| FR-01.01 | Notes | Capture note | Must | The system SHALL capture a note |\n"
    "| FR-01.02 | Notes | List notes | Must | The system SHALL list notes |\n"
)


def _project(tmp_path: Path) -> Path:
    pkg = build_package(tmp_path)
    (pkg / "screen-map.json").write_text(json.dumps({"screens": [
        {"id": "notes", "mockup": "01-notes.html", "requirements": ["capture-note", "list-notes"]}]}), encoding="utf-8")
    brief = json.loads((pkg / "brief.json").read_text(encoding="utf-8"))
    brief["package_sha256"] = bp.package_sha256(pkg)
    (pkg / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    spec = tmp_path / ".shipwright" / "planning" / "01-notes" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(SPEC, encoding="utf-8")
    return tmp_path


def _apply(root: Path) -> None:
    proc = subprocess.run([sys.executable, str(TOOL), "--project-root", str(root)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _screen(root: Path) -> Path:
    return root / ".shipwright" / "designs" / "screens" / "01-notes.html"


@pytest.mark.covers("FR-01.04")
def test_a_run_without_a_brief_package_gets_no_result(tmp_path):
    write_config(tmp_path)
    assert check_brief_design_applied(tmp_path) == []
    assert "brief_design_applied" not in [r.name for r in run_design_checks(tmp_path)]


@pytest.mark.covers("FR-01.04")
def test_a_brief_run_without_the_applied_marker_is_red(tmp_path):
    root = _project(tmp_path)
    [result] = check_brief_design_applied(root)
    assert result.is_failure and "did not apply" in result.detail
    assert "brief_design_applied" in [r.name for r in run_design_checks(root)]


@pytest.mark.covers("FR-01.04")
def test_hand_written_screens_with_typed_ids_stay_red_even_with_a_forged_marker(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    _screen(root).write_text("<html><!-- Requirements: FR-09.09 --></html>", encoding="utf-8")
    [result] = check_brief_design_applied(root)
    assert result.is_failure and "FR-01.01" in result.detail


@pytest.mark.covers("FR-01.04")
def test_after_a_real_apply_it_is_green_and_extra_review_loop_ids_are_fine(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    [result] = check_brief_design_applied(root)
    assert not result.is_failure, result.detail
    _screen(root).write_text(_screen(root).read_text(encoding="utf-8") + "<!-- Requirements: FR-05.05 -->", encoding="utf-8")
    [result] = check_brief_design_applied(root)
    assert not result.is_failure, result.detail


@pytest.mark.covers("FR-01.04")
def test_a_missing_upload_a_foreign_marker_and_a_lost_fr_row_are_red(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    designs = root / ".shipwright" / "designs"
    (designs / "uploads" / "01-notes.html").unlink()
    assert "01-notes.html" in check_brief_design_applied(root)[0].detail
    (designs / "uploads" / "01-notes.html").write_bytes((root / "brief" / "mockups" / "01-notes.html").read_bytes())
    (designs / "brief-package-applied.json").write_text(json.dumps({"package_sha256": "0" * 64}), encoding="utf-8")
    assert check_brief_design_applied(root)[0].is_failure
    (designs / "brief-package-applied.json").write_text("[]", encoding="utf-8")
    assert check_brief_design_applied(root)[0].is_failure
    _apply_marker = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))["brief_package"]["package_sha256"]
    (designs / "brief-package-applied.json").write_text(json.dumps({"package_sha256": _apply_marker}), encoding="utf-8")
    (root / ".shipwright" / "planning" / "01-notes" / "spec.md").write_text(SPEC.replace("List notes", "Browse"), encoding="utf-8")
    assert "list-notes" in check_brief_design_applied(root)[0].detail
