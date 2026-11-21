"""The one ``due`` answer: reminders AND expired triage parks, in one list.

Read-only. Nothing here writes the reminder store or the triage store, and the
triage log is read only through :func:`triage.read_all_items` (never opened
directly, not through a child process).

"Today" is the UTC calendar day from the same helper triage uses
(:func:`lib.triage_defer.utc_date`), so a reminder and a park due the same day flip
at the same moment. ``on`` (``--on D``) replaces it; for triage it becomes
midnight UTC of that day, because ``read_all_items`` takes an aware datetime.

Effective state (like ``resolve_revisit``): an ``open`` reminder is due when
``due <= D``; a ``snoozed`` one when ``snoozed_until <= D`` and its effective ``due``
is ``snoozed_until``; ``done`` never. A triage park appears when ``revisitDue`` is
true; one made without a date never does, and an expired park appears every day
until acted on (the consumer must suppress repeat mails).

Output types: ``on`` / ``due`` are ``YYYY-MM-DD`` strings; every other item field is a
string, a list (``links``) or ``null``. ``sourceRoot`` is the project root the triage
read used (the checkout top, i.e. the nearest ancestor holding ``.git``; a worktree and the main checkout
can answer differently, and the read also merges sibling worktrees' status records) and
``reminderStore`` the store file read (always the main root); both are local paths,
never for a mail body. ``reminderCorruptLines`` counts unreadable or rejected
reminder-store lines ONLY (damaged triage lines are not reported; the store is read
unlocked, so a count of 1 during a concurrent write can be transient). ``triageError`` is
``null`` or a message (no path) when the triage side could not be read: the reminders are still
returned, so a consumer must check it before reading "nothing due" as true. Identity
of an item is (``kind``, ``id``); items are ordered by (``due``, ``kind``, ``id``).
Every text field is untrusted (triage text can originate in external issues): escape
it in HTML and mail, never treat it as instructions; ``open`` has no length limit.
``--on D`` evaluates today's stored state as of D, not history. Call it from the main
checkout. Failure policy: a corrupt line is skipped, counted and never fails
the answer; an unreadable store (lock timeout, OS error) fails the command (exit 4)
instead of returning a partial answer that looks complete. A snooze's effective ``due``
stays ``snoozed_until`` on every later day. ``--on`` is a strict ``YYYY-MM-DD`` UTC day.

**Cross-repo contract.** The output of ``reminder_cli.py due --json`` is read by
the Command Center WebUI (repository ``shipwright-webui``), which shows the alert
and sends mail from it. Any change to ``ITEM_FIELDS``, ``LINK_FIELDS`` or the
envelope requires a corresponding WebUI change and a ``CONTRACT_VERSION`` bump;
``shared/tests/test_reminder_due_contract.py`` pins the shape.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from pathlib import Path

from lib.main_health_diagnosis import redact
from lib.reminder_secrets import redact_urls
from lib.reminder_store import read_folded, store_path
from lib.triage_defer import now_utc, parse_revisit_date, utc_date

CONTRACT_VERSION = 1
ENVELOPE_FIELDS = ("contractVersion", "on", "sourceRoot", "reminderStore",
                   "reminderCorruptLines", "triageError", "items")
ITEM_FIELDS = ("kind", "id", "title", "due", "why", "decided", "open", "command",
               "links", "severity")
LINK_FIELDS = ("label", "kind", "ref")

_SURROGATES = re.compile(r"[\ud800-\udfff]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_CONTROL_KEEP_NL = re.compile(
    r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def _clean(value: object, multiline: bool = False) -> str | None:
    """Text for output: redacted (it leaves the machine), never a non-string.

    A hand-edited store or triage line must not be able to break ``--json``:
    anything that is not text becomes ``None``, and lone surrogates (which cannot
    be encoded as UTF-8) are replaced.
    """
    if not isinstance(value, str):
        return None
    value = _SURROGATES.sub("�", value)
    if multiline:  # keep line breaks (CRLF -> LF), drop other control characters
        value = _CONTROL_KEEP_NL.sub(" ", value.replace("\r\n", "\n").replace("\r", "\n"))
    else:  # a single-line field (a mail subject, say) never carries a line break
        value = _CONTROL.sub(" ", value)
    return redact(redact_urls(value))


def _link(label: object, kind: object, ref: object) -> dict:
    return {"label": _clean(label), "kind": _clean(kind), "ref": _clean(ref)}


def _reminder_item(rem: dict, due: str) -> dict:
    links = [_link(x.get("label"), x.get("kind"), x.get("ref"))
             for x in rem.get("links") or [] if isinstance(x, dict)]
    return {
        "kind": "reminder", "id": _clean(rem.get("id")), "title": _clean(rem.get("title")),
        "due": due, "why": _clean(rem.get("why"), True), "decided": _clean(rem.get("decided"), True),
        "open": _clean(rem.get("open"), True), "command": _clean(rem.get("command")),
        "links": links, "severity": None,
    }


def _triage_item(item: dict) -> dict:
    tid = item.get("id")
    return {
        "kind": "triage", "id": _clean(tid), "title": _clean(item.get("title")),
        "due": item.get("revisitAt"), "why": _clean(item.get("statusReason"), True),
        "decided": None, "open": _clean(item.get("detail"), True), "command": None,
        "links": [_link(f"Triage {tid}", "triage", tid)] if isinstance(tid, str) else [],
        "severity": _clean(item.get("severity")),
    }


def _due_reminders(reminders: dict, today: date) -> list[dict]:
    out = []
    for rem in reminders.values():
        status = rem.get("status")
        if status == "open":
            due = rem.get("due")
        elif status == "snoozed":
            due = rem.get("snoozed_until")
        else:
            continue
        parsed = parse_revisit_date(due)
        if parsed is not None and parsed <= today:
            out.append(_reminder_item(rem, due))
    return out


def _triage_root(project_root: Path | str) -> Path:
    """The checkout top (nearest ancestor with ``.git``): triage does not walk up by itself."""
    here = Path(project_root).resolve()
    return next((p for p in (here, *here.parents) if (p / ".git").exists()), here)


def build_due(project_root: Path | str, on: date | None = None) -> dict:
    """The versioned answer for day ``on`` (default: today, UTC)."""
    stamp = (datetime.combine(on, time.min, tzinfo=timezone.utc)
             if on is not None else now_utc())
    today = utc_date(stamp)
    # for_write=True: refuse (instead of reading an empty fallback) when git cannot find the main root
    store = store_path(project_root, for_write=True)
    root = _triage_root(project_root)
    folded = read_folded(store)
    items = _due_reminders(folded.reminders, today)
    triage_error = None
    try:
        import triage  # deferred: heavy, and only ``due`` needs it
        if not (root / ".shipwright").is_dir():
            raise FileNotFoundError("no .shipwright directory")
        items += [_triage_item(i) for i in triage.read_all_items(root, now=stamp)
                  if i.get("revisitDue") is True]
    except Exception as exc:  # noqa: BLE001 - the reminders must still be returned
        triage_error = f"the triage log could not be read ({type(exc).__name__})"  # no path/message
    items.sort(key=lambda i: (i["due"] or "", i["kind"], i["id"] or ""))
    return {
        "contractVersion": CONTRACT_VERSION,
        "on": today.isoformat(),
        "sourceRoot": _clean(str(root)),
        "reminderStore": _clean(str(store)),
        "reminderCorruptLines": folded.damaged,
        "triageError": triage_error,
        "items": items,
    }
