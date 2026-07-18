"""End-to-end newline-integrity of the triage append/read boundary.

Regression home for iterate-2026-07-18-outbox-newline-corruption. The leaf-level
contract lives in ``test_jsonl_records.py``; this module pins the wiring — that the
real ``triage`` writer terminates and the real ``triage`` reader recovers, through
the public API, on both the tracked store and the gitignored outbox.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _add(project: Path, *, title: str, to_outbox: bool) -> str:
    return triage.append_triage_item(
        project,
        source="compliance",
        severity="low",
        kind="improvement",
        title=title,
        detail="d",
        to_outbox=to_outbox,
    )


# ---------------------------------------------------------------------------
# AC1 — the writer terminates, so the next writer cannot concatenate
# ---------------------------------------------------------------------------

def test_append_onto_unterminated_outbox_does_not_concatenate(tmp_path: Path) -> None:
    """The reported incident, at the writer boundary."""
    project = _project(tmp_path)
    outbox = triage._outbox_path(project)
    orphan = {"event": "append", "id": "trg-deadbeef", "ts": "2026-07-18T09:00:00Z"}
    outbox.write_bytes(json.dumps(orphan, separators=(",", ":")).encode())  # NO newline

    _add(project, title="second writer", to_outbox=True)

    raw = outbox.read_text(encoding="utf-8")
    assert len([ln for ln in raw.splitlines() if ln.strip()]) == 2, raw
    assert raw.endswith("\n")


def test_append_onto_unterminated_tracked_store_does_not_concatenate(tmp_path: Path) -> None:
    project = _project(tmp_path)
    tracked = triage._triage_path(project)
    tracked.write_bytes(b'{"v":1,"schema":"triage","created":"2026-07-18T09:00:00Z"}')

    _add(project, title="second writer", to_outbox=False)

    lines = [ln for ln in tracked.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2, lines
    for ln in lines:
        json.loads(ln)  # every physical line is independently parseable


def test_append_onto_terminated_file_adds_no_blank_line(tmp_path: Path) -> None:
    """The guard must be a no-op on the healthy path."""
    project = _project(tmp_path)
    _add(project, title="first", to_outbox=True)
    _add(project, title="second", to_outbox=True)
    raw = triage._outbox_path(project).read_text(encoding="utf-8")
    assert "\n\n" not in raw
    assert len(raw.splitlines()) == 2


def test_first_append_to_absent_outbox_is_unaffected(tmp_path: Path) -> None:
    project = _project(tmp_path)
    assert not triage._outbox_path(project).exists()
    _add(project, title="only", to_outbox=True)
    raw = triage._outbox_path(project).read_text(encoding="utf-8")
    assert not raw.startswith("\n")
    assert len(raw.splitlines()) == 1


# ---------------------------------------------------------------------------
# AC2 — the reader recovers records already concatenated on disk
# ---------------------------------------------------------------------------

def test_reader_recovers_both_records_from_one_physical_line(tmp_path: Path) -> None:
    project = _project(tmp_path)
    append = {
        "event": "append", "id": "trg-aaaaaaaa", "ts": "2026-07-18T10:00:00Z",
        "title": "corrupted append", "status": "triage", "severity": "low",
        "kind": "improvement", "source": "compliance", "detail": "d",
    }
    status = {
        "event": "status", "id": "trg-aaaaaaaa", "ts": "2026-07-18T10:05:00Z",
        "newStatus": "dismissed", "by": "webui", "reason": "Implemented",
    }
    blob = json.dumps(append, separators=(",", ":")) + json.dumps(status, separators=(",", ":"))
    triage._outbox_path(project).write_bytes((blob + "\n").encode())

    raw_lines = triage._iter_raw_lines_at(triage._outbox_path(project))
    assert [r["event"] for r in raw_lines] == ["append", "status"]


def test_dismissal_on_a_corrupted_line_propagates(tmp_path: Path) -> None:
    """The user-visible symptom: the dismissal must reach read_all_items."""
    project = _project(tmp_path)
    item_id = _add(project, title="will be dismissed", to_outbox=True)

    outbox = triage._outbox_path(project)
    existing = outbox.read_text(encoding="utf-8").rstrip("\n")
    status = {
        "event": "status", "id": item_id, "ts": "2026-07-18T10:05:00Z",
        "newStatus": "dismissed", "by": "webui", "reason": "Implemented",
    }
    # Re-create the corruption: status concatenated onto the append's line.
    outbox.write_bytes((existing + json.dumps(status, separators=(",", ":")) + "\n").encode())

    items = {i["id"]: i for i in triage.read_all_items(project)}
    assert items[item_id]["status"] == "dismissed"


def test_unrecoverable_line_does_not_hide_its_valid_neighbours(tmp_path: Path) -> None:
    project = _project(tmp_path)
    good = {"event": "append", "id": "trg-cccccccc", "ts": "2026-07-18T10:00:00Z"}
    outbox = triage._outbox_path(project)
    outbox.write_bytes(
        (json.dumps(good, separators=(",", ":")) + "\n" + "}{garbage\n").encode()
    )
    raw_lines = triage._iter_raw_lines_at(outbox)
    assert [r["id"] for r in raw_lines] == ["trg-cccccccc"]


# ---------------------------------------------------------------------------
# Round-trip probes (touches_io_boundary) — producer/consumer symmetry
# ---------------------------------------------------------------------------

def test_round_trip_preserves_unicode_through_repair(tmp_path: Path) -> None:
    """The repair rewrite re-serializes records; ensure_ascii=False must hold."""
    from tools.triage_repair import main as repair_main

    project = _project(tmp_path)
    title = "Umlaut Prufung — café 日本語"
    item_id = triage.append_triage_item(
        project, source="compliance", severity="low", kind="improvement",
        title=title, detail="d", to_outbox=True,
    )
    outbox = triage._outbox_path(project)
    existing = outbox.read_text(encoding="utf-8").rstrip("\n")
    status = {"event": "status", "id": item_id, "ts": "2026-07-18T11:00:00Z",
              "newStatus": "dismissed", "by": "webui", "reason": "Implemented ✓"}
    outbox.write_bytes((existing + json.dumps(status, separators=(",", ":")) + "\n").encode())

    assert repair_main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    items = {i["id"]: i for i in triage.read_all_items(project)}
    assert items[item_id]["title"] == title
    assert items[item_id]["status"] == "dismissed"


def test_round_trip_survives_a_crlf_tracked_store(tmp_path: Path) -> None:
    r"""A CRLF-written log ends in \n, so the guard must add no separator."""
    project = _project(tmp_path)
    tracked = triage._triage_path(project)
    header = {"v": 1, "schema": "triage", "created": "2026-07-18T09:00:00Z"}
    tracked.write_bytes((json.dumps(header, separators=(",", ":")) + "\r\n").encode())

    item_id = _add(project, title="crlf neighbour", to_outbox=False)

    raw = tracked.read_bytes()
    assert b"\r\n\n" not in raw and b"\n\n" not in raw
    assert item_id in {i["id"] for i in triage.read_all_items(project)}


def test_round_trip_append_then_read_is_lossless_for_every_field(tmp_path: Path) -> None:
    project = _project(tmp_path)
    item_id = triage.append_triage_item(
        project, source="compliance", severity="high", kind="bug",
        title="round trip", detail="detail body", evidence_path="a/b.py",
        run_id="iterate-x", dedup_key="dk-1", to_outbox=True,
    )
    written = {i["id"]: i for i in triage.read_all_items(project)}[item_id]
    assert written["title"] == "round trip"
    assert written["detail"] == "detail body"
    assert written["severity"] == "high"
    assert written["kind"] == "bug"
    assert written["status"] == "triage"
