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


# --- touches_io_boundary risk flag (Sub-Iterate A — Boundary Tests Foundation) ---


class TestTouchesIoBoundary:
    def test_touches_io_boundary_in_taxonomy(self):
        assert "touches_io_boundary" in RISK_TAXONOMY

    def test_touches_io_boundary_min_complexity_small(self):
        assert RISK_TAXONOMY["touches_io_boundary"]["min_complexity"] == "small"

    def test_touches_io_boundary_enforces_round_trip_test(self):
        enforces = RISK_TAXONOMY["touches_io_boundary"]["enforces"]
        assert "round_trip_test" in enforces

    def test_touches_io_boundary_flag_detection_dotenv(self):
        flags = detect_risk_flags("update parse_env to handle BOM and inline comments")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_flag_detection_hooks_json(self):
        flags = detect_risk_flags("add new entry to hooks.json for stop hook")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_flag_detection_serializer(self):
        # E MEDIUM-A1: bare `write_text`/`parse_` are too loose. Use the
        # tightened `json.dumps` pattern instead — same intent (a real
        # producer/consumer change), now anchored.
        flags = detect_risk_flags(
            "switch the run config writer from json.dumps to a stricter encoder"
        )
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_flag_detection_settings(self):
        # E MEDIUM-A1: bare `load_` dropped. settings.json still triggers.
        flags = detect_risk_flags("modify settings.json schema and json.load it")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_not_fired_for_unrelated(self):
        flags = detect_risk_flags("fix button color on the dashboard")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names

    # E spec MEDIUM-A1 — anchored patterns must NOT fire on unrelated prompts.

    def test_touches_io_boundary_not_fired_for_load_user_route(self):
        """`load_user` is a route name, not an IO boundary verb."""
        flags = detect_risk_flags("rewrite the load_user route to use sessions")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names, (
            f"loose 'load_' pattern must not fire on route names, got {names!r}"
        )

    def test_touches_io_boundary_not_fired_for_dump_utility_prompt(self):
        """Bare `dump` should not fire — only `json.dump(s)` / `yaml.dump`."""
        flags = detect_risk_flags("improve dump utility for stack traces")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names, (
            f"bare 'dump' pattern must not fire, got {names!r}"
        )

    def test_touches_io_boundary_not_fired_for_parse_query_helper(self):
        """`parse_query` is a request helper, not env parsing."""
        flags = detect_risk_flags("add parse_query helper for URL params")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names, (
            f"loose 'parse_' pattern must not fire on URL helpers, got {names!r}"
        )

    def test_touches_io_boundary_not_fired_for_serialize_method(self):
        """`serialize` as a method name is too generic to fire the flag."""
        flags = detect_risk_flags("add serialize method to the Cart model")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names, (
            f"bare 'serialize' must not fire on model method names, got {names!r}"
        )

    def test_touches_io_boundary_not_fired_for_write_text_in_ui_prompt(self):
        """write_text must not fire when used as a UI label, not a method."""
        flags = detect_risk_flags("rewrite the page header text")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" not in names, (
            f"'rewrite' / 'write_text' substring must not fire, got {names!r}"
        )

    def test_touches_io_boundary_still_fires_for_parse_env(self):
        """Specific anchored pattern `parse_env` still fires (positive control)."""
        flags = detect_risk_flags("update parse_env to handle BOM and inline comments")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_still_fires_for_json_dump(self):
        """Specific anchored pattern `json.dump` still fires."""
        flags = detect_risk_flags("switch from json.dumps to ujson for speed")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names

    def test_touches_io_boundary_still_fires_for_hooks_json(self):
        """`hooks.json` still fires (not loosened)."""
        flags = detect_risk_flags("add new entry to hooks.json for stop hook")
        names = [f["flag"] for f in flags]
        assert "touches_io_boundary" in names
