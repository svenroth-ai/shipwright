"""A park's whole life, across every component that touches it.

`cross_component` integration coverage for
iterate-2026-08-01-triage-defer-lifecycle. Reference shape:
`shared/tests/test_parallel_merge_cascade_integration.py`.

The unit tests each prove one component obeys one rule. This file proves the
components COMPOSE, because every part of this change is a handshake between
two of them and each handshake is where the original defect lived:

- the **producer** (`append_triage_item_idempotent`) must not re-raise a finding
  a person parked — that was the defect that made parking close to a no-op;
- the **store** (`read_all_items`) must hand every consumer the same effective
  status, so nobody has to know about expiry;
- the **resolver** (`github_triage.resolve_stale`) must close a parked entry
  when its finding disappears, without ever overwriting a decision that ended
  the entry's life;
- the **renderers** (terminal, `triage_inbox.md`, `list --json`) must all agree
  on what is open and what is parked, on the same data at the same moment.

Nothing here is mocked except the passage of time, which is injected as the one
UTC instant the store already threads through a read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from github_triage.resolve import resolve_stale  # noqa: E402
from tools.aggregate_triage import render_markdown  # noqa: E402
from tools.triage_promote import defer, unpark  # noqa: E402
from triage import (  # noqa: E402
    append_triage_item_idempotent,
    mark_status,
    read_all_items,
)

TRIAGE_CLI = _SHARED_SCRIPTS / "tools" / "triage_cli.py"

DEDUP_KEY = "gh-security:acme/widget"
REVISIT = "2099-09-01"
BEFORE = datetime(2099, 8, 31, 23, 0, tzinfo=timezone.utc)
ON_THE_DAY = datetime(2099, 9, 1, 0, 0, tzinfo=timezone.utc)


def _import_finding(project: Path) -> str | None:
    """One run of a real producer against a finding that is still present."""
    return append_triage_item_idempotent(
        project, source="github", severity="high", kind="bug",
        title="Dependabot alerts on widget", detail="3 open advisories",
        dedup_key=DEDUP_KEY, window_seconds=None,
    )


def _sweep(project: Path, *, finding_still_present: bool) -> int:
    """One run of the real auto-resolver, told what the fetch just saw."""
    return resolve_stale(
        project,
        resolvable_prefixes={"gh-security:"},
        current_keys={DEDUP_KEY} if finding_still_present else set(),
    )


def _surfaces(project: Path) -> tuple[str, str, dict]:
    tty = subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(project), "list"],
        capture_output=True, text=True, check=False, encoding="utf-8",
    ).stdout
    md = render_markdown(read_all_items(project), now="2026-08-01T00:00:00Z")
    payload = json.loads(subprocess.run(
        [sys.executable, str(TRIAGE_CLI), "--project-root", str(project),
         "list", "--json"],
        capture_output=True, text=True, check=False, encoding="utf-8",
    ).stdout)
    return tty, md, payload


def _status(project: Path, item_id: str, *, now: datetime | None = None) -> str:
    return next(i["status"] for i in read_all_items(project, now=now)
                if i["id"] == item_id)


def test_a_park_survives_re_import_then_returns_by_itself_on_every_surface(
    tmp_path: Path,
) -> None:
    """Producer → store → three renderers, across the day the park expires.

    The single scenario the five parts were written for: a machine-raised
    finding is parked with a date, the check keeps seeing it and keeps quiet,
    every surface says the same thing about it, and on the named day it comes
    back without anyone doing anything.
    """
    item = _import_finding(tmp_path)
    assert item is not None

    # The producer runs again while the finding is still there — no duplicate.
    assert _import_finding(tmp_path) is None

    defer(tmp_path, item_id=item, reason="upstream fix is queued",
          revisit_at=REVISIT)

    # THE defect this change exists to fix: before, this produced a SECOND open
    # entry, leaving the operator with a duplicate plus a permanent parked row.
    assert _import_finding(tmp_path) is None
    assert len(read_all_items(tmp_path)) == 1

    # Every surface agrees: parked, with its date, and not among the open work.
    tty, md, payload = _surfaces(tmp_path)
    assert f"[deferred] {item}" in tty
    assert "No open triage items." in tty
    assert REVISIT in tty and REVISIT in md
    assert payload["open"] == []
    assert [e["id"] for e in payload["deferred"]] == [item]
    assert payload["deferred"][0]["revisitDue"] is False

    # The day before, still parked. On the day, open — with nothing written.
    assert _status(tmp_path, item, now=BEFORE) == "snoozed"
    events_before = (tmp_path / ".shipwright" / "triage.jsonl").read_bytes()
    assert _status(tmp_path, item, now=ON_THE_DAY) == "triage"
    assert (tmp_path / ".shipwright" / "triage.jsonl").read_bytes() == events_before


def test_a_parked_entry_closes_itself_when_its_finding_disappears(
    tmp_path: Path,
) -> None:
    """Producer → store → resolver. Operator decision #2 of 2026-07-27: a parked
    entry closes automatically, exactly like an open one — and the operator does
    not have to come back on the revisit date to discover the problem is gone."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="not this sprint", revisit_at=REVISIT)

    # The fetch succeeds and no longer reports the finding.
    assert _sweep(tmp_path, finding_still_present=False) == 1
    assert _status(tmp_path, item) == "dismissed"

    _, md, payload = _surfaces(tmp_path)
    assert payload["deferred"] == [] and payload["open"] == []
    assert "Deferred" not in md


@pytest.mark.parametrize("hostile", ['["high"]', '{"rank": 0}'])
@pytest.mark.parametrize(
    ("revisit_at", "payload_section"),
    [(REVISIT, "deferred"), ("2020-01-01", "open")],
)
def test_unhashable_severity_cannot_take_down_any_surface(
    tmp_path: Path, hostile: str, revisit_at: str, payload_section: str,
) -> None:
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="later", revisit_at=revisit_at)
    store = tmp_path / ".shipwright" / "triage.jsonl"
    raw = store.read_text(encoding="utf-8")
    store.write_text(raw.replace('"severity":"high"', f'"severity":{hostile}'),
                     encoding="utf-8")

    tty, md, payload = _surfaces(tmp_path)
    assert item in tty and item in md
    assert payload[payload_section][0]["id"] == item


def test_markdown_surface_escapes_every_untrusted_context(tmp_path: Path) -> None:
    """Stored text cannot become Markdown structure, HTML, or a code escape."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="later", revisit_at=REVISIT)
    store = tmp_path / ".shipwright" / "triage.jsonl"
    hostile_id = f"{item}`forged"
    hostile_title = "`tick` **bold** [link](https://example) <img src=x>"
    raw = store.read_text(encoding="utf-8")
    raw = raw.replace(item, hostile_id)
    raw = raw.replace("Dependabot alerts on widget", hostile_title)
    raw = raw.replace('"severity":"high"', '"severity":"`high`"')
    store.write_text(raw, encoding="utf-8")

    md = render_markdown(read_all_items(tmp_path), now="2026-08-01T00:00:00Z")
    assert "<img" not in md
    assert "&lt;img src=x&gt;" in md
    assert "[link](" not in md
    assert r"\[link\]\(https://example\)" in md
    assert "``id=" in md
    assert hostile_id in md


def test_hostile_park_cannot_inject_markup_after_it_expires(tmp_path: Path) -> None:
    """Expiry must not move trusted-as-data bytes into active Markdown."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="later", revisit_at="2020-01-01")
    store = tmp_path / ".shipwright" / "triage.jsonl"
    records = [json.loads(line) for line in store.read_text(
        encoding="utf-8").splitlines()]
    hostile_id = 'trg-x"><img src=x>`'
    for record in records:
        if record.get("id") == item:
            record["id"] = hostile_id
        if record.get("event") == "append":
            record["title"] = "**bold** [link](https://example)"
            record["source"] = {"label": "[source](https://example) <svg>"}
            record["severity"] = ["high"]
            record["originalTs"] = [1]
            record["evidencePath"] = "proof`forged"
            record.pop("suggestedPriority", None)
            record.pop("suggestedDomain", None)
    store.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in records)
        + "\n",
        encoding="utf-8",
    )

    md = render_markdown(read_all_items(tmp_path), now="2026-08-01T00:00:00Z")
    assert '<a id="trg-x&quot;&gt;&lt;img src=x&gt;`"></a>' in md
    assert r"\[source\]\(https://example\) &lt;svg&gt;" in md
    assert "### Source: [source](" not in md
    assert r"**\*\*bold\*\* \[link\]\(https://example\)**" in md
    assert "``id=trg-x\"><img src=x>`" in md
    assert "Evidence: ``proof`forged``" in md


def test_a_parked_entry_whose_finding_is_still_there_is_left_alone(
    tmp_path: Path,
) -> None:
    """The other half of the same handshake — a successful fetch that still
    sees the finding must not close the park."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="not this sprint", revisit_at=REVISIT)
    assert _sweep(tmp_path, finding_still_present=True) == 0
    assert _status(tmp_path, item) == "snoozed"


def test_a_dismissal_recorded_by_a_person_still_survives_the_sweep(
    tmp_path: Path,
) -> None:
    """The `trg-93ceb2b0` guarantee, end to end. Widening which statuses a
    producer may close must not have widened it to decisions that ENDED an
    entry's life — only a park moved."""
    item = _import_finding(tmp_path)
    mark_status(tmp_path, item, new_status="dismissed", by="operator",
                reason="accepted risk")
    assert _sweep(tmp_path, finding_still_present=False) == 0
    assert _status(tmp_path, item) == "dismissed"
    stored = next(i for i in read_all_items(tmp_path) if i["id"] == item)
    assert stored["statusReason"] == "accepted risk"


def test_un_parking_re_opens_the_entry_and_re_arms_the_producer(
    tmp_path: Path,
) -> None:
    """Un-park → store → producer. After the reversal the entry is open, its
    date is gone, and the finding is once again suppressed as an OPEN duplicate
    rather than as a park — the two suppression routes must hand over cleanly."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="mis-click", revisit_at=REVISIT)
    unpark(tmp_path, item_id=item, reason="parked by mistake")

    stored = next(i for i in read_all_items(tmp_path) if i["id"] == item)
    assert (stored["status"], stored["revisitAt"]) == ("triage", None)
    assert _import_finding(tmp_path) is None

    tty, md, payload = _surfaces(tmp_path)
    assert [e["id"] for e in payload["open"]] == [item]
    assert payload["deferred"] == []
    assert f"[open] {item}" in tty
    assert "Deferred" not in md


def test_an_expired_park_is_closed_by_the_producer_like_any_open_entry(
    tmp_path: Path,
) -> None:
    """The two mechanisms meet: expiry made it open, so the resolver treats it
    as open. Neither had to be told about the other."""
    item = _import_finding(tmp_path)
    defer(tmp_path, item_id=item, reason="later", revisit_at="2020-01-01")
    assert _status(tmp_path, item) == "triage"
    assert _sweep(tmp_path, finding_still_present=False) == 1
    assert _status(tmp_path, item) == "dismissed"
