"""Shared helpers for the github_triage test modules (keeps the legacy ones small)."""

from __future__ import annotations

from pathlib import Path

from triage import read_all_items


def open_card_sources(root: Path) -> set[str]:
    """Which feeds ('cs' / 'art') currently hold an open per-finding card."""
    return {
        i["dedupKey"].split(":")[2] for i in read_all_items(root)
        if i.get("status") == "triage" and i.get("dedupKey", "").count(":") >= 4
        and i["dedupKey"].startswith("gh-security:")
    }


def is_rollup(key: str) -> bool:
    """The per-repo roll-up key; per-finding cards add ``:feed:rule:path``."""
    return key.startswith("gh-security:") and key.count(":") == 1
