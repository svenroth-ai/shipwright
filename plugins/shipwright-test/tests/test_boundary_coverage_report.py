"""Tests for plugins/shipwright-test/scripts/tools/boundary_coverage_report.py.

Sub-Iterate D — Boundary Coverage Report (ADR-027).

Practices Sub-Iterate A's round-trip test pattern: a fixture markdown
table is parsed into BoundarySpec objects, rendered back to JSON,
re-rendered to markdown, and re-parsed — assert structural equivalence.

Also exercises all 8 probe categories from A's `boundary-probes.md`
against the markdown table parser since iterate-spec authors edit
the Affected Boundaries section by hand (touches_io_boundary == True).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Import plugin-specific tools/boundary_coverage_report.py directly via path —
# conftest already injects shared/scripts which owns the `tools` namespace.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_BCR_PATH = PLUGIN_ROOT / "scripts" / "tools" / "boundary_coverage_report.py"
_spec = importlib.util.spec_from_file_location("boundary_coverage_report", _BCR_PATH)
bcr = importlib.util.module_from_spec(_spec)
sys.modules["boundary_coverage_report"] = bcr
_spec.loader.exec_module(bcr)  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SPEC_WITH_BOUNDARIES = """\
# Sub-Iterate Foo

## Context

Some context.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `producer_a.py::write` | `consumer_b.py::read` | JSON |
| `tool.py::serialize` | `parser.py::deserialize` | YAML |
| `markdown writer` | `markdown reader` | Markdown table |

## Confidence Calibration

- empirical probe ran
"""

SPEC_WITHOUT_BOUNDARIES = """\
# Some Iterate

## Context

Touches `.env.local` and writes `shipwright_run_config.json`.

## Implementation

Done.
"""

SPEC_EMPTY_BOUNDARIES_SECTION = """\
# Sub-Iterate

## Affected Boundaries

(none — pure refactor)

## Next

continue
"""

SPEC_NON_ASCII_BOUNDARIES = """\
# Sub-Iterate Ümlaut

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `Müllabfuhr.py::dump` | `consumer.py::load` | JSON — ümlaut payload |

## Done
"""


def _write_spec(tmp_path: Path, name: str, content: str, encoding: str = "utf-8",
                bom: bool = False, crlf: bool = False) -> Path:
    """Write a spec file with controllable encoding hazards."""
    if crlf:
        content = content.replace("\n", "\r\n")
    data = content.encode(encoding)
    if bom:
        data = b"\xef\xbb\xbf" + data
    spec_path = tmp_path / name
    spec_path.write_bytes(data)
    return spec_path


def _make_events_file(tmp_path: Path, events: list[dict]) -> Path:
    """Write a fixture shipwright_events.jsonl."""
    events_path = tmp_path / "shipwright_events.jsonl"
    with events_path.open("w", encoding="utf-8") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")
    return events_path


# ---------------------------------------------------------------------------
# Parser tests — the markdown table is the load-bearing boundary
# ---------------------------------------------------------------------------


class TestParseMarkdownTable:
    """The Affected Boundaries section parser. 8-probe coverage from A."""

    def test_parses_three_columns(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_WITH_BOUNDARIES)
        result = bcr.parse_affected_boundaries(spec)
        assert len(result) == 3
        assert result[0].producer == "`producer_a.py::write`"
        assert result[0].consumer == "`consumer_b.py::read`"
        assert result[0].format == "JSON"
        assert result[1].producer == "`tool.py::serialize`"
        assert result[2].format == "Markdown table"

    def test_section_missing_returns_empty(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_WITHOUT_BOUNDARIES)
        result = bcr.parse_affected_boundaries(spec)
        assert result == []

    def test_section_present_but_no_table_returns_empty(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_EMPTY_BOUNDARIES_SECTION)
        result = bcr.parse_affected_boundaries(spec)
        assert result == []

    # Probe 1: UTF-8 BOM
    def test_handles_utf8_bom(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_WITH_BOUNDARIES, bom=True)
        result = bcr.parse_affected_boundaries(spec)
        assert len(result) == 3
        assert result[0].producer == "`producer_a.py::write`"

    # Probe 2: CRLF line endings
    def test_handles_crlf_line_endings(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_WITH_BOUNDARIES, crlf=True)
        result = bcr.parse_affected_boundaries(spec)
        assert len(result) == 3
        # Trailing \r must not pollute the value
        assert result[0].format == "JSON"

    # Probe 3: Non-ASCII (umlauts)
    def test_handles_non_ascii(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_NON_ASCII_BOUNDARIES)
        result = bcr.parse_affected_boundaries(spec)
        assert len(result) == 1
        assert "Müllabfuhr" in result[0].producer
        assert "ümlaut" in result[0].format

    # Probe 4: stops at next ## heading
    def test_stops_at_next_h2(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", SPEC_WITH_BOUNDARIES)
        result = bcr.parse_affected_boundaries(spec)
        # Should not bleed into Confidence Calibration content
        for r in result:
            assert "empirical probe" not in r.producer
            assert "empirical probe" not in r.format

    # Probe 5: tolerant of whitespace/alignment markers in separator
    def test_tolerant_of_alignment_separator(self, tmp_path):
        content = """\
# X
## Affected Boundaries

| Producer | Consumer | Format |
|:--------:|---------:|:-------|
| p1 | c1 | f1 |

## Next
"""
        spec = _write_spec(tmp_path, "spec.md", content)
        result = bcr.parse_affected_boundaries(spec)
        assert len(result) == 1
        assert result[0].producer == "p1"

    # Probe 6: extra whitespace inside cells
    def test_strips_cell_whitespace(self, tmp_path):
        content = """\
# X
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
|    p1    |   c1    |   f1   |
"""
        spec = _write_spec(tmp_path, "spec.md", content)
        result = bcr.parse_affected_boundaries(spec)
        assert result[0].producer == "p1"
        assert result[0].consumer == "c1"
        assert result[0].format == "f1"

    # Probe 7: empty file does not crash
    def test_empty_file_returns_empty(self, tmp_path):
        spec = _write_spec(tmp_path, "spec.md", "")
        result = bcr.parse_affected_boundaries(spec)
        assert result == []

    # Probe 8: heading match is exact (## Affected Boundaries) — no false positives
    def test_heading_match_is_exact(self, tmp_path):
        content = """\
# X

## Affected Boundaries Notes

Just notes, not a table section.

## Next
"""
        spec = _write_spec(tmp_path, "spec.md", content)
        result = bcr.parse_affected_boundaries(spec)
        assert result == []


# ---------------------------------------------------------------------------
# scan_specs — walks .shipwright/planning/iterate/**
# ---------------------------------------------------------------------------


class TestScanSpecs:
    def test_walks_iterate_planning_tree(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "iter1.md", SPEC_WITH_BOUNDARIES)
        sub_root = planning_root / "campaigns" / "demo" / "sub-iterates"
        sub_root.mkdir(parents=True)
        _write_spec(sub_root, "A.md", SPEC_NON_ASCII_BOUNDARIES)

        result = bcr.scan_specs(tmp_path)
        # Two specs, one with 3 boundaries, one with 1
        spec_paths = sorted(s.spec_path.name for s in result)
        assert spec_paths == ["A.md", "iter1.md"]
        all_boundaries = [b for s in result for b in s.boundaries]
        assert len(all_boundaries) == 4

    def test_returns_empty_when_dir_missing(self, tmp_path):
        result = bcr.scan_specs(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# correlate_with_commits — drift signal + round-trip heuristic
# ---------------------------------------------------------------------------


class TestCorrelateWithCommits:
    def test_drift_signal_fires_when_io_commit_lacks_section(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        # Spec WITHOUT Affected Boundaries; mentions an IO file
        _write_spec(planning_root, "drift.md", SPEC_WITHOUT_BOUNDARIES)
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "ts": "2026-05-03T10:00:00+00:00",
                "type": "work_completed",
                "source": "iterate",
                "commit": "deadbeef",
                "description": "drift",
                "changed_files": [".env.local", "shipwright_run_config.json"],
            }
        ])

        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path)
        # Drift row should exist for drift.md (IO files but no section)
        drift_rows = [r for r in rows if r.drift_signal]
        assert len(drift_rows) >= 1

    def test_no_drift_when_section_present(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "ok.md", SPEC_WITH_BOUNDARIES)
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-2",
                "type": "work_completed",
                "source": "iterate",
                "commit": "cafebabe",
                "changed_files": [".env.local"],
            }
        ])
        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path)
        for r in rows:
            assert not r.drift_signal

    def test_round_trip_detection_heuristic(self, tmp_path):
        """If a test file mentions producer name, mark round_trip_tested=True."""
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# X
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_special_producer.py | my_consumer.py | JSON |
"""
        _write_spec(planning_root, "x.md", spec_text)
        # Fake a test file mentioning the producer
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_round_trip.py").write_text(
            "def test_my_special_producer_round_trip(): pass\n",
            encoding="utf-8",
        )
        events_path = _make_events_file(tmp_path, [])

        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        any_tested = any(
            br.round_trip_tested for r in rows for br in r.boundary_results
        )
        assert any_tested, "Producer mention in test file should mark round_trip_tested=True"

    def test_missing_events_file_handled_gracefully(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "ok.md", SPEC_WITH_BOUNDARIES)
        specs = bcr.scan_specs(tmp_path)
        # Path does not exist
        rows = bcr.correlate_with_commits(specs, tmp_path / "missing.jsonl")
        # Doesn't crash; rows still returned (without commit correlation)
        assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# Render → JSON → re-render → re-parse → assert equivalence
# (A's round-trip pattern, applied to D's own outputs)
# ---------------------------------------------------------------------------


class TestRoundTripRender:
    def test_render_json_then_markdown_then_reparse_equivalent(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_path = _write_spec(planning_root, "spec.md", SPEC_WITH_BOUNDARIES)
        original = bcr.parse_affected_boundaries(spec_path)
        assert len(original) == 3

        # render_json
        specs_for_render = [bcr.SpecBoundaries(spec_path=spec_path, boundaries=original)]
        rows = bcr.correlate_with_commits(specs_for_render, tmp_path / "missing.jsonl")
        json_obj = bcr.render_json(rows)
        assert "rows" in json_obj
        assert len(json_obj["rows"]) == 1
        assert len(json_obj["rows"][0]["boundaries"]) == 3

        # render_markdown — must contain all producer values
        md = bcr.render_markdown(rows)
        assert "`producer_a.py::write`" in md
        assert "`tool.py::serialize`" in md
        assert "markdown writer" in md

        # Re-parse the rendered markdown table:
        # Put it in a synthetic spec and re-extract
        synth = (
            "# Synth\n\n## Affected Boundaries\n\n"
            + bcr._render_boundaries_table(original) + "\n## End\n"
        )
        synth_path = tmp_path / "synth.md"
        synth_path.write_text(synth, encoding="utf-8")
        re_parsed = bcr.parse_affected_boundaries(synth_path)
        assert len(re_parsed) == len(original)
        for a, b in zip(original, re_parsed):
            assert a.producer == b.producer
            assert a.consumer == b.consumer
            assert a.format == b.format


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestCLI:
    def test_cli_writes_json_and_markdown(self, tmp_path, monkeypatch, capsys):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "spec.md", SPEC_WITH_BOUNDARIES)

        out_md = tmp_path / "report.md"
        out_json = tmp_path / "report.json"

        # Programmatic call (CLI dispatches into main())
        rc = bcr.main([
            "--project-root", str(tmp_path),
            "--output-markdown", str(out_md),
            "--output-json", str(out_json),
        ])
        assert rc == 0
        assert out_md.exists()
        assert out_json.exists()
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert "rows" in data
        assert any(b["producer"] == "`producer_a.py::write`"
                   for r in data["rows"] for b in r["boundaries"])


# ---------------------------------------------------------------------------
# E spec HIGH-6 — slug correlation collision protection
# ---------------------------------------------------------------------------


class TestSlugCollisionProtection:
    """Short stems (`r1.md`, `A.md`) must not match arbitrary commit text."""

    def test_short_stem_does_not_collide_with_unrelated_commit(self, tmp_path):
        """A spec named `r1.md` must NOT match commits where 'r1' appears
        only as a substring (e.g. inside a hash, version string, or path).
        """
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# r1
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_producer | my_consumer | JSON |
"""
        _write_spec(planning_root, "r1.md", spec_text)
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "source": "iterate",
                "commit": "deadbeef",
                # Description contains "r1" as substring of "fetchr1" — pure collision.
                "description": "tweak hashr1 helper for migration",
                "changed_files": ["src/parser.py"],
            }
        ])
        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        # Find the r1.md row.
        r1_row = next(r for r in rows if r.spec_path.name == "r1.md")
        # The spec must NOT have falsely matched the unrelated commit.
        assert "deadbeef" not in r1_row.commits, (
            f"Short slug 'r1' falsely matched unrelated commit "
            f"description that only contains it as a substring. "
            f"matched={r1_row.commits!r}"
        )

    def test_short_stem_matches_with_word_boundary(self, tmp_path):
        """A spec named `r1.md` matches commit 'iterate r1: do X' (word boundary)."""
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# r1
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_producer | my_consumer | JSON |
"""
        _write_spec(planning_root, "r1.md", spec_text)
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "source": "iterate",
                "commit": "cafebabe",
                "description": "iterate r1: do X",
                "changed_files": ["src/x.py"],
            }
        ])
        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        r1_row = next(r for r in rows if r.spec_path.name == "r1.md")
        assert "cafebabe" in r1_row.commits, (
            "Short slug should match when surrounded by word boundaries"
        )

    def test_long_stem_keeps_substring_behavior(self, tmp_path):
        """For len >= 8, plain substring still works (high specificity)."""
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# very-specific-feature-name
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| p | c | JSON |
"""
        _write_spec(planning_root, "very-specific-feature-name.md", spec_text)
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "commit": "abc1234",
                # Embed the slug inside a longer description.
                "description": "Wired very-specific-feature-name end-to-end",
                "changed_files": [],
            }
        ])
        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        long_row = next(
            r for r in rows if r.spec_path.name == "very-specific-feature-name.md"
        )
        assert "abc1234" in long_row.commits


# ---------------------------------------------------------------------------
# E spec HIGH-5 — round-trip heuristic scoping
# ---------------------------------------------------------------------------


class TestRoundTripScoping:
    """Old unrelated tests mentioning a producer name must NOT mark the
    boundary `tested=True`. The heuristic should scope to the test files
    that actually appeared in the matched commit's `changed_files`.
    """

    def test_unrelated_old_test_does_not_count_as_evidence(self, tmp_path):
        """An old test from a different feature that happens to mention
        the producer name must NOT mark `round_trip_tested=True` once we
        have `changed_files` for the matched commit.
        """
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# narrow-iterate
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_producer | my_consumer | JSON |
"""
        _write_spec(planning_root, "narrow-iterate-feature.md", spec_text)

        # Old unrelated test that happens to mention the producer name
        # but was NOT added in the matched commit.
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_old_unrelated.py").write_text(
            "# my_producer is mentioned here\n"
            "def test_unrelated(): pass\n",
            encoding="utf-8",
        )

        # Matched commit only changed an unrelated test file.
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "commit": "deadbeef",
                "description": "narrow-iterate-feature commit",
                "changed_files": ["tests/test_some_other.py"],
            }
        ])

        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        narrow_row = next(
            r for r in rows if r.spec_path.name == "narrow-iterate-feature.md"
        )
        # The unrelated old test must not count.
        assert all(
            not br.round_trip_tested for br in narrow_row.boundary_results
        ), "Unrelated old test must not mark round_trip_tested=True"

    def test_relevant_changed_test_does_count_as_evidence(self, tmp_path):
        """A test file that IS in `changed_files` and mentions the
        producer should count.
        """
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# narrow-iterate
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_producer | my_consumer | JSON |
"""
        _write_spec(planning_root, "narrow-iterate-feature.md", spec_text)

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_my_producer.py").write_text(
            "def test_producer_round_trip():\n"
            "    from x import my_producer\n"
            "    assert True\n",
            encoding="utf-8",
        )

        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "commit": "cafebabe",
                "description": "narrow-iterate-feature: add round-trip",
                "changed_files": ["tests/test_my_producer.py"],
            }
        ])

        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        narrow_row = next(
            r for r in rows if r.spec_path.name == "narrow-iterate-feature.md"
        )
        assert any(
            br.round_trip_tested for br in narrow_row.boundary_results
        ), "Relevant changed test should mark round_trip_tested=True"

    def test_missing_changed_files_falls_back_to_unknown_marker(self, tmp_path):
        """When `changed_files` is missing on the event, the heuristic
        falls back to the full-walk AND marks the row's tested status
        as `unknown` to preserve the audit signal.
        """
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        spec_text = """\
# narrow-iterate-feature
## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| my_producer | my_consumer | JSON |
"""
        _write_spec(planning_root, "narrow-iterate-feature.md", spec_text)

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_old.py").write_text(
            "# mentions my_producer\n", encoding="utf-8",
        )

        # Event with NO changed_files key.
        events_path = _make_events_file(tmp_path, [
            {
                "v": 1,
                "id": "evt-1",
                "type": "work_completed",
                "commit": "deadbeef",
                "description": "narrow-iterate-feature legacy commit",
            }
        ])

        specs = bcr.scan_specs(tmp_path)
        rows = bcr.correlate_with_commits(specs, events_path, project_root=tmp_path)
        narrow_row = next(
            r for r in rows if r.spec_path.name == "narrow-iterate-feature.md"
        )
        # The render layer must expose this as 'unknown' rather than False.
        # We accept either a literal "unknown" string or a sentinel; the
        # CoverageRow.to_dict() output must distinguish unknown from False.
        d = narrow_row.boundary_results[0].to_dict()
        assert d.get("round_trip_tested") in ("unknown", None) or d.get("round_trip_tested_unknown"), (
            f"Missing changed_files must produce 'unknown' marker, got {d!r}"
        )


# ---------------------------------------------------------------------------
# E spec HIGH-4 — merge_boundary_coverage helper
# ---------------------------------------------------------------------------


class TestMergeIntoFlag:
    """`boundary_coverage_report.py --merge-into <test_results.json>` merges
    the JSON output into shipwright_test_results.json#boundary_coverage_report.
    """

    def test_merge_into_creates_key_in_existing_file(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "spec.md", SPEC_WITH_BOUNDARIES)

        # Pre-existing test results file.
        results_path = tmp_path / "shipwright_test_results.json"
        results_path.write_text(
            json.dumps({"existing_key": "preserved"}, indent=2),
            encoding="utf-8",
        )

        rc = bcr.main([
            "--project-root", str(tmp_path),
            "--merge-into", str(results_path),
        ])
        assert rc == 0
        merged = json.loads(results_path.read_text(encoding="utf-8"))
        assert merged.get("existing_key") == "preserved"
        assert "boundary_coverage_report" in merged
        assert "rows" in merged["boundary_coverage_report"]

    def test_merge_into_creates_file_if_missing(self, tmp_path):
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "spec.md", SPEC_WITH_BOUNDARIES)

        results_path = tmp_path / "shipwright_test_results.json"
        # Note: file does not exist yet.

        rc = bcr.main([
            "--project-root", str(tmp_path),
            "--merge-into", str(results_path),
        ])
        assert rc == 0
        assert results_path.exists()
        merged = json.loads(results_path.read_text(encoding="utf-8"))
        assert "boundary_coverage_report" in merged

    def test_merge_into_idempotent(self, tmp_path):
        """Running twice produces the same final shape (last write wins)."""
        planning_root = tmp_path / ".shipwright" / "planning" / "iterate"
        planning_root.mkdir(parents=True)
        _write_spec(planning_root, "spec.md", SPEC_WITH_BOUNDARIES)

        results_path = tmp_path / "shipwright_test_results.json"
        bcr.main([
            "--project-root", str(tmp_path),
            "--merge-into", str(results_path),
        ])
        first = json.loads(results_path.read_text(encoding="utf-8"))
        bcr.main([
            "--project-root", str(tmp_path),
            "--merge-into", str(results_path),
        ])
        second = json.loads(results_path.read_text(encoding="utf-8"))
        assert first["boundary_coverage_report"] == second["boundary_coverage_report"]
