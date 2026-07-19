"""Record-boundary recovery at the SHARED event-log read sites (Tier A).

Sibling of ``test_events_newline_integrity.py``, which pins the writer half plus
the one reader (``config.read_events``) that PR #405 converted. This module pins
the three shared readers that PR #405 left on the pre-fix idiom — bare
``json.loads(line)`` under an ``except json.JSONDecodeError`` that skips the
WHOLE physical line, discarding every record on it.

Why a separate module: the leaf contract lives in ``test_jsonl_records.py`` and
the writer wiring in ``test_events_newline_integrity.py``. This is the third
concern — that each *caller* delegates AND keeps its own local contract, which
is where the interesting differences are (see the corrupt-policy table in the
iterate spec: the callers legitimately disagree about what a fragment means).

The input under test is built exactly as git's union merge builds it: two valid
records joined on one physical line because one side's blob was unterminated. No
crash, no interrupted write, no operator edit required.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.events_log import (  # noqa: E402
    finalized_run_ids,
    latest_event_dt,
    resolve_events_path,
)
from tools.verifiers.common import read_events_jsonl  # noqa: E402

_A = {
    "v": 1, "id": "evt-aaa", "ts": "2026-07-19T10:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-a", "run_id": "iterate-side-a",
}
_B = {
    "v": 1, "id": "evt-bbb", "ts": "2026-07-19T11:00:00+00:00",
    "type": "work_completed", "adr_id": "iterate-side-b", "run_id": "iterate-side-b",
}


def _write_concatenated(project_root: Path) -> Path:
    """One physical line holding TWO valid records — what union merge produces."""
    path = resolve_events_path(project_root)
    path.write_text(json.dumps(_A) + json.dumps(_B) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# AC1 — latest_event_dt: partial recovery is CORRECT here (renderer banner)
# ---------------------------------------------------------------------------

def test_latest_event_dt_recovers_both_records_from_a_concatenated_line(tmp_path: Path) -> None:
    """Pre-fix this returned None: the whole line was skipped, so the dashboard
    'data as of' banner went blank even though both events were on disk."""
    _write_concatenated(tmp_path)
    dt = latest_event_dt(tmp_path)
    assert dt is not None, "concatenated line discarded BOTH records"
    # 11:00 is side B — proving the SECOND record on the line was seen too,
    # not merely that the line stopped being skipped.
    assert dt.isoformat() == "2026-07-19T11:00:00+00:00"


def test_latest_event_dt_uses_what_recovered_despite_a_fragment(tmp_path: Path) -> None:
    """Partial, not all-or-nothing. A stale-but-present banner beats a blank one,
    and the docstring already documents silent skipping of corrupt input."""
    path = resolve_events_path(tmp_path)
    path.write_text(json.dumps(_A) + "{not json at all\n", encoding="utf-8")
    dt = latest_event_dt(tmp_path)
    assert dt is not None and dt.isoformat() == "2026-07-19T10:00:00+00:00"


# ---------------------------------------------------------------------------
# AC2 — finalized_run_ids: a fragment means UNDETERMINABLE, never a partial set
# ---------------------------------------------------------------------------

def test_finalized_run_ids_recovers_both_records_from_a_concatenated_line(tmp_path: Path) -> None:
    """Pre-fix this returned an EMPTY SET — not None. Empty set reads as the
    confident claim 'this tree finalized no runs', so the drift gate scoped
    itself to nothing and passed. A fail-open gate failing open by accident."""
    _write_concatenated(tmp_path)
    assert finalized_run_ids(tmp_path) == {"iterate-side-a", "iterate-side-b"}


def test_finalized_run_ids_skips_a_fragment_and_keeps_what_decoded(tmp_path: Path) -> None:
    """The pre-existing corrupt policy, deliberately UNCHANGED by this fix.

    Both external reviewers proposed widening ``None`` to cover unrecoverable
    fragments, arguing a partial set is a confident partial answer. Reviewing
    that against the documented contract, it is a POLICY change, not record
    recovery: ``None`` is reserved for absent-or-unreadable, "one bad row must
    not take down the audit" is explicit in the docstring, and
    ``test_arch_drift_event_scope.test_finalized_run_ids_skips_corrupt_lines``
    pins it. Changing it inside a defect repair would violate this iterate's
    governing invariant. Filed as follow-up instead.

    This case exists so the two behaviours stay distinguishable: CONCATENATION
    is recovered (that is the bug), a FRAGMENT is skipped (that is the contract).
    """
    path = resolve_events_path(tmp_path)
    path.write_text(json.dumps(_A) + "{truncated\n", encoding="utf-8")
    assert finalized_run_ids(tmp_path) == {"iterate-side-a"}


def test_finalized_run_ids_keeps_none_on_absent_log(tmp_path: Path) -> None:
    """The pre-existing fail-open contract must survive the delegation."""
    assert finalized_run_ids(tmp_path) is None


def test_finalized_run_ids_returns_empty_set_for_an_existing_empty_log(tmp_path: Path) -> None:
    """Existing-but-empty is DETERMINABLE (this tree owns nothing) and must stay
    distinguishable from undeterminable. Guards against over-correcting AC2."""
    resolve_events_path(tmp_path).write_text("", encoding="utf-8")
    assert finalized_run_ids(tmp_path) == set()


# ---------------------------------------------------------------------------
# AC3 — verifiers: recover, but keep BOTH documented G5 properties
# ---------------------------------------------------------------------------

def test_read_events_jsonl_recovers_both_records_from_a_concatenated_line(tmp_path: Path) -> None:
    _write_concatenated(tmp_path)
    assert [e["id"] for e in read_events_jsonl(tmp_path)] == ["evt-aaa", "evt-bbb"]


def test_read_events_jsonl_stays_silent_on_corruption(tmp_path: Path) -> None:
    """G5: corruption surfaces as a CheckResult, never as a warning. The shared
    parser returns corruption as DATA (it never prints), so the caller has to
    discard it deliberately — this pins that it does."""
    path = tmp_path / "shipwright_events.jsonl"
    path.write_text(json.dumps(_A) + "{truncated\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert [e["id"] for e in read_events_jsonl(tmp_path)] == ["evt-aaa"]
    assert caught == [], f"verifier reader must stay silent, emitted: {[str(w.message) for w in caught]}"


def test_read_events_jsonl_reads_the_literal_path_without_worktree_redirect(tmp_path: Path) -> None:
    """The other half of G5. ``config.read_events`` resolves through
    ``resolve_events_path``; the verifiers deliberately do NOT, so a verifier run
    inside a worktree audits THAT tree. Delegating the parser must not quietly
    inherit the redirect."""
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(_A) + "\n", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    assert read_events_jsonl(nested) == [], "verifier reader must not walk up to a parent log"


# ---------------------------------------------------------------------------
# AC6 — recovery stays partial (all-or-nothing would reproduce the bug)
# ---------------------------------------------------------------------------

def test_read_events_jsonl_skips_a_bare_scalar_line(tmp_path: Path) -> None:
    """AC10 also covers this Tier-A site. A scalar line was previously RETURNED
    into the list (the old code appended only dicts here, so it was filtered —
    but the fragment path now reports it instead of silently dropping it).
    Only JSON objects are records; pinned so the guarantee is not incidental."""
    path = tmp_path / "shipwright_events.jsonl"
    path.write_text("5\n" + json.dumps(_A) + "\n", encoding="utf-8")
    events = read_events_jsonl(tmp_path)
    assert all(isinstance(e, dict) for e in events)
    assert [e["id"] for e in events] == ["evt-aaa"]


def test_backfill_scan_recovers_fr_links_from_a_concatenated_line(tmp_path: Path) -> None:
    """The SEVENTH read site, found by the Stage-2 code review — the brief's
    "six sites" enumeration was incomplete.

    ``backfill_scan`` builds the commit -> affected_frs map that drives FR
    backfill and traceability, so a dropped record silently un-links an FR from
    the commit that covered it. Same defect class, different surface.
    """
    from lib.backfill_scan import _load_events_fr_by_commit

    a = {"type": "work_completed", "commit": "aaa1111", "affected_frs": ["FR-01.01"]}
    b = {"type": "work_completed", "commit": "bbb2222", "affected_frs": ["FR-01.02"]}
    resolve_events_path(tmp_path).write_text(
        json.dumps(a) + json.dumps(b) + "\n", encoding="utf-8"
    )
    by_commit = _load_events_fr_by_commit(tmp_path)
    assert by_commit == {"aaa1111": {"FR-01.01"}, "bbb2222": {"FR-01.02"}}


def test_recovery_is_partial_not_all_or_nothing(tmp_path: Path) -> None:
    path = tmp_path / "shipwright_events.jsonl"
    path.write_text(json.dumps(_A) + json.dumps(_B) + "{tail\n", encoding="utf-8")
    got = [e["id"] for e in read_events_jsonl(tmp_path)]
    assert got == ["evt-aaa", "evt-bbb"], "a trailing fragment must not void the valid records"


# ---------------------------------------------------------------------------
# AC8 — three latent UNCAUGHT crashes, surfaced by the external review round
# ---------------------------------------------------------------------------

def test_latest_event_dt_does_not_crash_on_a_bare_scalar_line(tmp_path: Path) -> None:
    """Pre-fix: ``json.loads('5')`` -> int, then ``5.get('ts')`` raised
    AttributeError, which ``except OSError`` never caught."""
    resolve_events_path(tmp_path).write_text("5\n" + json.dumps(_A) + "\n", encoding="utf-8")
    dt = latest_event_dt(tmp_path)
    assert dt is not None and dt.isoformat() == "2026-07-19T10:00:00+00:00"


def test_readers_do_not_crash_on_undecodable_bytes(tmp_path: Path) -> None:
    """Pre-fix BOTH functions raised UnicodeDecodeError — a ValueError, so the
    existing ``except OSError`` never caught it. That directly contradicted
    ``latest_event_dt``'s own docstring promise that corruption must not 'brick
    every renderer'. An interrupted write truncating mid multi-byte sequence is
    one of this bug's documented causes."""
    path = resolve_events_path(tmp_path)
    path.write_bytes(json.dumps(_A).encode() + b"\n\xff\xfe garbage\n")
    dt = latest_event_dt(tmp_path)
    assert dt is not None and dt.isoformat() == "2026-07-19T10:00:00+00:00"
    # Undecodable bytes degrade to a fragment, which is skipped — the surviving
    # record still counts (the pre-existing corrupt policy, kept).
    assert finalized_run_ids(tmp_path) == {"iterate-side-a"}
