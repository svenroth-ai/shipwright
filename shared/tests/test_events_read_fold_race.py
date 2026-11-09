"""A fold racing the assembling reader (issue 978, S2 review F1 closed in S6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lib.events_log import ARCHIVE_DIR, DROPS_DIR
from lib.events_read import read_events_assembled

sys.path.append(str(Path(__file__).resolve().parent))
from _events_read_helpers import _drop, _line, _write  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def test_a_fold_racing_the_read_never_loses_an_event_and_stays_fail_closed(tmp_path, monkeypatch):
    """S2 review F1 (closed in S6): the drop is folded between the listing and the read."""
    import lib.events_read as er
    path = _drop(tmp_path, "run-f", _line(id="1", ts="2026-01-01T00:00:00Z"))
    real, state = er._read_one, {"folded": False}

    def fold_then_read(p, kind):
        if not state["folded"] and Path(p) == path:
            state["folded"] = True
            _write(tmp_path / ARCHIVE_DIR / "fold-aaaaaaaaaaaa.jsonl", _line(id="1", ts="2026-01-01T00:00:00Z"))
            path.unlink()
        return real(p, kind)

    monkeypatch.setattr(er, "_read_one", fold_then_read)
    read = read_events_assembled(tmp_path)
    assert [e["id"] for e in read.records] == ["1"]                 # from the archive, once
    assert [f.status for f in read.files if f.kind == "drop"] == ["unreadable"]
    assert read.absence_blockers("run-f")                            # the gate still refuses to say "absent"


def test_event_files_list_the_drops_before_the_archive(tmp_path, monkeypatch):
    """A fold adds the archive file first: listing drops first can see an event twice, never zero times."""
    import lib.events_log as el
    _drop(tmp_path, "run-o", _line(id="1"))
    _write(tmp_path / ARCHIVE_DIR / "fold-aaaaaaaaaaaa.jsonl", _line(id="1"))
    listed: list[str] = []
    real_glob = Path.glob

    def spy(self, pattern):
        listed.append(self.name)
        return real_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", spy)
    names = [p.parent.name for p in el.event_files(tmp_path)[1:]]
    assert listed == [DROPS_DIR, ARCHIVE_DIR] and names == [ARCHIVE_DIR, DROPS_DIR]
