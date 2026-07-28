"""Shared setup for the release-aggregator re-run suites.

Split out so the converging-re-run tests and the refusal tests are separate
modules without either of them re-deriving what "the release state on disk"
means. Every assertion in both suites goes through :func:`changelog_text` and
:func:`drop_texts`, so a test can never assert something weaker than "what is
on disk" — the two things an interrupted release can destroy are the changelog
bytes and the pending drop set.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from tools.aggregate_changelog import CHANGELOG_NAME, aggregate
from tools.write_changelog_drop import drop_dir, write_changelog_drop


HEADER = (
    "# Changelog\n"
    "\n"
    "All notable changes to this project will be documented in this file.\n"
    "\n"
)

PRIOR_RELEASE = "## [0.2.0] - 2026-04-01\n\n### Added\n\n- old bullet\n"

DUPLICATE_SECTIONS = (
    "## [0.3.0] - 2026-04-23\n\n### Added\n\n- a\n\n"
    "## [0.3.0] - 2026-04-23\n\n### Added\n\n- b\n\n" + PRIOR_RELEASE
)


def seed(project: Path, body: str = PRIOR_RELEASE) -> None:
    """Write a Keep-a-Changelog skeleton with `body` below the header."""
    (project / CHANGELOG_NAME).write_text(HEADER + body, encoding="utf-8")


def seed_drops(project: Path, items: list[tuple[str, str, str]]) -> None:
    """`items` are ``(run_id, category, bullet)`` triples."""
    for run_id, category, bullet in items:
        write_changelog_drop(project, run_id, category, bullet)


def pending() -> list[tuple[str, str, str]]:
    """Three drops across two categories — the ordinary release shape."""
    return [
        ("iterate-2026-04-20-a", "Added", "first bullet"),
        ("iterate-2026-04-21-b", "Added", "second bullet"),
        ("iterate-2026-04-22-c", "Fixed", "third bullet"),
    ]


def changelog_text(project: Path) -> str:
    return (project / CHANGELOG_NAME).read_text(encoding="utf-8")


def drop_texts(project: Path) -> set[str]:
    base = drop_dir(project)
    if not base.is_dir():
        return set()
    return {p.read_text(encoding="utf-8").strip() for p in base.rglob("*.md")}


def interrupt_after_write(project: Path, version: str, release_date: str) -> None:
    """Run one aggregation, then restore the drop files.

    Reproduces the real failure window: ``_atomic_write`` succeeded and the
    process died before the unlink loop ran, so ``CHANGELOG.md`` holds the
    section AND every drop is still pending.
    """
    backup = project / "_drops_backup"
    shutil.copytree(drop_dir(project), backup)
    aggregate(project, version, release_date=release_date)
    shutil.rmtree(drop_dir(project))
    shutil.copytree(backup, drop_dir(project))
    shutil.rmtree(backup)
