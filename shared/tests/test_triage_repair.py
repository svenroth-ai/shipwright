"""Repair pass for already-corrupted triage lines.

The outbox is UNTRACKED, so a corrupted line has no git history to recover from —
repair must preserve both records. Regression home for
iterate-2026-07-18-outbox-newline-corruption (AC4).
"""
from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from tools.triage_repair import main, scan_path  # noqa: E402

APPEND = {"event": "append", "id": "trg-aaaaaaaa", "ts": "2026-07-18T10:00:00Z"}
STATUS = {"event": "status", "id": "trg-aaaaaaaa", "newStatus": "dismissed", "by": "webui"}


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _corrupt_outbox(project: Path, *, tail: str = "") -> Path:
    p = triage._outbox_path(project)
    p.write_bytes((_j(APPEND) + _j(STATUS) + tail + "\n").encode())
    return p


# ---------------------------------------------------------------------------
# scan — reporting
# ---------------------------------------------------------------------------

def test_scan_reports_a_concatenated_line(tmp_path: Path) -> None:
    p = _corrupt_outbox(_project(tmp_path))
    report = scan_path(p)
    assert report.needs_repair is True
    assert report.recovered_records == 2
    assert report.unrecoverable == []


def test_scan_is_clean_on_a_healthy_file(tmp_path: Path) -> None:
    p = triage._outbox_path(_project(tmp_path))
    p.write_bytes((_j(APPEND) + "\n" + _j(STATUS) + "\n").encode())
    assert scan_path(p).needs_repair is False


def test_scan_flags_an_unterminated_file(tmp_path: Path) -> None:
    """An unterminated file is a latent corruption: the NEXT append concatenates."""
    p = triage._outbox_path(_project(tmp_path))
    p.write_bytes(_j(APPEND).encode())
    assert scan_path(p).needs_repair is True


def test_scan_separates_unrecoverable_text(tmp_path: Path) -> None:
    p = _corrupt_outbox(_project(tmp_path), tail='{"truncated":')
    report = scan_path(p)
    assert report.recovered_records == 2
    assert report.unrecoverable == ['{"truncated":']


# ---------------------------------------------------------------------------
# --apply — mutation
# ---------------------------------------------------------------------------

def test_report_mode_never_mutates(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    before = p.read_bytes()
    assert main(["--project-root", str(project)]) == 1  # non-zero: repair needed
    assert p.read_bytes() == before


def test_apply_requires_the_quiesced_acknowledgement(tmp_path: Path) -> None:
    """The atomic replace swaps the inode; a non-cooperating writer would be lost."""
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    before = p.read_bytes()
    assert main(["--project-root", str(project), "--apply"]) == 2
    assert p.read_bytes() == before


def test_apply_splits_the_line_and_preserves_both_records(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [json.loads(ln) for ln in lines] == [APPEND, STATUS]
    assert p.read_bytes().endswith(b"\n")


def test_apply_terminates_an_unterminated_file(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = triage._outbox_path(project)
    p.write_bytes(_j(APPEND).encode())
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    assert p.read_bytes().endswith(b"\n")


def test_apply_quarantines_unrecoverable_text_verbatim(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project, tail='{"truncated":')
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    # Both good records survive in the repaired file...
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [json.loads(ln) for ln in lines] == [APPEND, STATUS]

    # ...and the unrecoverable fragment is preserved, not dropped.
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"
    entries = [json.loads(ln) for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert any(e["original"] == '{"truncated":' for e in entries)


def test_retry_after_a_crashed_replace_does_not_double_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real retry: quarantine succeeded, the replace then failed, so the
    fragment is STILL on disk and the next run re-processes it.

    The previous version of this test re-ran `main` on an already-repaired file, so
    it never reached `_repair` at all and passed even with the whole content-hash
    dedupe deleted (caught by both reviewers as a false green).
    """
    import tools.triage_repair as tr

    project = _project(tmp_path)
    _corrupt_outbox(project, tail='{"truncated":')
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"

    boom = {"n": 0}

    def exploding_write(path, data):
        boom["n"] += 1
        raise OSError("simulated crash after quarantine, before replace")

    monkeypatch.setattr(tr, "durable_atomic_write", exploding_write)
    with pytest.raises(OSError):
        main(["--project-root", str(project), "--apply", "--writers-quiesced"])
    monkeypatch.undo()  # restore before the retry below re-runs the real write

    assert boom["n"] == 1
    first = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(first) == 1  # quarantined before the crash

    # The source is untouched, so the retry hits _repair again with the same fragment.
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    second = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(second) == 1, "content-hash dedupe must not re-quarantine the fragment"


def test_repeated_identical_fragments_quarantine_once(tmp_path: Path) -> None:
    """Dedupe also applies within a single run."""
    project = _project(tmp_path)
    frag = '{"truncated":'
    p = triage._outbox_path(project)
    p.write_bytes(((_j(APPEND) + frag + "\n") * 2).encode())

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"
    entries = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(entries) == 1


def test_second_run_on_a_repaired_file_is_clean(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _corrupt_outbox(project)
    argv = ["--project-root", str(project), "--apply", "--writers-quiesced"]
    assert main(argv) == 0
    after = triage._outbox_path(project).read_bytes()
    assert main(argv) == 0
    assert triage._outbox_path(project).read_bytes() == after


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
