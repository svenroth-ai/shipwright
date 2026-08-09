"""Delivery visibility for valid amend events held in the triage outbox."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.triage_amend import has_amend_content, validate_amend_event  # noqa: E402
from lib.triage_delivery import undelivered_amends_from_records  # noqa: E402
from triage import KINDS, SEVERITIES  # noqa: E402

_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_AMEND = {
    "event": "amend", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "by": "webui", "title": "corrected",
}


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _valid_amend(event: dict) -> bool:
    return has_amend_content(event) and validate_amend_event(
        event, severities=SEVERITIES, kinds=KINDS,
    )


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines()]


def test_outbox_only_valid_amend_for_a_tracked_item_is_undelivered() -> None:
    assert undelivered_amends_from_records(
        _records(_j(_APPEND)), _records(_j(_AMEND)), is_valid_amend=_valid_amend,
    ) == {"trg-good0001"}


def test_invalid_or_orphan_amend_never_creates_a_delivery_signal() -> None:
    invalid = {**_AMEND, "severity": "unknown"}
    contentless = {key: value for key, value in _AMEND.items() if key != "title"}
    orphan = {**_AMEND, "id": "trg-orphan01"}
    assert undelivered_amends_from_records(
        _records(_j(_APPEND)),
        _records(_j(invalid) + "\n" + _j(contentless) + "\n" + _j(orphan)),
        is_valid_amend=_valid_amend,
    ) == set()


def test_outbox_only_append_cannot_make_its_amend_look_pending() -> None:
    assert undelivered_amends_from_records(
        [], _records(_j(_APPEND) + "\n" + _j(_AMEND)), is_valid_amend=_valid_amend,
    ) == set()


def test_each_amend_is_compared_independently_not_as_a_deciding_event() -> None:
    earlier = {**_AMEND, "ts": "2026-01-02T00:00:00Z", "title": "first"}
    later = {**_AMEND, "ts": "2026-01-03T00:00:00Z", "detail": "second"}
    assert undelivered_amends_from_records(
        _records(_j(_APPEND) + "\n" + _j(later)), _records(_j(earlier)),
        is_valid_amend=_valid_amend,
    ) == {"trg-good0001"}


def test_tracked_equivalent_amend_clears_the_outbox_delivery_signal() -> None:
    assert undelivered_amends_from_records(
        _records(_j(_APPEND) + "\n" + _j(_AMEND)), _records(_j(_AMEND)),
        is_valid_amend=_valid_amend,
    ) == set()
