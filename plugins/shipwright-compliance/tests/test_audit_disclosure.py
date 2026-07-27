"""Producer/reader tests for audit_disclosure.py — the durable last-run record.

The detective audit is on demand by design (no schedule, no CI trigger), so the
only honest thing the evidence documents can do is say when it last happened.
That answer has to survive a fresh clone, which means it lives in tracked state
and not in the gitignored ``audit-report.*`` transients.

Scope bookkeeping and record validation are covered by
``test_audit_disclosure_state.py``, rendering by
``test_audit_disclosure_render.py``, and the five evidence documents carrying
the disclosure by ``test_evidence_docs_disclose_audit.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.lib.audit_disclosure import (
    CONFIG_FILE,
    LAST_AUDIT_KEY,
    read_last_audit,
    record_audit_run,
)


def _write_config(root: Path, payload: dict) -> Path:
    path = root / CONFIG_FILE
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def bare_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


class TestRecordAuditRun:
    """AC-4 — the audit records its own run durably, in tracked state."""

    def test_records_run_with_counts_and_verdict(self, bare_root: Path):
        result = record_audit_run(
            bare_root,
            statuses=["pass", "pass", "fail", "skip"],
            any_fail=True,
            ran_at="2026-07-20T08:00:00+00:00",
        )
        assert result["recorded"] is True

        doc = json.loads((bare_root / CONFIG_FILE).read_text(encoding="utf-8"))
        block = doc[LAST_AUDIT_KEY]
        assert block["ran_at"] == "2026-07-20T08:00:00+00:00"
        assert block["verdict"] == "fail"
        assert block["scope"] == "full"
        assert block["checks"] == {"total": 4, "pass": 2, "fail": 1, "skip": 1}

    def test_failing_audit_is_still_recorded(self, bare_root: Path):
        """A failing cross-check still *happened* — the reader must see it ran."""
        record_audit_run(bare_root, statuses=["fail"], any_fail=True)
        assert read_last_audit(bare_root)["verdict"] == "fail"

    def test_partial_scope_is_recorded_verbatim(self, bare_root: Path):
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False, scope="A,B",
        )
        assert read_last_audit(bare_root)["scope"] == "A,B"

    def test_preserves_unrelated_config_keys(self, bare_root: Path):
        """Read-modify-write: the config is also a human-edited settings file."""
        _write_config(
            bare_root,
            {
                "enforcement": {"rtm_coverage_min": 0.7},
                "traceability": {"test_roots": ["tests"]},
                "phases_covered": ["iterate"],
            },
        )
        record_audit_run(bare_root, statuses=["pass"], any_fail=False)

        doc = json.loads((bare_root / CONFIG_FILE).read_text(encoding="utf-8"))
        assert doc["enforcement"] == {"rtm_coverage_min": 0.7}
        assert doc["traceability"] == {"test_roots": ["tests"]}
        assert doc["phases_covered"] == ["iterate"]
        assert doc[LAST_AUDIT_KEY]["verdict"] == "pass"

    def test_second_run_replaces_the_first(self, bare_root: Path):
        record_audit_run(
            bare_root, statuses=["fail"], any_fail=True,
            ran_at="2026-07-01T00:00:00+00:00",
        )
        record_audit_run(
            bare_root, statuses=["pass"], any_fail=False,
            ran_at="2026-07-20T00:00:00+00:00",
        )
        block = read_last_audit(bare_root)
        assert block["ran_at"] == "2026-07-20T00:00:00+00:00"
        assert block["verdict"] == "pass"

    def test_round_trips_through_the_file(self, bare_root: Path):
        """Boundary probe: what the producer writes is what the consumer reads."""
        written = record_audit_run(
            bare_root,
            statuses=["pass", "skip"],
            any_fail=False,
            scope="A,B",
            ran_at="2026-07-20T08:00:00+00:00",
        )
        assert read_last_audit(bare_root) == written[LAST_AUDIT_KEY]

    def test_written_file_is_valid_utf8_json_with_trailing_newline(
        self, bare_root: Path,
    ):
        """Matches how update_compliance.py writes the same file."""
        record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        raw = (bare_root / CONFIG_FILE).read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert isinstance(json.loads(raw), dict)

    def test_never_raises_on_an_unwritable_config(self, bare_root: Path):
        """Fail-soft: recording must never change the audit's exit code."""
        (bare_root / CONFIG_FILE).mkdir()  # a directory where a file belongs
        result = record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        assert result["recorded"] is False
        assert result["reason"]

    def test_corrupt_config_is_not_clobbered_silently(self, bare_root: Path):
        """A malformed config is reported, not overwritten with a fresh one."""
        (bare_root / CONFIG_FILE).write_text("{not json", encoding="utf-8")
        result = record_audit_run(bare_root, statuses=["pass"], any_fail=False)
        assert result["recorded"] is False
        assert (bare_root / CONFIG_FILE).read_text(encoding="utf-8") == "{not json"

    def test_unknown_finding_statuses_do_not_inflate_the_buckets(
        self, bare_root: Path,
    ):
        """Total counts everything; the named buckets only count what they name."""
        record_audit_run(
            bare_root, statuses=["pass", "weird", "skip"], any_fail=False,
        )
        assert read_last_audit(bare_root)["checks"] == {
            "total": 3, "pass": 1, "fail": 0, "skip": 1,
        }


class TestImportDiscipline:
    """ADR-045 — the disclosure modules must import under BOTH package roots.

    ``collect_all`` is reached as ``scripts.lib.collectors`` by this plugin and
    as ``lib.collectors`` by callers that put ``…/scripts`` on ``sys.path`` (the
    FR-table / traceability tooling does exactly that). An absolute
    ``scripts.lib.…`` import inside the chain resolves under the first root and
    not the second, which fails far away from the edit that caused it.
    """

    def test_collectors_import_under_the_bare_lib_package_root(self):
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, sys.argv[1]); "
             "from lib.collectors import collect_all; "
             "from lib._audit_disclosure_render import freshness_note; "
             "print('ok')",
             str(scripts_dir)],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, result.stderr
        assert "ok" in result.stdout
