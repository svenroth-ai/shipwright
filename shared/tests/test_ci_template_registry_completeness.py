"""Reverse-direction drift test for the CI template registry.

The existing forward test (``test_ci_workflow_convention.py``) pins:
*every value in ``TEMPLATE_BY_PROFILE`` must resolve to a file on disk.*

This test pins the reverse: *every ``ci-*.yml.template`` file in
``shared/templates/github-actions/`` MUST have a matching
``TEMPLATE_BY_PROFILE`` entry.*

Failure mode covered: orphan template files that ship in the repo but
are unreachable from the scaffolder because nobody wired them up in the
registry. This is the canonical pattern that landed two zero-caller
orphans (``ci-nextjs.yml.template`` + ``claude-review.yml.template``)
in iterate-2026-05-10-adopt-ci-scaffolders before they were detected.

The ``claude-review.yml.template`` is profile-agnostic by design and
lives outside ``ci-*`` namespace — it's bound to its own
``CLAUDE_REVIEW_TEMPLATE_PATH`` constant. ``security.yml.template`` is
similarly profile-agnostic. Both are excluded by the explicit
``ci-*.yml.template`` glob.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.ci_workflow import TEMPLATE_BY_PROFILE  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "shared" / "templates" / "github-actions"


def _registered_template_paths() -> set[str]:
    """Return registered ``ci-*.yml.template`` paths as normalized POSIX strings."""
    return {Path(p).as_posix() for p in TEMPLATE_BY_PROFILE.values()}


def _on_disk_ci_templates() -> list[Path]:
    """Return all ``ci-*.yml.template`` files on disk (sorted, no hidden files)."""
    return sorted(
        p for p in TEMPLATES_DIR.glob("ci-*.yml.template")
        if p.is_file() and not p.name.startswith(".")
    )


def test_every_ci_template_on_disk_has_registry_entry() -> None:
    """No orphan ``ci-*.yml.template`` files.

    If a template exists in ``shared/templates/github-actions/`` matching
    the ``ci-*.yml.template`` pattern, it MUST be registered in
    ``TEMPLATE_BY_PROFILE``. Otherwise the scaffolder is unable to reach
    it and the template is dead code.
    """
    registered = _registered_template_paths()
    orphans: list[str] = []

    for template_file in _on_disk_ci_templates():
        rel = template_file.relative_to(REPO_ROOT).as_posix()
        if rel not in registered:
            orphans.append(rel)

    assert not orphans, (
        f"Found {len(orphans)} orphan ci-*.yml.template file(s) with no "
        f"TEMPLATE_BY_PROFILE entry: {orphans}. "
        f"Either register the template in shared/scripts/lib/ci_workflow.py "
        f"or remove the file. Registered templates: {sorted(registered)}"
    )


def test_registry_glob_finds_at_least_one_template() -> None:
    """Smoke check: the glob actually matches files.

    If the directory is empty or the glob misses everything, the
    completeness test above would silently pass (vacuously true). This
    guards against that failure mode.
    """
    on_disk = _on_disk_ci_templates()
    assert on_disk, (
        f"No ci-*.yml.template files found under {TEMPLATES_DIR} — "
        f"the glob pattern or directory layout has drifted. The reverse "
        f"completeness check above would pass vacuously without this guard."
    )
