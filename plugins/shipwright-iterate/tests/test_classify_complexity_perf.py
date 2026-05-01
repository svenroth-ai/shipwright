"""Tests for the touches_build risk-flag (Iterate I3 / T3 hook).

Verifies that performance-relevant changes — dependencies, build configs —
trigger the touches_build flag, while ordinary source changes don't.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_complexity import (  # noqa: E402
    RISK_TAXONOMY,
    TOUCHES_BUILD_FILE_PATTERNS,
    detect_risk_flags,
    touches_build_files,
)


# ── Taxonomy registration ───────────────────────────────────────────────────

def test_touches_build_in_taxonomy():
    assert "touches_build" in RISK_TAXONOMY
    flag = RISK_TAXONOMY["touches_build"]
    assert flag["min_complexity"] == "small"
    assert "performance_test_layer" in flag["enforces"]


# ── Prompt-keyword detection ────────────────────────────────────────────────

def test_keyword_package_json_fires_flag():
    flags = detect_risk_flags("Update dependencies in package.json")
    flag_names = [f["flag"] for f in flags]
    assert "touches_build" in flag_names


def test_keyword_next_config_fires_flag():
    flags = detect_risk_flags("Tweak next.config.ts to enable standalone output")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_vite_config_fires_flag():
    flags = detect_risk_flags("Add proxy config to vite.config.ts")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_pnpm_lockfile_fires_flag():
    flags = detect_risk_flags("Refresh pnpm-lock.yaml after security update")
    assert "touches_build" in [f["flag"] for f in flags]


def test_keyword_unrelated_does_not_fire_flag():
    flags = detect_risk_flags("Rename a button label in src/components/Header.tsx")
    assert "touches_build" not in [f["flag"] for f in flags]


# ── Diff-driven file-glob detection ─────────────────────────────────────────

def test_touches_build_files_detects_package_json():
    assert touches_build_files(["src/foo.tsx", "package.json"]) is True


def test_touches_build_files_detects_lockfile_with_path_prefix():
    assert touches_build_files(["webui/client/package-lock.json"]) is True


def test_touches_build_files_detects_next_config_variants():
    for variant in ["next.config.js", "next.config.ts",
                    "next.config.mjs", "next.config.cjs"]:
        assert touches_build_files([variant]) is True, f"failed for {variant}"


def test_touches_build_files_detects_tsconfig():
    assert touches_build_files(["packages/shared/tsconfig.json"]) is True


def test_touches_build_files_returns_false_on_src_only():
    assert touches_build_files([
        "src/components/Header.tsx",
        "src/lib/util.ts",
        "tests/unit/util.test.ts",
    ]) is False


def test_touches_build_files_returns_false_on_empty():
    assert touches_build_files([]) is False


def test_touches_build_files_handles_windows_separators():
    assert touches_build_files(["webui\\client\\package.json"]) is True


def test_touches_build_files_does_not_match_partial_basename():
    """`my-package.json` should NOT trigger — exact basename match required."""
    assert touches_build_files(["my-package.json"]) is False


# ── Coverage of all documented file patterns ────────────────────────────────

def test_all_documented_patterns_are_detected():
    """Every entry in TOUCHES_BUILD_FILE_PATTERNS should fire from a synthetic diff."""
    for pat in TOUCHES_BUILD_FILE_PATTERNS:
        assert touches_build_files([f"some/path/{pat}"]) is True, (
            f"pattern {pat} declared but not detected"
        )
