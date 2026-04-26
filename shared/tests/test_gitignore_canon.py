"""Layer 5: ``.gitignore`` canon test.

Per ``ARTIFACT_MIGRATIONS`` status, verify the root ``.gitignore``:

- ``in_progress`` → BOTH the legacy entry and ``.shipwright/`` must be
  present. Untracked files in either location stay safe.
- ``migrated``    → ``.shipwright/`` present; legacy entry **stays**
  (Gemini #2: removing it would expose accidentally-tracked files).
  We require a comment marker (``legacy path - do not remove``) on the
  entry so future readers know not to clean it up.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.artifact_migrations import ARTIFACT_MIGRATIONS


_REPO_ROOT = Path(__file__).resolve().parents[2]
_GITIGNORE = _REPO_ROOT / ".gitignore"
_SHIPWRIGHT_ENTRY = ".shipwright/"
_LEGACY_RETENTION_COMMENT_TOKEN = "legacy path"


@pytest.fixture(scope="module")
def gitignore_lines() -> list[str]:
    if not _GITIGNORE.exists():
        pytest.skip(f".gitignore not found at {_GITIGNORE}")
    return _GITIGNORE.read_text(encoding="utf-8").splitlines()


def _line_index_matching(lines: list[str], entry: str) -> int | None:
    """Return the first line index whose stripped content equals *entry*.

    Accepts a leading ``/`` since gitignore-anchored entries (``/foo/``)
    and unanchored entries (``foo/``) are both legitimate.
    """
    targets = {entry, "/" + entry.lstrip("/"), entry.lstrip("/")}
    for i, line in enumerate(lines):
        if line.split("#", 1)[0].strip() in targets:
            return i
    return None


def test_shipwright_dir_is_ignored(gitignore_lines):
    """``.shipwright/`` must always be in .gitignore (covers all migrations)."""
    assert _line_index_matching(gitignore_lines, _SHIPWRIGHT_ENTRY) is not None, (
        ".gitignore must contain `.shipwright/` entry"
    )


@pytest.mark.parametrize("migration", ARTIFACT_MIGRATIONS, ids=lambda m: m["name"])
def test_legacy_entry_present_during_in_progress(gitignore_lines, migration):
    """During migration, both legacy + canonical must be ignored."""
    if migration["status"] != "in_progress":
        pytest.skip(f"migration `{migration['name']}` is {migration['status']}")
    legacy_entry = migration["legacy_dirname"] + "/"
    assert _line_index_matching(gitignore_lines, legacy_entry) is not None, (
        f"During in_progress migration of `{migration['name']}`, .gitignore "
        f"must keep `{legacy_entry}` so untracked legacy files stay safe."
    )


@pytest.mark.parametrize("migration", ARTIFACT_MIGRATIONS, ids=lambda m: m["name"])
def test_legacy_entry_kept_with_comment_after_migration(gitignore_lines, migration):
    """Post-migration the legacy entry STAYS (Gemini #2) with a comment."""
    if migration["status"] != "migrated":
        pytest.skip(f"migration `{migration['name']}` is {migration['status']}")
    legacy_entry = migration["legacy_dirname"] + "/"
    idx = _line_index_matching(gitignore_lines, legacy_entry)
    assert idx is not None, (
        f"After migration of `{migration['name']}`, the legacy `{legacy_entry}` "
        f"entry MUST remain in .gitignore (do not remove — it protects "
        f"accidentally-tracked files in old projects)."
    )
    # The line itself, or one of the two surrounding lines, must contain
    # the retention-comment token.
    window = gitignore_lines[max(0, idx - 1): idx + 2]
    assert any(_LEGACY_RETENTION_COMMENT_TOKEN in line for line in window), (
        f"After migration of `{migration['name']}`, the legacy entry must "
        f"have a comment containing `{_LEGACY_RETENTION_COMMENT_TOKEN}` "
        f"nearby so future maintainers know not to remove it."
    )
