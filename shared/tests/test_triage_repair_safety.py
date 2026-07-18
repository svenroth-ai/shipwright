"""Repair-pass SAFETY guarantees: minimal rewrite, refusals, lock ordering.

Split out of `test_triage_repair.py` at the 300-LOC gate
(iterate-2026-07-18-outbox-newline-corruption). These are the properties that keep
the repair from becoming the very defect it fixes: it must not reflow a tracked
log's EOLs, must never destroy bytes it cannot preserve, and must hold the
canonical lock across the read so a cooperating writer is not overwritten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# `shared/scripts` MUST precede `shared/tests` on sys.path: BOTH contain a real
# `tools` package, and `shared/tests/tools` would otherwise shadow the one holding
# triage_repair. conftest already puts `shared/tests` on the path, so insert this
# at position 0 unconditionally rather than guarding on membership (a guard would
# leave a pre-existing, lower-priority entry in place).
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
# The sibling-helper dir goes at the END: prepending it would put `shared/tests`
# ahead of `shared/scripts` and re-shadow `tools`.
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.append(_TESTS)

import triage  # noqa: E402
from _triage_repair_helpers import (  # noqa: E402
    APPEND,
    STATUS,
    corrupt_outbox as _corrupt_outbox,
    j as _j,
    project as _project,
)
from tools.triage_repair import main  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal rewrite — do not reflow EOLs or re-serialize healthy lines
# ---------------------------------------------------------------------------

def test_crlf_tracked_log_is_not_reflowed_to_lf(tmp_path: Path) -> None:
    """Re-serializing every line would produce a whole-file diff on a merge=union
    tracked artifact — a defect this repo already has a regression test for."""
    project = _project(tmp_path)
    header = {"v": 1, "schema": "triage", "created": "2026-07-18T09:00:00Z"}
    other = {"event": "append", "id": "trg-bbbbbbbb"}
    tracked = triage._triage_path(project)
    tracked.write_bytes(
        (_j(header) + "\r\n" + _j(other) + "\r\n" + _j(APPEND) + _j(STATUS) + "\r\n").encode()
    )

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    raw = tracked.read_bytes()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n"), "EOL style must survive"
    lines = raw.decode("utf-8").splitlines()
    assert json.loads(lines[0]) == header, "schema header must survive"
    assert [json.loads(ln) for ln in lines] == [header, other, APPEND, STATUS]


def test_healthy_lines_are_preserved_byte_for_byte(tmp_path: Path) -> None:
    """A spaced-out but valid line must not be silently re-serialized."""
    project = _project(tmp_path)
    spaced = '{"event": "append", "id": "trg-spaced"}'
    p = triage._outbox_path(project)
    p.write_bytes((spaced + "\n" + _j(APPEND) + _j(STATUS) + "\n").encode())

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    assert p.read_text(encoding="utf-8").splitlines()[0] == spaced


# ---------------------------------------------------------------------------
# Refusals — never destroy what cannot be preserved
# ---------------------------------------------------------------------------

def test_file_with_invalid_utf8_is_reported_but_not_rewritten(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = triage._outbox_path(project)
    p.write_bytes(_j(APPEND).encode() + b"\xff\xfe garbage\n")
    before = p.read_bytes()

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 1
    assert p.read_bytes() == before, "undecodable bytes must not be destroyed"


def test_wholly_unrecoverable_file_is_not_emptied(tmp_path: Path) -> None:
    """Rewriting to zero bytes would drop the schema header and wedge the sweep."""
    project = _project(tmp_path)
    tracked = triage._triage_path(project)
    tracked.write_bytes(b"total garbage not json\n")
    before = tracked.read_bytes()

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 1
    assert tracked.read_bytes() == before


def test_repaired_file_reads_back_through_the_public_api(tmp_path: Path) -> None:
    """Round-trip: repair on disk must agree with what the reader recovers."""
    project = _project(tmp_path)
    item_id = triage.append_triage_item(
        project, source="compliance", severity="low", kind="improvement",
        title="t", detail="d", to_outbox=True,
    )
    outbox = triage._outbox_path(project)
    existing = outbox.read_text(encoding="utf-8").rstrip("\n")
    status = {"event": "status", "id": item_id, "ts": "2026-07-18T11:00:00Z",
              "newStatus": "dismissed", "by": "webui", "reason": "Implemented"}
    outbox.write_bytes((existing + _j(status) + "\n").encode())

    before = {i["id"]: i["status"] for i in triage.read_all_items(project)}
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    after = {i["id"]: i["status"] for i in triage.read_all_items(project)}
    assert before == after == {item_id: "dismissed"}


def test_clean_corpus_is_a_noop(tmp_path: Path) -> None:
    project = _project(tmp_path)
    triage.append_triage_item(
        project, source="compliance", severity="low", kind="improvement",
        title="t", detail="d", to_outbox=True,
    )
    outbox = triage._outbox_path(project)
    before = outbox.read_bytes()
    assert main(["--project-root", str(project)]) == 0
    assert outbox.read_bytes() == before


def test_apply_scans_inside_the_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scanning outside the lock lets a cooperating writer append between the read
    and the atomic replace; the stale snapshot then overwrites that record."""
    import tools.triage_repair as tr

    project = _project(tmp_path)
    _corrupt_outbox(project)
    order: list[str] = []

    real_lock_cls = tr.triage._load_file_lock_cls()
    real_scan = tr.scan_path

    class SpyLock:
        def __init__(self, path):
            self._inner = real_lock_cls(path)

        def __enter__(self):
            order.append("lock")
            return self._inner.__enter__()

        def __exit__(self, *exc):
            order.append("unlock")
            return self._inner.__exit__(*exc)

    def spy_scan(path):
        order.append("scan")
        return real_scan(path)

    monkeypatch.setattr(tr.triage, "_load_file_lock_cls", lambda: SpyLock)
    monkeypatch.setattr(tr, "scan_path", spy_scan)

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    assert order[0] == "lock", f"scan must happen inside the lock, got {order}"
    assert "scan" in order and order.index("scan") < order.index("unlock")


def test_report_mode_takes_no_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Report mode is read-only; taking the canonical lock would block producers."""
    import tools.triage_repair as tr

    project = _project(tmp_path)
    _corrupt_outbox(project)

    def boom_lock():
        raise AssertionError("report mode must not take the lock")

    monkeypatch.setattr(tr.triage, "_load_file_lock_cls", boom_lock)
    assert main(["--project-root", str(project)]) == 1
