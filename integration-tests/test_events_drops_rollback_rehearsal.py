"""Both rollbacks rehearsed on a COPY of this repo's real event history (issue 978, S8, KC3).

The real ``shipwright_events.jsonl`` is copied into a temp git repo (the original is hashed before and after:
never touched). The copy is put into the shape a flipped repo would have -- the oldest events stay in the legacy
log, the rest is split into per-run drop files -- and then each rollback runs through the real CLI:

* emergency fold: every drop into the archive, ``events_layout`` back to ``legacy``; post-change readers see the same events;
* full fold: archive + drops back into the one legacy log; a PRE-change reader (one plain file) sees every event once.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "scripts"))
FOLD = REPO / "shared" / "scripts" / "tools" / "fold_events.py"
REAL_LOG = REPO / "shipwright_events.jsonl"
KEEP_LEGACY = 400  # the oldest events stay in the legacy log, as in a repo that flipped mid-history

pytestmark = pytest.mark.covers("FR-01.11")


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def _key(event: dict) -> str:
    from lib.events_read import sanitize_key
    for field in ("adr_id", "session"):
        val = event.get(field)
        if isinstance(val, str) and val:
            return sanitize_key(val)
    return "_legacy"


def _fold(root: Path, *args: str) -> dict:
    r = subprocess.run([sys.executable, str(FOLD), *args, "--project-root", str(root), "--stage"],
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    return json.loads(r.stdout)


def _body(event: dict) -> str:
    return json.dumps({k: v for k, v in event.items() if k != "run"}, sort_keys=True)


@pytest.fixture(autouse=True)
def _own_layout(monkeypatch):
    """The rehearsal drives the layout through the copy's sync config; the replay gate's forced-drops override must not leak in."""
    monkeypatch.delenv("SHIPWRIGHT_EVENTS_LAYOUT", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", raising=False)


@pytest.fixture(name="rehearsal")
def _rehearsal(tmp_path):
    from lib.events_read import read_events_assembled

    before = hashlib.sha256(REAL_LOG.read_bytes()).hexdigest()
    lines = [ln for ln in REAL_LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
    baseline = [_body(json.loads(ln)) for ln in lines]
    root = tmp_path / "copy"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        _git(root, "config", k, v)
    (root / ".gitignore").write_text("*.lock\n", encoding="utf-8")
    (root / "shipwright_sync_config.json").write_text('{"events_layout": "drops"}\n', encoding="utf-8")
    (root / "shipwright_events.jsonl").write_text("\n".join(lines[:KEEP_LEGACY]) + "\n", encoding="utf-8", newline="\n")
    groups: dict[str, list[str]] = {}
    for ln in lines[KEEP_LEGACY:]:
        event = json.loads(ln)
        key = _key(event)
        event["run"] = key
        groups.setdefault(key, []).append(json.dumps(event, separators=(",", ":"), ensure_ascii=False))
    folder = root / "shipwright_events.d"
    folder.mkdir()
    for n, (key, rows) in enumerate(sorted(groups.items())):   # a unique nonce: names that differ only in case must not collide
        (folder / f"{key}--aaaaaaaa--{n:08x}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "flipped copy of the real history")
    read = read_events_assembled(root)
    assert Counter(_body(r) for r in read.records) == Counter(baseline)   # the split loses and invents nothing
    yield root, baseline, len(lines)
    assert hashlib.sha256(REAL_LOG.read_bytes()).hexdigest() == before     # the real log was never touched


def _assert_same_history(root: Path, baseline: list[str]) -> None:
    from lib.events_log import finalized_run_ids, latest_event_dt
    from lib.events_read import read_events_assembled

    read = read_events_assembled(root)
    assert not read.skipped_files and not read.corrupt
    assert Counter(_body(r) for r in read.records) == Counter(baseline)
    assert finalized_run_ids(root) == {json.loads(b).get("adr_id") for b in baseline
                                       if json.loads(b).get("type") == "work_completed" and json.loads(b).get("adr_id")}
    assert latest_event_dt(root) is not None


def test_emergency_fold_on_a_copy_of_the_real_history(rehearsal):
    root, baseline, _n = rehearsal
    result = _fold(root, "emergency")
    assert result["status"].startswith("folded")
    _git(root, "commit", "-q", "-m", "emergency fold")
    assert json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8"))["events_layout"] == "legacy"
    assert not list((root / "shipwright_events.d").glob("*.jsonl"))
    assert list((root / "shipwright_events.archive").glob("fold-*.jsonl"))
    _assert_same_history(root, baseline)
    # the integrity checker accepts the fold commit
    check = subprocess.run([sys.executable, str(REPO / "shared" / "scripts" / "checks" / "check_events_integrity.py"),
                            "--project-root", str(root), "--base-ref", "HEAD~1", "--head-ref", "HEAD"],
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert check.returncode == 0, check.stdout[-800:]
    # and the repo keeps working on the legacy layout: a new event lands in the legacy log
    from tools import record_event
    record_event.append_event(root, {"v": 1, "id": "evt-after", "ts": "2026-11-07T10:00:00+00:00", "type": "task_created"})
    assert b"evt-after" in (root / "shipwright_events.jsonl").read_bytes()


def test_full_fold_gives_a_pre_change_reader_every_event_exactly_once(rehearsal):
    root, baseline, n = rehearsal
    _fold(root, "emergency")
    _git(root, "commit", "-q", "-m", "emergency fold")
    result = _fold(root, "full")
    assert result["status"] == "folded_into_legacy"
    _git(root, "commit", "-q", "-m", "full fold")
    plain = [json.loads(ln) for ln in (root / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(plain) == n and Counter(_body(r) for r in plain) == Counter(baseline)   # one plain file, no duplicates
    assert not list((root / "shipwright_events.d").glob("*.jsonl"))
    assert not list((root / "shipwright_events.archive").glob("*.jsonl"))
    _assert_same_history(root, baseline)
    again = _fold(root, "full")
    assert again["appended"] == 0                                                        # idempotent


def test_full_fold_straight_from_drops_without_the_emergency_step(rehearsal):
    root, baseline, n = rehearsal
    assert _fold(root, "full")["status"] == "folded_into_legacy"
    plain = (root / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([ln for ln in plain if ln.strip()]) == n
    _assert_same_history(root, baseline)
