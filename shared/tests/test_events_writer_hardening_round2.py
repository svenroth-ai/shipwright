"""Second hardening round of the per-run event file layout.

1 one definition of a drop file name, shared by the writer, the reader, the staging tool, the fold and the
  integrity check (they used three different patterns);
2 a run's events keep their order across a rotation: the first event of a new file never ties with, or sorts
  before, an earlier event of the same run key;
3 the writer never appends to a drop whose last line is torn: it starts a new file and keeps using that one;
4 the legacy layout writes the same bytes as before.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _events_drops_fixtures import _append, _drop_names, _ev, _git, _drops_repo, _layout  # noqa: E402,F401
from lib import events_stage  # noqa: E402
from lib.events_fold_io import drop_key_of, name_problem  # noqa: E402
from lib.events_layout import worktree_id  # noqa: E402
from lib.events_log import DROPS_DIR  # noqa: E402
from lib.events_read import DROP_NAME, read_events_assembled  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

LATER = "2026-11-06T10:00:05+00:00"
EARLIER = "2026-11-06T09:59:00+00:00"


def _ids(root) -> list[str]:
    """The events in the REAL reader's order (parsed instant, then id)."""
    return [e["id"] for e in read_events_assembled(root).records]


def _close(root) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "close the open drop")


def _plant(root, name: str, *events: dict) -> Path:
    path = root / DROPS_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in events), encoding="utf-8", newline="\n")
    return path


# ---- 1 one name rule -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,ok", [
    ("run-x--aaaaaaaa--00000001.jsonl", True),
    ("campaign-s--u1--aaaaaaaa--00000001.jsonl", True),    # a per-unit key contains the separator itself
    ("_branch-feat-x--aaaaaaaa--00000001.jsonl", True),
    ("k" * 80 + "--aaaaaaaa--00000001.jsonl", True),
    ("x--AAAAAAAA--00000001.jsonl", False),                # not lower-case hex
    ("x--aaaaaaa--00000001.jsonl", False),                 # short worktree id
    ("x--aaaaaaaa--00000001.jsonl.bak", False),
    ("x--aaaaaaaa--00000001.jsonl\n", False),              # a trailing newline: ``$`` would have let it through
    (".hidden--aaaaaaaa--00000001.jsonl", False),          # keys never start with a dot
    ("a b--aaaaaaaa--00000001.jsonl", False),              # a space is not a key character
    ("--aaaaaaaa--00000001.jsonl", False),                 # empty key
    ("k" * 81 + "--aaaaaaaa--00000001.jsonl", False),      # key over 80 characters
])
def test_every_module_judges_a_drop_name_the_same_way(name, ok):
    assert bool(DROP_NAME.match(name)) is ok                          # the reader
    assert (name_problem(DROPS_DIR, name) is None) is ok              # fold / quarantine / integrity check
    assert (drop_key_of(name) is not None) is ok


def test_the_writers_open_file_check_refuses_a_trailing_newline_in_the_nonce():
    from lib.events_layout import _NONCE
    assert _NONCE.match("0000abcd") and not _NONCE.match("0000abcd\n")


def test_the_staging_tool_has_no_name_pattern_of_its_own():
    assert events_stage._NAME is DROP_NAME


def test_a_name_the_integrity_checker_refuses_is_not_staged_either(drops_repo):
    wt8 = worktree_id(drops_repo)
    bad = _plant(drops_repo, f"a b--{wt8}--00000001.jsonl", _ev("evt-0000000000000b01"))
    good = _plant(drops_repo, f"ab--{wt8}--00000001.jsonl", _ev("evt-0000000000000b02"))
    assert name_problem(DROPS_DIR, bad.name) is not None
    assert events_stage.wt_drops(drops_repo) == [f"{DROPS_DIR}/{good.name}"]


@pytest.mark.parametrize("run_id", ["iterate 2026/odd id", "x" * 300, ".dotted", "ünï-run"])
def test_every_name_the_writer_makes_fits_the_one_rule(drops_repo, run_id):
    _append(drops_repo, _ev("evt-0000000000000c01"), run_id)
    names = _drop_names(drops_repo)
    assert names and all(DROP_NAME.match(n) for n in names)


def test_the_reader_loads_standalone_by_path_and_still_parses_the_drop_key(tmp_path):
    """Sentinel / flat context (``load_shared_lib``): no ``lib`` package on sys.path. The name rule lives inside events_read."""
    import subprocess
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(_ev("a")) + "\n", encoding="utf-8")
    _plant(tmp_path, "run-s--aaaaaaaa--00000001.jsonl", _ev("b", run="run-s", ts=LATER))
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('_flat_events_read', {str(_SCRIPTS / 'lib' / 'events_read.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)\n"
        f"read = mod.read_events_assembled({str(tmp_path)!r})\n"
        "print(','.join(e['id'] for e in read.records) + '|' + ','.join(str(f.key) for f in read.files if f.kind == 'drop'))\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip() == "a,b|run-s"


# ---- 2 order across a rotation ---------------------------------------------------------------------------------

def test_the_first_event_of_a_rotated_file_follows_the_last_event_of_the_closed_one(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000ff"), "r")
    _close(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001"), "r")   # same ts, smaller id: it sorted FIRST before the fix
    assert len(_drop_names(drops_repo)) == 2
    assert _ids(drops_repo) == ["evt-00000000000000ff", "evt-0000000000000001"]


def test_a_clock_that_runs_behind_the_stored_events_is_pushed_past_them(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000f1", ts=LATER), "r")
    _close(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001", ts=EARLIER), "r")
    assert _ids(drops_repo) == ["evt-00000000000000f1", "evt-0000000000000001"]


def test_the_newest_event_of_several_closed_files_wins_whatever_their_names_sort_like(drops_repo):
    _plant(drops_repo, "r--aaaaaaaa--ffffffff.jsonl", _ev("evt-0000000000000d01", ts=EARLIER, run="r"))
    _plant(drops_repo, "r--aaaaaaaa--00000000.jsonl", _ev("evt-0000000000000d02", ts=LATER, run="r"))
    _close(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001", ts=EARLIER), "r")
    assert _ids(drops_repo)[-1] == "evt-0000000000000001"


def test_the_order_holds_across_worktrees_of_the_same_run_key(drops_repo):
    _plant(drops_repo, "r--bbbbbbbb--00000001.jsonl", _ev("evt-00000000000000f2", run="r"))   # another worktree's file
    _close(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001"), "r")
    assert _ids(drops_repo) == ["evt-00000000000000f2", "evt-0000000000000001"]


def test_another_runs_events_do_not_move_this_runs_timestamps(drops_repo):
    _plant(drops_repo, "other--aaaaaaaa--00000001.jsonl", _ev("evt-00000000000000f3", ts=LATER, run="other"))
    _close(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001"), "r")
    assert read_events_assembled(drops_repo).records[0]["id"] == "evt-0000000000000001"


# ---- 3 a torn open drop ----------------------------------------------------------------------------------------

def _tear(root) -> Path:
    (first,) = [root / DROPS_DIR / n for n in _drop_names(root)]
    with first.open("ab") as fp:
        fp.write(b'{"v":1,"id":"evt-0000000000000a0')   # a write that died half way
    return first


def test_a_torn_open_drop_is_not_appended_to_and_the_new_file_is_then_reused(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000a01"), "r")
    torn = _tear(drops_repo)
    before = torn.read_bytes()
    for n in (2, 3, 4):
        _append(drops_repo, _ev(f"evt-0000000000000a0{n}"), "r")
    assert len(_drop_names(drops_repo)) == 2, "later writes must go to the one new file"
    assert torn.read_bytes() == before, "the torn file was changed"
    assert _ids(drops_repo) == [f"evt-0000000000000a0{n}" for n in (1, 2, 3, 4)]


def test_the_first_event_after_a_torn_file_does_not_tie_with_its_last_valid_event(drops_repo):
    _append(drops_repo, _ev("evt-00000000000000f4"), "r")
    _tear(drops_repo)
    _append(drops_repo, _ev("evt-0000000000000001"), "r")   # same ts, smaller id
    assert _ids(drops_repo) == ["evt-00000000000000f4", "evt-0000000000000001"]


def test_an_empty_drop_is_still_reused(drops_repo):
    empty = drops_repo / DROPS_DIR / f"r--{worktree_id(drops_repo)}--00000001.jsonl"   # named like this worktree's open drop
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_bytes(b"")
    _append(drops_repo, _ev("evt-0000000000000a01"), "r")
    assert _drop_names(drops_repo) == [empty.name]
    assert _ids(drops_repo) == ["evt-0000000000000a01"]


def test_a_complete_last_record_that_only_lacks_its_newline_still_counts_as_torn(drops_repo):
    _append(drops_repo, _ev("evt-0000000000000a01"), "r")
    (first,) = [drops_repo / DROPS_DIR / n for n in _drop_names(drops_repo)]
    first.write_bytes(first.read_bytes().rstrip(b"\n"))
    _append(drops_repo, _ev("evt-0000000000000a02"), "r")
    assert len(_drop_names(drops_repo)) == 2 and not first.read_bytes().endswith(b"\n")
    assert _ids(drops_repo) == ["evt-0000000000000a01", "evt-0000000000000a02"]


# ---- 4 legacy bytes --------------------------------------------------------------------------------------------

def test_the_legacy_layout_writes_exactly_the_bytes_it_always_did(tmp_path, monkeypatch):
    _layout(monkeypatch, "legacy")
    root = tmp_path / "repo"
    root.mkdir()
    event = _ev("evt-1a2b3c4d")
    _append(root, dict(event), "r")
    expected = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + os.linesep   # legacy appends in text mode, as always
    assert (root / "shipwright_events.jsonl").read_bytes() == expected.encode("utf-8")
    assert not (root / DROPS_DIR).exists()
