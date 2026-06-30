"""Tests for the Full Suite Runs synthesis path in test_evidence.py.

AC-2 of iterate-2026-05-21-empirical-followups. When `data.test_runs` is
empty but `data.work_events` has events with `tests_total > 0`, the
renderer synthesizes Full Suite Runs rows from work_events. When
`data.test_runs` is non-empty, the original test_run-based path runs
unchanged.

Origin: empirical-verification report 2026-05-21 — both shipwright and
webui have 0 explicit `test_run` events on the wire today; the Full
Suite Runs section was silently invisible until this fallback was added.

Split from test_test_evidence.py so neither file crosses the 300-line
guideline.
"""

from __future__ import annotations

from pathlib import Path


from scripts.lib.data_collector import (
    ComplianceData,
    TestRunEvent as _TestRunEvent,
    WorkEvent,
)
from scripts.lib.test_evidence import (
    _full_suite_runs_from_work_events,
    generate,
)


class TestFullSuiteRunsSynthesisFromWorkEvents:
    """End-to-end synthesis branch (the helper is reached via `generate()`)."""

    def test_renders_section_when_no_test_runs_but_work_events_exist(
        self, tmp_path: Path,
    ):
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-20T10:00:00Z", source="iterate",
                description="Add login", tests_passed=42, tests_total=42,
            ),
            WorkEvent(
                id="ev-2", timestamp="2026-05-21T11:00:00Z", source="iterate",
                description="Fix nav", tests_passed=43, tests_total=44,
                e2e_run=True,
            ),
        ]
        data.test_runs = []

        result = generate(data)
        assert "## Full Suite Runs" in result
        assert (
            "| Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date |"
            in result
        )
        assert "42/42" in result
        assert "43/44" in result
        assert "2026-05-20" in result
        assert "2026-05-21" in result

    def test_section_omitted_when_no_work_event_has_tests(self, tmp_path: Path):
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-20T10:00:00Z", source="iterate",
                description="Pure docs change",
                tests_passed=0, tests_total=0,
            ),
        ]
        data.test_runs = []
        result = generate(data)
        assert "## Full Suite Runs" not in result

    def test_section_omitted_when_no_data_at_all(self, tmp_path: Path):
        """0 test_runs + 0 work_events: hits the legacy fallback path
        which doesn't render Full Suite Runs at all."""
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = []
        data.test_runs = []
        result = generate(data)
        assert "## Full Suite Runs" not in result

    def test_test_run_path_unchanged_when_test_runs_exist(self, tmp_path: Path):
        """Synthesis is a fallback, not a replacement: when test_runs
        is populated, the original path wins and synthesis is skipped."""
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-20T10:00:00Z", source="iterate",
                description="Add feat", tests_passed=42, tests_total=42,
            ),
        ]
        data.test_runs = [
            _TestRunEvent(
                id="tr-1", timestamp="2026-05-21T00:00:00Z", trigger="ci",
                unit_passed=100, unit_total=100, unit_evaluated=True,
                integration_passed=20, integration_total=20,
                integration_evaluated=True,
            ),
        ]
        result = generate(data)
        assert "## Full Suite Runs" in result
        assert "100/100" in result  # from test_run
        assert "20/20" in result    # from test_run
        # Synthesis row would have shown 42/42 in the Full Suite Runs
        # section — but we do not synthesize when test_runs is non-empty.
        suite_section = result.split("## Full Suite Runs")[1].split("##")[0]
        assert "42/42" not in suite_section

    def test_synthesis_caps_at_30_after_filter(self, tmp_path: Path):
        """Filter on tests_total > 0 FIRST, then cap last 30.

        Per OpenAI #3 + Gemini #5: zero-test events do NOT consume the
        cap budget; exactly the last 30 qualifying events render.
        """
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        events: list[WorkEvent] = []
        # 35 qualifying.
        for i in range(35):
            events.append(WorkEvent(
                id=f"ev-q-{i}",
                timestamp=f"2026-04-{(i % 28) + 1:02d}T00:00:00Z",
                source="iterate", description=f"qualifying {i}",
                tests_passed=10 + i, tests_total=20 + i,
            ))
        # 10 non-qualifying (tests_total=0) interleaved.
        for i in range(10):
            events.append(WorkEvent(
                id=f"ev-nq-{i}", timestamp="2026-04-15T00:00:00Z",
                source="iterate", description="docs only",
                tests_passed=0, tests_total=0,
            ))
        data.work_events = events
        data.test_runs = []

        result = generate(data)
        suite_section = result.split("## Full Suite Runs")[1].split("##")[0]
        table_lines = [
            line for line in suite_section.splitlines()
            if line.startswith("| ") and "----" not in line
            and "Run | Trigger" not in line
        ]
        assert len(table_lines) == 30, (
            f"expected 30 rows after filter+cap, got {len(table_lines)}"
        )
        # The last qualifying event MUST appear (passed=10+34=44, total=20+34=54).
        assert "44/54" in result

    def test_integration_pgtap_e2e_smoke_all_dash(self, tmp_path: Path):
        """work_completed events don't carry Integration / pgTAP / Smoke
        breakdowns; E2E is a boolean (no counts). All four render as the
        em-dash placeholder.

        Per OpenAI #2 + iterate spec: documented honesty. Synthesizing
        a count from a boolean would mislead. E2E gets the em-dash
        ALWAYS in the synthesis branch.
        """
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="With e2e", tests_passed=42, tests_total=42,
                e2e_run=True,
            ),
        ]
        data.test_runs = []

        result = generate(data)
        suite_section = result.split("## Full Suite Runs")[1].split("##")[0]
        data_rows = [
            line for line in suite_section.splitlines()
            if line.startswith("| ") and "----" not in line
            and "Run | Trigger" not in line
        ]
        assert len(data_rows) == 1
        cells = [c.strip() for c in data_rows[0].strip("|").split("|")]
        # cells: [Run, Trigger, Unit, Integration, pgTAP, E2E, Smoke, Date]
        assert cells[0] == "1"
        assert cells[1] == "iterate"
        assert cells[2] == "42/42"
        # Integration, pgTAP, E2E, Smoke all em-dash.
        em_dash = "—"
        assert cells[3] == em_dash
        assert cells[4] == em_dash
        assert cells[5] == em_dash  # E2E always em-dash in synthesis branch
        assert cells[6] == em_dash
        assert cells[7] == "2026-05-21"

    def test_round_trip_producer_to_file_to_consumer(self, tmp_path: Path):
        """Boundary-probe round-trip: synthesize markdown, parse table
        back, assert column count and ordering match source events.

        Per ADR-031: markdown is also a producer/consumer boundary.
        """
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        source_events = [
            WorkEvent(
                id="ev-A", timestamp="2026-05-20T10:00:00Z", source="iterate",
                description="A change", tests_passed=10, tests_total=10,
            ),
            WorkEvent(
                id="ev-B", timestamp="2026-05-21T11:00:00Z", source="build",
                section="auth", tests_passed=20, tests_total=22,
            ),
        ]
        data.work_events = source_events
        data.test_runs = []

        result = generate(data)
        suite_section = result.split("## Full Suite Runs")[1].split("##")[0]
        data_rows = [
            line for line in suite_section.splitlines()
            if line.startswith("| ") and "----" not in line
            and "Run | Trigger" not in line
        ]
        parsed = []
        for row in data_rows:
            cells = [c.strip() for c in row.strip("|").split("|")]
            parsed.append(cells)

        assert len(parsed) == 2
        for cells in parsed:
            assert len(cells) == 8, (
                f"expected 8 cells per row, got {len(cells)}: {cells!r}"
            )
        # File-order preserved: ev-A first, ev-B second.
        assert parsed[0][1] == "iterate" and parsed[0][2] == "10/10"
        assert parsed[1][1] == "build" and parsed[1][2] == "20/22"

    def test_drift_protection_both_branches_render_same_columns(
        self, tmp_path: Path,
    ):
        """The synthesis branch and the test_run branch produce
        structurally-identical column headers (Registry-driven SSoT
        drift protection — a refactor adding a column to one branch
        must add it to the other)."""
        # Branch 1: test_run-based
        data1 = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data1.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="x", tests_passed=1, tests_total=1,
            ),
        ]
        data1.test_runs = [
            _TestRunEvent(
                id="tr-1", timestamp="2026-05-21T00:00:00Z", trigger="ci",
                unit_passed=100, unit_total=100, unit_evaluated=True,
            ),
        ]
        # Branch 2: synthesis from work_events
        data2 = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data2.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="x", tests_passed=1, tests_total=1,
            ),
        ]
        data2.test_runs = []

        out1 = generate(data1)
        out2 = generate(data2)

        def header_line(out: str) -> str:
            section = out.split("## Full Suite Runs")[1]
            for line in section.splitlines():
                if line.startswith("| Run "):
                    return line.strip()
            raise AssertionError("Full Suite Runs header missing")

        assert header_line(out1) == header_line(out2)


class TestFullSuiteRunsSynthesisHelpers:
    """Unit tests for the helper itself, independent of `generate()`."""

    def test_helper_returns_empty_when_no_qualifying_events(self, tmp_path: Path):
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="docs only", tests_passed=0, tests_total=0,
            ),
        ]
        out = _full_suite_runs_from_work_events(data)
        assert out == []

    def test_helper_returns_empty_when_no_work_events(self, tmp_path: Path):
        data = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data.work_events = []
        out = _full_suite_runs_from_work_events(data)
        assert out == []

    def test_helper_header_matches_test_run_path(self, tmp_path: Path):
        """Header row text identical to the test_run-based `_full_suite_runs`
        function (drift-protection at the helper level)."""
        from scripts.lib.test_evidence import _full_suite_runs

        data_synth = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data_synth.work_events = [
            WorkEvent(
                id="ev-1", timestamp="2026-05-21T10:00:00Z", source="iterate",
                description="x", tests_passed=1, tests_total=1,
            ),
        ]
        data_synth.test_runs = []
        synth_lines = _full_suite_runs_from_work_events(data_synth)

        data_run = ComplianceData(
            project_root=tmp_path, timestamp="2026-05-21T00:00:00Z"
        )
        data_run.work_events = []
        data_run.test_runs = [
            _TestRunEvent(
                id="tr-1", timestamp="2026-05-21T00:00:00Z", trigger="ci",
                unit_passed=100, unit_total=100, unit_evaluated=True,
            ),
        ]
        run_lines = _full_suite_runs(data_run)

        # Same heading + header/separator rows; synthesis adds an honest note.
        assert synth_lines[0] == run_lines[0] == "## Full Suite Runs"
        assert run_lines[2] in synth_lines and run_lines[3] in synth_lines
        assert any("no `test_run` events" in l for l in synth_lines)
