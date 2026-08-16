"""iterate-2026-08-16-fr-gate-test-evidence: CLI-level coverage for
`record_event.py`'s `--no-tests-reason` flag and the gate it satisfies.

Unit coverage for the gate function itself lives in
`test_fr_gate_test_evidence.py`; this file is the CLI-integration slice
(AC-1/AC-4). Kept in its own file (not appended to the baseline-capped
`test_record_event.py`) to avoid ratcheting it, per the existing convention
(`test_fr_gate_behavior_affecting.py` set the precedent).
"""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


class TestFrGateTestEvidenceCli:
    def test_main_rejects_behavior_affecting_frs_without_evidence(self, tmp_path, capsys):
        from record_event import main
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "change",
            "--affected-frs", "FR-01.01", "--spec-impact", "modify",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "fr_gate_missing_test_evidence" in captured.out
        assert not (tmp_path / "shipwright_events.jsonl").exists()

    def test_main_passes_with_no_tests_reason(self, tmp_path, capsys):
        """--no-tests-reason satisfies the gate and is serialized onto the
        written event (compact JSON, no spaces)."""
        from record_event import main
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "change",
            "--affected-frs", "FR-01.01", "--spec-impact", "modify",
            "--no-tests-reason", "scanner change - no isolated harness yet",
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "fr_gate_missing_test_evidence" not in captured.out
        log = tmp_path / "shipwright_events.jsonl"
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert '"no_tests_reason":"scanner change' in content

    def test_main_zero_total_still_requires_reason(self, tmp_path, capsys):
        """--tests-total 0 is not evidence — matches every read-side
        consumer's "zero tests is not evidence" rule."""
        from record_event import main
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "change",
            "--affected-frs", "FR-01.01", "--spec-impact", "modify",
            "--tests-passed", "0", "--tests-total", "0",
        ])
        assert rc == 1
        captured = capsys.readouterr()
        assert "fr_gate_missing_test_evidence" in captured.out

    def test_main_docs_only_iterate_needs_no_evidence(self, tmp_path, capsys):
        """spec_impact none (behaviour-preserving) is never gated by this
        rule, even with FRs declared and no tests at all."""
        from record_event import main
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "work_completed",
            "--source", "iterate",
            "--intent", "change",
            "--affected-frs", "FR-01.01", "--spec-impact", "none",
            "--spec-impact-justification", "docs-only iterate, no behavior change",
        ])
        assert rc == 0
        captured = capsys.readouterr()
        assert "fr_gate_missing_test_evidence" not in captured.out
