"""Reminder store + CLI: round trip, refusals, secret check (E1a)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from lib.reminder_store import (
    ReminderError, ReminderNotFound, add_reminder, read_folded, set_status, store_path,
)
from lib.reminder_secrets import find_secret_field, text_has_secret
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


@pytest.mark.covers("FR-01.22/AC01")
def test_round_trip_add_list_show_done_snooze(tmp_path, capsys):
    root = str(tmp_path)
    rec = _add(root, decided="d", open_="o", command="c",
               links=[{"label": "L", "kind": "campaign", "ref": "x"}])
    assert rec["id"].startswith("rem-") and len(rec["id"]) == 12
    folded = read_folded(store_path(root)).reminders
    assert folded[rec["id"]]["links"] == [{"label": "L", "kind": "campaign", "ref": "x"}]
    snoozed = set_status(root, rec["id"], "snoozed", until="2026-12-01", now=NOW)
    assert snoozed["status"] == "snoozed" and snoozed["snoozed_until"] == "2026-12-01"
    done = set_status(root, rec["id"], "done", now=NOW)
    assert done["status"] == "done" and done["done_at"].startswith("2026-11-21")
    reopened = set_status(root, rec["id"], "open", now=NOW)
    assert reopened["status"] == "open" and reopened["snoozed_until"] is None
    # CLI surface over the same store
    assert main(["--project-root", root, "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contractVersion"] == 1 and len(payload["reminders"]) == 1
    assert main(["show", rec["id"], "--project-root", root, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == rec["id"]


@pytest.mark.covers("FR-01.22/AC01")
def test_cli_add_done_and_list_hides_done(tmp_path, capsys):
    root = str(tmp_path)
    assert main(["--project-root", root, "add", "T", "--due", "2026-11-28", "--why", "w",
                 "--link", "L=url=https://example.com/a?b=c"]) == 0
    rid = capsys.readouterr().out.split()[1]
    assert main(["done", rid, "--project-root", root]) == 0
    capsys.readouterr()
    assert main(["list", "--project-root", root]) == 0
    assert "no reminders" in capsys.readouterr().out
    assert main(["list", "--all", "--project-root", root]) == 0
    assert rid in capsys.readouterr().out


@pytest.mark.parametrize("kw", [
    {"due": "2026-13-01"}, {"due": "28.11.2026"}, {"due": "2026-2-3"}, {"due": "2026-02-30"},
    {"title": ""}, {"links": [{"label": "L", "kind": "bogus", "ref": "r"}]},
    {"links": [{"label": "", "kind": "file", "ref": "r"}]},
])
@pytest.mark.covers("FR-01.22/AC04")
def test_malformed_input_is_refused(tmp_path, kw):
    with pytest.raises(ReminderError):
        _add(str(tmp_path), **kw)
    assert not store_path(tmp_path).exists()


@pytest.mark.covers("FR-01.22/AC04")
def test_status_refusals(tmp_path):
    root = str(tmp_path)
    rid = _add(root)["id"]
    with pytest.raises(ReminderError, match="YYYY-MM-DD"):
        set_status(root, rid, "snoozed", until="soon", now=NOW)
    with pytest.raises(ReminderError, match="after today"):
        set_status(root, rid, "snoozed", until="2026-11-21", now=NOW)
    with pytest.raises(ReminderError, match="after today"):
        set_status(root, rid, "snoozed", until="2026-11-01", now=NOW)
    with pytest.raises(ReminderError, match="not one of"):
        set_status(root, rid, "archived", now=NOW)
    with pytest.raises(ReminderNotFound):
        set_status(root, "rem-deadbeef", "done", now=NOW)
    set_status(root, rid, "done", now=NOW)
    with pytest.raises(ReminderError, match="cannot be snoozed"):
        set_status(root, rid, "snoozed", until="2027-01-01", now=NOW)


@pytest.mark.covers("FR-01.22/AC04")
def test_cli_refusals_are_plain_messages(tmp_path, capsys):
    root = str(tmp_path)
    assert main(["--project-root", root, "add", "T", "--due", "nope", "--why", "w"]) == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err
    assert main(["done", "rem-00000000", "--project-root", root]) == 3
    assert "No reminder" in capsys.readouterr().err
    assert main(["--project-root", root, "add", "T", "--due", "2026-11-28", "--why", "w",
                 "--link", "broken"]) == 2


@pytest.mark.parametrize("field,value", [
    ("title", GH_TOKEN), ("why", "see " + GH_TOKEN), ("decided", URL_CREDS),
    ("open_", URL_PARAM), ("command", "curl " + URL_AMP),
])
@pytest.mark.covers("FR-01.22/AC03")
def test_secret_in_each_text_field_is_refused(tmp_path, field, value):
    with pytest.raises(ReminderError, match="secret"):
        _add(str(tmp_path), **{field: value})
    assert not store_path(tmp_path).exists()


@pytest.mark.parametrize("sub", ["label", "ref"])
@pytest.mark.covers("FR-01.22/AC03")
def test_secret_in_link_fields_is_refused(tmp_path, sub):
    link = {"label": "ok", "kind": "url", "ref": "https://example.com"}
    link[sub] = URL_CREDS
    with pytest.raises(ReminderError, match=rf"links\[0\]\.{sub}"):
        _add(str(tmp_path), links=[link])


@pytest.mark.covers("FR-01.22/AC03")
def test_secret_check_unit():
    assert text_has_secret(GH_TOKEN) and text_has_secret(URL_CREDS)
    assert not text_has_secret("rotate the key next week; see https://example.com/docs")
    assert not text_has_secret("mail me at bob@example.com")
    assert find_secret_field({"a": "fine", "b": ["x", GH_TOKEN]}) == "b[1]"


@pytest.mark.covers("FR-01.22/AC03")
def test_secret_in_status_event_text_is_refused(tmp_path):
    rid = _add(str(tmp_path))["id"]
    with pytest.raises(ReminderError, match="secret"):
        set_status(str(tmp_path), "rem-" + GH_TOKEN, "done", now=NOW)
    assert rid in read_folded(store_path(tmp_path)).reminders


@pytest.mark.covers("FR-01.22/AC06")
def test_fold_last_valid_wins_and_tolerates_damage(tmp_path):
    root = str(tmp_path)
    rid = _add(root)["id"]
    path = store_path(root)
    with open(path, "a", encoding="utf-8") as fp:  # no trailing newline, then junk
        fp.write('{"event":"status","id":"%s","status":"done","at":"2026-01-01T00:00:00Z"}' % rid)
    set_status(root, rid, "open", now=NOW)  # separator guard keeps both records
    with open(path, "a", encoding="utf-8") as fp:
        fp.write('{"event":"status","id":"%s","status":"bogus"}\nnot json\n' % rid)
    folded = read_folded(path)
    assert folded.reminders[rid]["status"] == "open"
    assert len(folded.corrupt) == 1 and len(folded.rejected) == 1
    # the separator guard is pinned on the raw file: one object per physical line
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and line != "not json":
            assert isinstance(json.loads(line), dict)


@pytest.mark.covers("FR-01.22/AC06")
def test_stray_object_is_counted_not_dropped(tmp_path):
    root = str(tmp_path)
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"event":"Add","id":"rem-0000000c"}' + chr(10), encoding="utf-8")
    folded = read_folded(path)
    assert not folded.reminders and len(folded.rejected) + len(folded.corrupt) == 1


@pytest.mark.covers("FR-01.22/AC02")
def test_main_root_fallback_outside_git(tmp_path):
    assert store_path(tmp_path) == tmp_path / ".shipwright" / "reminders.jsonl"




@pytest.mark.covers("FR-01.22/AC06")
def test_bad_stamp_is_rejected_so_json_output_survives(tmp_path):
    root = str(tmp_path)
    rid = _add(root)["id"]
    path = store_path(root)
    bad = r'{"event":"status","id":"%s","status":"done","at":"\ud800"}' % rid
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(chr(10) + bad + chr(10))
    folded = read_folded(path)
    assert folded.reminders[rid]["status"] == "open"
    assert len(folded.rejected) + len(folded.corrupt) == 1
    assert main(["--project-root", root, "list", "--json"]) == 0
