"""`reminder_cli.py due`: reminders and expired triage parks in one answer (E1b)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from lib.reminder_due import ITEM_FIELDS, LINK_FIELDS, _clean
from lib.reminder_store import add_reminder, set_status
from tools.reminder_cli import main
from triage import append_triage_item, mark_status

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
DAY = "2099-01-10"


def _park(project, title, revisit, *, reason="waiting", detail="ctx"):
    tid = append_triage_item(project, source="t", severity="high", kind="bug",
                             title=title, detail=detail)
    mark_status(project, tid, new_status="snoozed", by="manualDefer", reason=reason,
                revisit_at=revisit)
    return tid


def _rem(project, title, due, **kw):
    return add_reminder(project, title=title, due=due, why="because", now=NOW, **kw)


def _due(project, capsys, on=DAY):
    assert main(["--project-root", str(project), "due", "--on", on, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


@pytest.mark.covers("FR-01.22/AC07")
def test_expired_park_and_open_reminder_share_one_list_and_shape(tmp_path, capsys):
    tid = _park(tmp_path, "parked thing", DAY, reason="later")
    rem = _rem(tmp_path, "do it", DAY, command="run x",
               links=[{"label": "c", "kind": "campaign", "ref": "slug"}])
    out = _due(tmp_path, capsys)
    assert out["contractVersion"] == 1 and out["on"] == DAY
    assert {i["id"] for i in out["items"]} == {tid, rem["id"]}
    assert all(tuple(i) == ITEM_FIELDS for i in out["items"])
    assert all(tuple(k) == LINK_FIELDS for i in out["items"] for k in i["links"])
    park = next(i for i in out["items"] if i["kind"] == "triage")
    assert (park["due"], park["why"], park["decided"], park["open"], park["command"],
            park["severity"]) == (DAY, "later", None, "ctx", None, "high")
    assert park["links"] == [{"label": f"Triage {tid}", "kind": "triage", "ref": tid}]
    r = next(i for i in out["items"] if i["kind"] == "reminder")
    assert r["severity"] is None and r["command"] == "run x"


@pytest.mark.covers("FR-01.22/AC07")
def test_omits_unexpired_park_done_and_unfinished_snooze(tmp_path, capsys):
    _park(tmp_path, "not yet", "2099-03-01")
    done = _rem(tmp_path, "finished", DAY)
    set_status(tmp_path, done["id"], "done", now=NOW)
    snz = _rem(tmp_path, "later", DAY)
    set_status(tmp_path, snz["id"], "snoozed", until="2099-02-01", now=NOW)
    assert _due(tmp_path, capsys)["items"] == []


@pytest.mark.covers("FR-01.22/AC07")
def test_ended_snooze_is_due_with_snoozed_until_as_due(tmp_path, capsys):
    snz = _rem(tmp_path, "later", "2099-01-01")
    set_status(tmp_path, snz["id"], "snoozed", until=DAY, now=NOW)
    [item] = _due(tmp_path, capsys)["items"]
    assert (item["id"], item["due"]) == (snz["id"], DAY)
    assert _due(tmp_path, capsys, on="2099-01-09")["items"] == []
    [later] = _due(tmp_path, capsys, on="2099-06-01")["items"]
    assert later["due"] == DAY  # stays snoozed_until on every later day


@pytest.mark.covers("FR-01.22/AC07")
def test_same_day_reminder_and_park_appear_together_and_past_due_stays(tmp_path, capsys):
    _park(tmp_path, "p", DAY)
    _rem(tmp_path, "r", DAY)
    _rem(tmp_path, "overdue", "2098-12-01")
    out = _due(tmp_path, capsys)
    assert [i["due"] for i in out["items"]] == ["2098-12-01", DAY, DAY]


@pytest.mark.covers("FR-01.22/AC07")
def test_park_without_a_date_never_appears(tmp_path, capsys):
    tid = append_triage_item(tmp_path, source="t", severity="low", kind="bug",
                             title="t", detail="d")
    mark_status(tmp_path, tid, new_status="snoozed", by="x", reason="r")
    assert _due(tmp_path, capsys)["items"] == []


@pytest.mark.covers("FR-01.22/AC08")
def test_triage_text_is_redacted_at_output_time(tmp_path, capsys):
    secret = "gh" + "p_" + "a1B2" * 6
    url = "https://" + "ali" + "ce:" + "hunt" + "er2@example.com/x"
    _park(tmp_path, f"leak {secret}", DAY, reason=f"see {url}", detail=f"tok {secret}")
    [item] = _due(tmp_path, capsys)["items"]
    blob = json.dumps(item)
    assert secret not in blob and "hunt" + "er2" not in blob
    assert "[REDACTED]" in blob


@pytest.mark.covers("FR-01.22/AC08")
def test_odd_text_cannot_break_json_output():
    # A hand-edited store line can carry a lone surrogate (JSON "\ud800"), which
    # cannot be encoded as UTF-8; non-text values must not leak either.
    assert _clean("bad " + chr(0xD800) + " x") == "bad � x"
    assert _clean(5) is None and _clean(None) is None
    json.dumps(_clean("bad " + chr(0xD800)), ensure_ascii=False).encode("utf-8")


@pytest.mark.covers("FR-01.22/AC07")
def test_default_day_is_today_utc_and_text_output_names_the_root(tmp_path, capsys):
    assert main(["--project-root", str(tmp_path), "due"]) == 0
    text = capsys.readouterr().out
    assert "nothing due on" in text and f"source_root: {tmp_path.resolve()}" in text


@pytest.mark.covers("FR-01.22/AC07")
def test_bad_on_date_is_refused(tmp_path, capsys):
    assert main(["--project-root", str(tmp_path), "due", "--on", "2099-13-40"]) == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.covers("FR-01.22/AC07")
def test_due_is_read_only(tmp_path, capsys):
    _park(tmp_path, "p", DAY)
    _rem(tmp_path, "r", DAY)
    files = {p: p.read_bytes() for p in (tmp_path / ".shipwright").glob("*.jsonl")}
    _due(tmp_path, capsys)
    assert files == {p: p.read_bytes() for p in (tmp_path / ".shipwright").glob("*.jsonl")}


@pytest.mark.covers("FR-01.22/AC07")
def test_damaged_store_is_counted_not_read_as_absence(tmp_path, capsys):
    _rem(tmp_path, "r", DAY)
    with open(tmp_path / ".shipwright" / "reminders.jsonl", "a", encoding="utf-8") as f:
        f.write("{not json\n")
    out = _due(tmp_path, capsys)
    assert out["reminderCorruptLines"] == 1 and len(out["items"]) == 1


@pytest.mark.covers("FR-01.22/AC08")
def test_control_characters_are_flattened_and_blocks_redacted():
    assert _clean("a\r\nBcc: x\x1b[31m") == "a  Bcc: x [31m"
    assert _clean("l1\r\nl2\x07", True) == "l1\nl2 "
    pem = "-----BEGIN RSA " + "PRIVATE KEY-----\nAAAA\n-----END RSA " + "PRIVATE KEY-----"
    out = _clean(f"x {pem} y", True)
    assert "AAAA" not in out and out.endswith(" y")
    assert "hunter" not in _clean("pass" + "word: hunter2 ok")


@pytest.mark.covers("FR-01.22/AC07")
def test_unreadable_triage_still_returns_reminders_and_says_so(tmp_path, capsys, monkeypatch):
    import triage

    def boom(*a, **k):
        raise RuntimeError("triage broke")

    monkeypatch.setattr(triage, "read_all_items", boom)
    _rem(tmp_path, "r", DAY)
    out = _due(tmp_path, capsys)
    assert len(out["items"]) == 1 and "RuntimeError" in out["triageError"]


@pytest.mark.covers("FR-01.22/AC07")
def test_nothing_in_the_due_path_opens_triage_directly():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "scripts"
    for rel in ("lib/reminder_due.py", "tools/reminder_cli.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "triage.jsonl" not in text and "subprocess" not in text, rel
    assert "read_all_items" in (root / "lib/reminder_due.py").read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.22/AC07")
def test_from_a_real_worktree_reminders_come_from_the_main_store(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    cli = Path(__file__).resolve().parent.parent / "scripts" / "tools" / "reminder_cli.py"
    main_dir, wt = tmp_path / "main", tmp_path / "wt"
    main_dir.mkdir()

    def git(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.com", "-c", "commit.gpgsign=false", *a],
                       cwd=main_dir, check=True, capture_output=True)

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "i")
    git("worktree", "add", "-q", str(wt), "-b", "side")
    r = subprocess.run([sys.executable, str(cli), "--project-root", str(wt), "add", "T",
                        "--due", DAY, "--why", "w"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r = subprocess.run([sys.executable, str(cli), "--project-root", str(wt), "due", "--on",
                        DAY, "--json"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert [i["title"] for i in out["items"]] == ["T"]
    store = main_dir / ".shipwright" / "reminders.jsonl"
    assert Path(out["reminderStore"]).resolve() == store.resolve()
    assert Path(out["sourceRoot"]).resolve() == wt.resolve()


@pytest.mark.covers("FR-01.22/AC08")
def test_url_query_credentials_are_masked_and_name_kept():
    url = "https://example.com/hook?a=1&" + "ke" + "y=abc123&b=2"
    out = _clean(url)
    assert "abc123" not in out and "&key=[REDACTED]" in out and "a=1" in out


@pytest.mark.covers("FR-01.22/AC08")
def test_prefixed_secret_names_and_separators_are_handled():
    assert "abc123" not in _clean("https://x/cb?client_" + "sec" + "ret=abc123")
    assert "hunter2" not in _clean("db_" + "pass" + "word: hunter2")
    assert _clean("a\u2028b\u202ec") == "a b c"


@pytest.mark.covers("FR-01.22/AC07")
def test_today_is_the_utc_day_for_both_sources(tmp_path, capsys, monkeypatch):
    import lib.reminder_due as rd
    from datetime import timedelta
    _park(tmp_path, "p", DAY)
    _rem(tmp_path, "r", DAY)
    _rem(tmp_path, "later", "2099-01-11")
    # 23:30 at UTC-5 on the 9th is already the 10th in UTC.
    monkeypatch.setattr(rd, "now_utc", lambda: datetime(2099, 1, 9, 23, 30, tzinfo=timezone(timedelta(hours=-5))))
    assert main(["--project-root", str(tmp_path), "due", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["on"] == DAY and sorted(i["kind"] for i in out["items"]) == ["reminder", "triage"]
    monkeypatch.setattr(rd, "now_utc", lambda: datetime(2099, 1, 9, 23, 59, 59, tzinfo=timezone.utc))
    assert main(["--project-root", str(tmp_path), "due", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["items"] == []


@pytest.mark.covers("FR-01.22/AC08")
def test_json_quoted_secret_keys_are_masked():
    out = _clean('{"pass' + 'word": "hunter2", "other": 1}')
    assert "hunter2" not in out and "other" in out


@pytest.mark.covers("FR-01.22/AC07")
def test_from_a_subdirectory_triage_is_still_read(tmp_path, capsys):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _park(tmp_path, "p", DAY)
    sub = tmp_path / "deep" / "dir"
    sub.mkdir(parents=True)
    out = _due(sub, capsys)
    assert [i["kind"] for i in out["items"]] == ["triage"] and out["triageError"] is None


@pytest.mark.covers("FR-01.22/AC07")
def test_no_shipwright_directory_is_reported_not_read_as_empty(tmp_path, capsys):
    out = _due(tmp_path, capsys)
    assert out["items"] == [] and "FileNotFoundError" in out["triageError"]


@pytest.mark.covers("FR-01.22/AC08")
@pytest.mark.parametrize("text, leaked", [
    ("HF_" + "TOK" + "EN=hf_abcdefghijklmnop", "hf_abcdefghijklmnop"),
    ("AWS_" + "SEC" + "RET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG", "wJalrXUtnFEMI"),
    ("STRIPE_" + "SEC" + "RET_KEY=sk_live_abcdef123456", "sk_live_abcdef123456"),
    ("DB_" + "PA" + "SS=hunter2", "hunter2"),
    ("pass" + "word: \"correct horse battery\"", "horse"),
    ("pass" + "word='abc,def'", "def"),
])
def test_environment_style_secret_names_are_masked(text, leaked):
    assert leaked not in _clean(text)


@pytest.mark.covers("FR-01.22/AC08")
def test_pgp_key_block_and_huge_fields_are_handled():
    pgp = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nAAAA1234\n-----END PGP PRIVATE KEY BLOCK-----"
    assert "AAAA1234" not in _clean("see " + pgp, multiline=True)
    out = _clean("a" * 200_000)
    assert out is not None and len(out) <= 8000


@pytest.mark.covers("FR-01.22/AC07")
def test_empty_on_is_refused_not_read_as_today(tmp_path, capsys):
    assert main(["--project-root", str(tmp_path), "due", "--on", "", "--json"]) == 2


@pytest.mark.covers("FR-01.22/AC07")
def test_unreadable_store_exits_4(tmp_path):
    from lib.reminder_store import store_path
    path = store_path(tmp_path, for_write=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # the store path is a directory: reading it is an OS error, not a crash
    assert main(["--project-root", str(tmp_path), "due", "--json"]) == 4
