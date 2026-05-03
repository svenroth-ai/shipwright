"""Tests for shared/scripts/lib/session_role.py.

Round-trip + boundary probes against the JSON marker file. The probes
exercise the 8-category checklist in
`plugins/shipwright-iterate/skills/iterate/references/boundary-probes.md`
that apply to a machine-and-operator-edited JSON file:

- Round-trip happy path
- UTF-8 BOM (Notepad save artefact)
- CRLF line endings
- Non-ASCII in `notes` (umlauts)
- Empty `notes` value
- Idempotent rewrite (same role + worktree → no change)
- Malformed file recovery
- Detect parallel sessions across `.worktrees/<slug>/`

Categories deliberately skipped + why (machine-only-ish JSON):
- POSIX `export KEY=value` prefix — not applicable (JSON, not env)
- Inline `# comment` — JSON does not support comments
- `#` inside a value — handled by JSON's quoting model
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.session_role import (
    MARKER_RELPATH,
    VALID_ROLES,
    detect_parallel_sessions,
    read_role,
    write_role,
)


# ---------------------------------------------------------------------------
# Round-trip — happy path
# ---------------------------------------------------------------------------


def test_round_trip_canonical(tmp_project):
    """write_role → read_role returns a dict with the same role/path/session."""
    written = write_role(
        tmp_project,
        role="canonical",
        session_id="sess-abc",
        worktree_path=str(tmp_project),
        notes="primary repo",
    )
    read_back = read_role(tmp_project)

    assert read_back is not None
    assert read_back["role"] == "canonical"
    assert read_back["set_by_session_id"] == "sess-abc"
    assert read_back["worktree_path"] == str(tmp_project)
    assert read_back["notes"] == "primary repo"
    # Atomic write: no leftover .tmp file.
    assert not (tmp_project / ".shipwright" / "iterate_session_role.json.tmp").exists()
    # Round-trip equivalence (drop synthetic _marker_path which is only
    # added by detect_parallel_sessions).
    for key in ("role", "set_at", "set_by_session_id", "worktree_path", "notes"):
        assert written[key] == read_back[key]


def test_round_trip_secondary(tmp_project):
    write_role(
        tmp_project,
        role="secondary",
        session_id="sess-xyz",
        worktree_path=str(tmp_project / ".worktrees" / "feature-x"),
        notes="",
    )
    read_back = read_role(tmp_project)
    assert read_back is not None
    assert read_back["role"] == "secondary"


# ---------------------------------------------------------------------------
# Boundary probe: UTF-8 BOM
# ---------------------------------------------------------------------------


def test_read_strips_utf8_bom(tmp_project):
    """A Notepad-saved marker file has a leading BOM; reader must strip it."""
    target = tmp_project / MARKER_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "role": "canonical",
        "set_at": "2026-05-03T12:00:00+00:00",
        "set_by_session_id": "sess-bom",
        "worktree_path": str(tmp_project),
        "notes": "saved by notepad",
    }
    # Prepend BOM bytes to the JSON.
    target.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))

    result = read_role(tmp_project)
    assert result is not None, "BOM-prefixed marker was not parsed"
    assert result["role"] == "canonical"
    assert result["set_by_session_id"] == "sess-bom"


# ---------------------------------------------------------------------------
# Boundary probe: CRLF line endings
# ---------------------------------------------------------------------------


def test_read_handles_crlf(tmp_project):
    """A marker file written with CRLF on Windows must still parse."""
    target = tmp_project / MARKER_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload_str = json.dumps({
        "role": "secondary",
        "set_at": "2026-05-03T12:00:00+00:00",
        "set_by_session_id": "sess-crlf",
        "worktree_path": str(tmp_project),
        "notes": "windows save",
    }, indent=2)
    target.write_bytes(payload_str.replace("\n", "\r\n").encode("utf-8"))

    result = read_role(tmp_project)
    assert result is not None, "CRLF marker was not parsed"
    assert result["role"] == "secondary"


# ---------------------------------------------------------------------------
# Boundary probe: Non-ASCII in `notes`
# ---------------------------------------------------------------------------


def test_round_trip_non_ascii_notes(tmp_project):
    """Umlauts + em-dash in notes survive the round-trip as UTF-8."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="sess-ü",
        worktree_path=str(tmp_project),
        notes="München — primärer Worktree (ä ö ü)",
    )
    result = read_role(tmp_project)
    assert result is not None
    assert result["notes"] == "München — primärer Worktree (ä ö ü)"


# ---------------------------------------------------------------------------
# Boundary probe: empty notes
# ---------------------------------------------------------------------------


def test_empty_notes_handled(tmp_project):
    """Empty string notes do not crash and survive the round-trip."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="sess-empty",
        worktree_path=str(tmp_project),
        notes="",
    )
    result = read_role(tmp_project)
    assert result is not None
    assert result["notes"] == ""


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_write_role_idempotent_same_role_same_path(tmp_project):
    """Re-writing the same role + worktree_path leaves the file untouched."""
    first = write_role(
        tmp_project,
        role="canonical",
        session_id="sess-1",
        worktree_path=str(tmp_project),
        notes="first",
    )
    target = tmp_project / MARKER_RELPATH
    mtime_first = target.stat().st_mtime
    bytes_first = target.read_bytes()

    second = write_role(
        tmp_project,
        role="canonical",
        session_id="sess-2",  # different session — must NOT overwrite set_at
        worktree_path=str(tmp_project),
        notes="ignored on idempotent path",
    )

    assert target.stat().st_mtime == mtime_first
    assert target.read_bytes() == bytes_first
    assert second["set_at"] == first["set_at"]
    assert second["set_by_session_id"] == first["set_by_session_id"]


def test_write_role_overwrites_when_role_changes(tmp_project):
    """Switching role canonical → secondary writes a fresh marker."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    write_role(
        tmp_project,
        role="secondary",
        session_id="sess-2",
        worktree_path=str(tmp_project),
    )
    result = read_role(tmp_project)
    assert result is not None
    assert result["role"] == "secondary"
    assert result["set_by_session_id"] == "sess-2"


def test_write_role_rejects_invalid_role(tmp_project):
    """Unknown role raises ValueError before touching the disk."""
    with pytest.raises(ValueError):
        write_role(
            tmp_project,
            role="leader",  # invalid
            session_id="sess-1",
            worktree_path=str(tmp_project),
        )
    assert not (tmp_project / MARKER_RELPATH).exists()


# ---------------------------------------------------------------------------
# Malformed-file recovery
# ---------------------------------------------------------------------------


def test_read_role_returns_none_when_marker_missing(tmp_project):
    assert read_role(tmp_project) is None


def test_read_role_returns_none_on_garbage(tmp_project):
    """Junk bytes in the marker file return None (default permissive)."""
    target = tmp_project / MARKER_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not json at all", encoding="utf-8")
    assert read_role(tmp_project) is None


def test_read_role_returns_none_on_unknown_role(tmp_project):
    """A marker with a role outside VALID_ROLES is treated as missing."""
    target = tmp_project / MARKER_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"role": "leader", "set_at": "x"}), encoding="utf-8"
    )
    assert read_role(tmp_project) is None


# ---------------------------------------------------------------------------
# detect_parallel_sessions
# ---------------------------------------------------------------------------


def _make_worktree(project_root: Path, slug: str, role: str, session_id: str) -> Path:
    """Create a fake `.worktrees/<slug>/` with a session-role marker."""
    wt = project_root / ".worktrees" / slug
    (wt / ".shipwright").mkdir(parents=True, exist_ok=True)
    write_role(wt, role=role, session_id=session_id, worktree_path=str(wt))
    return wt


def test_detect_parallel_sessions_main_only(tmp_project):
    """One canonical marker in the main repo → list of length 1."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="main",
        worktree_path=str(tmp_project),
    )
    found = detect_parallel_sessions(tmp_project)
    assert len(found) == 1
    assert found[0]["role"] == "canonical"
    assert "_marker_path" in found[0]


def test_detect_parallel_sessions_main_plus_worktree(tmp_project):
    """Canonical in main repo + secondary in `.worktrees/<slug>/` → two markers."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="main",
        worktree_path=str(tmp_project),
    )
    _make_worktree(tmp_project, "feature-x", "secondary", "wt-1")

    found = detect_parallel_sessions(tmp_project)
    assert len(found) == 2
    roles = {entry["role"] for entry in found}
    assert roles == {"canonical", "secondary"}


def test_detect_parallel_sessions_skips_worktrees_without_marker(tmp_project):
    """Worktree dir without a marker is silently skipped."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="main",
        worktree_path=str(tmp_project),
    )
    # Create an empty worktree dir.
    (tmp_project / ".worktrees" / "no-marker").mkdir(parents=True)

    found = detect_parallel_sessions(tmp_project)
    assert len(found) == 1
    assert found[0]["role"] == "canonical"


def test_detect_parallel_sessions_no_markers_anywhere(tmp_project):
    assert detect_parallel_sessions(tmp_project) == []


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_roles_contains_both_expected_values():
    assert set(VALID_ROLES) == {"canonical", "secondary"}


def test_marker_relpath_under_dotshipwright():
    assert MARKER_RELPATH.parts == (".shipwright", "iterate_session_role.json")
