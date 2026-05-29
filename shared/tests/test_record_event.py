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

from record_event import (  # noqa: E402
    _fr_or_change_type_gate_error,
    build_event,
    parse_args,
)


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


class TestFrOrChangeTypeGate:
    """Iterate C.1 (ADR-059) — hard-enforce FR-or-change-type at finalize."""

    def _iterate_event(self, **overrides) -> dict:
        event = {
            "type": "work_completed",
            "source": "iterate",
            "intent": "feature",
        }
        event.update(overrides)
        return event

    def test_iterate_with_affected_frs_passes(self):
        event = self._iterate_event(affected_frs=["FR-01.01"])
        assert _fr_or_change_type_gate_error(event) is None

    def test_iterate_with_new_frs_passes(self):
        event = self._iterate_event(new_frs=["FR-02.07"])
        assert _fr_or_change_type_gate_error(event) is None

    def test_iterate_with_change_type_and_none_reason_passes(self):
        event = self._iterate_event(change_type="tooling", none_reason="CI fix")
        assert _fr_or_change_type_gate_error(event) is None

    def test_iterate_without_any_classification_rejected(self):
        event = self._iterate_event()
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_unclassified"

    def test_change_type_without_none_reason_rejected(self):
        event = self._iterate_event(change_type="tooling")
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_change_type_with_whitespace_only_none_reason_rejected(self):
        event = self._iterate_event(change_type="docs", none_reason="   ")
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_invalid_change_type_rejected_by_gate(self):
        # CLI argparse uses `choices=` so the bad value never reaches
        # the gate; but if a producer constructs the event dict
        # directly, the gate guards against it.
        event = self._iterate_event(change_type="garbage", none_reason="x")
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert err["error"] == "fr_gate_unclassified"

    def test_bug_iterate_still_gated(self):
        """BUG iterates aren't exempt — they classify as tooling/compliance
        when no FR is tied (unlike spec_impact gate which exempts BUG)."""
        event = self._iterate_event(intent="bug")
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        # Same iterate WITH change_type passes.
        event["change_type"] = "tooling"
        event["none_reason"] = "test-flake fix"
        assert _fr_or_change_type_gate_error(event) is None

    def test_build_events_bypass_gate(self):
        event = {
            "type": "work_completed",
            "source": "build",
            "section": "01-login",
        }
        assert _fr_or_change_type_gate_error(event) is None

    def test_non_work_completed_events_bypass(self):
        for event_type in ("phase_started", "phase_completed", "test_run",
                           "split_completed", "task_created"):
            event = {"type": event_type, "source": "iterate"}
            assert _fr_or_change_type_gate_error(event) is None, (
                f"{event_type} should bypass FR gate"
            )

    def test_main_exits_1_when_gate_rejects(self, tmp_path, capsys):
        """CLI integration: rejecting events return exit 1, write nothing."""
        from record_event import main
        log = tmp_path / "shipwright_events.jsonl"
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "feature",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "fr_gate_unclassified" in captured.out
        assert not log.exists()

    def test_main_passes_with_affected_frs(self, tmp_path, capsys, monkeypatch):
        """CLI integration: events with affected_frs land on disk."""
        from record_event import main
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "test-session")
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "feature",
            "--affected-frs", "FR-01.01",
            "--spec-impact", "modify",
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "fr_gate_unclassified" not in captured.out
        assert (tmp_path / "shipwright_events.jsonl").exists()

    def test_main_passes_with_change_type(self, tmp_path, capsys):
        """CLI integration: change_type + none_reason path also passes.

        Code-review-L4: assert the event actually landed on disk, not
        just that success-shaped JSON was printed.
        """
        from record_event import main
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "bug",
            "--change-type", "tooling",
            "--none-reason", "fix flaky CI",
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "success" in captured.out
        # The event file MUST exist and contain a work_completed line
        # with our classification serialized (compact JSON, no spaces).
        log = tmp_path / "shipwright_events.jsonl"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert '"type":"work_completed"' in content
        assert '"change_type":"tooling"' in content
        assert '"none_reason":"fix flaky CI"' in content


class TestFrGateInputValidation:
    """Iterate C.1 — reviewer-flagged input validation hardening."""

    def _iterate_event(self, **overrides) -> dict:
        event = {
            "type": "work_completed",
            "source": "iterate",
            "intent": "feature",
        }
        event.update(overrides)
        return event

    def test_empty_list_affected_frs_rejected(self):
        """Gemini-M1: present-but-empty list should fail like missing field."""
        event = self._iterate_event(affected_frs=[])
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_list_of_empty_strings_rejected(self):
        """OpenAI-M3: shape validation rejects [\"\", \" \"]."""
        event = self._iterate_event(affected_frs=["", "  "])
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_tuple_affected_frs_rejected(self):
        """OpenAI-M3: only lists count; tuples / sets are invalid shape."""
        event = self._iterate_event(affected_frs=("FR-01.01",))
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_invalid_change_type_rejected_even_when_frs_present(self):
        """Gemini-M2 / OpenAI-L4: malformed change_type fails regardless of FRs."""
        event = self._iterate_event(
            affected_frs=["FR-01.01"],
            change_type="garbage",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert "garbage" in err["detail"]

    def test_multiline_none_reason_rejected(self):
        """OpenAI-M5: 'one-line' justification means literally one line."""
        event = self._iterate_event(
            change_type="tooling",
            none_reason="fix flaky CI\nsecond line",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_oversized_none_reason_rejected(self):
        """OpenAI-M5: max 280 chars."""
        event = self._iterate_event(
            change_type="tooling",
            none_reason="x" * 300,
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_control_chars_in_none_reason_rejected(self):
        event = self._iterate_event(
            change_type="tooling",
            none_reason="fix\x1bAttacker break",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None

    def test_tab_in_none_reason_allowed(self):
        """Tabs are whitespace but not control chars; accepted as common typo."""
        event = self._iterate_event(
            change_type="tooling",
            none_reason="fix\tflaky CI",
        )
        assert _fr_or_change_type_gate_error(event) is None

    def test_malformed_dict_input_clean_bypass(self):
        """OpenAI-L10: defensive .get() prevents KeyError on directly-built dicts."""
        # Empty dict — no 'type', no 'source'.
        assert _fr_or_change_type_gate_error({}) is None
        # Non-dict input also bypasses cleanly.
        assert _fr_or_change_type_gate_error("not-a-dict") is None
        assert _fr_or_change_type_gate_error(None) is None

    def test_valid_none_reason_at_max_length(self):
        """Boundary: exactly 280 chars passes."""
        event = self._iterate_event(
            change_type="docs",
            none_reason="x" * 280,
        )
        assert _fr_or_change_type_gate_error(event) is None

    def test_change_type_without_reason_rejected_even_with_frs(self):
        """Code-review-Gemini-M1: change_type-without-reason fails even when FRs are set.

        Rationale: if the operator bothered to set change_type, the
        metadata must be internally consistent (paired with a reason).
        FRs being present doesn't excuse an incomplete classification.
        """
        event = self._iterate_event(
            affected_frs=["FR-01.01"],
            change_type="tooling",
            # no none_reason
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None
        assert "none_reason" in err["detail"]

    def test_change_type_with_invalid_reason_rejected_even_with_frs(self):
        event = self._iterate_event(
            affected_frs=["FR-01.01"],
            change_type="tooling",
            none_reason="multi\nline reason",
        )
        err = _fr_or_change_type_gate_error(event)
        assert err is not None


# ──────────────────────────────────────────────────────────────────────
# Boundary probe — per-tree event log round-trip (touches_io_boundary)
# iterate-2026-05-29-events-jsonl-worktree-commit
# ──────────────────────────────────────────────────────────────────────

class TestWorktreeEventLogRoundTrip:
    """append_event / read_events / attach_commit_to_event round-trip on the
    WORKTREE-local log — and the main tree is never touched.

    These pin the per-tree model end-to-end: a producer call from inside an
    iterate worktree writes the worktree's own copy (which F6 commits), a reader
    from the same worktree sees it, the in-place SHA patch round-trips, and the
    main tree's log stays clean (no orphaned line — the bug this iterate fixes).
    """

    def test_append_then_read_roundtrips_in_worktree(self, git_origin_repo, make_worktree):
        from record_event import append_event, read_events

        work, _ = git_origin_repo
        wt = make_worktree(work, "rt")
        evt = {"v": 1, "id": "evt-rt000042", "ts": "2026-05-29T00:00:00Z",
               "type": "work_completed", "source": "iterate", "commit": "",
               "adr_id": "iterate-rt", "affected_frs": ["FR-01.01"]}
        returned = append_event(wt, evt)
        assert returned == "evt-rt000042"

        # Written to the worktree's OWN copy, NOT the main tree.
        assert (wt / "shipwright_events.jsonl").exists()
        assert not (work / "shipwright_events.jsonl").exists()

        # Reader from the same worktree sees exactly the one event back.
        events = read_events(wt)
        assert [e["id"] for e in events] == ["evt-rt000042"]
        assert events[0]["adr_id"] == "iterate-rt"

    def test_attach_commit_patches_worktree_log_in_place(self, git_origin_repo, make_worktree):
        from record_event import append_event, attach_commit_to_event, read_events

        work, _ = git_origin_repo
        wt = make_worktree(work, "rt2")
        append_event(wt, {"v": 1, "id": "evt-rt000099", "ts": "T",
                          "type": "work_completed", "source": "iterate",
                          "commit": "", "adr_id": "iterate-rt2"})
        ok = attach_commit_to_event(wt, "evt-rt000099", "feedc0de")
        assert ok is True
        # Patched in the worktree copy; main tree still clean.
        events = read_events(wt)
        assert events[0]["commit"] == "feedc0de"
        assert not (work / "shipwright_events.jsonl").exists()
