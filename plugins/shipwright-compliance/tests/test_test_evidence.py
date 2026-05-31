"""Tests for test_evidence.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.lib.data_collector import (
    ComplianceData,
    RequirementInfo,
    TestRunEvent as _TestRunEvent,
    WorkEvent,
    collect_all,
)
from scripts.lib.test_evidence import (
    _classify_work_event_layer,
    emit_test_failure_triage,
    generate,
    generate_file,
)


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Test Evidence Report" in result
        assert "## Summary" in result

    def test_summary_metrics(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Total sections tested | 3 |" in result
        assert "| Unit tests passed | 16 |" in result
        assert "| Unit tests failed | 0 |" in result

    def test_per_split_results(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Per-Split Results" in result
        assert "01-login" in result or "01-auth" in result  # Split or section name
        assert "| Unit |" in result  # Layer breakdown present

    def test_code_review_evidence(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Code Review Evidence" in result
        assert "PASS" in result

    def test_mermaid_pyramid(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "```mermaid" in result
        assert "Unit Tests" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "| Total sections tested | 0 |" in result


class TestProgressionOrder:
    def test_newest_event_first(self, empty_project_root: Path):
        """Row 1 in Test Progression table is the newest event."""
        data = ComplianceData(project_root=empty_project_root, timestamp="2026-04-06T00:00:00Z")
        data.work_events = [
            WorkEvent(
                id="ev-old", timestamp="2026-04-01T10:00:00Z", source="build",
                section="01-auth", tests_passed=10, tests_total=10,
            ),
            WorkEvent(
                id="ev-new", timestamp="2026-04-05T10:00:00Z", source="iterate",
                description="Add login flow", tests_passed=15, tests_total=15,
            ),
        ]
        result = generate(data)
        lines = result.splitlines()
        # Find data rows in Test Progression table (skip header/separator)
        table_rows = [
            l for l in lines
            if l.startswith("| ") and ("build" in l or "iterate" in l)
        ]
        assert len(table_rows) >= 2
        assert "iterate" in table_rows[0], "Newest event (iterate) should be first row"
        assert "build" in table_rows[1], "Older event (build) should be second row"


def _make_data(tmp_path, *, baseline=0, tests_passed=830, tests_total=831):
    """Helper to build ComplianceData with one work event for baseline tests."""
    data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
    data.baseline_failure_count = baseline
    we = WorkEvent(
        id="ev-1", timestamp="2026-04-06T10:00:00Z", source="iterate",
        description="Add feature", tests_passed=tests_passed, tests_total=tests_total,
        affected_frs=["FR-01.01"],
    )
    data.work_events = [we]
    data.requirements = [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    return data


class TestBaselineFailures:
    def test_baseline_failures_give_pass_baseline(self, tmp_path: Path):
        """Events with failures <= baseline get PASS (baseline) not FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "PASS (baseline)" in result
        assert "| FAIL |" not in result

    def test_failures_beyond_baseline_still_fail(self, tmp_path: Path):
        """Events with failures > baseline still get FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=828, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "PASS (baseline)" not in result

    def test_no_baseline_unchanged(self, tmp_path: Path):
        """Without baseline, behavior is strict equality."""
        data = _make_data(tmp_path, baseline=0, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "PASS (baseline)" not in result

    def test_all_passing_ignores_baseline(self, tmp_path: Path):
        """When all tests pass, result is PASS regardless of baseline."""
        data = _make_data(tmp_path, baseline=1, tests_passed=831, tests_total=831)
        result = generate(data)
        assert "| PASS |" in result
        assert "baseline" not in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "test-evidence.md"


class TestLayerColumn:
    """Iterate B.3 (ADR-057) — Test Progression Layer column classifier."""

    def _we(self, **kwargs) -> WorkEvent:
        defaults = dict(
            id="ev-x", timestamp="2026-04-06T10:00:00Z", source="iterate",
            description="test",
        )
        defaults.update(kwargs)
        return WorkEvent(**defaults)

    def test_unit_only(self):
        we = self._we(tests_passed=10, tests_total=10, e2e_run=False)
        assert _classify_work_event_layer(we) == "unit"

    def test_e2e_only(self):
        we = self._we(tests_passed=0, tests_total=0, e2e_run=True)
        assert _classify_work_event_layer(we) == "e2e"

    def test_mixed(self):
        we = self._we(tests_passed=10, tests_total=10, e2e_run=True)
        assert _classify_work_event_layer(we) == "mixed"

    def test_neither(self):
        we = self._we(tests_passed=0, tests_total=0, e2e_run=False)
        assert _classify_work_event_layer(we) == "—"

    def test_table_header_contains_layer_column(self, tmp_path: Path):
        data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
        data.work_events = [self._we(tests_passed=5, tests_total=5)]
        result = generate(data)
        assert "Layer" in result
        # Header row carries the new column between Source and New Tests.
        assert "| # | Event | Source | Layer | New Tests | Suite Total | Result | Date |" in result


class TestFullSuiteLayerColumns:
    """Iterate B.3 — Full Suite Runs table breaks out integration + pgTAP."""

    def test_integration_and_pgtap_columns(self, tmp_path: Path):
        data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
        data.work_events = [WorkEvent(
            id="ev-w", timestamp="2026-04-06T10:00:00Z", source="iterate",
            tests_passed=1, tests_total=1,
        )]
        data.test_runs = [_TestRunEvent(
            id="evt-tr", timestamp="2026-04-06T11:00:00Z", trigger="iterate",
            unit_passed=830, unit_total=831,
            integration_passed=42, integration_total=45,
            pgtap_passed=10, pgtap_total=10,
            e2e_passed=20, e2e_total=20,
        )]
        result = generate(data)
        assert "## Full Suite Runs" in result
        assert "Integration" in result
        assert "pgTAP" in result
        # The actual row carries our counts.
        assert "| 830/831 |" in result
        assert "| 42/45 |" in result
        assert "| 10/10 |" in result


@pytest.fixture
def triage_api():
    """Bring ``shared/scripts/triage`` onto ``sys.path`` for reads in tests."""
    shared = Path(__file__).resolve().parents[3] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import triage  # type: ignore
    return triage


def _seed_test_run_event(project_root: Path, event: dict) -> None:
    """Append one ``test_run`` event into ``shipwright_events.jsonl``."""
    log = project_root / "shipwright_events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    base = {
        "v": 1,
        "id": event.get("id", "evt-aaaa1111"),
        "ts": event.get("ts", "2026-05-21T11:00:00Z"),
        "type": "test_run",
        "trigger": event.get("trigger", "iterate"),
        "layers": event.get("layers", {}),
    }
    with log.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(base) + "\n")


def _read_test_evidence_items(triage_api, project_root: Path) -> list[dict]:
    return [
        i for i in triage_api.read_all_items(project_root)
        if i.get("source") == "test-evidence"
    ]


class TestEmitTestFailureTriage:
    """Iterate B.3 (ADR-057) — per-layer FAIL triage producer."""

    def test_no_test_runs_no_triage(self, tmp_path: Path, triage_api):
        # No test_run events at all → producer is a no-op.
        result = emit_test_failure_triage(tmp_path)
        assert result == {"appended": 0, "dismissed": 0}

    def test_all_green_no_triage(self, tmp_path: Path, triage_api):
        _seed_test_run_event(tmp_path, {
            "id": "evt-green1",
            "layers": {
                "unit":  {"passed": 100, "total": 100},
                "e2e":   {"passed": 5,   "total": 5},
            },
        })
        result = emit_test_failure_triage(tmp_path)
        assert result == {"appended": 0, "dismissed": 0}
        assert _read_test_evidence_items(triage_api, tmp_path) == []

    def test_one_item_per_failing_layer(self, tmp_path: Path, triage_api):
        _seed_test_run_event(tmp_path, {
            "id": "evt-red1",
            "layers": {
                "unit":        {"passed": 99,  "total": 100},
                "integration": {"passed": 9,   "total": 10},
                "pgtap":       {"passed": 10,  "total": 10},
                "e2e":         {"passed": 4,   "total": 5},
            },
        })
        result = emit_test_failure_triage(tmp_path)
        assert result["appended"] == 3   # unit, integration, e2e (pgtap green)
        items = _read_test_evidence_items(triage_api, tmp_path)
        keys = {i["dedupKey"] for i in items}
        assert keys == {"test-fail:unit", "test-fail:integration", "test-fail:e2e"}

    def test_layer_severity_mapping(self, tmp_path: Path, triage_api):
        """e2e/integration/pgtap → high; unit → low (ADR-054 D3)."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-red2",
            "layers": {
                "unit":        {"passed": 1, "total": 2},
                "integration": {"passed": 1, "total": 2},
                "pgtap":       {"passed": 1, "total": 2},
                "e2e":         {"passed": 1, "total": 2},
            },
        })
        emit_test_failure_triage(tmp_path)
        by_layer = {
            i["dedupKey"].split(":", 1)[1]: i
            for i in _read_test_evidence_items(triage_api, tmp_path)
        }
        assert by_layer["unit"]["severity"] == "low"
        assert by_layer["integration"]["severity"] == "high"
        assert by_layer["pgtap"]["severity"] == "high"
        assert by_layer["e2e"]["severity"] == "high"

    def test_event_id_dogfoods_b0_cross_link(self, tmp_path: Path, triage_api):
        """eventId points back at the originating test_run event (ADR-054 D5)."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-tr-12345678",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        emit_test_failure_triage(tmp_path)
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert item["eventId"] == "evt-tr-12345678"

    def test_idempotent(self, tmp_path: Path, triage_api):
        _seed_test_run_event(tmp_path, {
            "id": "evt-red3",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        first = emit_test_failure_triage(tmp_path)
        second = emit_test_failure_triage(tmp_path)
        assert first["appended"] == 1
        assert second["appended"] == 0

    def test_auto_resolve_when_layer_green(self, tmp_path: Path, triage_api):
        # First run: red.
        _seed_test_run_event(tmp_path, {
            "id": "evt-red4",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        emit_test_failure_triage(tmp_path)
        assert len(_read_test_evidence_items(triage_api, tmp_path)) == 1
        # Second run: same layer green.
        _seed_test_run_event(tmp_path, {
            "id": "evt-green2",
            "ts": "2026-05-21T12:00:00Z",
            "layers": {"unit": {"passed": 2, "total": 2}},
        })
        result = emit_test_failure_triage(tmp_path)
        assert result["dismissed"] == 1
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert item["status"] == "dismissed"
        assert item["statusReason"] == "testEvidenceResolved"

    def test_promoted_item_kept(self, tmp_path: Path, triage_api):
        _seed_test_run_event(tmp_path, {
            "id": "evt-red5",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        emit_test_failure_triage(tmp_path)
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        triage_api.mark_status(
            tmp_path, item["id"],
            new_status="promoted", by="user", promoted_task_id="TASK-99",
        )
        # Now layer goes green — promoted item must NOT flip to dismissed.
        _seed_test_run_event(tmp_path, {
            "id": "evt-green3",
            "ts": "2026-05-21T13:00:00Z",
            "layers": {"unit": {"passed": 2, "total": 2}},
        })
        result = emit_test_failure_triage(tmp_path)
        assert result["dismissed"] == 0
        kept = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert kept["status"] == "promoted"

    def test_e2e_failure_detail_lists_top10(self, tmp_path: Path, triage_api):
        """E2E failures get top-10 failure IDs from shipwright_test_results.json."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-red-e2e",
            "layers": {"e2e": {"passed": 5, "total": 18}},
        })
        # Seed test_results.json with 13 failures using zero-padded IDs
        # so the sorted top-10 matches the natural ordering.
        results = {
            "status": "fail",
            "e2e": {
                "passed": 5,
                "total": 18,
                "failures": [f"login.spec.ts:{i:02d}" for i in range(13)],
            },
        }
        (tmp_path / "shipwright_test_results.json").write_text(
            json.dumps(results), encoding="utf-8"
        )
        emit_test_failure_triage(tmp_path)
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert "13/18 failing in e2e" in item["detail"]
        assert "login.spec.ts:00" in item["detail"]
        assert "login.spec.ts:09" in item["detail"]
        # 10-element cap; the 11th onwards lands in "+N more".
        assert "+3 more" in item["detail"]
        assert "login.spec.ts:10" not in item["detail"]

    def test_launch_payload_carries_iterate_bug(self, tmp_path: Path, triage_api):
        _seed_test_run_event(tmp_path, {
            "id": "evt-red6",
            "layers": {"integration": {"passed": 1, "total": 5}},
        })
        emit_test_failure_triage(tmp_path)
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert "/shipwright-iterate --type bug" in item["launchPayload"]
        assert "integration" in item["launchPayload"]

    def test_emit_reports_errors(self, tmp_path: Path, monkeypatch, triage_api):
        """Append failures surface via the `error` key (B.2 pattern)."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-broken",
            "layers": {"unit": {"passed": 0, "total": 1}},
        })
        from scripts.lib import test_evidence

        def _broken_append(*args, **kwargs):
            raise RuntimeError("simulated outage")

        monkeypatch.setattr(
            test_evidence,
            "_import_triage_api",
            lambda: (_broken_append, triage_api.mark_status, triage_api.read_all_items),
        )
        result = emit_test_failure_triage(tmp_path)
        assert result["appended"] == 0
        assert "error" in result and "RuntimeError" in result["error"]


class TestEmitTestFailureTriageSafetyGuards:
    """Iterate B.3 — reviewer-flagged fixes for FAIL-triage producer."""

    def test_skipped_tests_not_counted_as_failures(self, tmp_path: Path, triage_api):
        """Gemini-H1: passed<total with explicit failed=0 must NOT emit a card."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-skips",
            "layers": {
                "unit": {"passed": 90, "total": 100, "failed": 0},
            },
        })
        result = emit_test_failure_triage(tmp_path)
        assert result == {"appended": 0, "dismissed": 0}
        assert _read_test_evidence_items(triage_api, tmp_path) == []

    def test_explicit_failed_triggers_emit(self, tmp_path: Path, triage_api):
        """Gemini-H1: explicit failed>0 triggers the card (preferred over fallback)."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-explicit-fail",
            "layers": {
                "unit": {"passed": 90, "total": 100, "failed": 3},
            },
        })
        emit_test_failure_triage(tmp_path)
        items = _read_test_evidence_items(triage_api, tmp_path)
        assert len(items) == 1
        assert "3/100 failing" in items[0]["detail"]

    def test_fallback_to_passed_total_delta_when_failed_absent(self, tmp_path: Path, triage_api):
        """When failed is absent from the wire, fall back to total-passed."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-legacy-fail",
            "layers": {
                "unit": {"passed": 90, "total": 100},  # no `failed` key
            },
        })
        emit_test_failure_triage(tmp_path)
        items = _read_test_evidence_items(triage_api, tmp_path)
        assert len(items) == 1
        assert "10/100 failing" in items[0]["detail"]

    def test_omitted_layer_does_not_dismiss_prior_card(self, tmp_path: Path, triage_api):
        """OpenAI-M6: an omitted layer is "unknown", not "green"."""
        # Run 1: unit fails → card opened.
        _seed_test_run_event(tmp_path, {
            "id": "evt-run1",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        emit_test_failure_triage(tmp_path)
        assert len(_read_test_evidence_items(triage_api, tmp_path)) == 1

        # Run 2: only e2e reported; unit layer is OMITTED from the
        # event (test runner didn't run unit this round).
        _seed_test_run_event(tmp_path, {
            "id": "evt-run2",
            "ts": "2026-05-21T14:00:00Z",
            "layers": {"e2e": {"passed": 5, "total": 5}},
        })
        result = emit_test_failure_triage(tmp_path)
        # Unit card must stay open — no positive evidence the failure
        # is resolved.
        assert result["dismissed"] == 0
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        assert item["status"] == "triage"

    def test_evaluated_layer_with_zero_failures_dismisses(self, tmp_path: Path, triage_api):
        """OpenAI-M6 sibling: evaluated AND failure-free → dismiss is appropriate."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-r1",
            "layers": {"unit": {"passed": 1, "total": 2}},
        })
        emit_test_failure_triage(tmp_path)

        _seed_test_run_event(tmp_path, {
            "id": "evt-r2",
            "ts": "2026-05-21T15:00:00Z",
            "layers": {"unit": {"passed": 2, "total": 2}},
        })
        result = emit_test_failure_triage(tmp_path)
        assert result["dismissed"] == 1

    def test_detail_strips_control_characters(self, tmp_path: Path, triage_api):
        """Gemini-L5 / OpenAI-M11 + code-review-M1: ANSI, control chars,
        AND embedded newlines must all be stripped from e2e failure IDs.
        Newlines break the surrounding markdown layout."""
        _seed_test_run_event(tmp_path, {
            "id": "evt-ansi",
            "layers": {"e2e": {"passed": 0, "total": 1, "failed": 1}},
        })
        # Failure ID contains ANSI escape + newline + CR + null.
        results = {
            "status": "fail",
            "e2e": {
                "passed": 0, "total": 1,
                "failures": ["\x1b[31mlogin.spec.ts\x1b[0m\nfailed\rat\x00line 42"],
            },
        }
        (tmp_path / "shipwright_test_results.json").write_text(
            json.dumps(results), encoding="utf-8"
        )
        emit_test_failure_triage(tmp_path)
        item = _read_test_evidence_items(triage_api, tmp_path)[0]
        # ALL control chars stripped — no newlines, no ANSI, no nulls.
        assert "\x1b" not in item["detail"]
        assert "\n" not in item["detail"]
        assert "\r" not in item["detail"]
        assert "\x00" not in item["detail"]
        # Content of the failure ID survives the strip + whitespace collapse.
        assert "login.spec.ts" in item["detail"]
        assert "failed at line 42" in item["detail"]


class TestRunEventBackwardCompatibility:
    """Iterate B.3 — TestRunEvent.from_dict tolerates events without new keys."""

    def test_legacy_event_without_integration_keys(self):
        legacy = {
            "id": "evt-legacy",
            "ts": "2026-04-01T00:00:00Z",
            "trigger": "build",
            "layers": {
                "unit": {"passed": 10, "total": 10},
                "e2e":  {"passed": 5,  "total": 5},
            },
        }
        tr = _TestRunEvent.from_dict(legacy)
        assert tr.unit_passed == 10
        assert tr.e2e_passed == 5
        # New layers default to 0 — no crash, no spurious failures.
        assert tr.integration_passed == 0
        assert tr.integration_total == 0
        assert tr.pgtap_passed == 0
        assert tr.pgtap_total == 0

    def test_new_event_carries_integration_and_pgtap(self):
        new = {
            "id": "evt-new",
            "ts": "2026-05-21T00:00:00Z",
            "trigger": "iterate",
            "layers": {
                "unit":        {"passed": 100, "total": 100},
                "integration": {"passed": 42,  "total": 45},
                "pgtap":       {"passed": 10,  "total": 10},
                "e2e":         {"passed": 20,  "total": 20},
            },
        }
        tr = _TestRunEvent.from_dict(new)
        assert tr.integration_passed == 42
        assert tr.integration_total == 45
        assert tr.pgtap_passed == 10
        assert tr.pgtap_total == 10
