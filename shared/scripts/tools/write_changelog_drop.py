"""Write one changelog entry to ``CHANGELOG-unreleased.d/<category>/``.

Replaces the legacy append-to-``CHANGELOG.md[Unreleased]`` pattern for
iterate F4. Each finalize writes one small Markdown file per bullet;
``/shipwright-changelog`` aggregates them at release time. The file-per-
bullet layout eliminates the append conflict on ``[Unreleased]`` that
made two parallel iterates unsafe.

Filename: ``<run_id_sanitized>_<NNN>.md`` where ``NNN`` is the smallest
unused zero-padded counter in the target category directory. We use
exclusive ``O_EXCL`` create so concurrent callers that pick the same
counter don't clobber each other — the loser retries with the next.

Contents: the raw bullet text (no Keep-a-Changelog headings, no ``- ``
prefix — that's added by the aggregator so the release section stays
consistent).

CLI:

    uv run shared/scripts/tools/write_changelog_drop.py \\
        --project-root . \\
        --run-id iterate-2026-04-23-feat-x \\
        --category Added \\
        --bullet "New parallel-iterate convention ..."

Caveat — Git-Bash on Windows mangles leading-slash arguments:
    Calling this script with ``--bullet "/shipwright-adopt now scaffolds ..."``
    from Git-Bash on Windows produces a drop file whose first line is
    ``C:/Program Files/Git/shipwright-adopt now scaffolds ...`` because
    the MSYS layer auto-converts the leading ``/`` into the Bash install
    root path BEFORE Python's argv is populated. This script emits a
    stderr WARN on detection but does NOT auto-rewrite — by the time
    we see the argv, the user's intent is unrecoverable (a literal
    reference to a path under Git's install dir would be a false
    positive). The release-time linter in ``aggregate_changelog.py``
    catches the same pattern; pass ``--strict`` to that script in CI to
    fail-fast.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
from pathlib import Path


_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import sanitize_run_id_for_filename  # noqa: E402


DROP_DIRNAME = "CHANGELOG-unreleased.d"

# Must stay in sync with append_changelog_entry.py's KEEP_A_CHANGELOG_CATEGORIES
# since both write the same conceptual bullets into different storage shapes.
ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
)

# Upper bound on counter loops — realistic max entries per iterate per category
# is one-digit; 1000 gives 3-digit filenames room to breathe without risking
# an infinite loop if the filesystem reports stale metadata.
_MAX_COUNTER = 1000


class ChangelogDropError(RuntimeError):
    """Raised when a bullet cannot be written (bad category, bad path, I/O)."""


# Mirror of aggregate_changelog._MSYS_MANGLE_RE. Kept as a duplicate to
# avoid a write-side import of the aggregator (which would create a
# circular module-load shape — aggregator imports drop_dir from here at
# import time).
_MSYS_MANGLE_RE = re.compile(
    r"^C:/Program Files/Git/[A-Za-z0-9._-]+(?=[\s/]|$)"
)


def _warn_if_msys_mangled(bullet: str, run_id: str, category: str) -> None:
    """Emit a stderr WARN when ``bullet`` looks like a Git-Bash mangle.

    Does NOT raise — by the time we see the argv, the user's intent is
    not reliably recoverable. Auto-rewriting risks false positives on
    legitimate paths under Git's install dir.
    """
    first_line = bullet.lstrip().splitlines()[0] if bullet.strip() else ""
    if not _MSYS_MANGLE_RE.match(first_line):
        return
    print(
        f"[write_changelog_drop] WARNING: bullet for run_id={run_id!r} "
        f"category={category!r} starts with {first_line!r} — looks like "
        f"Git-Bash on Windows auto-converted a leading slash in your "
        f"--bullet argv into 'C:/Program Files/Git/'. The drop file is "
        f"being written verbatim so you can inspect it; consider editing "
        f"the file or re-running with the bullet quoted differently "
        f"(e.g. prefix with a backslash or use '--bullet=...' instead "
        f"of '--bullet ...'). aggregate_changelog.py --strict will "
        f"refuse to publish it.",
        file=sys.stderr,
    )


def drop_dir(project_root: Path) -> Path:
    return project_root / DROP_DIRNAME


def category_dir(project_root: Path, category: str) -> Path:
    if category not in ALLOWED_CATEGORIES:
        raise ChangelogDropError(
            f"unknown category {category!r}. "
            f"Allowed: {sorted(ALLOWED_CATEGORIES)}"
        )
    return drop_dir(project_root) / category


def _next_counter_path(project_root: Path, category: str, run_id: str) -> Path:
    """Pick the smallest unused ``<run_id>_NNN.md`` path in ``category_dir``.

    Race-safe: the caller must open this path with ``O_EXCL``. If the open
    fails with ``FileExistsError``, the caller is expected to re-call this
    function to get the next free counter.
    """
    cat_dir = category_dir(project_root, category)
    cat_dir.mkdir(parents=True, exist_ok=True)
    safe_run_id = sanitize_run_id_for_filename(run_id)
    for counter in range(1, _MAX_COUNTER):
        candidate = cat_dir / f"{safe_run_id}_{counter:03d}.md"
        if not candidate.exists():
            return candidate
    raise ChangelogDropError(
        f"too many drops for run_id={run_id} in category={category} "
        f"(counter overflow at {_MAX_COUNTER})"
    )


def _find_existing_drop(project_root: Path, category: str, run_id: str, content: str) -> Path | None:
    """Return an existing ``<run_id>_NNN.md`` drop in ``category`` whose bytes
    equal ``content``, else ``None``.

    Makes re-invocation idempotent per ``(run_id, category, bullet)`` so a
    whole-bundle retry after a partial finalize failure does NOT duplicate the
    changelog bullet (iterate-2026-07-15-finalize-bundle). A DIFFERENT bullet in
    the same run still gets its own counter — multi-bullet-per-run is preserved.
    Compares raw bytes (the write path is binary, ``\\n``-only) so the check is
    newline-exact. First-run output is byte-identical to the pre-idempotency tool.
    """
    cat_dir = category_dir(project_root, category)
    if not cat_dir.is_dir():
        return None
    safe_run_id = sanitize_run_id_for_filename(run_id)
    want = content.encode("utf-8")
    for existing in sorted(cat_dir.glob(f"{safe_run_id}_*.md")):
        try:
            if existing.read_bytes() == want:
                return existing
        except OSError:
            continue
    return None


def _within_drop_dir(project_root: Path, candidate: Path) -> bool:
    """Defense-in-depth: the final write path must resolve under drop_dir."""
    base = drop_dir(project_root).resolve()
    try:
        candidate_resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return False
    try:
        candidate_resolved.relative_to(base)
    except ValueError:
        return False
    return True


def _atomic_exclusive_write(target: Path, content: str) -> None:
    """Create ``target`` exclusively and write ``content`` to it.

    Uses ``os.O_CREAT | os.O_EXCL`` so two callers racing for the same
    counter produce deterministic results: exactly one wins, the loser
    receives ``FileExistsError`` and the outer counter loop tries the next
    number. This is the only race-safe primitive on Windows — a
    ``tempfile + os.replace`` pattern leaks target-exists races because
    ``os.replace`` overwrites on POSIX and fails non-atomically on Windows
    when the destination is touched mid-rename.

    The bullet is small so a partial-write window is not operationally
    meaningful; the caller can fsync / flush the encompassing commit
    boundary if stronger durability is needed later.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY  # Windows: bypass newline rewriting at OS layer
    # 0o600 (owner-only): a local, non-secret changelog drop owned by the author.
    fd = os.open(target, flags, 0o600)
    try:
        # Normalize newlines ourselves so POSIX and Windows output match.
        with os.fdopen(fd, "wb", closefd=True) as fh:
            fh.write(content.encode("utf-8"))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(target)
        raise


def write_changelog_drop(
    project_root: Path,
    run_id: str,
    category: str,
    bullet: str,
) -> Path:
    """Write one changelog bullet to the drop directory.

    ``bullet`` is the raw bullet content WITHOUT the leading ``- `` marker.
    The aggregator adds the marker + Keep-a-Changelog category headings
    at release time.

    Returns the absolute path to the written file.
    """
    if category not in ALLOWED_CATEGORIES:
        raise ChangelogDropError(
            f"unknown category {category!r}. Allowed: {sorted(ALLOWED_CATEGORIES)}"
        )
    stripped = bullet.strip()
    if not stripped:
        raise ChangelogDropError("bullet is empty")

    _warn_if_msys_mangled(stripped, run_id, category)

    project_root = project_root.resolve()

    # Idempotency: a re-run with identical (run_id, category, bullet) returns the
    # existing drop instead of claiming a new counter (whole-bundle retry safety).
    existing = _find_existing_drop(project_root, category, run_id, stripped + "\n")
    if existing is not None:
        return existing

    for _ in range(_MAX_COUNTER):
        candidate = _next_counter_path(project_root, category, run_id)
        if not _within_drop_dir(project_root, candidate):
            raise ChangelogDropError(
                f"refusing to write outside drop directory: {candidate}"
            )
        try:
            _atomic_exclusive_write(candidate, stripped + "\n")
            return candidate
        except FileExistsError:
            # Another caller grabbed this counter — try the next one.
            continue
    raise ChangelogDropError(
        f"failed to claim a drop filename after {_MAX_COUNTER} attempts"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--category",
        required=True,
        choices=sorted(ALLOWED_CATEGORIES),
        help="Keep-a-Changelog section",
    )
    parser.add_argument(
        "--bullet",
        required=True,
        help="Raw bullet text (no leading '- ')",
    )
    args = parser.parse_args(argv)

    try:
        path = write_changelog_drop(
            Path(args.project_root),
            args.run_id,
            args.category,
            args.bullet,
        )
    except ChangelogDropError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(str(path.relative_to(Path(args.project_root).resolve())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
