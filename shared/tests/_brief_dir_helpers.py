"""Builders for the Brief-package intake tests (campaign brief-driven-run, B2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import brief_dir_intake as bdi  # noqa: E402

bp = bdi._lib("brief_package")

CAPTURE = """## Capture note
Requirement: A user can add a note with a title and a body.
- Outcome: a saved note appears in the list
- Fit criterion: a note added with a title is listed within one second
- Purpose: keep ideas from getting lost
- Boundaries: plain text only, one user
- Failure: an empty title is refused with a message
- Glossary: n/a: no new term
- Rationale: n/a: the simplest capture flow
- Out of scope: sharing and attachments
"""

LIST_NOTES = """## List notes
Requirement: A user sees all Notes, newest first.
- Outcome: the Notes list shows newest first
- Fit criterion: the latest note is the first row
- Purpose: find a note quickly
- Boundaries: at most 500 notes are shown
- Failure: an empty list shows a hint
- Rationale: n/a: expected default order
- Out of scope: search
"""

GLOSSARY = "## Glossary\n- **Notes**: the user's saved short texts, each with a title and a body.\n"

DEFAULT_MD = "# Notes\n\nA tiny notes app.\n\n" + CAPTURE + "\n" + LIST_NOTES + "\n" + GLOSSARY


def build_package(project: Path, md: str = DEFAULT_MD, *, name: str = "brief",
                  approved_by: str | None = "human:sven", **over) -> Path:
    """A valid, approved package at ``project/<name>``; ``over`` overrides brief.json fields."""
    dest = Path(project) / name
    (dest / "mockups").mkdir(parents=True, exist_ok=True)
    files = {
        "brief.md": md, "scope.md": "# Scope\n\nIn: notes.\n",
        "visual-guidelines.md": "# Visual\n\nPlain.\n",
        "mockups/01-notes.html": "<!doctype html><html><body>Notes</body></html>\n",
        "screen-map.json": json.dumps({"screens": [{"id": "notes", "mockup": "01-notes.html"}]}) + "\n",
    }
    for rel, text in files.items():
        (dest / rel).write_bytes(text.encode("utf-8"))
    brief = {"version": bp.BRIEF_VERSION, "profile": "vite-hono", "deploy_target": "none", "autonomy": "guided",
             "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
             "design_system": "visual-guidelines.md", "brief_dir": name, "env_preflight": [],
             "allow_parallel_builders": False, "ui_host": "web"}
    brief.update(over)
    if approved_by:
        brief.update(approved_by=approved_by, approved_at="2026-10-25T00:00:00Z")
    (dest / "brief.json").write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    brief["package_sha256"] = bp.package_sha256(dest)
    (dest / "brief.json").write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    return dest


def write_config(project: Path) -> Path:
    path = Path(project) / bdi.CONFIG_NAME
    path.write_text(json.dumps({"schemaVersion": 2, "profile": "vite-hono"}) + "\n", encoding="utf-8")
    return path
