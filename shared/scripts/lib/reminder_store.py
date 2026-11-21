"""Reminder store: an append-only JSONL log, folded on read.

One file, ``.shipwright/reminders.jsonl``, git-ignored and local, resolved at the
MAIN repo root so a reminder written from any worktree lands in one place
(precedent: :mod:`lib.quarantine_log`). The ONLY writer is ``tools/reminder_cli.py``;
the WebUI must call that CLI, never append here itself (its own lockfile does not
coordinate with :class:`lib.file_lock.FileLock`).

Two event types: ``add`` (carries every field) and ``status`` (``done``,
``snoozed`` + ``snoozed_until``, ``open``). Fold rule: events are applied in file
order and the last valid one per id wins; an ``add`` for an id already known is
ignored (uniqueness is enforced under the lock at write time). Reading reuses
:func:`lib.jsonl_records.read_jsonl_records`; a corrupt line never reads as absence
(it is returned on ``Folded.corrupt``).
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from lib.file_lock import FileLock
from lib.jsonl_records import ends_without_newline, read_jsonl_records
from lib.reminder_secrets import REFUSAL, find_secret_field
from lib.repo_root import resolve_main_repo_root
from lib.shipwright_paths import lock_beside
from lib.triage_defer import now_utc, utc_date

REMINDERS_FILE = ".shipwright/reminders.jsonl"
STATUSES = ("open", "done", "snoozed")
LINK_KINDS = ("campaign", "triage", "file", "url")
MAX_TEXT = 2000
MAX_TITLE = 200
MAX_LINKS = 20

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ID_RE = re.compile(r"rem-[0-9a-f]{8}")
_TEXT_FIELDS = ("title", "why", "decided", "open", "command", "links")
LOCK_TIMEOUT_SECONDS = 15.0  # one read + one append: a stuck holder must not hang a caller
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]")
_MULTILINE_OK = ("why", "decided", "open")


class ReminderError(ValueError):
    """A refusal with a plain-language message safe to show the operator."""


class ReminderNotFound(ReminderError):
    """No reminder has the given id."""


@dataclass
class Folded:
    reminders: dict[str, dict] = field(default_factory=dict)
    corrupt: list = field(default_factory=list)
    #: events that parsed as JSON but were invalid or refused; never silently dropped
    rejected: list = field(default_factory=list)

    @property
    def damaged(self) -> int:
        return len(self.corrupt) + len(self.rejected)


def _inside_git_checkout(project_root: Path | str) -> bool:
    here = Path(project_root).resolve()
    return any((p / ".git").exists() for p in (here, *here.parents))


def store_path(project_root: Path | str, *, for_write: bool = False) -> Path:
    """The store at the MAIN root (``project_root`` itself outside git). A write refuses
    to fall back inside a checkout whose main root git could not resolve."""
    root = resolve_main_repo_root(project_root)
    if root is None:
        if for_write and _inside_git_checkout(project_root):
            raise ReminderError(
                "Could not find the main repository (git did not answer); the reminder "
                "was not saved. Check that git works and try again."
            )
        root = Path(project_root)
    return Path(root) / REMINDERS_FILE


def not_found_message(rid: str, folded: Folded) -> str:
    msg = f"No reminder with id {rid!r}."
    if folded.damaged:
        msg += (f" The store has {folded.damaged} unreadable or rejected line(s); "
                "the reminder may be in one of them.")
    return msg


def parse_day(raw: object, what: str = "date") -> date:
    """Strict ``YYYY-MM-DD``; anything else is refused with a plain message."""
    if not isinstance(raw, str) or not _DATE_RE.fullmatch(raw):
        raise ReminderError(f"{what} must be a day written YYYY-MM-DD.")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ReminderError(f"{what} is not a real calendar day.") from None


def _text(value: object, name: str, *, required: bool, limit: int = MAX_TEXT) -> str | None:
    if value is None or value == "":
        if required:
            raise ReminderError(f"{name} is required.")
        return None
    if not isinstance(value, str):
        raise ReminderError(f"{name} must be text.")
    if len(value) > limit:
        raise ReminderError(f"{name} is too long ({len(value)} characters, at most {limit}).")
    if name in _MULTILINE_OK:  # CRLF from Windows editors / textareas is a line break
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    bad = _CONTROL_RE.search(value) or (
        re.search(r"[\r\n]", value) if name not in _MULTILINE_OK else None
    )
    if bad:
        raise ReminderError(f"{name} must not contain control characters or line breaks.")
    return value


def normalize_links(links: object) -> list[dict]:
    if links in (None, ""):
        return []
    if not isinstance(links, list) or len(links) > MAX_LINKS:
        raise ReminderError(f"links must be a list of at most {MAX_LINKS} entries.")
    out = []
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            raise ReminderError(f"links[{i}] must be an object with label, kind and ref.")
        kind = link.get("kind")
        if kind not in LINK_KINDS:
            raise ReminderError(
                f"links[{i}].kind is not one of {', '.join(LINK_KINDS)}."
            )
        out.append({
            "label": _text(link.get("label"), f"links[{i}].label", required=True, limit=MAX_TITLE),
            "kind": kind,
            "ref": _text(link.get("ref"), f"links[{i}].ref", required=True),
        })
    return out


def _refuse_secret(fields: dict) -> None:
    hit = find_secret_field(fields)
    if hit:
        raise ReminderError(f"The text in `{hit}` {REFUSAL}")


def _stamp(now: datetime | None) -> str:
    return (now or now_utc()).isoformat().replace("+00:00", "Z")


def _is_event(obj: dict) -> bool:
    at = obj.get("at")  # an ISO stamp only: a stray byte here would break --json output
    return (obj.get("event") in ("add", "status") and isinstance(obj.get("id"), str)
            and isinstance(at, str) and re.fullmatch(r"[0-9T:.+Z-]{1,40}", at) is not None)


def _validated_add(ev: dict) -> dict:
    if not _ID_RE.fullmatch(ev["id"]):
        raise ReminderError("bad id")
    return {
        "id": ev["id"],
        "title": _text(ev.get("title"), "title", required=True, limit=MAX_TITLE),
        "due": parse_day(ev.get("due"), "due").isoformat(),
        "why": _text(ev.get("why"), "why", required=False),
        "decided": _text(ev.get("decided"), "decided", required=False),
        "open": _text(ev.get("open"), "open", required=False),
        "command": _text(ev.get("command"), "command", required=False),
        "links": normalize_links(ev.get("links")),
        "status": "open",
        "snoozed_until": None,
        "created_at": ev.get("at"),
        "done_at": None,
    }


def _apply(rem: dict | None, ev: dict) -> dict:
    """Apply one event to ``rem``; raise ``ReminderError`` when the event is invalid."""
    if ev["event"] == "add":
        if rem is not None:
            raise ReminderError("duplicate add")
        return _validated_add(ev)
    if rem is None:
        raise ReminderError("status event for an unknown reminder")
    status = ev.get("status")
    if status not in STATUSES:
        raise ReminderError("unknown status")
    new = dict(rem)
    if status == "snoozed":
        if rem["status"] == "done":
            raise ReminderError("a done reminder cannot be snoozed")
        new["snoozed_until"] = parse_day(ev.get("snoozed_until"), "snoozed_until").isoformat()
        new["status"] = "snoozed"
    elif status == "done":
        new.update(status="done", done_at=rem["done_at"] or ev.get("at"))
    else:
        new.update(status="open", snoozed_until=None, done_at=None)
    return new


def read_folded(path: Path | str) -> Folded:
    """Fold the log: last valid event per id wins, in file order."""
    rr = read_jsonl_records(path, is_record=_is_event)
    out = Folded(corrupt=rr.corrupt)
    for ev in rr.records:
        if not _is_event(ev):
            out.rejected.append(ev)  # a stray object is counted, never dropped
            continue
        try:
            out.reminders[ev["id"]] = _apply(out.reminders.get(ev["id"]), ev)
        except ReminderError:
            out.rejected.append(ev)
    return out


def _append(path: Path, event: dict) -> None:
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never assume the previous writer left a trailing newline (jsonl_records).
    needs_separator = ends_without_newline(path)
    with open(path, "a", encoding="utf-8", newline="") as fp:
        if needs_separator:
            fp.write("\n")
        fp.write(line)
        fp.flush()
        os.fsync(fp.fileno())


def add_reminder(
    project_root: Path | str,
    *,
    title: str,
    due: str,
    why: str | None = None,
    decided: str | None = None,
    open_: str | None = None,
    command: str | None = None,
    links: list | None = None,
    now: datetime | None = None,
) -> dict:
    """Validate, then append an ``add`` event under the lock; return the record."""
    ev = {"event": "add", "id": "rem-00000000", "at": _stamp(now),
          "title": title, "due": due, "why": why, "decided": decided,
          "open": open_, "command": command, "links": links or []}
    checked = _validated_add(ev)  # id is a placeholder; every other field is checked
    _refuse_secret({k: checked[k] for k in _TEXT_FIELDS})
    # Persist ONLY the validated record, never caller input that was not checked.
    ev = {"event": "add", "id": ev["id"], "at": ev["at"],
          **{k: checked[k] for k in _TEXT_FIELDS + ("due",) if checked[k] not in (None, "", [])}}
    path = store_path(project_root, for_write=True)
    with FileLock(lock_beside(path), timeout_seconds=LOCK_TIMEOUT_SECONDS):
        known = read_folded(path).reminders
        rid = "rem-" + secrets.token_hex(4)
        while rid in known:
            rid = "rem-" + secrets.token_hex(4)
        ev["id"] = rid
        _append(path, ev)
    checked["id"] = rid
    return checked


def set_status(
    project_root: Path | str,
    rid: str,
    status: str,
    *,
    until: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Append a ``status`` event (``done`` / ``snoozed`` / ``open``) under the lock."""
    if status not in STATUSES:
        raise ReminderError(f"status is not one of {', '.join(STATUSES)}.")
    ev = {"event": "status", "id": rid, "status": status, "at": _stamp(now)}
    if status == "snoozed":
        day = parse_day(until, "--until")
        if day <= utc_date(now or now_utc()):
            raise ReminderError(f"--until {day.isoformat()} must be after today (UTC).")
        ev["snoozed_until"] = day.isoformat()
    elif until is not None:
        raise ReminderError("--until only applies to a snooze.")
    _refuse_secret({k: v for k, v in ev.items() if isinstance(v, str)})
    path = store_path(project_root, for_write=True)
    with FileLock(lock_beside(path), timeout_seconds=LOCK_TIMEOUT_SECONDS):
        folded = read_folded(path)
        current = folded.reminders.get(rid)
        if current is None:
            raise ReminderNotFound(not_found_message(rid, folded))
        if status == "done" and current["status"] == "done":
            return current  # idempotent: no second event, done_at stays
        if status == "snoozed" and current["status"] == "done":
            raise ReminderError(f"{rid} is already done and cannot be snoozed.")
        _append(path, ev)
        return _apply(current, ev)
