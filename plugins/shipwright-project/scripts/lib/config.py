"""Session state management for /shipwright-project.

Adapted from deep-project. Files are checkpoints, JSON is minimal.

The session.json stores only:
- input_file_hash: Detect if requirements changed
- session_created_at: When session started

Everything else is derived from file existence:
- Interview complete: shipwright_project_interview.md exists
- Manifest created: project-manifest.md exists
- Directories created: NN-name/ directories exist
- Specs written: spec.md in each directory
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class SessionFilename(StrEnum):
    """Session file names for shipwright-project."""

    STATE = "shipwright_project_session.json"
    INTERVIEW = "shipwright_project_interview.md"
    MANIFEST = "project-manifest.md"


def _atomic_write(path: Path, content: str) -> None:
    """Write file atomically using temp file + rename.

    Cross-platform: no fcntl dependency (Windows compatible).
    """
    path = Path(os.fspath(path))
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        # On Windows, target must not exist for rename
        if os.name == "nt" and path.exists():
            path.unlink()
        os.rename(tmp_path, path)
    except Exception:
        os.close(fd) if not os.path.exists(tmp_path) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of file content."""
    path = Path(os.fspath(file_path))
    content = path.read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def session_state_path(planning_dir: str | Path) -> Path:
    """Get path to session state file."""
    return Path(os.fspath(planning_dir)) / SessionFilename.STATE


def session_state_exists(planning_dir: str | Path) -> bool:
    """Check if session state exists."""
    return session_state_path(planning_dir).exists()


def load_session_state(planning_dir: str | Path) -> dict[str, Any] | None:
    """Load session state, or None if not exists."""
    path = session_state_path(planning_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Corrupted session state at {path}: {e}")


def save_session_state(planning_dir: str | Path, state: dict[str, Any]) -> None:
    """Save session state atomically."""
    path = session_state_path(planning_dir)
    _atomic_write(path, json.dumps(state, indent=2))


def create_initial_session_state(initial_file: str | Path) -> dict[str, Any]:
    """Create initial session state with file hash."""
    return {
        "input_file_hash": compute_file_hash(initial_file),
        "session_created_at": datetime.now(timezone.utc).isoformat(),
    }


def check_input_file_changed(
    planning_dir: str | Path, initial_file: str | Path
) -> bool | None:
    """Check if input file has changed since session started.

    Returns True if changed, False if unchanged, None if no state exists.
    """
    state = load_session_state(planning_dir)
    if state is None:
        return None
    current_hash = compute_file_hash(initial_file)
    return current_hash != state.get("input_file_hash")
