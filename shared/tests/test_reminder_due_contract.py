"""The `due` output is a cross-repo contract; pin its shape and keep it stated (E1b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib import reminder_due
from lib.reminder_due import build_due

_REPO = Path(__file__).resolve().parent.parent.parent


@pytest.mark.covers("FR-01.22/AC09")
def test_shape_is_pinned():
    assert reminder_due.CONTRACT_VERSION == 1
    assert reminder_due.ENVELOPE_FIELDS == (
        "contractVersion", "on", "sourceRoot", "reminderStore", "reminderCorruptLines",
        "triageError", "items")
    assert reminder_due.ITEM_FIELDS == (
        "kind", "id", "title", "due", "why", "decided", "open", "command", "links",
        "severity")
    assert reminder_due.LINK_FIELDS == ("label", "kind", "ref")


@pytest.mark.covers("FR-01.22/AC09")
def test_envelope_matches_the_pinned_fields(tmp_path):
    assert tuple(build_due(tmp_path)) == reminder_due.ENVELOPE_FIELDS


@pytest.mark.covers("FR-01.22/AC09")
def test_contract_names_the_webui_and_the_rule():
    text = (_REPO / "shared/scripts/lib/reminder_due.py").read_text(encoding="utf-8")
    assert "Cross-repo contract" in text
    assert "shipwright-webui" in text and "Command Center" in text
    assert "requires a corresponding WebUI change" in text
    guide = (_REPO / "docs/guide.md").read_text(encoding="utf-8")
    assert "due [--on YYYY-MM-DD]" in guide and "contractVersion" in guide
