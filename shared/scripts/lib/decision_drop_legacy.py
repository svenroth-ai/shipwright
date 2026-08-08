"""Legacy-drop quarantine for the decision-drops tracking flip.

doubt-reviewer HIGH #3 (iterate-2026-08-08-track-decision-drops): a project's
decision-drops directory going from gitignored to tracked exposes whatever
pre-tracking drops its main checkout already has on disk — never
gitleaks/prompt-scanned, because they predate this feature entirely. Left
alone, ``/shipwright-changelog`` Step 6's directory-level ``git add -A``
cannot tell those apart from a fresh drop and would silently commit them,
unscanned, into a public ``decision_log.md``.

A drop whose *file* predates :data:`LEGACY_CUTOFF_DATE` is therefore moved —
never deleted — into the gitignored :data:`LEGACY_QUARANTINE_DIRNAME` sibling
instead of being aggregated, out of ``-A``'s reach until an explicit, scanned
backfill moves it back. Freshness is read from the file's own filesystem
mtime, NOT its JSON ``date`` field: that field is a narrative authoring date
an operator may legitimately backdate for the rendered decision_log.md entry
(``write_decision_drop --date`` / ``test_authoring_date_preserved``), which is
orthogonal to whether the file itself has actually been scanned. A file
created today always gets today's mtime regardless of its ``date`` field; a
pre-tracking file already sitting on disk keeps its true original write time
until this quarantine (or a real git checkout) touches it. Used by
``tools/aggregate_decisions.py``; kept out of that module so its own growth
doesn't ratchet the bloat baseline.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

#: The date this run made decision-drops trackable. A drop file whose mtime
#: is strictly before this date is pre-tracking content that has never been
#: through a gitleaks/prompt-scan pass.
LEGACY_CUTOFF_DATE = "2026-08-08"

#: Under ``.shipwright/agent_docs/`` — a sibling of ``decision-drops/``,
#: gitignored so it can never reach a commit via any ``git add -A``.
LEGACY_QUARANTINE_DIRNAME = "decision-drops-legacy-pending-scan"

_CUTOFF = date.fromisoformat(LEGACY_CUTOFF_DATE)


def legacy_dir(project_root: Path) -> Path:
    """Resolve the quarantine directory under ``project_root``."""
    return Path(project_root) / ".shipwright" / "agent_docs" / LEGACY_QUARANTINE_DIRNAME


def is_legacy_drop(path: Path) -> bool:
    """True if *path*'s filesystem mtime predates :data:`LEGACY_CUTOFF_DATE`.
    Fails CLOSED: a stat error (e.g. a race with a concurrent delete) is
    treated as legacy, never the reverse."""
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return True
    return mtime < _CUTOFF


def partition_by_freshness(drops: list[Path]) -> tuple[list[Path], list[Path]]:
    """Split *drops* into ``(fresh, legacy)`` by each file's own mtime."""
    fresh: list[Path] = []
    legacy: list[Path] = []
    for p in drops:
        (legacy if is_legacy_drop(p) else fresh).append(p)
    return fresh, legacy


def format_quarantine_warning(names: list[str], *, dry_run: bool) -> str:
    """CLI warning line for ``aggregate_decisions.main`` — kept here so its
    own growth doesn't ratchet that module's bloat baseline."""
    verb = "would quarantine" if dry_run else "quarantined"
    return (
        f"WARNING: {verb} {len(names)} pre-tracking decision-drop(s) dated "
        f"before {LEGACY_CUTOFF_DATE} into {LEGACY_QUARANTINE_DIRNAME}/ (never "
        "gitleaks/prompt-scanned — review and reintroduce manually): "
        + ", ".join(names)
    )


def quarantine_legacy_drops(project_root: Path, legacy: list[Path]) -> tuple[list[str], list[str]]:
    """Move each of *legacy* into the quarantine dir. Returns ``(moved, errors)``
    — filenames actually moved, and ``"<name>: <error>"`` strings for any that
    could not be moved (left in place; caller surfaces both)."""
    if not legacy:
        return [], []
    qdir = legacy_dir(project_root)
    qdir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    errors: list[str] = []
    for p in legacy:
        try:
            shutil.move(str(p), str(qdir / p.name))
            moved.append(p.name)
        except OSError as exc:
            errors.append(f"{p.name}: could not quarantine (legacy): {exc}")
    return moved, errors
