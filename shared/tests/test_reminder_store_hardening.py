"""Reminder store: input hardening, fold damage tolerance and CLI contracts (E1a, part 2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from lib.reminder_store import (
    ReminderError, add_reminder, read_folded, set_status, store_path,
)
from lib.reminder_secrets import text_has_secret
from tools.reminder_cli import main

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)

# Secret-shaped fixtures are assembled from fragments so no scanner trips on
# this file (precedent: test_backfill_engine_units.py).
GH_TOKEN = "gh" + "p_" + "a1B2" * 6
URL_CREDS = "https://" + "ali" + "ce:" + "hunt" + "er2@example.com/x"
URL_PARAM = "https://example.com/hook?" + "tok" + "en=abc123"
URL_AMP = "https://example.com/hook?a=1&" + "ke" + "y=abc123"


def _add(root, **kw):
    base = dict(title="Start R1", due="2026-11-28", why="because", now=NOW)
    base.update(kw)
    return add_reminder(root, **base)


@pytest.mark.covers("FR-01.22/AC04")
def test_now_default_uses_real_clock(tmp_path):
    root = str(tmp_path)
    rid = _add(root, now=None)["id"]
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    assert set_status(root, rid, "snoozed", until=tomorrow)["snoozed_until"] == tomorrow


@pytest.mark.covers("FR-01.22/AC03")
def test_only_validated_fields_are_persisted(tmp_path):
    link = {"label": "L", "kind": "url", "ref": "https://example.com", "note": GH_TOKEN}
    rid = _add(str(tmp_path), links=[link])["id"]
    raw = store_path(tmp_path).read_text(encoding="utf-8")
    assert GH_TOKEN not in raw and rid in raw


@pytest.mark.parametrize("text", [
    "https://" + GH_TOKEN + "@example.com/r.git",
    "https://example.com/cb#acc" + "ess_token=abc",
])
@pytest.mark.covers("FR-01.22/AC03")
def test_more_url_credential_shapes_are_refused(tmp_path, text):
    with pytest.raises(ReminderError, match="secret"):
        _add(str(tmp_path), command=text)


@pytest.mark.parametrize("kw", [
    {"title": "a\nb"}, {"title": "x\x1b[2Jy"}, {"why": "bell\x07"},
    {"links": [{"label": "L\r", "kind": "file", "ref": "r"}]},
])
@pytest.mark.covers("FR-01.22/AC03")
def test_control_characters_are_refused(tmp_path, kw):
    with pytest.raises(ReminderError, match="control characters"):
        _add(str(tmp_path), **kw)
    assert _add(str(tmp_path), why="line one\nline two")["why"] == "line one\nline two"


@pytest.mark.covers("FR-01.22/AC04")
def test_done_is_idempotent_and_stray_snooze_cannot_undo_it(tmp_path):
    root = str(tmp_path)
    rid = _add(root)["id"]
    first = set_status(root, rid, "done", now=NOW)
    again = set_status(root, rid, "done", now=NOW + timedelta(days=1))
    assert again["done_at"] == first["done_at"]
    assert store_path(root).read_text(encoding="utf-8").count('"status":"done"') == 1
    with open(store_path(root), "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"event": "status", "id": rid, "status": "snoozed",
                             "snoozed_until": "2027-01-01"}) + "\n")
    assert read_folded(store_path(root)).reminders[rid]["status"] == "done"


@pytest.mark.covers("FR-01.22/AC05")
def test_id_collision_is_retried_under_the_lock(tmp_path, monkeypatch):
    import secrets as secrets_mod
    root = str(tmp_path)
    monkeypatch.setattr(secrets_mod, "token_hex", lambda n: "aaaaaaaa")
    first = _add(root)["id"]
    seq = iter(["aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr(secrets_mod, "token_hex", lambda n: next(seq))
    assert first == "rem-aaaaaaaa" and _add(root)["id"] == "rem-bbbbbbbb"


@pytest.mark.covers("FR-01.22/AC06")
def test_damaged_store_is_visible_to_list_and_not_found(tmp_path, capsys):
    root = str(tmp_path)
    store_path(root).parent.mkdir(parents=True)
    store_path(root).write_text("garbage not json\n", encoding="utf-8")
    assert main(["--project-root", root, "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["corruptLines"] == 1
    assert main(["done", "rem-00000000", "--project-root", root]) == 3
    assert "unreadable or rejected line" in capsys.readouterr().err


@pytest.mark.covers("FR-01.22/AC05")
def test_lock_timeout_gives_a_documented_exit_code(tmp_path, capsys, monkeypatch):
    import lib.reminder_store as rs
    from lib.file_lock import FileLock
    from lib.shipwright_paths import lock_beside
    monkeypatch.setattr(rs, "LOCK_TIMEOUT_SECONDS", 0.2)
    path = store_path(tmp_path)
    with FileLock(lock_beside(path)):
        import threading
        out = {}
        # a second process-like holder: the lock is thread-reentrant, so use a thread
        t = threading.Thread(target=lambda: out.setdefault("rc", main(
            ["--project-root", str(tmp_path), "add", "T", "--due", "2026-11-28", "--why", "w"])))
        t.start(); t.join()
    assert out["rc"] == 4
    assert "busy or unreadable" in capsys.readouterr().err


@pytest.mark.covers("FR-01.22/AC06")
def test_rejected_events_are_counted_and_secrets_never_echoed(tmp_path, capsys):
    root = str(tmp_path)
    store_path(root).parent.mkdir(parents=True)
    store_path(root).write_text(
        '{"event":"add","id":"rem-0000000a","title":"t","due":"bad"}' + chr(10), encoding="utf-8")
    assert main(["--project-root", root, "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["corruptLines"] == 1
    assert main(["--project-root", root, "add", "T", "--due", "2026-11-28", "--why", "w",
                 "--link", GH_TOKEN]) == 2
    cap = capsys.readouterr()
    assert GH_TOKEN not in cap.out + cap.err


@pytest.mark.covers("FR-01.22/AC01")
def test_crlf_in_multiline_fields_is_normalised(tmp_path):
    rec = _add(str(tmp_path), why="one\r\ntwo\rthree")
    assert rec["why"] == "one\ntwo\nthree"


@pytest.mark.covers("FR-01.22/AC03")
def test_harmless_userinfo_is_not_refused_but_credentials_are(tmp_path):
    assert not text_has_secret("ssh://git@github.com/org/repo.git")
    assert not text_has_secret("https://host?x=a@b")
    assert text_has_secret(URL_CREDS)


@pytest.mark.covers("FR-01.22/AC04")
def test_non_ascii_digits_are_not_a_date(tmp_path):
    with pytest.raises(ReminderError, match="YYYY-MM-DD"):
        _add(str(tmp_path), due="\uff12\uff10\uff12\uff16-11-28")


@pytest.mark.covers("FR-01.22/AC04")
def test_cli_snooze_verb_and_its_refusals(tmp_path, capsys):
    root = str(tmp_path)
    rid = _add(root)["id"]
    future = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
    assert main(["snooze", rid, "--until", future, "--project-root", root]) == 0
    assert "snoozed" in capsys.readouterr().out
    assert main(["snooze", rid, "--until", "2020-01-01", "--project-root", root]) == 2
    assert "after today" in capsys.readouterr().err
    assert main(["done", rid, "--project-root", root]) == 0
    capsys.readouterr()
    assert main(["snooze", rid, "--until", future, "--project-root", root]) == 2
    assert "cannot be snoozed" in capsys.readouterr().err


@pytest.mark.covers("FR-01.22/AC06")
def test_lone_surrogate_from_a_non_utf8_byte_is_rejected_not_crashing(tmp_path, capsys):
    root = str(tmp_path)
    path = store_path(root)
    path.parent.mkdir(parents=True)
    line = b'{"event":"add","id":"rem-0000000b","title":"caf\xe4","due":"2026-11-28"}\n'
    path.write_bytes(line)
    assert main(["--project-root", root, "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["corruptLines"] == 1
    with pytest.raises(ReminderError, match="control characters"):
        _add(root, title="caf\udce4")


@pytest.mark.covers("FR-01.22/AC02")
def test_write_refuses_to_fall_back_when_git_is_broken_inside_a_checkout(tmp_path, monkeypatch):
    import lib.reminder_store as rs
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(rs, "resolve_main_repo_root", lambda _p: None)
    with pytest.raises(ReminderError, match="main repository"):
        _add(str(tmp_path))
    assert not (tmp_path / ".shipwright" / "reminders.jsonl").exists()
    assert store_path(tmp_path) == tmp_path / ".shipwright" / "reminders.jsonl"  # reads still work
