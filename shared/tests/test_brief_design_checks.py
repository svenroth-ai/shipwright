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
    html = _screen(root).read_text(encoding="utf-8")
    _screen(root).write_text(html.replace("FR-01.02", "FR-01.02, FR-05.05"), encoding="utf-8")
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


@pytest.mark.covers("FR-01.04")
def test_a_tampered_package_is_red_before_the_screen_map_is_trusted(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    original = (root / "brief" / "screen-map.json").read_bytes()
    (root / "brief" / "screen-map.json").write_text(json.dumps({"screens": []}), encoding="utf-8")
    [result] = check_brief_design_applied(root)
    assert result.is_failure and "does not verify" in result.detail
    (root / "brief" / "screen-map.json").write_bytes(original)
    assert not check_brief_design_applied(root)[0].is_failure
    (root / "brief" / "mockups" / "01-notes.html").write_text("<html>swapped</html>", encoding="utf-8")
    assert "does not verify" in check_brief_design_applied(root)[0].detail


@pytest.mark.covers("FR-01.04")
def test_a_recorded_package_without_brief_dir_is_still_a_brief_run_and_red(tmp_path):
    root = _project(tmp_path)
    _apply(root)
    path = root / "shipwright_run_config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    del cfg["brief_dir"]
    path.write_text(json.dumps(cfg), encoding="utf-8")
    [result] = check_brief_design_applied(root)
    assert result.is_failure and "does not verify" in result.detail


@pytest.mark.covers("FR-01.04")
def test_a_malformed_screen_map_entry_reads_plainly_not_opaquely(tmp_path):
    root = _project(tmp_path)
    from tools import brief_design_plan as plan
    assert plan.applied_file_issues(root / "brief", root, {"screens": ["x", {"mockup": ""}, {"mockup": "../a.html"}]}) == []


@pytest.mark.covers("FR-01.04")
def test_shared_plan_helpers_agree_with_the_hash_and_the_registry(tmp_path):
    import importlib.util

    from tools import brief_design_plan as plan

    assert plan._SNIFF_BYTES == bdi._lib("brief_package_manifest")._SNIFF_BYTES  # one rule for "text" as the package hash
    assert plan.same_content(b"a\r\nb", b"a\nb") and not plan.same_content(b"\x00a\r\n", b"\x00a\n")
    path = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-design" / "scripts" / "lib" / "screen_registry.py"
    spec = importlib.util.spec_from_file_location("_t_registry", path)
    registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(registry)
    html = "<html><!-- Requirements: FR-01.01, bad, FR-01.02 -->\n<!-- Requirements: FR-09.09 --></html>"
    page = tmp_path / "p.html"
    page.write_text(html, encoding="utf-8")
    assert plan.linked_frs(html) == set(registry.parse_screen_linked_frs(page)) == {"FR-01.01", "FR-01.02"}
    assert plan.linked_frs("<html></html>") == set()


@pytest.mark.covers("FR-01.04")
def test_fr_ids_by_slug_skips_the_iterate_folder_and_dedupes(tmp_path):
    from tools.brief_design_plan import fr_ids_by_slug

    for split in ("01-notes", "iterate", "02-more"):
        spec = tmp_path / ".shipwright" / "planning" / split / "spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text(SPEC, encoding="utf-8")
    ids = fr_ids_by_slug(tmp_path)
    assert ids["capture-note"] == ["FR-01.01"] and ids["list-notes"] == ["FR-01.02"]
    assert fr_ids_by_slug(tmp_path / "empty") == {}


@pytest.mark.covers("FR-01.04")
def test_a_null_brief_dir_is_still_a_brief_run_and_a_non_object_config_is_not(tmp_path):
    root = _project(tmp_path)
    path = root / "shipwright_run_config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["brief_dir"] = None
    path.write_text(json.dumps(cfg), encoding="utf-8")
    [result] = check_brief_design_applied(root)
    assert result.is_failure
    path.write_text("[]", encoding="utf-8")
    assert check_brief_design_applied(root) == []
