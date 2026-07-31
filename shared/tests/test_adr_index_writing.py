"""Writing the ADR index — atomicity, locking, and what may land in the folder.

The renderer's rules live in ``test_adr_index.py``; the call sites that drive it
live in ``test_adr_index_producers.py``. This file covers ``rebuild_adr_index``
itself: that a missing folder is untouched, that the write is atomic and LF-exact,
and that nothing transient is left in a TRACKED folder F6 stages wholesale.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lib import atomic_write
from lib.adr_index import (
    ADR_INDEX_FILENAME,
    ADR_SPEC_FOLDER,
    REGEN_COMMAND,
    REGEN_TOOL_RELPATH,
    rebuild_adr_index,
    regen_command_resolved,
    render_adr_index,
)


def _folder(root: Path) -> Path:
    folder = root / ADR_SPEC_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _adr(root: Path, name: str, body: str) -> Path:
    path = _folder(root) / name
    path.write_text(body, encoding="utf-8")
    return path


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _regen_script() -> Path:
    """The regen tool, resolved against THIS repo's shared root.

    `REGEN_COMMAND` keeps `{shared_root}` unresolved on purpose — it is rendered
    into the committed INDEX.md of adopted repos, which have no `shared/`.
    """
    return _REPO_ROOT / "shared" / REGEN_TOOL_RELPATH


def test_missing_folder_is_a_strict_noop(tmp_path):
    """Ledger 13 / R4 — never mint an ADR folder or an empty index.

    Refreshing on every release pass must not create a new committed artifact
    in a repo that never adopted ADRs.
    """
    assert rebuild_adr_index(tmp_path) is None
    assert not (tmp_path / ADR_SPEC_FOLDER).exists()


def test_rebuild_leaves_nothing_but_the_index_in_the_adr_folder(tmp_path):
    """The ADR folder is TRACKED and F6 stages it as a folder.

    `file_lock` leaves its lock file on disk, and the canonical gitignore
    whitelists `/.shipwright/planning/` wholesale — so a lock written beside
    INDEX.md would be untracked-and-not-ignored in an adopted repo and F6's
    folder-level `git add` would commit it. Nothing transient may land here.
    """
    _adr(tmp_path, "095-x.md", "# ADR-095: X\n")
    rebuild_adr_index(tmp_path)
    names = sorted(p.name for p in _folder(tmp_path).iterdir())
    assert names == ["095-x.md", ADR_INDEX_FILENAME], f"stray file in the ADR folder: {names}"
    assert (tmp_path / ".shipwright" / "locks" / "adr_index.lock").exists()


def test_rebuild_writes_the_render(tmp_path):
    _adr(tmp_path, "083-x.md", "# ADR-083: X\n")
    path = rebuild_adr_index(tmp_path)
    assert path is not None
    assert path.read_text(encoding="utf-8") == render_adr_index(_folder(tmp_path))


def test_failed_write_leaves_the_previous_index_intact(tmp_path, monkeypatch):
    """Ledger 21 / R3 — atomic replace, so no partial INDEX.md survives.

    Patches the rename inside `lib.atomic_write` (by MODULE OBJECT per ADR-045),
    which is where the publish actually happens now that the writer routes
    through the shared `durable_atomic_write` primitive.
    """
    _adr(tmp_path, "084-x.md", "# ADR-084: X\n")
    good = rebuild_adr_index(tmp_path).read_text(encoding="utf-8")
    _adr(tmp_path, "085-y.md", "# ADR-085: Y\n")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_write.os, "replace", boom)
    with pytest.raises(OSError):
        rebuild_adr_index(tmp_path)
    folder = _folder(tmp_path)
    assert (folder / ADR_INDEX_FILENAME).read_text(encoding="utf-8") == good
    assert not list(folder.glob("*.tmp*")), "temp file leaked"


def test_render_is_written_verbatim_lf_even_on_windows(tmp_path):
    """The LF contract must hold in BYTES, not just through read_text().

    `Path.write_text` translates to os.linesep, so on Windows the committed
    artifact would be CRLF while the render is LF — invisible to every test that
    compares via `read_text` (which un-translates), and whole-file churn in a
    consumer repo whose autocrlf is off.
    """
    _adr(tmp_path, "093-x.md", "# ADR-093: X\n")
    raw = rebuild_adr_index(tmp_path).read_bytes()
    assert b"\r\n" not in raw


# --------------------------------------------------------------- the CLI (R1)


def test_regen_command_names_a_script_that_exists():
    """Ledger 23 / R1 — the command we tell people to run must be real.

    Pointing them at `aggregate_decisions.py` instead would fold and DELETE
    their decision-drops as a side effect of refreshing an index.
    """
    assert "aggregate_decisions" not in REGEN_COMMAND
    assert _regen_script().is_file(), f"{REGEN_COMMAND} names a script that is missing"


def test_regen_command_is_layout_independent():
    """Ledger 28 — it is rendered into the committed index of ADOPTED repos.

    Those have no `shared/` directory, so a monorepo-relative path baked into
    that header would be unrunnable in every repo it actually ships to. The
    `{shared_root}` placeholder is the convention every other iterate-skill
    command already uses.
    """
    assert "{shared_root}" in REGEN_COMMAND
    assert not REGEN_COMMAND.startswith("uv run shared/")
    resolved = regen_command_resolved()
    assert "{shared_root}" not in resolved
    assert Path(resolved.split("uv run ", 1)[1].split(" ", 1)[0]).is_file()


def test_cli_regenerates_the_index(tmp_path):
    """Ledger 22 / R1."""
    _adr(tmp_path, "090-x.md", "# ADR-090: X\n")
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    index = _folder(tmp_path) / ADR_INDEX_FILENAME
    assert "- [ADR-090 — X]" in index.read_text(encoding="utf-8")


def test_cli_on_a_repo_without_adrs_creates_nothing(tmp_path):
    """R4 at the CLI boundary."""
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / ADR_SPEC_FOLDER).exists()
