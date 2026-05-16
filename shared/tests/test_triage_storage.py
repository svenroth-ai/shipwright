"""Storage + lock + idempotency tests for the triage inbox.

AC-8 boundary probes (also AC-1 round-trip per ADR-024):
- Producer->file->consumer round-trip (every field preserved)
- Empty-file probe (missing file → [])
- Mixed-status (last-status-wins by file order)
- Corrupt-line probe (skip + continue)
- Concurrent in-process append (ThreadPoolExecutor)
- Cross-process append (subprocess)
- Stale-lock recovery (mirrors record_event.py pattern)
- Status-history-ordering (file order, not ts)
- Unicode + path-with-spaces probe
- Idempotent mark_status (no duplicate events on same status)
- File-existence: read on missing → []; mark_status on missing → FileNotFoundError
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402
from triage import (  # noqa: E402
    TRIAGE_FILE,
    append_triage_item,
    mark_status,
    read_all_items,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def project_with_spaces(tmp_path: Path) -> Path:
    """OneDrive-style path with spaces — matches user's working directory shape."""
    p = tmp_path / "AI Backup - Documents" / "shipwright"
    p.mkdir(parents=True)
    return p


# --- Round-trip: every field producer→file→consumer ---------------------

def test_round_trip_all_fields(project: Path) -> None:
    """ADR-024 round-trip: produce → file on disk → consume preserves every field."""
    item_id = append_triage_item(
        project,
        source="compliance",
        severity="high",
        kind="compliance",
        title="RLS policy missing on table x",
        detail="line 42 of supabase/migrations/0042_x.sql",
        evidence_path=".shipwright/compliance/audit-2026-05-11.json",
        run_id="iterate-2026-05-11-triage-inbox-1a",
        commit="abcdef0",
    )

    [resolved] = read_all_items(project)

    assert resolved["id"] == item_id
    assert resolved["source"] == "compliance"
    assert resolved["severity"] == "high"
    assert resolved["kind"] == "compliance"
    assert resolved["title"] == "RLS policy missing on table x"
    assert resolved["detail"] == "line 42 of supabase/migrations/0042_x.sql"
    assert resolved["evidencePath"] == ".shipwright/compliance/audit-2026-05-11.json"
    assert resolved["runId"] == "iterate-2026-05-11-triage-inbox-1a"
    assert resolved["commit"] == "abcdef0"
    assert resolved["status"] == "triage"
    assert resolved["suggestedPriority"] == "P1"  # high → P1
    assert resolved["suggestedDomain"] == "compliance"  # source=compliance


def test_optional_fields_default_to_none(project: Path) -> None:
    append_triage_item(
        project,
        source="phaseQuality",
        severity="info",
        kind="maintenance",
        title="t",
        detail="d",
    )
    [resolved] = read_all_items(project)
    assert resolved["evidencePath"] is None
    assert resolved["runId"] is None
    assert resolved["commit"] is None


# --- File-existence probes ----------------------------------------------

def test_read_missing_file_returns_empty(project: Path) -> None:
    """No .shipwright/ dir, no triage.jsonl → []."""
    assert read_all_items(project) == []


def test_mark_status_missing_file_raises(project: Path) -> None:
    """mark_status on missing file is a clear error (not silent)."""
    with pytest.raises(FileNotFoundError):
        mark_status(project, "trg-deadbeef", new_status="dismissed", by="test")


def test_mark_status_missing_id_raises(project: Path) -> None:
    """mark_status on file-exists but id-missing also raises clearly."""
    append_triage_item(
        project, source="phaseQuality", severity="low",
        kind="bug", title="t", detail="d",
    )
    with pytest.raises(KeyError, match="trg-00000000"):
        mark_status(project, "trg-00000000", new_status="dismissed", by="test")


# --- Last-status-wins (file order, NOT ts) ------------------------------

def test_last_status_wins_by_file_order(project: Path) -> None:
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    mark_status(project, item_id, new_status="snoozed", by="user")
    mark_status(project, item_id, new_status="promoted", by="user",
                promoted_task_id="EXT:asana-1")

    [resolved] = read_all_items(project)
    assert resolved["status"] == "promoted"
    assert resolved["promotedTaskId"] == "EXT:asana-1"


def test_idempotent_mark_status_same_value(project: Path) -> None:
    """Marking the same status twice is a no-op on the resolved view.

    The history records both events (audit trail), but the resolved record
    is unchanged.
    """
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    mark_status(project, item_id, new_status="dismissed", by="audit")
    mark_status(project, item_id, new_status="dismissed", by="audit",
                reason="duplicateDismiss")

    [resolved] = read_all_items(project)
    assert resolved["status"] == "dismissed"


def test_mark_status_appends_never_mutates(project: Path) -> None:
    """Spec: JSONL never mutated — history events appended only."""
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    path = project / ".shipwright" / TRIAGE_FILE
    before = path.read_text(encoding="utf-8")
    mark_status(project, item_id, new_status="dismissed", by="test")
    after = path.read_text(encoding="utf-8")

    # After is strictly an extension of before
    assert after.startswith(before)
    assert len(after) > len(before)


# --- Mixed-status / aggregator-shape probes -----------------------------

def test_mixed_statuses_all_returned(project: Path) -> None:
    """read_all_items returns ALL items (filtering is the aggregator's job)."""
    a = append_triage_item(project, source="phaseQuality", severity="high",
                           kind="bug", title="a", detail="d")
    b = append_triage_item(project, source="compliance", severity="medium",
                           kind="compliance", title="b", detail="d")
    c = append_triage_item(project, source="phaseQuality", severity="low",
                           kind="bug", title="c", detail="d")
    mark_status(project, b, new_status="dismissed", by="audit")
    mark_status(project, c, new_status="promoted", by="user",
                promoted_task_id="EXT:1")

    items = {item["id"]: item for item in read_all_items(project)}
    assert items[a]["status"] == "triage"
    assert items[b]["status"] == "dismissed"
    assert items[c]["status"] == "promoted"


# --- Corrupt-line tolerance ---------------------------------------------

def test_corrupt_line_skipped(project: Path) -> None:
    """Reader skips JSONDecodeError lines — mirror record_event.py:read_events."""
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    path = project / ".shipwright" / TRIAGE_FILE
    # Append a corrupt line in the middle
    with path.open("a", encoding="utf-8") as fp:
        fp.write("{this is not valid json\n")
    append_triage_item(project, source="phaseQuality", severity="low",
                       kind="bug", title="t2", detail="d2")

    items = read_all_items(project)
    assert {it["id"] for it in items} >= {item_id}
    assert len(items) == 2  # the two valid items


def test_corrupt_line_then_status_event_still_resolves(project: Path) -> None:
    """Status events for a partly-poisoned id still resolve correctly."""
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    path = project / ".shipwright" / TRIAGE_FILE
    with path.open("a", encoding="utf-8") as fp:
        fp.write("not json\n")
    mark_status(project, item_id, new_status="dismissed", by="test")

    [resolved] = read_all_items(project)
    assert resolved["status"] == "dismissed"


# --- File lock: in-process contention -----------------------------------

def test_concurrent_appends_thread_pool(project: Path) -> None:
    """8 threads append in parallel — all 8 lines visible, no torn writes."""
    def _append(idx: int) -> str:
        return append_triage_item(
            project, source="phaseQuality", severity="low",
            kind="bug", title=f"item-{idx}", detail=f"detail-{idx}",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        ids = list(ex.map(_append, range(8)))

    items = read_all_items(project)
    assert len({it["id"] for it in items}) == 8
    assert set(ids) == {it["id"] for it in items}


# --- File lock: cross-process contention --------------------------------

def test_concurrent_appends_subprocess(project: Path) -> None:
    """MED-7: Two subprocesses append in parallel — both visible."""
    # Script that appends one item via the public API
    helper = textwrap.dedent(f"""
        import sys
        from pathlib import Path
        sys.path.insert(0, r"{_SHARED_SCRIPTS}")
        from triage import append_triage_item
        title = sys.argv[1]
        append_triage_item(
            r"{project}", source="phaseQuality", severity="medium",
            kind="bug", title=title, detail="d",
        )
    """)
    helper_path = project / "_append_helper.py"
    helper_path.write_text(helper, encoding="utf-8")

    procs = [
        subprocess.Popen([sys.executable, str(helper_path), f"sub-{i}"])
        for i in range(2)
    ]
    for p in procs:
        rc = p.wait(timeout=30)
        assert rc == 0, f"helper exited {rc}"

    items = read_all_items(project)
    titles = {it["title"] for it in items}
    assert {"sub-0", "sub-1"} <= titles


# --- Stale lock recovery (best-effort) ----------------------------------

def test_stale_lockfile_does_not_block(project: Path) -> None:
    """A leftover .lock file from a killed process shouldn't block forever.

    msvcrt.locking only holds while the file is open; closing the orphaned
    lock-fp releases it. We simulate by creating the lock-file empty and
    asserting the next append succeeds.
    """
    shipwright_dir = project / ".shipwright"
    shipwright_dir.mkdir(parents=True, exist_ok=True)
    lock_path = shipwright_dir / (TRIAGE_FILE + ".lock")
    lock_path.write_text("", encoding="utf-8")  # leftover, not locked

    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    [resolved] = read_all_items(project)
    assert resolved["id"] == item_id


# --- Unicode + path-with-spaces -----------------------------------------

def test_unicode_and_path_with_spaces(project_with_spaces: Path) -> None:
    """OneDrive-shaped path (`AI Backup - Documents`) + unicode title."""
    append_triage_item(
        project_with_spaces,
        source="phaseQuality",
        severity="medium",
        kind="bug",
        title="Üñîçōdé title ✓ 中文",
        detail="multi\nline\ndetail",
    )
    [resolved] = read_all_items(project_with_spaces)
    assert resolved["title"] == "Üñîçōdé title ✓ 中文"
    assert "\n" in resolved["detail"]


# --- originalTs separation from event ts --------------------------------

def test_original_ts_preserved_across_status_changes(project: Path) -> None:
    """originalTs == the first append ts; ts == the latest event ts.
    Both should be ISO-8601 with Z; after status flip, originalTs unchanged.
    """
    item_id = append_triage_item(
        project, source="phaseQuality", severity="medium",
        kind="bug", title="t", detail="d",
    )
    [first] = read_all_items(project)
    original_ts = first["originalTs"]
    first_ts = first["ts"]
    assert original_ts == first_ts  # before any status change

    # small sleep avoided — we just want different content
    mark_status(project, item_id, new_status="dismissed", by="test")
    [after] = read_all_items(project)
    assert after["originalTs"] == original_ts
    # ts may equal first_ts when clock resolution merges, that's fine —
    # the contract is "ts is the latest event timestamp", not "ts > first_ts".


# --- Bootstrap idempotency -----------------------------------------------

def test_bootstrap_only_writes_header_once(project: Path) -> None:
    """Two appends in a row produce a header + 2 events, not 2 headers."""
    append_triage_item(project, source="phaseQuality", severity="low",
                       kind="bug", title="a", detail="d")
    append_triage_item(project, source="phaseQuality", severity="low",
                       kind="bug", title="b", detail="d")
    path = project / ".shipwright" / TRIAGE_FILE
    lines = [json.loads(L) for L in path.read_text(encoding="utf-8").splitlines() if L.strip()]
    headers = [L for L in lines if L.get("schema") == "triage"]
    assert len(headers) == 1


def test_preexisting_header_is_respected(project: Path) -> None:
    """If the scaffolder already wrote a header, append doesn't re-add."""
    shipwright_dir = project / ".shipwright"
    shipwright_dir.mkdir(parents=True, exist_ok=True)
    triage_path = shipwright_dir / TRIAGE_FILE
    triage_path.write_text(
        json.dumps({"v": 1, "schema": "triage", "created": "2026-01-01T00:00:00Z"})
        + "\n",
        encoding="utf-8",
    )

    append_triage_item(project, source="phaseQuality", severity="low",
                       kind="bug", title="t", detail="d")

    lines = [json.loads(L) for L in triage_path.read_text(encoding="utf-8").splitlines() if L.strip()]
    headers = [L for L in lines if L.get("schema") == "triage"]
    assert len(headers) == 1
    assert headers[0]["created"] == "2026-01-01T00:00:00Z"  # not overwritten


# --- Pure-function sanity check (also covered in test_triage_mapping.py) -

def test_module_constants_present() -> None:
    assert hasattr(triage, "SCHEMA_VERSION")
    assert hasattr(triage, "TRIAGE_FILE")
    assert triage.TRIAGE_FILE == "triage.jsonl"


# --- Idempotent append (producer dedup) ---------------------------------

def test_idempotent_append_skips_recent_duplicate(project: Path) -> None:
    """Same source + dedup_key + commit within window → 2nd call returns None."""
    from triage import append_triage_item_idempotent

    first = append_triage_item_idempotent(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="C1 phase event missing",
        detail="phase=iterate",
        dedup_key="C1",
        commit="abc123",
    )
    second = append_triage_item_idempotent(
        project,
        source="phaseQuality",
        severity="high",
        kind="bug",
        title="C1 phase event missing",
        detail="phase=iterate",
        dedup_key="C1",
        commit="abc123",
    )
    assert first is not None
    assert second is None  # deduplicated

    # Resolved view still has only one item
    items = read_all_items(project)
    assert len(items) == 1
    assert items[0]["dedupKey"] == "C1"


def test_idempotent_append_different_commit_creates_new(project: Path) -> None:
    """Different commit → not deduplicated (issue may recur per commit)."""
    from triage import append_triage_item_idempotent

    a = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="C1", detail="d", dedup_key="C1", commit="abc",
    )
    b = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="C1", detail="d", dedup_key="C1", commit="def",
    )
    assert a is not None
    assert b is not None
    assert a != b


def test_idempotent_append_different_source_creates_new(project: Path) -> None:
    """Same dedup_key but different source → two distinct items."""
    from triage import append_triage_item_idempotent

    a = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d", dedup_key="X", commit="abc",
    )
    b = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="X", commit="abc",
    )
    assert a is not None
    assert b is not None
    assert a != b


def test_idempotent_skips_only_when_status_triage(project: Path) -> None:
    """If a duplicate exists but status is dismissed/promoted, append goes through."""
    from triage import append_triage_item_idempotent

    first = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d", dedup_key="C1", commit="abc",
    )
    assert first is not None
    mark_status(project, first, new_status="dismissed", by="user",
                reason="not-actionable")

    # The dismissed-item should NOT count as a duplicate that suppresses
    # future reports.
    second = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d", dedup_key="C1", commit="abc",
    )
    assert second is not None
    assert second != first


def test_idempotent_requires_dedup_key(project: Path) -> None:
    from triage import append_triage_item_idempotent

    with pytest.raises(ValueError, match="dedup_key"):
        append_triage_item_idempotent(
            project, source="phaseQuality", severity="high", kind="bug",
            title="t", detail="d", dedup_key="", commit="abc",
        )


def test_idempotent_match_commit_false_dedups_across_commits(project: Path) -> None:
    """match_commit=False → dedup on (source, key) only (compliance-style)."""
    from triage import append_triage_item_idempotent

    a = append_triage_item_idempotent(
        project, source="compliance", severity="medium", kind="compliance",
        title="t", detail="d", dedup_key="RLS-MISSING-X", commit="abc",
        match_commit=False,
    )
    b = append_triage_item_idempotent(
        project, source="compliance", severity="medium", kind="compliance",
        title="t", detail="d", dedup_key="RLS-MISSING-X", commit="def",
        match_commit=False,
    )
    assert a is not None
    assert b is None  # different commit but match_commit=False → dedup


def test_idempotent_window_none_dedups_across_age(project: Path) -> None:
    """window_seconds=None → no age check; any open match suppresses.

    Compliance producer relies on this: a finding stays as one triage item
    indefinitely as long as the item's status is `triage`, regardless of
    how long ago it was appended (Gemini HIGH from code review — the
    default 24h window would re-emit compliance findings on day 2).
    """
    from triage import _triage_path, append_triage_item_idempotent

    first = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="A1",
        match_commit=False, window_seconds=None,
    )
    assert first is not None

    # Backdate the originalTs so a 24h window would expire — for a
    # window_seconds=None caller, the dedup should still suppress.
    path = _triage_path(project)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '"originalTs":"2026',  # match this year's timestamp prefix
        '"originalTs":"2020',  # 6 years old → far older than 24h
    )
    path.write_text(text, encoding="utf-8")

    second = append_triage_item_idempotent(
        project, source="compliance", severity="high", kind="compliance",
        title="t", detail="d", dedup_key="A1",
        match_commit=False, window_seconds=None,
    )
    assert second is None  # age-independent dedup still fires


def test_idempotent_concurrency_under_lock(project: Path) -> None:
    """HIGH-1 from code review: dedup-scan + append are atomic under lock.

    Spawn 8 threads with identical (source, dedup_key, commit). All
    threads race to append; lock serializes them; only ONE should win.
    Pre-fix, the dedup-scan happened before the lock and all 8 could
    pass the check and all 8 would append.
    """
    from triage import append_triage_item_idempotent

    def _attempt(_i: int) -> str | None:
        return append_triage_item_idempotent(
            project,
            source="phaseQuality", severity="high", kind="bug",
            title="contended-finding", detail="d",
            dedup_key="C1", commit="abc",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_attempt, range(8)))

    # Exactly one append, seven dedup-skips
    appended = [r for r in results if r is not None]
    skipped = [r for r in results if r is None]
    assert len(appended) == 1, (
        f"expected exactly 1 append, got {len(appended)}: {results}"
    )
    assert len(skipped) == 7
    # And only one item visible on disk
    items = read_all_items(project)
    matching = [it for it in items if it.get("dedupKey") == "C1"]
    assert len(matching) == 1


# --- Dedup-key matching is case-sensitive (producer-side canon contract) -

def test_idempotent_append_dedup_key_is_case_sensitive(project: Path) -> None:
    """Storage-layer dedup is an EXACT string match — `c:\\…` and `C:\\…`
    are DISTINCT keys.

    This is intentional and load-bearing: append_triage_item_idempotent
    also dedups non-path keys (compliance check codes `A5.0`, `B7`, `E1`,
    `G2`) which must never be case-folded. Path canonicalization for the
    drift producer is therefore the PRODUCER's responsibility
    (check_drift._canonical_anchor), NOT the storage layer's. This test
    guards against a well-intentioned "fix" that lowercases keys inside
    triage.py — which would silently merge distinct compliance findings.
    """
    from triage import append_triage_item_idempotent

    a = append_triage_item_idempotent(
        project, source="drift", severity="medium", kind="maintenance",
        title="t", detail="d", dedup_key="drift:c:\\X\\CLAUDE.md:content",
        match_commit=False, window_seconds=None,
    )
    b = append_triage_item_idempotent(
        project, source="drift", severity="medium", kind="maintenance",
        title="t", detail="d", dedup_key="drift:C:\\X\\CLAUDE.md:content",
        match_commit=False, window_seconds=None,
    )
    assert a is not None
    assert b is not None  # different-cased key → NOT deduplicated
    assert a != b
    assert len(read_all_items(project)) == 2
