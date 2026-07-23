"""Round-trip probe for the review record (AC4, `touches_io_boundary`).

Producer → file on disk → consumer, with the payload chosen to break naive
serialization: embedded newlines, both quote characters, non-ASCII, emoji,
a null severity, a zero-ish line number, and text at the length cap.

This is the boundary that matters most in this change: the producer lives in
this repo and the primary consumer (`shipwright-webui`
`server/src/core/mission-context/review-state.ts`) lives in ANOTHER one, so a
serialization defect here surfaces as a wrong Mission view rather than a failing
test. The record's on-disk shape is pinned here on purpose.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    make_entry,
    new_record,
    read_record,
    record_path,
    upsert_review,
    write_record,
)

RUN_ID = "iterate-2026-07-21-review-record"
REASON = "docs-only diff; doubt-reviewer is conditional per iteration-reviews.md"

HOSTILE_FINDINGS = [
    {
        "severity": "high",
        "category": "correctness",
        "file": "shared/scripts/lib/räv_ütf8.py",
        "line": 42,
        "finding": 'Multi-line finding:\n  line two has "double" and \'single\' quotes,\n'
                   "  a tab\there, a backslash \\ and JSON-ish {\"key\": [1,2]}",
        "suggestion": "Nächste Zeile — em-dash, ellipsis…, emoji 🚢, and ünïcödé",
        "source": "code-reviewer",
    },
    {
        "severity": None,
        "category": None,
        "file": None,
        "line": None,
        "finding": "severity is null and stays null — no invented level",
        "suggestion": None,
        "source": "self-review",
    },
    {
        "severity": "low",
        "category": "edge-case",
        "file": "a/b/c.py",
        "line": 1,
        "finding": "x" * 4000,
        "suggestion": None,
        "source": "external-review",
    },
]


def _hostile_record():
    record = new_record(RUN_ID)
    record = upsert_review(record, make_entry(
        "code", "completed", findings=HOSTILE_FINDINGS,
        provider="openrouter", completed_at="2026-07-21T22:06:11.878865+00:00",
        recorded_by="code-reviewer",
    ))
    record = upsert_review(record, make_entry(
        "doubt", "not_applicable", disposition=REASON, recorded_by="close-missing",
    ))
    record = upsert_review(record, make_entry(
        "external_code", "completed", findings=[],
        parse_status="unstructured",
        raw_excerpt="the reviewer replied in prose we could not itemize —\n"
                    "keep it readable: äöü 🚢 \"quoted\"",
    ))
    record = upsert_review(record, make_entry("self", "completed"))
    record = upsert_review(record, make_entry("plan", "completed"))
    return record


def test_record_survives_a_round_trip_unchanged(tmp_path):
    written = _hostile_record()
    write_record(tmp_path, RUN_ID, written)

    read_back = read_record(tmp_path, RUN_ID)

    assert read_back == written


def test_findings_survive_verbatim(tmp_path):
    write_record(tmp_path, RUN_ID, _hostile_record())
    findings = read_record(tmp_path, RUN_ID)["reviews"]["code"]["findings"]

    assert findings == HOSTILE_FINDINGS
    assert "\n" in findings[0]["finding"]
    assert '"double"' in findings[0]["finding"]
    assert "🚢" in findings[0]["suggestion"]
    assert findings[1]["severity"] is None
    assert len(findings[2]["finding"]) == 4000


def test_a_second_write_is_byte_identical(tmp_path):
    """Serialization is stable, so re-writing an unchanged record produces no
    diff — otherwise every finalize would churn the file in git."""
    record = _hostile_record()
    write_record(tmp_path, RUN_ID, record)
    first = record_path(tmp_path, RUN_ID).read_bytes()

    write_record(tmp_path, RUN_ID, read_record(tmp_path, RUN_ID))

    assert record_path(tmp_path, RUN_ID).read_bytes() == first


def test_the_file_is_utf8_json_with_a_trailing_newline(tmp_path):
    """Pins the on-disk encoding for the cross-repo consumer: UTF-8, real
    characters (not \\u escapes), one trailing newline."""
    write_record(tmp_path, RUN_ID, _hostile_record())
    raw = record_path(tmp_path, RUN_ID).read_bytes()

    text = raw.decode("utf-8")
    assert text.endswith("}\n")
    assert "🚢" in text, "non-ASCII must be written literally, not \\u-escaped"
    assert json.loads(text)["run_id"] == RUN_ID


def test_the_on_disk_shape_matches_the_pinned_consumer_contract(tmp_path):
    """The webui ReviewRow reads exactly these keys. Renaming one here is a
    silent cross-repo break, so the names are asserted, not assumed."""
    write_record(tmp_path, RUN_ID, _hostile_record())
    record = json.loads(record_path(tmp_path, RUN_ID).read_text(encoding="utf-8"))

    assert set(record) == {"schema_version", "run_id", "reviews"}
    assert list(record["reviews"]) == list(REVIEW_TYPES)
    for entry in record["reviews"].values():
        assert set(entry) == {
            "review_type", "status", "findings_count", "findings", "provider",
            "completed_at", "disposition", "recorded_by", "parse_status",
            "raw_excerpt",
        }
        assert entry["findings_count"] == len(entry["findings"])
    for finding in record["reviews"]["code"]["findings"]:
        assert set(finding) == {
            "severity", "category", "file", "line", "finding", "suggestion", "source",
        }
