"""Fixture builders shared by the FR change-history test modules (campaign S7).

A plain helper module rather than a ``conftest.py`` addition: these are
constructors, not pytest fixtures, and the sibling ``conftest`` owns an
unrelated autouse env guard. Split out so neither test module has to carry the
setup and cross the size guideline.
"""

from __future__ import annotations

import json
from pathlib import Path

SPEC_HEADER = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
    "|---|---|---|---|---|---|---|\n"
)


def write_events(root: Path, events: list[dict]) -> None:
    (root / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )


def write_catalog(root: Path, fr_ids=("FR-01.01", "FR-01.02")) -> None:
    split = root / ".shipwright" / "planning" / "01-adopted"
    split.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"| {fr} | Adopted | Name {fr} | Must | Does a thing. | code | unit (inferred) |\n"
        for fr in fr_ids
    )
    (split / "spec.md").write_text(SPEC_HEADER + rows, encoding="utf-8")


def project(tmp_path: Path, events: list[dict], fr_ids=("FR-01.01", "FR-01.02")) -> Path:
    """A project tree with a parseable catalog and an event log."""
    write_catalog(tmp_path, fr_ids)
    write_events(tmp_path, events)
    return tmp_path


def work(**kw) -> dict:
    """A ``work_completed`` event with sane defaults; override any field."""
    base = {
        "type": "work_completed",
        "source": "iterate",
        "id": kw.pop("id", "evt-0001"),
        "ts": kw.pop("ts", "2026-01-01T00:00:00+00:00"),
    }
    base.update(kw)
    return base
