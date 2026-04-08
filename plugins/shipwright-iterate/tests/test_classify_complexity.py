"""Unit tests for classify_complexity.py."""

import json
import sys
from pathlib import Path

import pytest

# Add scripts/lib to path
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_complexity import (
    COMPLEXITY_ORDER,
    RISK_TAXONOMY,
    classify,
    detect_cross_split,
    detect_risk_flags,
    estimate_scope,
)


# --- Risk flag detection ---


class TestDetectRiskFlags:
    def test_auth_keywords(self):
        flags = detect_risk_flags("fix the auth redirect on login page")
        names = [f["flag"] for f in flags]
        assert "touches_auth" in names

    def test_migration_keywords(self):
        flags = detect_risk_flags("add a new migration for user table schema")
        names = [f["flag"] for f in flags]
        assert "touches_migrations" in names

    def test_billing_keywords(self):
        flags = detect_risk_flags("update the stripe checkout webhook handler")
        names = [f["flag"] for f in flags]
        assert "touches_billing" in names

    def test_shared_infra_keywords(self):
        flags = detect_risk_flags("change the layout component in src/components/ui/")
        names = [f["flag"] for f in flags]
        assert "touches_shared_infra" in names

    def test_middleware_keywords(self):
        flags = detect_risk_flags("update middleware.ts for new routes")
        names = [f["flag"] for f in flags]
        assert "touches_middleware" in names

    def test_rls_keywords(self):
        flags = detect_risk_flags("update RLS policies for the new table")
        names = [f["flag"] for f in flags]
        assert "touches_rls" in names

    def test_public_api_keywords(self):
        flags = detect_risk_flags("add a new api/ endpoint for course search")
        names = [f["flag"] for f in flags]
        assert "touches_public_api" in names

    def test_no_flags_for_simple_change(self):
        flags = detect_risk_flags("fix button color on dashboard")
        assert flags == []

    def test_empty_message(self):
        flags = detect_risk_flags("")
        assert flags == []

    def test_multiple_flags(self):
        flags = detect_risk_flags("update auth middleware and add stripe billing webhook")
        names = [f["flag"] for f in flags]
        assert "touches_auth" in names
        assert "touches_billing" in names

    def test_min_complexity_enforced(self):
        flags = detect_risk_flags("fix login auth issue")
        auth_flag = next(f for f in flags if f["flag"] == "touches_auth")
        assert auth_flag["min_complexity"] == "small"

    def test_enforcements_present(self):
        flags = detect_risk_flags("add migration for new schema")
        migration_flag = next(f for f in flags if f["flag"] == "touches_migrations")
        assert "mandatory_review" in migration_flag["enforces"]
        assert "down_sql" in migration_flag["enforces"]


# --- Scope estimation ---


class TestEstimateScope:
    def test_large_keywords(self):
        assert estimate_scope("implement multi-language i18n support") == "large"

    def test_medium_keywords(self):
        assert estimate_scope("add a search filter on the dashboard") == "medium"

    def test_small_keywords(self):
        assert estimate_scope("add a loading spinner to the list") == "small"

    def test_trivial_default(self):
        assert estimate_scope("fix button color") == "trivial"

    def test_empty_message(self):
        assert estimate_scope("") == "trivial"


# --- Cross-split detection ---


class TestDetectCrossSplit:
    def test_no_sync_config(self):
        result = detect_cross_split("some change", None)
        assert result is None

    def test_nonexistent_config(self):
        result = detect_cross_split("some change", "/nonexistent/path.json")
        assert result is None

    def test_single_split(self, tmp_path):
        config = {
            "mappings": [
                {"pattern": "src/auth/**", "frs": ["FR-01.03"]},
                {"pattern": "src/auth/login.ts", "frs": ["FR-01.04"]},
            ]
        }
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))
        result = detect_cross_split("update auth login", str(config_path))
        assert result is None  # Both FRs in split 01

    def test_cross_split_detected(self, tmp_path):
        config = {
            "mappings": [
                {"pattern": "src/auth/**", "frs": ["FR-01.03"]},
                {"pattern": "src/courses/**", "frs": ["FR-02.05"]},
            ]
        }
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))
        result = detect_cross_split("update auth and courses", str(config_path))
        assert result is not None
        assert result["flag"] == "cross_split"
        assert "01" in result["splits"]
        assert "02" in result["splits"]


# --- Full classification ---


class TestClassify:
    def test_trivial_no_risk(self):
        result = classify("fix button color")
        assert result["estimate"] == "trivial"
        assert result["risk_flags"] == []
        assert result["confidence"] > 0

    def test_risk_flag_bumps_to_small(self):
        result = classify("fix the login auth redirect")
        assert result["estimate"] in ("small", "medium")  # auth → min small
        assert "touches_auth" in result["risk_flags"]

    def test_medium_scope_keywords(self):
        result = classify("add a new search page with filters for courses")
        assert result["estimate"] in ("medium", "large")

    def test_large_scope_keywords(self):
        result = classify("implement multi-language i18n support for the whole app")
        assert result["estimate"] == "large"

    def test_enforcements_collected(self):
        result = classify("update RLS migration for auth")
        assert "mandatory_review" in result["enforcements"]

    def test_signals_present(self):
        result = classify("fix button color")
        assert "scope_keyword_estimate" in result["signals"]
        assert "risk_floor" in result["signals"]
        assert "cross_split" in result["signals"]
        assert "has_sync_config" in result["signals"]

    def test_sync_config_boosts_confidence(self, tmp_path):
        config = {"mappings": [{"pattern": "src/auth/**", "frs": ["FR-01.03"]}]}
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))

        without = classify("fix button color")
        with_config = classify("fix button color", str(config_path))
        assert with_config["confidence"] > without["confidence"]

    def test_non_english_input_no_crash(self):
        result = classify("Fehler beim Login beheben, kaputtes auth redirect")
        assert result["estimate"] is not None  # Should not crash on non-English input


# --- Risk taxonomy completeness ---


class TestRiskTaxonomy:
    def test_all_flags_have_required_fields(self):
        for name, flag in RISK_TAXONOMY.items():
            assert "patterns" in flag, f"{name} missing patterns"
            assert "min_complexity" in flag, f"{name} missing min_complexity"
            assert "enforces" in flag, f"{name} missing enforces"
            assert flag["min_complexity"] in COMPLEXITY_ORDER, (
                f"{name} has invalid min_complexity: {flag['min_complexity']}"
            )

    def test_cross_split_has_no_patterns(self):
        assert RISK_TAXONOMY["cross_split"]["patterns"] == []
