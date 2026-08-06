"""``apply_gc``'s write path — audit 2026-07-28, finding 9 (+ the read-once and
fingerprint hardening the external plan review asked for).

Before this change ``apply_gc`` hand-rolled tmp + fsync + ``os.replace`` (no bounded
retry past a Windows sharing violation, no parent-directory fsync) and wrote its
``.bak`` with ``write_text``, which is neither durable nor newline-neutral. Measured
2026-08-06: an LF log's backup came back CRLF, so the recovery artifact was not a
copy of the thing it backed up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _p in (_SHARED_SCRIPTS, _SHARED_SCRIPTS / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import triage  # noqa: E402
import triage_gc  # noqa: E402
from lib import atomic_write, triage_gc_core  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-06-05T00:00:00Z"}'


def _seed(root: Path, *, eol: str = "\n") -> Path:
    """A tracked log with one machine-churn item (droppable) and one human one."""
    path = root / ".shipwright" / "triage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        HEADER,
        json.dumps({"event": "append", "id": "trg-mach", "ts": "2026-08-01T00:00:00Z",
                    "originalTs": "2026-08-01T00:00:00Z", "title": "m",
                    "status": "triage"}, separators=(",", ":")),
        json.dumps({"event": "status", "id": "trg-mach", "ts": "2026-08-02T00:00:00Z",
                    "newStatus": "dismissed", "by": "auditDetector",
                    "reason": "auditResolved"}, separators=(",", ":")),
        json.dumps({"event": "append", "id": "trg-keep", "ts": "2026-08-01T00:00:00Z",
                    "originalTs": "2026-08-01T00:00:00Z", "title": "k",
                    "status": "triage"}, separators=(",", ":")),
    ]
    path.write_bytes((eol.join(lines) + eol).encode("utf-8"))
    return path


def test_backup_is_byte_identical_to_what_it_backs_up(tmp_path: Path) -> None:
    """finding 9. ``write_text`` translated LF to CRLF on Windows, so the .bak of an
    LF log was a whole-file diff against the log — on a ``merge=union`` artifact."""
    path = _seed(tmp_path)
    before = path.read_bytes()
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert path.with_suffix(path.suffix + ".bak").read_bytes() == before


def test_backup_preserves_crlf_too(tmp_path: Path) -> None:
    """The other direction: a CRLF log's backup must stay CRLF, not be normalised."""
    path = _seed(tmp_path, eol="\r\n")
    before = path.read_bytes()
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert path.with_suffix(path.suffix + ".bak").read_bytes() == before
    assert b"\r\n" in before


def test_both_writes_go_through_the_durable_primitive(tmp_path: Path, monkeypatch) -> None:
    """The point of finding 9: the retries and the parent-dir fsync come from
    ``durable_atomic_write``, so both writes must actually reach it."""
    _seed(tmp_path)
    seen: list[str] = []
    real = atomic_write.durable_atomic_write

    def spy(path, data):
        seen.append(Path(path).name)
        return real(path, data)

    monkeypatch.setattr(triage_gc_core, "durable_atomic_write", spy)
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    # The backup is fsynced to a .bak.tmp sibling and RENAMED onto .bak after the
    # fingerprint check, so the fsync stays outside the compare→publish window.
    assert seen == ["triage.jsonl.bak.tmp", "triage.jsonl"], seen


def test_backup_and_compaction_come_from_one_read(tmp_path: Path, monkeypatch) -> None:
    """External plan review, round 2. The old code read the file twice — once for
    the backup, once for the rewrite input — so a writer landing between them left
    the .bak preserving a version that was never the one compacted."""
    path = _seed(tmp_path)
    reads: list[str] = []
    real_read_bytes = Path.read_bytes

    def counting(self):
        if self.name == "triage.jsonl":
            reads.append("read")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting)
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    # One read for the content, one for the pre-publish fingerprint check. The
    # rewrite input is derived from the FIRST — never re-read from disk.
    assert len(reads) == 2, reads
    assert path.exists()


def test_refuses_to_publish_when_the_log_moved_under_the_lock(tmp_path: Path, monkeypatch) -> None:
    """The WebUI writer does not take the canonical triage lock, so it can append
    inside our critical section. Publishing then destroys that append."""
    path = _seed(tmp_path)
    real_union = triage_gc_core._union_droppable_ids

    def append_then_recompute(project_root):
        # The non-cooperating writer lands after the source read, inside the locked
        # section. Injected at the union recompute because that is the last hook
        # BEFORE the fingerprint check — the backup now happens after it, so hanging
        # this off the .bak write (as an earlier version did) would fire too late and
        # the test would pass without exercising the check at all.
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"event": "append", "id": "trg-late",
                                 "originalTs": "2026-08-06T00:00:00Z",
                                 "title": "late", "status": "triage"},
                                separators=(",", ":")) + "\n")
        return real_union(project_root)

    monkeypatch.setattr(triage_gc_core, "_union_droppable_ids", append_then_recompute)
    with pytest.raises(RuntimeError, match="changed under us"):
        triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    # Nothing was published, so the late append is still there...
    assert "trg-late" in path.read_text(encoding="utf-8")
    assert "trg-mach" in path.read_text(encoding="utf-8")
    # ...and the refusal left no .bak for a compaction that never happened.
    assert not path.with_suffix(path.suffix + ".bak").exists()


def test_the_published_log_is_written_with_LF_on_every_platform(tmp_path: Path) -> None:
    """An unasserted behaviour change the code review surfaced: the old hand-rolled
    path used `open(tmp, "w")`, which emits CRLF on Windows; `durable_atomic_write`
    writes bytes verbatim, so the published log is now LF everywhere. That is the
    improvement (deterministic, matches CI) — pin it, because only the .bak's EOL
    was covered and a silent regression here rewrites a `merge=union` artifact."""
    path = _seed(tmp_path)
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    published = path.read_bytes()
    assert b"\r\n" not in published
    # header + trg-keep's append. trg-mach loses BOTH its append and its status line.
    assert published.count(b"\n") == 2
    assert published.endswith(b"}\n")           # exactly one trailing newline, LF


def test_malformed_json_refuses_before_writing_anything(tmp_path: Path) -> None:
    """The pre-existing refusal, re-pinned now that the write path changed: a refusal
    must leave no .bak and no partial rewrite behind."""
    path = _seed(tmp_path)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("{not json\n")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="malformed JSON"):
        triage_gc.apply_gc(tmp_path, {"trg-mach"})
    assert path.read_bytes() == before
    assert not path.with_suffix(path.suffix + ".bak").exists()


def test_backup_write_failure_leaves_the_live_log_untouched(tmp_path: Path, monkeypatch) -> None:
    """The backup is written FIRST, so a failure there must abort before the live
    log is republished — otherwise the compaction lands with no recovery copy."""
    path = _seed(tmp_path)
    before = path.read_bytes()

    def fail_on_backup(target, data):
        if ".bak" in Path(target).name:
            raise OSError("disk full")
        raise AssertionError("the live log must not be written after a backup failure")

    monkeypatch.setattr(triage_gc_core, "durable_atomic_write", fail_on_backup)
    with pytest.raises(OSError, match="disk full"):
        triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert path.read_bytes() == before


def test_publish_failure_leaves_the_live_log_untouched(tmp_path: Path, monkeypatch) -> None:
    """``durable_atomic_write`` removes its temp and re-raises on failure, so the
    live path is never left pointing at a half-written file."""
    path = _seed(tmp_path)
    before = path.read_bytes()
    real = atomic_write.durable_atomic_write

    def fail_on_live(target, data):
        if Path(target).name == "triage.jsonl":
            raise OSError("simulated replace failure")
        return real(target, data)

    monkeypatch.setattr(triage_gc_core, "durable_atomic_write", fail_on_live)
    with pytest.raises(OSError, match="simulated replace failure"):
        triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert path.read_bytes() == before
    assert not list(path.parent.glob("triage.jsonl.*.tmp"))


def test_undecodable_bytes_refuse_the_rewrite(tmp_path: Path) -> None:
    """The decode is STRICT by design — this rewrites a tracked artifact wholesale,
    so a byte we cannot read is a reason to refuse rather than round-trip blindly.
    What matters is that refusing costs nothing: no backup, no partial publish."""
    path = _seed(tmp_path)
    before = path.read_bytes()
    with path.open("ab") as fh:
        fh.write(b'{"event":"append","id":"trg-bad","title":"\xff\xfe"}\n')
    poisoned = path.read_bytes()

    with pytest.raises(UnicodeDecodeError):
        triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])

    assert path.read_bytes() == poisoned          # nothing published
    assert path.read_bytes() != before            # control: the poison really landed
    assert not path.with_suffix(path.suffix + ".bak").exists()


def test_apply_gc_keeps_its_historical_return(tmp_path: Path) -> None:
    """``apply_gc`` returns the backup path (or the live path with backup=False).
    The reporting variant is additive — existing callers must be unaffected."""
    path = _seed(tmp_path)
    got = triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert got == path.with_suffix(path.suffix + ".bak")
    _seed(tmp_path)
    assert triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"],
                              backup=False) == path


def test_reporting_variant_returns_the_bytes_it_published(tmp_path: Path) -> None:
    """``--commit`` needs the exact content GC wrote; re-reading the file cannot
    prove the file is still that content."""
    path = _seed(tmp_path)
    applied = triage_gc.apply_gc_reporting(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    assert applied.written_text == path.read_text(encoding="utf-8")
    assert applied.dropped == 1
    assert "trg-mach" not in applied.written_text
    assert "trg-keep" in applied.written_text
    assert {i["id"] for i in triage.read_all_items(tmp_path)} == {"trg-keep"}
