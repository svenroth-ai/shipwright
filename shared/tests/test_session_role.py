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
import subprocess
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
# E HIGH-2 — worktree-blindness regression test
# ---------------------------------------------------------------------------


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_detect_from_worktree_cwd_sees_main_and_worktree(tmp_project):
    """Calling detect_parallel_sessions from a worktree path must see BOTH
    markers (main repo + worktree).

    This is the dog-food self-failure C admitted to in its Confidence
    Calibration "Edge cases NOT probed" list — the original implementation
    only scanned the cwd's own `.worktrees/` and missed the main repo
    when invoked from a worktree directory.
    """
    # Initialize a real git repo + commit an initial file so worktree-add works.
    subprocess.run(["git", "init", "-q", str(tmp_project)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_project), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_project), "config", "user.name", "Test"],
        check=True,
    )
    (tmp_project / "README.md").write_text("seed", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_project), "add", "README.md"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_project), "commit", "-q", "-m", "seed"],
        check=True,
    )

    # Write canonical marker in the main repo.
    write_role(
        tmp_project,
        role="canonical",
        session_id="main-sess",
        worktree_path=str(tmp_project),
    )

    # Add a real git worktree under .worktrees/feature-x and write a
    # secondary marker in it.
    wt_path = tmp_project / ".worktrees" / "feature-x"
    subprocess.run(
        [
            "git", "-C", str(tmp_project), "worktree", "add", "-b",
            "feature-x", str(wt_path),
        ],
        check=True,
    )
    write_role(
        wt_path,
        role="secondary",
        session_id="wt-sess",
        worktree_path=str(wt_path),
    )

    # The bug: invoking detect_parallel_sessions FROM the worktree path
    # should still see BOTH markers, because git-rev-parse can resolve the
    # canonical repo root via --git-common-dir.
    found = detect_parallel_sessions(wt_path)
    roles = {entry["role"] for entry in found}
    assert roles == {"canonical", "secondary"}, (
        f"Expected to see both markers from worktree cwd, got roles {roles!r} "
        f"(entries: {found})"
    )
    assert len(found) == 2


# ---------------------------------------------------------------------------
# E MEDIUM-C2 — race-safe tmp file naming
# ---------------------------------------------------------------------------


def test_write_role_uses_unique_tmp_name(tmp_project, monkeypatch):
    """write_role must use a unique tmp name per call so two near-concurrent
    writes don't clobber each other's tmp file.

    We can't easily simulate true concurrency in a unit test, but we can
    verify the pattern is race-safe by construction: capture the tmp paths
    that are created and assert they differ across two interleaved invocations.
    """
    import tempfile as _tempfile
    captured_names: list[str] = []
    real_named_tmp = _tempfile.NamedTemporaryFile

    def spy(*args, **kwargs):
        h = real_named_tmp(*args, **kwargs)
        captured_names.append(h.name)
        return h

    # Patch in the session_role module's tempfile reference.
    import lib.session_role as session_role_mod  # type: ignore
    monkeypatch.setattr(
        session_role_mod, "tempfile", _tempfile, raising=False
    )
    monkeypatch.setattr(
        session_role_mod.tempfile, "NamedTemporaryFile", spy
    )

    write_role(
        tmp_project, role="canonical",
        session_id="s1", worktree_path=str(tmp_project),
    )
    # Force a fresh write (different role triggers non-idempotent path).
    write_role(
        tmp_project, role="secondary",
        session_id="s2", worktree_path=str(tmp_project),
    )

    assert len(captured_names) == 2, (
        f"Expected 2 NamedTemporaryFile calls, got {captured_names!r}"
    )
    assert captured_names[0] != captured_names[1], (
        f"Two writes produced the same tmp name: {captured_names!r}"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_roles_contains_both_expected_values():
    assert set(VALID_ROLES) == {"canonical", "secondary"}


def test_marker_relpath_under_dotshipwright():
    assert MARKER_RELPATH.parts == (".shipwright", "iterate_session_role.json")
