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
    CAMPAIGN_STATUS_GLOB,
    CHURN_ALLOWLIST,
    TRIAGE_LOG,
    classify,
    dedup_event_lines,
    dedup_triage_lines,
    is_campaign_status,
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


def test_ci_security_json_in_churn_allowlist() -> None:
    # The AR-10 CI-security summary is a DERIVED compliance snapshot, regenerated
    # by the SAME _update_compliance producer as the five compliance MDs — but a
    # .json, so the .md-shaped DERIVED_MDS missed it and classify() wrongly marked
    # it BLOCKING, aborting merges (hit merging #374). It must be auto-resolvable.
    assert ".shipwright/compliance/ci-security.json" in CHURN_ALLOWLIST


def test_classify_admits_ci_security_json() -> None:
    resolvable, blocking = classify([".shipwright/compliance/ci-security.json"])
    assert resolvable == [".shipwright/compliance/ci-security.json"]
    assert blocking == []


# --- campaign status.json glob predicate (campaign S3) ----------------------
# status.json lives at a WILDCARD path (one per campaign), so it cannot be a
# fixed CHURN_ALLOWLIST entry — admitted by the is_campaign_status glob predicate
# instead. It is a per-tree tracked churn artifact resolved like a DERIVED_MD
# (placeholder side then regenerate-from-events), NOT added to CHURN_ALLOWLIST
# (which would break the exact-path doc-sync registry test).

_STATUS = ".shipwright/planning/iterate/campaigns/2026-06-07-demo/status.json"


def test_is_campaign_status_truth_table() -> None:
    assert is_campaign_status(_STATUS)
    # backslash form normalises (robust standalone, not only via classify's norm)
    assert is_campaign_status(_STATUS.replace("/", "\\"))
    # exactly ONE slug segment — a nested extra dir must NOT match (the single
    # `*` in the glob spans one path segment, never `a/b`).
    assert not is_campaign_status(
        ".shipwright/planning/iterate/campaigns/demo/nested/status.json"
    )
    # missing slug segment does not match
    assert not is_campaign_status(".shipwright/planning/iterate/campaigns/status.json")
    # a DIFFERENT json / the curated campaign.md in the campaign dir does not match
    assert not is_campaign_status(".shipwright/planning/iterate/campaigns/demo/campaign.md")
    assert not is_campaign_status(
        ".shipwright/planning/iterate/campaigns/demo/sub-iterates/S1-x.md"
    )
    # a same-named file outside the campaigns tree does not match
    assert not is_campaign_status("status.json")
    assert not is_campaign_status(".shipwright/other/status.json")


def test_glob_constant_is_single_segment_wildcard() -> None:
    # the predicate's glob is the documented SSoT shape (one `*` slug segment).
    assert CAMPAIGN_STATUS_GLOB == ".shipwright/planning/iterate/campaigns/*/status.json"
    assert CAMPAIGN_STATUS_GLOB not in CHURN_ALLOWLIST  # separate predicate, not a fixed entry


def test_classify_admits_campaign_status_via_glob() -> None:
    a = ".shipwright/planning/iterate/campaigns/c-one/status.json"
    b = ".shipwright/planning/iterate/campaigns/c-two/status.json"
    resolvable, blocking = classify([a, b, "src/app.py"])
    assert a in resolvable and b in resolvable
    assert blocking == ["src/app.py"]


def test_classify_still_blocks_campaign_md_curated_prose() -> None:
    # campaign.md is curated prose — must reach a human (never auto-resolved).
    md = ".shipwright/planning/iterate/campaigns/demo/campaign.md"
    resolvable, blocking = classify([md])
    assert blocking == [md]
    assert resolvable == []


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


# --- triage dedup: keep-last collapse of same-id APPEND events ----------------
# (iterate-2026-06-10-triage-dedup-keep-last-append) A producer that re-appends an
# UPDATED version of an existing finding writes a second, NON-byte-identical
# ``append`` for the same id. The append-log reader (``triage.read_all_items``
# pass 1) keeps the LAST append's content; the sweep/reconcile validator
# (``validate_triage_text``) enforces exactly one append per id. So
# ``dedup_triage_lines`` MUST collapse same-id appends to keep-LAST — otherwise a
# legitimate update trips the validator and blocks the whole outbox sweep
# (the trg-60ef91fb double-append that wedged the 2026-06-08 outbox delivery).

# Two NON-byte-identical appends for the SAME id (compact vs spaced serialization).
_A1 = '{"event":"append","id":"trg-x","ts":"2026-06-09T06:17:00Z","title":"draft"}'
_A2 = '{"event": "append", "id": "trg-x", "ts": "2026-06-09T06:29:00Z", "title": "resolved"}'


def test_triage_dedup_collapses_same_id_appends_keep_last() -> None:
    out, warn = dedup_triage_lines([_TRIAGE_HEADER, _A1, _A2])
    assert out == [_TRIAGE_HEADER, _A2]   # earlier append dropped, LAST kept (reader parity)
    assert warn == []
    assert validate_triage_text("\n".join(out) + "\n") == []


def test_triage_dedup_same_id_appends_unblocks_validator() -> None:
    # The RAW (un-deduped) two-append text is exactly what tripped the sweep...
    raw = _TRIAGE_HEADER + "\n" + _A1 + "\n" + _A2 + "\n"
    assert any("duplicate append" in e for e in validate_triage_text(raw))
    # ...and routing it through dedup_triage_lines first makes it valid (the fix).
    deduped, _ = dedup_triage_lines([_TRIAGE_HEADER, _A1, _A2])
    assert validate_triage_text("\n".join(deduped) + "\n") == []


def test_triage_dedup_keep_last_preserves_status_and_order() -> None:
    """append(v1) -> status -> append(v2): keep append(v2) + status, drop v1.

    The reader resolves appends (pass 1, last-wins) and statuses (pass 2, ts-
    sorted) in SEPARATE passes, so a kept append after a status never un-flips
    the status — dropping the earlier append is safe and order is preserved.
    """
    status = '{"event":"status","id":"trg-x","newStatus":"dismissed"}'
    out, warn = dedup_triage_lines([_TRIAGE_HEADER, _A1, status, _A2])
    assert out == [_TRIAGE_HEADER, status, _A2]
    assert warn == []
    assert validate_triage_text("\n".join(out) + "\n") == []


def test_triage_dedup_different_id_appends_untouched() -> None:
    a = '{"event":"append","id":"trg-a","ts":"1"}'
    b = '{"event":"append","id":"trg-b","ts":"2"}'
    out, _ = dedup_triage_lines([_TRIAGE_HEADER, a, b])
    assert out == [_TRIAGE_HEADER, a, b]


def test_triage_dedup_keep_last_passes_through_unparseable() -> None:
    # A corrupt (non-JSON) line must NOT be swallowed by the append collapse — it
    # passes through so the validator still flags it.
    out, _ = dedup_triage_lines([_TRIAGE_HEADER, _A1, "NOT JSON", _A2])
    assert out == [_TRIAGE_HEADER, "NOT JSON", _A2]


def test_triage_dedup_byte_identical_appends_still_single() -> None:
    # Regression: byte-identical same-id appends collapse to one (the pre-existing
    # contract) — keep-last must not double-keep when the lines are identical.
    out, warn = dedup_triage_lines([_TRIAGE_HEADER, _A1, _A1])
    assert out == [_TRIAGE_HEADER, _A1]
    assert warn == []
