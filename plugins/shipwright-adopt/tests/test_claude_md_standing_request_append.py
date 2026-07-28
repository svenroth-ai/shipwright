"""Adopt must DELIVER the standing request, not merely render it.

The Stage-3 doubt pass of iterate-2026-07-28-review-subagents-standing-request
disproved a shipped claim: `write_claude_md` refuses to overwrite an existing
CLAUDE.md over ~1 KB and writes its render to a side-file the harness never
loads. Every repo mature enough to be worth adopting takes that branch, so the
grant reached **none** of them — while the mirror test in `shared/tests` stayed
green, because it calls the *renderer* directly.

So these go through the **writer**. The content half — that all three carriers
hold the same section, and that it never affirmatively grants fan-out — lives in
`shared/tests/test_claude_md_standing_request.py`; this file owns only the
question of whether an adopted project actually receives it.

Appending is defensible where overwriting is not: nothing existing is touched,
the operator keeps the backup `preserve_if_exists` already took, and the
preservation log says so.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.artifact_writer import write_claude_md
from lib.claude_md_renderer import (
    STANDING_REQUEST_HEADING,
    STANDING_REQUEST_SECTION,
)


#: Operative instructions from the grant, plus the carve-out that keeps it from
#: reading as authorising fan-out. Derived from the shipped constant so this
#: file cannot drift from it independently.
_GRANT_MARKERS = (
    "The review cascade is requested by default",
    "never pause to ask",
    "this file is that request",
    "The grant covers reviewers, not fan-out",
    "section-builder",
)


def _loadbearing_fixture(proj: Path) -> None:
    """A CLAUDE.md over the ~1 KB load-bearing threshold."""
    body = "# Real Project\n\n" + ("Load-bearing prose. " * 120) + "\n"
    assert len(body.encode("utf-8")) > 1024, "fixture must trip the 1 KB threshold"
    (proj / "CLAUDE.md").write_text(body, encoding="utf-8")


def _adopt(proj: Path) -> None:
    write_claude_md(
        proj,
        project_name="Demo",
        profile="vite-hono",
        stack={"runtime": {}, "frontend": {}, "backend": {},
               "database": {}, "auth": {}},
        commands={"build": "x", "test": "x", "dev": "x"},
        product_description="demo",
    )


def _preservation_notes(proj: Path) -> list[str]:
    """Every `CLAUDE.md` note from adopt's preservation log, oldest first."""
    log = proj / ".shipwright" / "adopt" / "preservation_log.json"
    entries = json.loads(log.read_text(encoding="utf-8"))["entries"]
    return [e.get("note", "") for e in entries if e["file"] == "CLAUDE.md"]


def test_the_markers_are_actually_in_the_shipped_constant() -> None:
    """Guard the guard: if the constant is reworded, these markers must be
    updated deliberately rather than silently asserting nothing."""
    for marker in _GRANT_MARKERS:
        assert marker in STANDING_REQUEST_SECTION, (
            f"{marker!r} is no longer in STANDING_REQUEST_SECTION — this file "
            "would be asserting against text that does not ship."
        )


def test_a_preserved_loadbearing_claude_md_still_receives_the_grant(tmp_path: Path) -> None:
    """The delivery leg. Preserved means preserved AND informed."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)
    _adopt(proj)

    delivered = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Load-bearing prose." in delivered, (
        "preserved content must survive — appending must never overwrite"
    )
    for marker in _GRANT_MARKERS:
        assert marker in delivered, (
            f"a preserved load-bearing CLAUDE.md did not receive {marker!r} — "
            "the adopted project would run without the standing request while "
            "a greenfield one gets it."
        )


def test_the_original_survives_byte_for_byte_at_the_head(tmp_path: Path) -> None:
    """Appending is only defensible if it is genuinely additive."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)
    original = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    _adopt(proj)

    delivered = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert delivered.startswith(original.rstrip("\n")), (
        "the original bytes must be intact at the head — an append that "
        "reflows or re-encodes the preserved file is an overwrite in disguise"
    )


def test_appending_the_grant_is_idempotent(tmp_path: Path) -> None:
    """Adopt is re-runnable; a second pass must not stack a duplicate section."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)

    _adopt(proj)
    after_one = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    _adopt(proj)
    after_two = (proj / "CLAUDE.md").read_text(encoding="utf-8")

    assert after_one.count(STANDING_REQUEST_HEADING) == 1
    assert after_two == after_one, (
        "a second adopt run changed CLAUDE.md — the append must be idempotent "
        "by heading, or repeated onboarding stacks duplicate grants"
    )


def test_the_preservation_log_records_that_the_file_was_appended_to(tmp_path: Path) -> None:
    """The audit trail must not still read 'skipped'.

    `preservation_log.json` is the operator's only record of what adopt did to
    a file it promised to preserve. The action stays `skipped_loadbearing` —
    the render genuinely was skipped — so the note is the sole place the append
    is disclosed. Left unchanged, the log would assert adopt touched nothing
    while the file on disk had grown a section.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)
    _adopt(proj)

    notes = _preservation_notes(proj)
    assert notes, "adopt recorded no preservation entry for CLAUDE.md"
    assert "APPENDED" in notes[-1], (
        "the preservation log must disclose the append — an entry that only "
        f"says the render was skipped understates what happened: {notes[-1]!r}"
    )
    assert "nothing overwritten" in notes[-1], (
        "…and must say the append was additive, which is the property that "
        "makes writing to a preserved file defensible at all"
    )


def test_a_second_run_records_that_the_grant_was_already_present(tmp_path: Path) -> None:
    """The two cases must be distinguishable in the log, or 'APPENDED' on every
    re-run would suggest repeated modification of a preserved file."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)

    _adopt(proj)
    _adopt(proj)

    notes = _preservation_notes(proj)
    assert len(notes) >= 2, "each adopt run must append its own log entry"
    assert "already present" in notes[-1], (
        f"a re-run must record a no-op, not another append: {notes[-1]!r}"
    )
    assert "APPENDED" not in notes[-1], (
        "the second run wrote nothing — claiming an append would make the log "
        "unusable as evidence of what adopt actually changed"
    )
