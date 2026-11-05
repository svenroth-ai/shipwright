"""Dormant drops layout (issue 978, S0): switch precedence, write path, assembled read."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from lib import events_layout as el
from lib.config import read_events
from lib.events_layout import (
    DROPS_DIR,
    events_layout,
    read_events_assembled,
    resolve_events_write_path,
    sanitize_key,
)
sys.path.append(str(Path(__file__).resolve().parent))

from _events_split import split_log  # noqa: E402

CRLF, LF = bytes([13, 10]), bytes([10])
FIX = Path(__file__).parent / "fixtures" / "events_layout"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (el.ENV_LAYOUT, el.ENV_LAYOUT_TEST, "SHIPWRIGHT_RUN_ID"):
        monkeypatch.delenv(name, raising=False)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f").write_text("x")
    _git(tmp_path, "add", "f")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_default_is_legacy(tmp_path):
    assert events_layout(tmp_path) == "legacy"
    assert resolve_events_write_path(tmp_path) == tmp_path / "shipwright_events.jsonl"
    assert not (tmp_path / DROPS_DIR).exists()


def test_plain_env_var_without_test_flag_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    assert events_layout(tmp_path) == "legacy"
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "0")
    assert events_layout(tmp_path) == "legacy"
    assert resolve_events_write_path(tmp_path) == tmp_path / "shipwright_events.jsonl"
    assert not (tmp_path / DROPS_DIR).exists()


def test_env_var_with_test_flag_switches(tmp_path, monkeypatch):
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    assert events_layout(tmp_path) == "drops"
    monkeypatch.setenv(el.ENV_LAYOUT, "bogus")
    assert events_layout(tmp_path) == "legacy"


def test_config_key_read_at_runtime(tmp_path):
    cfg = tmp_path / "shipwright_sync_config.json"
    cfg.write_text(json.dumps({"events_layout": "drops"}))
    assert events_layout(tmp_path) == "drops"
    cfg.write_text(json.dumps({"events_layout": "legacy"}))
    assert events_layout(tmp_path) == "legacy"
    cfg.write_text(json.dumps({"events_layout": "weird"}))
    assert events_layout(tmp_path) == "legacy"
    cfg.write_text("{not json")
    assert events_layout(tmp_path) == "legacy"


def test_test_override_beats_config(tmp_path, monkeypatch):
    (tmp_path / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}))
    monkeypatch.setenv(el.ENV_LAYOUT, "legacy")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    assert events_layout(tmp_path) == "legacy"


def test_sanitize_key_is_path_safe():
    assert sanitize_key("a/b" + chr(92) + "c:d") == "a-b-c-d"
    assert sanitize_key("..") == "_run"
    assert len(sanitize_key("x" * 500)) == 80
    assert "/" not in sanitize_key("../../etc")


def test_drops_write_path_rotates_on_commit(tmp_path, monkeypatch):
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "run-1")
    root = _repo(tmp_path)
    first = resolve_events_write_path(root)
    assert first.parent == root / DROPS_DIR and first.name.startswith("run-1--")
    assert not first.exists()  # no empty file before the first complete write
    first.write_text("{}\n")
    assert resolve_events_write_path(root) == first  # open file is reused
    _git(root, "add", str(first))
    _git(root, "commit", "-q", "-m", "close")
    second = resolve_events_write_path(root)
    assert second != first and second.name.startswith("run-1--")  # committed => rotated


def test_assembled_read_equals_legacy_read_without_drops(tmp_path):
    shutil.copy(FIX / "unsplit.jsonl", tmp_path / "shipwright_events.jsonl")
    assert read_events_assembled(tmp_path).records == read_events(tmp_path)
    assert len(read_events(tmp_path)) == 26


def test_split_log_reads_back_in_unsplit_order(tmp_path):
    unsplit_root, split_root = tmp_path / "u", tmp_path / "s"
    unsplit_root.mkdir()
    split_root.mkdir()
    shutil.copy(FIX / "unsplit.jsonl", unsplit_root / "shipwright_events.jsonl")
    split_log(FIX / "unsplit.jsonl", split_root)
    assert read_events_assembled(split_root).records == read_events_assembled(unsplit_root).records


def test_committed_split_fixture_matches_the_splitter(tmp_path):
    split_log(FIX / "unsplit.jsonl", tmp_path)
    expected = {p.name: p.read_bytes() for p in (tmp_path / DROPS_DIR).iterdir()}
    actual = {p.name: p.read_bytes() for p in (FIX / "split" / DROPS_DIR).iterdir()}
    assert actual == expected


# ---- adopted plan-review findings (S0) -----------------------------------------

@pytest.mark.parametrize("config,env,flag,expected", [
    (None, None, None, "legacy"),
    ("drops", None, None, "drops"),            # config alone selects (BRIEF: config key, then default)
    ("drops", "legacy", None, "drops"),        # env without the test flag is ignored
    ("legacy", "drops", None, "legacy"),       # ... in both directions
    ("legacy", "drops", "1", "drops"),         # test override wins over config
    ("drops", "legacy", "1", "legacy"),
    ("drops", "drops", "0", "drops"),          # flag must be exactly "1"
    ("legacy", "drops", "true", "legacy"),
    (None, "drops", "1", "drops"),
    (None, "garbage", "1", "legacy"),
    ("garbage", None, None, "legacy"),
])
def test_layout_precedence_matrix(tmp_path, monkeypatch, config, env, flag, expected):
    if config is not None:
        (tmp_path / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": config}))
    if env is not None:
        monkeypatch.setenv(el.ENV_LAYOUT, env)
    if flag is not None:
        monkeypatch.setenv(el.ENV_LAYOUT_TEST, flag)
    assert events_layout(tmp_path) == expected
    # Writers and readers resolve through the same function: the write target agrees.
    target = resolve_events_write_path(tmp_path)
    assert (target.parent.name == DROPS_DIR) == (expected == "drops")


def _tools_record_event():
    import importlib
    return importlib.import_module("tools.record_event")


def _event(i, run="r"):
    return {"id": f"{i:08x}", "ts": f"2026-11-01T10:00:{i % 60:02d}Z", "type": "task_created",
            "description": f"{run} event {i}", "source": "t"}


def test_legacy_mode_bytes_are_exactly_todays(tmp_path):
    """Legacy write path: the same file, the same bytes, the same lock, no folder."""
    re_ = _tools_record_event()
    events = [_event(i) for i in range(3)]
    for e in events:
        re_.append_event(tmp_path, e)
    expected = "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events)
    # text-mode append, as before the change (CRLF on Windows is pre-existing)
    assert (tmp_path / "shipwright_events.jsonl").read_bytes().replace(CRLF, LF) == expected.encode("utf-8")
    assert not (tmp_path / DROPS_DIR).exists()
    assert el.events_lock_path(tmp_path) == tmp_path / "shipwright_events.jsonl.lock"
    assert read_events_assembled(tmp_path).records == events


def test_drops_writes_survive_rotation_and_concurrency_exactly_once(tmp_path, monkeypatch):
    """Concurrent same-key appenders plus a commit (rotation) in between: every
    recorded event is readable exactly once, no empty/partial drop remains."""
    import threading
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "run-conc")
    re_ = _tools_record_event()
    root = _repo(tmp_path)
    errors = []

    def burst(base):
        try:
            for i in range(base, base + 6):
                re_.append_event(root, _event(i, "run-conc"))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=burst, args=(b,)) for b in (0, 10, 20, 30)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    first_files = sorted((root / DROPS_DIR).glob("*.jsonl"))
    assert len(first_files) == 1  # the open file was shared under the lock
    _git(root, "add", DROPS_DIR)
    _git(root, "commit", "-q", "-m", "close")  # rotation boundary
    burst(100)
    files = sorted((root / DROPS_DIR).glob("*.jsonl"))
    assert len(files) == 2 and all(f.stat().st_size > 0 for f in files)
    ids = [e["id"] for e in read_events_assembled(root).records]
    assert len(ids) == 30 and len(set(ids)) == 30
    assert not list((root / DROPS_DIR).glob("*.lock")) and not list((root / DROPS_DIR).glob("*.tmp"))


def test_rotation_probe_failure_never_reuses_an_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "run-p")
    root = _repo(tmp_path)
    first = resolve_events_write_path(root)
    first.write_text("{}\n")
    assert resolve_events_write_path(root) == first
    monkeypatch.setattr(el, "_names_in_head", lambda _root: None)  # probe failed
    second = resolve_events_write_path(root)
    assert second != first and second.name.startswith("run-p--")


def test_unborn_head_means_nothing_committed(tmp_path, monkeypatch):
    monkeypatch.setenv(el.ENV_LAYOUT, "drops")
    monkeypatch.setenv(el.ENV_LAYOUT_TEST, "1")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "run-u")
    _git(tmp_path, "init", "-q", "-b", "main")  # no commit yet
    first = resolve_events_write_path(tmp_path)
    first.write_text("{}\n")
    assert resolve_events_write_path(tmp_path) == first


def test_the_test_flag_is_never_set_by_plugins_or_templates():
    """BRIEF section 2: the override flag is set only by the harness / this repo's CI."""
    repo = Path(__file__).resolve().parents[2]
    import os
    offenders = []
    for base in (repo / "plugins", repo / "shared" / "templates"):
        for cur, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {"tests", ".venv", "node_modules", "__pycache__"}]
            for name in files:
                path = Path(cur) / name
                if path.suffix not in {".py", ".md", ".json", ".yml", ".yaml", ".sh", ".toml", ".txt"}:
                    continue
                if el.ENV_LAYOUT_TEST in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(path.relative_to(repo).as_posix())
    assert not offenders, offenders


def test_config_with_bom_crlf_and_non_ascii_is_read(tmp_path):
    """Boundary probe (human-edited JSON): BOM, CRLF, non-ASCII neighbours, empty value."""
    cfg = tmp_path / "shipwright_sync_config.json"
    body = '{\r\n  "note": "k\u00e4se",\r\n  "events_layout": "drops"\r\n}\r\n'
    cfg.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert events_layout(tmp_path) == "drops"
    cfg.write_text('{"events_layout": ""}', encoding="utf-8")
    assert events_layout(tmp_path) == "legacy"


def test_legacy_target_is_the_events_log_resolver(tmp_path):
    from lib.events_log import resolve_events_path
    assert resolve_events_write_path(tmp_path) == resolve_events_path(tmp_path)
    assert el.events_lock_path(tmp_path).name == resolve_events_path(tmp_path).name + ".lock"
