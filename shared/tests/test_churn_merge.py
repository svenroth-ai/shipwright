"""Unit tests for ``churn_merge.py`` — the pure allowlist / classify / dedup /
validate logic split out of ``resolve_churn_conflicts.py`` for isolation. The
resolver's git-integration tests live in ``test_resolve_churn_conflicts.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import (  # noqa: E402
    CHURN_ALLOWLIST,
    TRIAGE_LOG,
    classify,
    dedup_event_lines,
    dedup_triage_lines,
    validate_events_text,
    validate_triage_text,
)

_TRIAGE_HEADER = '{"v":1,"schema":"triage","created":"2026-06-05T00:00:00Z"}'


# --- allowlist / classify ---------------------------------------------------

def test_classify_blocks_source_allows_churn() -> None:
    resolvable, blocking = classify(
        [
            ".shipwright/compliance/dashboard.md",
            "shipwright_events.jsonl",
            "shipwright_test_results.json",
            "src/app.py",
            "shared/scripts/tools/foo.py",
        ]
    )
    assert "src/app.py" in blocking and "shared/scripts/tools/foo.py" in blocking
    assert ".shipwright/compliance/dashboard.md" in resolvable
    assert "shipwright_events.jsonl" in resolvable


def test_architecture_md_is_NOT_allowlisted_so_it_blocks() -> None:
    # Curated prose must reach a human (folds external-review G4/O1).
    assert ".shipwright/agent_docs/architecture.md" not in CHURN_ALLOWLIST
    resolvable, blocking = classify([".shipwright/agent_docs/architecture.md"])
    assert blocking == [".shipwright/agent_docs/architecture.md"]
    assert resolvable == []


def test_classify_normalises_backslash_paths() -> None:
    resolvable, blocking = classify([r".shipwright\compliance\sbom.md"])
    assert resolvable == [".shipwright/compliance/sbom.md"]
    assert blocking == []


# --- events dedup / validate ------------------------------------------------

def test_dedup_collapses_byte_identical_lines_only() -> None:
    out, warn = dedup_event_lines(['{"id":"a"}', '{"id":"a"}', '{"id":"b"}', ""])
    assert out == ['{"id":"a"}', '{"id":"b"}']
    assert warn == []


def test_dedup_keeps_both_on_id_collision_and_warns() -> None:
    # Two DISTINCT lines sharing an evt id: never drop, but warn (G2/O6).
    out, warn = dedup_event_lines(['{"id":"x","ts":1}', '{"id":"x","ts":2}'])
    assert len(out) == 2
    assert warn and "x" in warn[0]


def test_validate_flags_non_json_line() -> None:
    errs = validate_events_text('{"ok":1}\nNOT JSON\n')
    assert any("not valid JSON" in e for e in errs)


def test_validate_requires_run_event_when_run_id_given() -> None:
    present = '{"type":"work_completed","adr_id":"iterate-x","id":"e1"}\n'
    assert validate_events_text(present, require_run_id="iterate-x") == []
    absent = '{"type":"phase_completed","id":"e2"}\n'
    assert validate_events_text(absent, require_run_id="iterate-x")


# --- triage dedup / validate (campaign 2026-06-05-track-triage-jsonl, C2) ----

def test_triage_in_churn_allowlist() -> None:
    assert TRIAGE_LOG in CHURN_ALLOWLIST
    assert TRIAGE_LOG == ".shipwright/triage.jsonl"


def test_triage_dedup_collapses_identical_lines_only() -> None:
    out, warn = dedup_triage_lines([_TRIAGE_HEADER, '{"id":"a"}', '{"id":"a"}', ""])
    assert out == [_TRIAGE_HEADER, '{"id":"a"}']
    assert warn == []


def test_triage_dedup_does_NOT_warn_on_shared_append_status_id() -> None:
    """append+status events intentionally share an item id — no false warning."""
    lines = ['{"event":"append","id":"trg-x"}', '{"event":"status","id":"trg-x"}']
    out, warn = dedup_triage_lines(lines)
    assert out == lines          # both kept
    assert warn == []            # the events-log id-collision warning must NOT fire


def test_triage_validate_accepts_header_plus_json() -> None:
    assert validate_triage_text(_TRIAGE_HEADER + '\n{"event":"append","id":"a"}\n') == []


def test_triage_validate_flags_missing_header() -> None:
    errs = validate_triage_text('{"event":"append","id":"a"}\n')  # no header first line
    assert errs and any("header" in e for e in errs)


def test_triage_validate_flags_non_json_line() -> None:
    errs = validate_triage_text(_TRIAGE_HEADER + "\nNOT JSON\n")
    assert errs and any("not valid JSON" in e for e in errs)


def test_triage_validate_flags_empty_log() -> None:
    assert validate_triage_text("") == ["triage log is empty after merge — the header was dropped"]


def test_triage_validate_accepts_append_then_status() -> None:
    ok = (_TRIAGE_HEADER + '\n{"event":"append","id":"trg-x"}\n'
          '{"event":"status","id":"trg-x","newStatus":"dismissed"}\n')
    assert validate_triage_text(ok) == []


def test_triage_validate_flags_orphan_status() -> None:
    """A status whose append is absent ANYWHERE was dropped by the merge — the
    reader would silently discard it, so the validator must reject it (Codex HIGH)."""
    errs = validate_triage_text(
        _TRIAGE_HEADER + '\n{"event":"status","id":"trg-x","newStatus":"dismissed"}\n')
    assert errs and any("no append anywhere" in e for e in errs)


def test_triage_validate_accepts_status_before_append_reordered() -> None:
    """merge=union may interleave so a status precedes its append while BOTH are
    present — two-pass validation must NOT false-fail (GPT-5.4 external-review)."""
    reordered = (_TRIAGE_HEADER
                 + '\n{"event":"status","id":"trg-x","newStatus":"dismissed"}'
                 + '\n{"event":"append","id":"trg-x"}\n')
    assert validate_triage_text(reordered) == []


def test_triage_validate_flags_duplicate_append() -> None:
    errs = validate_triage_text(
        _TRIAGE_HEADER + '\n{"event":"append","id":"trg-x"}\n{"event":"append","id":"trg-x"}\n')
    assert errs and any("duplicate append" in e for e in errs)
