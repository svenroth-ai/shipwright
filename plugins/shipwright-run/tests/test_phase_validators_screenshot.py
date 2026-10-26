"""Test phase: the screenshot check is BLOCKING exactly when Design applied a Brief package (campaign B3c)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_phase_validators_late import _good_results, _messages, _write_results, late, validate_phase  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

_TOLERANCE = late._screenshot_tolerance()


@pytest.fixture(autouse=True)
def _no_canon(monkeypatch):
    monkeypatch.setattr(late, "_run_canon_checks", lambda *_a, **_k: None)


def _package(root: Path) -> None:
    designs = root / ".shipwright" / "designs"
    designs.mkdir(parents=True)
    (designs / "brief-package-applied.json").write_text("{}", encoding="utf-8")


def _block(**over) -> dict:
    return {"applies": True, "status": "pass", "captured": True, "tolerance": _TOLERANCE, **over}


def _run(root: Path, block) -> tuple[bool, str]:
    results = _good_results()
    if block is not None:
        results["screenshot_check"] = block
    _write_results(root, results)
    valid, issues = validate_phase("test", root)
    return valid, _messages(issues)


def test_the_tolerance_constant_is_found_beside_the_run_plugin():
    assert _TOLERANCE == 0.15


def test_project_without_a_package_is_unaffected(tmp_path):
    assert _run(tmp_path, None) == (True, "")
    assert _run(tmp_path, {"status": "fail"})[0] is True  # even a stray block does not block without a package


def test_package_without_a_result_blocks(tmp_path):
    _package(tmp_path)
    valid, msg = _run(tmp_path, None)
    assert not valid and "no result" in msg


def test_package_with_a_passing_fresh_result_is_valid(tmp_path):
    _package(tmp_path)
    assert _run(tmp_path, _block()) == (True, "")


@pytest.mark.parametrize("bad", [
    _block(status="fail"), _block(status="error"), _block(applies=False), _block(captured=False),
    _block(captured="yes"), _block(tolerance=0.9), {"status": "pass"}, "pass",
])
def test_package_with_anything_but_a_real_pass_blocks(tmp_path, bad):
    _package(tmp_path)
    valid, msg = _run(tmp_path, bad)
    assert not valid and "creenshot" in msg


def test_a_missing_test_plugin_skips_only_the_tolerance_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(late, "_screenshot_tolerance", lambda: None)
    _package(tmp_path)
    assert _run(tmp_path, _block(tolerance=0.9)) == (True, "")
    assert _run(tmp_path, _block(status="fail"))[0] is False


def test_corrupt_results_still_report_before_the_screenshot_rule(tmp_path):
    _package(tmp_path)
    (tmp_path / "shipwright_test_results.json").write_text(json.dumps({"mode": "standalone"}), encoding="utf-8")
    assert validate_phase("test", tmp_path)[0] is False
