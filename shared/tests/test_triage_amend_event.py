"""`triage.amend_triage_item` writer validation and errors.

iterate-2026-08-08-triage-amend-event (trg-b310add8 / P2.46). Covers the
iterate spec's AC1 and AC6, plus the existence/residence contract mirrored
from `mark_status`. Split when this file crossed the 300-LOC guideline
(Stage-2 code review fix round): read-side overlay, `(ts, file-order)`
interleaving, locking, and the Boundary Probe live in
`test_triage_amend_event_overlay.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import amend_triage_item, append_triage_item, read_all_items  # noqa: E402


def _seed(root: Path, **overrides) -> str:
    kwargs = dict(
        source="manual", severity="low", kind="bug",
        title="Original title", detail="Original detail",
    )
    kwargs.update(overrides)
    return append_triage_item(root, **kwargs)


# --- writer validation / errors ---------------------------------------------

def test_amend_rejects_contentless_call(tmp_path: Path):
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="amend must set at least one of"):
        amend_triage_item(tmp_path, item_id, by="tester")


def test_amend_rejects_unknown_severity(tmp_path: Path):
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="unknown severity"):
        amend_triage_item(tmp_path, item_id, by="tester", severity="urgent")


def test_amend_rejects_unknown_kind(tmp_path: Path):
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="unknown kind"):
        amend_triage_item(tmp_path, item_id, by="tester", kind="epic")


def test_amend_rejects_an_empty_title(tmp_path: Path):
    """AC1/AC6: mirrors `append_triage_item`'s own guard — an empty title must
    never reach the wire (it would fail the schema's `minLength: 1`)."""
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        amend_triage_item(tmp_path, item_id, by="tester", title="")


def test_amend_rejects_a_whitespace_only_title(tmp_path: Path):
    """The whitespace-only case is the one that would otherwise slip past both
    the writer AND the wire schema, only to be silently skipped by
    `validate_amend_event` on read — a "successful" CLI call whose correction
    never takes effect."""
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        amend_triage_item(tmp_path, item_id, by="tester", title="   ")


def test_amend_rejects_a_non_string_title(tmp_path: Path):
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="title must be a non-empty string"):
        amend_triage_item(tmp_path, item_id, by="tester", title=42)  # type: ignore[arg-type]


def test_amend_rejects_a_non_string_detail(tmp_path: Path):
    """Stage-2 code review finding 1: a non-str `detail` must never reach the
    wire — it fails the schema and is then skipped WHOLE by
    `validate_amend_event` on read, silently discarding any co-submitted,
    otherwise-valid `title` too."""
    item_id = _seed(tmp_path)
    with pytest.raises(ValueError, match="detail must be a string"):
        amend_triage_item(tmp_path, item_id, by="tester", title="fix", detail=42)  # type: ignore[arg-type]


def test_amend_raises_filenotfound_when_store_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        amend_triage_item(tmp_path, "trg-anything", by="tester", title="x")


def test_amend_validates_arguments_before_checking_store_existence(tmp_path: Path):
    """Stage-2 code review finding 2: argument validation must run BEFORE any
    I/O (mirrors `mark_status`'s documented rule), so a contentless call on an
    uninitialized store reports the real defect, not `FileNotFoundError`."""
    with pytest.raises(ValueError, match="amend must set at least one of"):
        amend_triage_item(tmp_path, "trg-anything", by="tester")


def test_amend_raises_keyerror_for_unknown_id(tmp_path: Path):
    _seed(tmp_path)
    with pytest.raises(KeyError):
        amend_triage_item(tmp_path, "trg-doesnotexist", by="tester", title="x")


def test_amend_defaults_by_to_cli(tmp_path: Path):
    item_id = _seed(tmp_path)
    amend_triage_item(tmp_path, item_id, title="new title")
    item = next(i for i in read_all_items(tmp_path) if i["id"] == item_id)
    assert item["amendedBy"] == "cli"
