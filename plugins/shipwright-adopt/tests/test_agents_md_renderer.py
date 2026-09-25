"""Verify AGENTS.md generation: single-source with CLAUDE.md, Codex appendix,
and load-bearing preservation — the AGENTS.md counterpart of
`test_claude_md_standing_request_append.py` /
`test_artifact_writer_data_preservation.py` (R4,
iterate-2026-09-23-m5-agents-md-generation-drift).

The core design constraint under test: `write_agents_md` must never re-derive
the shared body. It calls `_render_claude_md(..., host_name="Codex")` — the
exact function CLAUDE.md's own writer calls — so there is nothing here that
can drift against CLAUDE.md's content independently of that one function.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.agents_md_renderer import CODEX_APPENDIX_MARKER, _read_codex_appendix, write_agents_md
from lib.artifact_writer import write_claude_md
from lib.claude_md_renderer import STANDING_REQUEST_HEADING, _render_claude_md


_KWARGS = dict(
    project_name="Demo",
    profile="vite-hono",
    stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
    commands={"build": "x", "test": "x", "dev": "x"},
    product_description="demo",
)


def _loadbearing_fixture(proj: Path, filename: str) -> None:
    body = "# Real Project\n\n" + ("Load-bearing prose. " * 120) + "\n"
    assert len(body.encode("utf-8")) > 1024, "fixture must trip the 1 KB threshold"
    (proj / filename).write_text(body, encoding="utf-8")


def _preservation_notes(proj: Path, file: str) -> list[str]:
    log = proj / ".shipwright" / "adopt" / "preservation_log.json"
    entries = json.loads(log.read_text(encoding="utf-8"))["entries"]
    return [e.get("note", "") for e in entries if e["file"] == file]


def test_fresh_write_has_codex_host_name_and_appendix(tmp_path: Path) -> None:
    path = write_agents_md(tmp_path, **_KWARGS)
    assert path == tmp_path / "AGENTS.md"
    body = path.read_text(encoding="utf-8")
    assert "Codex withholds subagent spawning" in body
    assert "Claude Code withholds subagent spawning" not in body
    assert CODEX_APPENDIX_MARKER in body
    assert "gpt-5.6" not in body


def test_shared_body_matches_render_claude_md_with_codex_host_name(tmp_path: Path) -> None:
    """The single-source guarantee: AGENTS.md's shared body is byte-for-byte
    what `_render_claude_md(..., host_name="Codex")` produces directly, with
    only the appendix appended after it."""
    path = write_agents_md(tmp_path, **_KWARGS)
    body = path.read_text(encoding="utf-8")
    expected_shared = _render_claude_md(host_name="Codex", **_KWARGS)
    assert body.startswith(expected_shared)
    appendix = _read_codex_appendix()
    assert body == expected_shared + "\n\n" + appendix + "\n"


def test_no_backup_when_absent(tmp_path: Path) -> None:
    write_agents_md(tmp_path, **_KWARGS)
    assert not (tmp_path / ".shipwright" / "adopt" / "backups" / "AGENTS.md.preserved").exists()


def test_loadbearing_agents_md_is_preserved_and_receives_both_sections(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj, "AGENTS.md")
    original = (proj / "AGENTS.md").read_text(encoding="utf-8")

    result = write_agents_md(proj, **_KWARGS)

    assert result == proj / ".shipwright" / "adopt" / "AGENTS.md.adopt-suggested"
    assert result.exists()
    delivered = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert delivered.startswith(original.rstrip("\n")), (
        "the original bytes must be intact at the head — appending must never overwrite"
    )
    assert STANDING_REQUEST_HEADING in delivered
    assert "Codex withholds subagent spawning" in delivered
    assert CODEX_APPENDIX_MARKER in delivered

    backup = proj / ".shipwright" / "adopt" / "backups" / "AGENTS.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == original


def test_appending_both_sections_is_idempotent(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj, "AGENTS.md")

    write_agents_md(proj, **_KWARGS)
    after_one = (proj / "AGENTS.md").read_text(encoding="utf-8")
    write_agents_md(proj, **_KWARGS)
    after_two = (proj / "AGENTS.md").read_text(encoding="utf-8")

    assert after_one.count(STANDING_REQUEST_HEADING) == 1
    assert after_one.count(CODEX_APPENDIX_MARKER) == 1
    assert after_two == after_one, (
        "a second adopt run changed AGENTS.md — the append must be idempotent "
        "by heading, or repeated onboarding stacks duplicate sections"
    )


def test_preservation_log_discloses_both_appends(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj, "AGENTS.md")
    write_agents_md(proj, **_KWARGS)

    notes = _preservation_notes(proj, "AGENTS.md")
    assert notes, "adopt recorded no preservation entry for AGENTS.md"
    note = notes[-1]
    assert "standing-request section APPENDED" in note
    assert "Codex appendix APPENDED" in note
    assert "nothing overwritten" in note


def test_preservation_log_second_run_records_both_already_present(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj, "AGENTS.md")
    write_agents_md(proj, **_KWARGS)
    write_agents_md(proj, **_KWARGS)

    notes = _preservation_notes(proj, "AGENTS.md")
    assert len(notes) >= 2
    note = notes[-1]
    assert "standing-request section already present" in note
    assert "Codex appendix already present" in note
    assert "APPENDED" not in note


def test_thin_existing_agents_md_is_overwritten_with_backup(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# placeholder\n", encoding="utf-8")
    write_agents_md(tmp_path, **_KWARGS)
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "demo" in body
    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "AGENTS.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == "# placeholder\n"


def test_agents_md_generation_does_not_disturb_claude_md(tmp_path: Path) -> None:
    """The two writers are independent — running both must not cross-contaminate."""
    write_claude_md(tmp_path, **_KWARGS)
    write_agents_md(tmp_path, **_KWARGS)

    claude_body = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    agents_body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Claude Code withholds subagent spawning" in claude_body
    assert "Codex withholds subagent spawning" in agents_body
    assert "Codex operating policy" not in claude_body


def test_agents_md_does_not_misname_itself_as_claude_md(tmp_path: Path) -> None:
    """Doubt-reviewer (R4, high): the 'Editing this file' section and its
    growth-gate bullet must track host_name too, not just the standing-request
    sentence — otherwise AGENTS.md calls itself CLAUDE.md and cites an env var
    (`check_agent_doc_budget.py`'s enforcement) that only reads CLAUDE.md."""
    path = write_agents_md(tmp_path, **_KWARGS)
    body = path.read_text(encoding="utf-8")
    assert "AGENTS.md is **orientation + a terse invariant index**" in body
    assert "CLAUDE.md is **orientation + a terse invariant index**" not in body
    assert "SHIPWRIGHT_CLAUDE_MD_GROWTH_OK" not in body
    assert "No automated growth gate for this file yet" in body


def test_claude_md_growth_gate_bullet_is_unchanged(tmp_path: Path) -> None:
    """Regression guard for the host_name-parameterized growth-gate bullet:
    the CLAUDE.md path must render byte-identical to before that change."""
    path = write_claude_md(tmp_path, **_KWARGS)
    body = path.read_text(encoding="utf-8")
    assert "CLAUDE.md is **orientation + a terse invariant index**" in body
    assert "SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1" in body
    assert "No automated growth gate for this file yet" not in body


def test_codex_appendix_marker_is_embedded_in_the_live_file() -> None:
    """The marker must actually be present in the shipped appendix — a test
    asserting against a marker the file doesn't contain would pass vacuously."""
    assert CODEX_APPENDIX_MARKER in _read_codex_appendix()


def test_appendix_reword_between_runs_does_not_duplicate(tmp_path: Path, monkeypatch) -> None:
    """The idempotency marker is an inert HTML comment embedded in the
    appendix file itself, decoupled from its visible heading/body — so a
    reword of the heading or body between two adopt runs must not produce a
    duplicate appendix section (external code-review cascade, R4)."""
    import lib.agents_md_renderer as renderer

    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj, "AGENTS.md")
    write_agents_md(proj, **_KWARGS)

    monkeypatch.setattr(
        renderer, "_read_codex_appendix",
        lambda: CODEX_APPENDIX_MARKER + "\n## A completely reworded heading\n\nReworded body.",
    )
    write_agents_md(proj, **_KWARGS)

    body = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert body.count(CODEX_APPENDIX_MARKER) == 1


def test_appendix_not_skipped_by_a_colliding_unmarked_heading(tmp_path: Path) -> None:
    """The appendix's visible heading text ("## Codex operating policy") is
    generic enough that a project could plausibly already have hand-written a
    section of that exact name before ever adopting Shipwright. That must NOT
    make `_append_codex_appendix` treat Shipwright's own appendix as already
    present (external code-review cascade, R4, medium) — only the marker
    counts, so an unmarked, pre-existing same-named section is not a match."""
    proj = tmp_path / "proj"
    proj.mkdir()
    body = (
        "# Real Project\n\n## Codex operating policy\n\n"
        "This is the project's own hand-written section, not Shipwright's.\n\n"
        + ("Load-bearing prose. " * 100) + "\n"
    )
    assert len(body.encode("utf-8")) > 1024, "fixture must trip the loadbearing threshold"
    (proj / "AGENTS.md").write_text(body, encoding="utf-8")

    write_agents_md(proj, **_KWARGS)

    delivered = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert delivered.startswith(body.rstrip("\n"))
    assert CODEX_APPENDIX_MARKER in delivered, (
        "Shipwright's own appendix was skipped because of a pre-existing, "
        "unmarked section sharing its heading text — the marker must be what "
        "gates the idempotency check, not the visible heading"
    )
    assert delivered.count("## Codex operating policy") == 2, (
        "both the project's own pre-existing section and Shipwright's "
        "delivered appendix should now be present"
    )


def test_append_preserves_original_crlf_line_endings(tmp_path: Path) -> None:
    """Doubt-reviewer (R4, medium): appending must not silently rewrite the
    PRE-EXISTING portion's line endings (e.g. CRLF -> LF -> CRLF round-trip
    via universal-newline translation) — that would contradict 'nothing
    existing is touched' with a full-file line-ending diff."""
    proj = tmp_path / "proj"
    proj.mkdir()
    original = ("# Real Project\r\n\r\n" + ("Load-bearing prose. " * 120) + "\r\n")
    assert len(original.encode("utf-8")) > 1024, "fixture must trip the loadbearing threshold"
    (proj / "AGENTS.md").write_bytes(original.encode("utf-8"))

    write_agents_md(proj, **_KWARGS)

    raw = (proj / "AGENTS.md").read_bytes()
    original_bytes = original.encode("utf-8")
    assert raw.startswith(original_bytes), (
        "the preserved original bytes (incl. its CRLF line endings) must survive "
        "byte-for-byte at the head of the file after an append"
    )
    appended_tail = raw[len(original_bytes):]
    assert b"\r\n" not in appended_tail, (
        "the newly appended section is always LF-terminated by design (mixed "
        "line endings in the final file are the deliberate, documented "
        "trade-off — external code-review cascade, R4, low — over silently "
        "rewriting the whole file to one ending); this pins that as intended "
        "rather than an undocumented accident"
    )
