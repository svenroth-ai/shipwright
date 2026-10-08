"""check_rtm_coverage hook: manifest-based requirement coverage, WARNs, ratchet (U9)."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import hook_env  # noqa: E402
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")

HOOK = Path(__file__).parent.parent / "scripts" / "hooks" / "check_rtm_coverage.py"
COMMIT = {"tool_input": {"command": "git commit -m x"}}


def _manifest(root: Path, passing: int, total: int, generated_at=None):
    reqs = {}
    for i in range(total):
        link = {"id": f"t{i}", "layer": "unit", "status": "enabled",
                "executed": "pass" if i < passing else "fail"}  # not_run = not measured
        reqs[f"01::FR-01.{i:02d}"] = {"id": f"FR-01.{i:02d}", "status": "active",
                                      "tests": {"unit": [link]}, "acs": {}}
    path = root / ".shipwright" / "compliance" / "test-traceability.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 4,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_commit": "", "requirements": reqs}), encoding="utf-8")


def _config(root: Path, **enforcement):
    (root / "shipwright_compliance_config.json").write_text(
        json.dumps({"enforcement": enforcement}), encoding="utf-8")


def _run(root: Path, *, full: bool = False):
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(COMMIT), capture_output=True,
                       text=True, cwd=str(root), env=hook_env(root), timeout=60)
    return r if full else (r.returncode, r.stdout.strip())


def test_blocks_on_requirement_coverage_and_prints_the_definition(tmp_path):
    _manifest(tmp_path, 3, 10)
    rc, out = _run(tmp_path)
    assert rc == 2
    hso = json.loads(out)["hookSpecificOutput"]
    assert "Requirement coverage 30% (3/10 active requirements" in hso["reason"]
    assert hso["details"]["metric"] == "requirements"
    assert len(hso["details"]["uncovered_requirements"]) == 7


def test_block_reason_and_clearing_advice_reach_stderr(tmp_path):
    """On exit 2 Claude Code shows the model STDERR, not the stdout JSON."""
    _manifest(tmp_path, 3, 10)
    r = _run(tmp_path, full=True)
    assert r.returncode == 2
    assert "BLOCKED (check_rtm_coverage): Requirement coverage 30% (3/10" in r.stderr
    assert "rtm_coverage_baseline" in r.stderr and "separate command first" in r.stderr
    assert "compliance_overrides.log" in r.stderr and "Continue anyway" in r.stderr
    hso = json.loads(r.stdout)["hookSpecificOutput"]  # stdout JSON kept for compatibility
    assert hso["blocked"] and "separate command first" in hso["details"]["staging_hint"]


def test_allows_when_requirement_coverage_sufficient(tmp_path):
    _manifest(tmp_path, 9, 10)
    rc, out = _run(tmp_path)
    assert rc == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "Requirement coverage 90% (9/10 active requirements" in ctx and ">= 80%" in ctx
    assert "WARN" not in ctx


def test_adopted_shape_without_rtm_line_no_longer_fails_open(tmp_path):
    """The RTM has no coverage line (no build sections); the old hook allowed every commit."""
    _manifest(tmp_path, 1, 10)
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
        "| Build sections | 0 |\n", encoding="utf-8")
    assert _run(tmp_path)[0] == 2


def test_manifest_wins_over_legacy_rtm_line(tmp_path):
    _manifest(tmp_path, 10, 10)
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 10% |\n", encoding="utf-8")
    assert _run(tmp_path)[0] == 0


def test_stale_manifest_warns_but_still_gates(tmp_path):
    _manifest(tmp_path, 10, 10, generated_at="2020-01-01T00:00:00+00:00")
    rc, out = _run(tmp_path)
    assert rc == 0
    assert "WARN" in json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "days old" in out


def test_corrupt_manifest_is_a_visible_warn(tmp_path):
    path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 0 and "cannot read" in out and "NOT evaluating" in out


def test_compliance_dir_without_any_figure_warns(tmp_path):
    d = tmp_path / ".shipwright" / "compliance"
    d.mkdir(parents=True)
    (d / "traceability-matrix.md").write_text("# RTM\n", encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 0 and "NOT evaluating" in out


def test_no_compliance_data_stays_silent(tmp_path):
    assert _run(tmp_path) == (0, "")


def test_zero_active_requirements_is_not_100_percent(tmp_path):
    _manifest(tmp_path, 0, 0)
    rc, out = _run(tmp_path)
    assert rc == 0 and "no active requirements" in out


def test_baseline_ratchets_the_threshold_down_from_measured_value(tmp_path):
    _manifest(tmp_path, 5, 10)
    assert _run(tmp_path)[0] == 2
    _config(tmp_path, rtm_coverage_baseline=0.5)
    assert _run(tmp_path)[0] == 0


def test_baseline_never_raises_the_threshold(tmp_path):
    _manifest(tmp_path, 7, 10)
    _config(tmp_path, rtm_coverage_min=0.6, rtm_coverage_baseline=0.9)
    assert _run(tmp_path)[0] == 0


def test_invalid_threshold_config_warns_and_uses_default(tmp_path):
    _manifest(tmp_path, 10, 10)
    _config(tmp_path, rtm_coverage_min="high")
    rc, out = _run(tmp_path)
    assert rc == 0 and "must be a number between 0 and 1" in out


def test_ac_metric_is_reported_but_does_not_gate(tmp_path):
    """FR passes, an AC does not: allowed; the AC figure is in the block message when FR blocks."""
    _manifest(tmp_path, 10, 10)
    path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["requirements"]["01::FR-01.00"]["acs"] = {
        "AC01": {"tests": {"unit": [{"status": "enabled", "executed": "fail"}]}}}
    path.write_text(json.dumps(data), encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 0 and "ACs 0/1 = 0%" in out
    _manifest(tmp_path, 1, 10)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["requirements"]["01::FR-01.00"]["acs"] = {
        "AC01": {"tests": {"unit": [{"status": "enabled", "executed": "fail"}]}}}
    path.write_text(json.dumps(data), encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 2 and "ACs 0/1 = 0%" in out


def test_measured_above_baseline_prompts_to_raise_it(tmp_path):
    _manifest(tmp_path, 8, 10)
    _config(tmp_path, rtm_coverage_baseline=0.5)
    rc, out = _run(tmp_path)
    assert rc == 0 and "raise it" in out


def test_unreadable_manifest_never_falls_back_to_the_section_line(tmp_path):
    path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    path.parent.mkdir(parents=True)
    path.write_text("{oops", encoding="utf-8")
    (path.parent / "traceability-matrix.md").write_text(
        "| Traceability coverage | 5% |\n", encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 0 and "NOT evaluating" in out


def test_zero_active_requirements_never_falls_back_to_the_section_line(tmp_path):
    _manifest(tmp_path, 0, 0)
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 5% |\n", encoding="utf-8")
    assert _run(tmp_path)[0] == 0


@pytest.mark.parametrize("enforcement", [None, ["rtm_coverage_min"], "x", 5])
def test_non_object_enforcement_config_warns_and_uses_default(tmp_path, enforcement):
    _manifest(tmp_path, 10, 10)
    (tmp_path / "shipwright_compliance_config.json").write_text(
        json.dumps({"enforcement": enforcement}), encoding="utf-8")
    rc, out = _run(tmp_path)
    assert rc == 0 and "unreadable" in out


def test_invalid_baseline_warns_and_valid_baseline_survives_invalid_min(tmp_path):
    _manifest(tmp_path, 5, 10)
    _config(tmp_path, rtm_coverage_baseline="high")
    rc, out = _run(tmp_path)
    assert rc == 2 and "rtm_coverage_baseline must be a number" in out
    _config(tmp_path, rtm_coverage_min="typo", rtm_coverage_baseline=0.5)
    assert _run(tmp_path)[0] == 0


def test_fractional_threshold_is_compared_exactly_never_rounded(tmp_path):
    _manifest(tmp_path, 79, 100)
    _config(tmp_path, rtm_coverage_min=0.795)
    rc, out = _run(tmp_path)
    assert rc == 2 and "< 79.5% threshold" in out


# --- in-process legs: subprocess runs above are invisible to diff coverage -------------

def _load_hook():
    spec = importlib.util.spec_from_file_location("check_rtm_coverage_inproc", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _main_inproc(mod, monkeypatch, root, capsys):
    monkeypatch.setattr(mod, "_resolve_project_root", lambda: str(root))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(COMMIT)))
    rc = mod.main()
    return rc, capsys.readouterr().out


def test_inproc_block_pass_warn_and_silent_paths(tmp_path, monkeypatch, capsys):
    mod = _load_hook()
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert (rc, out) == (0, "")  # no compliance data
    _manifest(tmp_path, 3, 10)
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 2 and "ratchet_hint" in out and "uncovered_requirements" in out
    _manifest(tmp_path, 10, 10)
    _config(tmp_path, rtm_coverage_baseline=0.5)
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0 and "raise it" in out and "Requirement coverage 100%" in out


def test_inproc_legacy_section_line_and_unevaluable_warn(tmp_path, monkeypatch, capsys):
    mod = _load_hook()
    d = tmp_path / ".shipwright" / "compliance"
    d.mkdir(parents=True)
    # the blocking leg (both streams, no staging hint): test_rtm_hook_followups
    (d / "traceability-matrix.md").write_text("| Traceability coverage | 90% |\n", encoding="utf-8")
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0 and "RTM build-section coverage 90% (share of build sections" in out
    (d / "traceability-matrix.md").write_text("# nothing\n", encoding="utf-8")
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0 and "NOT evaluating" in out
    (tmp_path / "shipwright_compliance_config.json").write_text("{bad", encoding="utf-8")
    assert "unreadable" in mod._read_threshold(str(tmp_path))[1][0]
    assert mod.get_threshold(str(tmp_path)) == 0.80


def test_inproc_unexpected_error_is_a_visible_warn_not_a_silent_allow(tmp_path, monkeypatch, capsys):
    mod = _load_hook()

    def boom(_root):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(mod, "_measure", boom)
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "RuntimeError" in ctx and "NOT evaluating" in ctx


def test_inproc_import_failure_of_the_coverage_module_is_a_visible_warn(tmp_path, monkeypatch, capsys):
    mod = _load_hook()

    def no_import():
        raise ImportError("gone")

    monkeypatch.setattr(mod, "_lib", no_import)
    rc, out = _main_inproc(mod, monkeypatch, tmp_path, capsys)
    assert rc == 0 and "ImportError" in out and "NOT evaluating" in out


def test_baseline_float_noise_does_not_nag(tmp_path):
    """0.57 * 100 == 56.99999999999999: exactly-at-baseline coverage must not prompt a raise."""
    _manifest(tmp_path, 57, 100)
    _config(tmp_path, rtm_coverage_baseline=0.57)
    rc, out = _run(tmp_path)
    assert rc == 0 and "raise it" not in out
