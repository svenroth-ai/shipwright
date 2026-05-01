"""Unit tests for performance_check module (AC-5 of iterate-20260430-phase0-i3).

Covers (a)-(i): config precedence, lhr parsing, bundle measurement (with
sourcemap/precompressed-sibling exclusion + 0-files-skip), gate evaluation,
skip-cases, dev_url validation, deep-merge precedence, test-seam guard.
No subprocess invocations — pure-Python surface only.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.performance_check import (  # noqa: E402
    BUILTIN_DEFAULTS,
    SKIP_REASON_NO_BUNDLE_MATCH,
    SKIP_REASON_PROFILE_OPTS_OUT,
    _test_seam_active,
    evaluate_gate,
    measure_bundle,
    parse_lighthouse_report,
    resolve_config,
    validate_dev_url,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ── (a) resolve_config — basic precedence ─────────────────────────────────────

def test_resolve_config_uses_builtin_when_no_overrides():
    cfg = resolve_config(profile_perf=None, test_config_perf=None, cli_gate=None)
    assert cfg["lighthouse"]["min_score"] == BUILTIN_DEFAULTS["lighthouse"]["min_score"]
    assert cfg["bundle"]["max_kb_gz"] == BUILTIN_DEFAULTS["bundle"]["max_kb_gz"]
    assert cfg["gate"] == "warn"


def test_resolve_config_profile_overrides_builtin():
    profile = {
        "enabled": True,
        "lighthouse": {"min_score": 90, "lcp_max_ms": 2000},
        "bundle": {"max_kb_gz": 200, "build_output_dir": ".next/static"},
        "gate": "warn",
    }
    cfg = resolve_config(profile_perf=profile, test_config_perf=None, cli_gate=None)
    assert cfg["lighthouse"]["min_score"] == 90
    assert cfg["lighthouse"]["lcp_max_ms"] == 2000
    assert cfg["bundle"]["max_kb_gz"] == 200
    assert cfg["bundle"]["build_output_dir"] == ".next/static"


def test_resolve_config_cli_gate_wins():
    profile = {"gate": "warn"}
    test_cfg = {"gate": "warn"}
    cfg = resolve_config(profile_perf=profile, test_config_perf=test_cfg, cli_gate="block")
    assert cfg["gate"] == "block"


# ── (h) deep-merge precedence (Review Finding 4) ──────────────────────────────

def test_resolve_config_deep_merge_lighthouse_partial_override():
    """Project sets only lighthouse.min_score; should inherit lcp_max_ms from profile."""
    profile = {
        "enabled": True,
        "lighthouse": {"min_score": 80, "lcp_max_ms": 3000},
        "bundle": {"max_kb_gz": 250, "build_output_dir": ".next/static"},
        "gate": "warn",
    }
    test_cfg = {"lighthouse": {"min_score": 95}}  # only one field
    cfg = resolve_config(profile_perf=profile, test_config_perf=test_cfg, cli_gate=None)
    assert cfg["lighthouse"]["min_score"] == 95  # overridden
    assert cfg["lighthouse"]["lcp_max_ms"] == 3000  # inherited from profile


def test_resolve_config_lighthouse_playwright_cwd_override():
    """Monorepo layouts override playwright_cwd via profile."""
    profile = {
        "enabled": True,
        "lighthouse": {"min_score": 85, "lcp_max_ms": 2500,
                       "playwright_cwd": "client"},
        "bundle": {"max_kb_gz": 250, "build_output_dir": "client/dist"},
        "gate": "warn",
    }
    cfg = resolve_config(profile_perf=profile, test_config_perf=None, cli_gate=None)
    assert cfg["lighthouse"]["playwright_cwd"] == "client"


def test_resolve_config_deep_merge_bundle_partial_override():
    profile = {
        "enabled": True,
        "lighthouse": {"min_score": 85, "lcp_max_ms": 2500},
        "bundle": {"max_kb_gz": 250, "build_output_dir": "dist/"},
        "gate": "warn",
    }
    test_cfg = {"bundle": {"max_kb_gz": 150}}  # only size, not dir
    cfg = resolve_config(profile_perf=profile, test_config_perf=test_cfg, cli_gate=None)
    assert cfg["bundle"]["max_kb_gz"] == 150
    assert cfg["bundle"]["build_output_dir"] == "dist/"


# ── (b) parse_lighthouse_report ──────────────────────────────────────────────

def test_parse_lighthouse_report_good_fixture():
    lhr = json.loads((FIXTURES / "lhci" / "lhr-good.json").read_text(encoding="utf-8"))
    parsed = parse_lighthouse_report(lhr)
    assert parsed["score"] == 92  # 0.92 → 92 (rounded)
    assert parsed["lcp_ms"] == 1840
    assert parsed["error"] is None


def test_parse_lighthouse_report_bad_fixture():
    lhr = json.loads((FIXTURES / "lhci" / "lhr-bad.json").read_text(encoding="utf-8"))
    parsed = parse_lighthouse_report(lhr)
    assert parsed["score"] == 71
    assert parsed["lcp_ms"] == 4100
    assert parsed["error"] is None


def test_parse_lighthouse_report_missing_keys():
    parsed = parse_lighthouse_report({"categories": {}, "audits": {}})
    assert parsed["score"] is None
    assert parsed["error"] is not None  # diagnostic-set when missing


# ── (c) measure_bundle — sourcemap / precompressed-sibling exclusion ──────────

def test_measure_bundle_excludes_map_gz_br_files():
    """sample-app has main.js, styles.css, main.js.map, vendor.js.gz, vendor.js.br.
    Only main.js + styles.css should contribute."""
    bundle_dir = FIXTURES / "bundle" / "sample-app"
    result = measure_bundle(bundle_dir)
    assert result["skipped"] is False
    assert result["files_measured"] == 2
    assert result["total_kb_gz"] > 0
    # The two repeating-pattern files compress massively — total is small
    assert result["total_kb_gz"] < 5  # generous upper bound
    paths = result["files"]
    assert any(p.endswith("main.js") for p in paths)
    assert any(p.endswith("styles.css") for p in paths)
    assert not any(".map" in p for p in paths)
    assert not any(p.endswith(".gz") for p in paths)
    assert not any(p.endswith(".br") for p in paths)


# ── (f) measure_bundle — 0-files skip (Review Finding 3) ──────────────────────

def test_measure_bundle_empty_dir_returns_skip_not_zero_pass():
    bundle_dir = FIXTURES / "bundle" / "empty-app"
    result = measure_bundle(bundle_dir)
    assert result["skipped"] is True
    assert result["files_measured"] == 0
    assert SKIP_REASON_NO_BUNDLE_MATCH in result["skip_reason"]
    assert str(bundle_dir) in result["skip_reason"]  # diagnostic includes dir


def test_measure_bundle_missing_dir_returns_skip():
    result = measure_bundle(FIXTURES / "bundle" / "this-does-not-exist")
    assert result["skipped"] is True
    assert "not found" in result["skip_reason"].lower() or "missing" in result["skip_reason"].lower()


# ── (d) evaluate_gate — warn vs block semantics ──────────────────────────────

def test_evaluate_gate_warn_always_returns_success_true():
    results = {
        "lighthouse": {"ran": True, "score_passed": False, "lcp_passed": False, "skipped": False},
        "bundle": {"ran": True, "passed": False, "skipped": False},
    }
    assert evaluate_gate(results, gate="warn") is True


def test_evaluate_gate_block_returns_success_false_on_fail():
    results = {
        "lighthouse": {"ran": True, "score_passed": False, "lcp_passed": True, "skipped": False},
        "bundle": {"ran": True, "passed": True, "skipped": False},
    }
    assert evaluate_gate(results, gate="block") is False


def test_evaluate_gate_block_passes_when_all_pass():
    results = {
        "lighthouse": {"ran": True, "score_passed": True, "lcp_passed": True, "skipped": False},
        "bundle": {"ran": True, "passed": True, "skipped": False},
    }
    assert evaluate_gate(results, gate="block") is True


def test_evaluate_gate_block_ignores_skipped_layers():
    """Skipped layers are not failures — they're explicit non-results."""
    results = {
        "lighthouse": {"ran": False, "skipped": True, "skip_reason": "no dev_url"},
        "bundle": {"ran": True, "passed": True, "skipped": False},
    }
    assert evaluate_gate(results, gate="block") is True


# ── (e) skip-cases produce structured non-empty skip_reasons ─────────────────

def test_resolve_config_profile_opts_out_when_disabled():
    profile = {"enabled": False, "lighthouse": {}, "bundle": {}, "gate": "warn"}
    cfg = resolve_config(profile_perf=profile, test_config_perf=None, cli_gate=None)
    assert cfg["enabled"] is False
    assert SKIP_REASON_PROFILE_OPTS_OUT in cfg.get("skip_reason", "")


# ── (g) validate_dev_url — scheme guard (Review Finding 9) ───────────────────

@pytest.mark.parametrize("bad_url", [
    "file:///etc/passwd",
    "gopher://example.com",
    "javascript:alert(1)",
    "ftp://example.com",
    "",
    "not-a-url",
])
def test_validate_dev_url_rejects_non_http(bad_url):
    with pytest.raises(ValueError):
        validate_dev_url(bad_url)


@pytest.mark.parametrize("good_url", [
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:8080",
    "http://[::1]:3000",
])
def test_validate_dev_url_accepts_http_https_loopback(good_url):
    validate_dev_url(good_url)  # no exception


def test_validate_dev_url_warns_on_non_loopback(capsys):
    """Non-loopback hosts emit WARNING but don't raise."""
    validate_dev_url("https://example.com")
    captured = capsys.readouterr()
    assert "WARNING" in captured.err or "non-loopback" in captured.err.lower()


# ── (i) test-seam guard (Review Finding 10) ───────────────────────────────────

def test_test_seam_inactive_when_test_mode_not_set(monkeypatch, capsys):
    monkeypatch.setenv("SHIPWRIGHT_PERF_LHCI_FAKE", str(FIXTURES / "lhci" / "lhr-good.json"))
    monkeypatch.delenv("SHIPWRIGHT_TEST_MODE", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert _test_seam_active() is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err or "ignoring" in captured.err.lower()


def test_test_seam_active_when_test_mode_set(monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_PERF_LHCI_FAKE", str(FIXTURES / "lhci" / "lhr-good.json"))
    monkeypatch.setenv("SHIPWRIGHT_TEST_MODE", "1")
    assert _test_seam_active() is True


def test_test_seam_inactive_when_fake_path_does_not_exist(monkeypatch, capsys):
    monkeypatch.setenv("SHIPWRIGHT_PERF_LHCI_FAKE", "/totally/nonexistent/path.json")
    monkeypatch.setenv("SHIPWRIGHT_TEST_MODE", "1")
    assert _test_seam_active() is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "non-existent" in captured.err.lower() or "does not exist" in captured.err.lower()


def test_test_seam_inactive_when_fake_dir_has_no_lhr_json(monkeypatch, capsys, tmp_path):
    """Fake-seam directory without any lhr-*.json should warn + return False
    (Review Finding 5: never silent-skip + never fake-empty-result)."""
    empty_dir = tmp_path / "no-lhr"
    empty_dir.mkdir()
    monkeypatch.setenv("SHIPWRIGHT_PERF_LHCI_FAKE", str(empty_dir))
    monkeypatch.setenv("SHIPWRIGHT_TEST_MODE", "1")
    assert _test_seam_active() is False
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "no lhr" in captured.err.lower()
