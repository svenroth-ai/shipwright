"""Tests for `shared/scripts/tools/record_event.py` (Iterate B.3).

Coverage gap closed by iterate-2026-05-21-b3-test-evidence-layer-and-triage:
record_event's test_run layers dict gained ``integration`` and ``pgtap``
keys (ADR-057) — both producer-side (CLI args wired into layers dict)
and reader-side (TestRunEvent.from_dict tolerates legacy events without
the new keys) deserve direct unit coverage so future refactors don't
silently regress the schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from record_event import build_event, parse_args  # noqa: E402


def _args_for_test_run(**kwargs) -> list[str]:
    """Render a record_event CLI argv list for the test_run branch."""
    argv = ["--project-root", ".", "--type", "test_run"]
    if "trigger" in kwargs:
        argv += ["--trigger", str(kwargs["trigger"])]
    for flag, key in (
        ("--unit-passed",        "unit_passed"),
        ("--unit-total",         "unit_total"),
        ("--integration-passed", "integration_passed"),
        ("--integration-total",  "integration_total"),
        ("--pgtap-passed",       "pgtap_passed"),
        ("--pgtap-total",        "pgtap_total"),
        ("--e2e-passed",         "e2e_passed"),
        ("--e2e-total",          "e2e_total"),
        ("--smoke-status",       "smoke_status"),
    ):
        if key in kwargs:
            argv += [flag, str(kwargs[key])]
    return argv


class TestRunEventLayersSchema:
    """Iterate B.3 (ADR-057) — test_run layers dict gains integration / pgtap."""

    def test_legacy_unit_e2e_only(self):
        """Producer pre-B.3 emits the 3-key shape; still works."""
        args = parse_args(_args_for_test_run(
            trigger="iterate",
            unit_passed=830, unit_total=831,
            e2e_passed=20, e2e_total=20,
            smoke_status="pass",
        ))
        event = build_event(args)
        assert event["type"] == "test_run"
        layers = event["layers"]
        assert layers["unit"] == {"passed": 830, "total": 831}
        assert layers["e2e"] == {"passed": 20, "total": 20}
        assert layers["smoke"] == {"status": "pass"}
        # New keys absent — backward-compatible payload.
        assert "integration" not in layers
        assert "pgtap" not in layers

    def test_integration_keys_present_when_flags_passed(self):
        args = parse_args(_args_for_test_run(
            trigger="iterate",
            integration_passed=42, integration_total=45,
        ))
        event = build_event(args)
        assert event["layers"]["integration"] == {"passed": 42, "total": 45}

    def test_pgtap_keys_present_when_flags_passed(self):
        args = parse_args(_args_for_test_run(
            trigger="iterate",
            pgtap_passed=10, pgtap_total=10,
        ))
        event = build_event(args)
        assert event["layers"]["pgtap"] == {"passed": 10, "total": 10}

    def test_all_four_layers_in_one_event(self):
        args = parse_args(_args_for_test_run(
            trigger="iterate",
            unit_passed=100,        unit_total=100,
            integration_passed=42,  integration_total=45,
            pgtap_passed=10,        pgtap_total=10,
            e2e_passed=20,          e2e_total=20,
            smoke_status="pass",
        ))
        event = build_event(args)
        layers = event["layers"]
        assert set(layers.keys()) == {"unit", "integration", "pgtap", "e2e", "smoke"}
        assert layers["integration"]["passed"] == 42
        assert layers["pgtap"]["total"] == 10

    def test_only_passed_flag_still_creates_layer(self):
        """``--integration-passed`` without ``--integration-total`` is tolerated."""
        args = parse_args(_args_for_test_run(
            trigger="iterate",
            integration_passed=5,
        ))
        event = build_event(args)
        # The handler creates the layer dict when EITHER flag is set.
        assert event["layers"]["integration"] == {"passed": 5}

    def test_no_layer_flags_omits_layers_key(self):
        """No layer flags → no ``layers`` key on the event (clean wire format)."""
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--trigger", "manual"])
        event = build_event(args)
        # `trigger` is set, but no layers → key omitted.
        assert event["trigger"] == "manual"
        assert "layers" not in event


class TestRunEventValidation:
    """Iterate B.3 (ADR-057) — reviewer-flagged H3 / M2 validation guards."""

    def test_negative_value_rejected_at_cli(self):
        """``--unit-passed=-5`` raises SystemExit at argparse layer."""
        import pytest
        with pytest.raises(SystemExit):
            parse_args(["--project-root", ".", "--type", "test_run",
                        "--unit-passed", "-5", "--unit-total", "10"])

    def test_non_integer_rejected_at_cli(self):
        import pytest
        with pytest.raises(SystemExit):
            parse_args(["--project-root", ".", "--type", "test_run",
                        "--unit-passed", "five", "--unit-total", "10"])

    def test_passed_exceeds_total_rejected(self):
        """``passed > total`` is corrupt — build_event raises ValueError."""
        import pytest
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--unit-passed", "15", "--unit-total", "10"])
        with pytest.raises(ValueError, match="unit passed.*> total"):
            build_event(args)

    def test_failed_exceeds_total_rejected(self):
        import pytest
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--integration-failed", "8", "--integration-total", "5"])
        with pytest.raises(ValueError, match="integration failed.*> total"):
            build_event(args)


class TestRunEventFailedField:
    """Iterate B.3 — explicit ``failed`` count on layers (Gemini-H1)."""

    def test_failed_present_when_flag_set(self):
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--unit-passed", "8", "--unit-total", "10",
                           "--unit-failed", "1"])
        event = build_event(args)
        assert event["layers"]["unit"] == {"passed": 8, "total": 10, "failed": 1}

    def test_failed_absent_when_flag_omitted(self):
        """Backward-compat — producers that don't pass --failed keep working."""
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--unit-passed", "10", "--unit-total", "10"])
        event = build_event(args)
        assert "failed" not in event["layers"]["unit"]

    def test_integration_failed_serializes(self):
        """Code-review-L3: --integration-failed lands on the wire correctly."""
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--integration-passed", "7",
                           "--integration-total", "10",
                           "--integration-failed", "3"])
        event = build_event(args)
        assert event["layers"]["integration"] == {
            "passed": 7, "total": 10, "failed": 3,
        }

    def test_pgtap_failed_serializes(self):
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--pgtap-passed", "8",
                           "--pgtap-total", "10",
                           "--pgtap-failed", "2"])
        event = build_event(args)
        assert event["layers"]["pgtap"] == {
            "passed": 8, "total": 10, "failed": 2,
        }

    def test_e2e_failed_serializes(self):
        args = parse_args(["--project-root", ".", "--type", "test_run",
                           "--e2e-passed", "4",
                           "--e2e-total", "5",
                           "--e2e-failed", "1"])
        event = build_event(args)
        assert event["layers"]["e2e"] == {
            "passed": 4, "total": 5, "failed": 1,
        }
