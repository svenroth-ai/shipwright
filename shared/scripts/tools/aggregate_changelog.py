"""Release-time aggregator for ``CHANGELOG-unreleased.d/``.

Called from ``/shipwright-changelog`` at release time. Reads the Keep-a-
Changelog drop files written by iterate F4, groups them into a versioned
Markdown section, inserts the section at the structural point in
``CHANGELOG.md`` (above the first prior version heading, not blindly at
the top — which would corrupt the standard ``# Changelog`` title), and
deletes only the drop files that were actually included in the snapshot.

Concurrency model:

* The aggregator holds a lock on ``CHANGELOG.md.lock`` for the entire
  read-render-write-cleanup transaction. This matches the existing
  ``append_changelog_entry.py`` locking so a legacy writer and the
  aggregator can never interleave on the same repo.
* A new iterate that writes a drop file between the aggregator's
  snapshot phase and its cleanup phase IS preserved (selective delete
  only touches the snapshot set). That bullet simply lands in the next
  release.

Legacy coexistence:

* ``CHANGELOG.md`` may still carry pre-refactor ``## [Unreleased]``
  bullets. We do NOT parse / mutate those — brittle. Instead we emit a
  release-time WARNING to stderr so the operator decides manually.
* The aggregator does not touch ``[Unreleased]``; it inserts the new
  version section immediately above whatever currently sits at the top
  versioned heading.

CLI:

    uv run shared/scripts/tools/aggregate_changelog.py \\
        --project-root . \\
        --version 0.3.0 \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.file_lock import LockTimeout, file_lock  # noqa: E402
from tools.write_changelog_drop import (  # noqa: E402
    drop_dir,
)


CHANGELOG_NAME = "CHANGELOG.md"
CHANGELOG_LOCK_NAME = "CHANGELOG.md.lock"

# Max size we'll read from any single drop file — matches the iterate
# entry-file bound so pathological content can't wedge the aggregator.
MAX_DROP_FILE_BYTES = 64 * 1024

# Category render order per Keep-a-Changelog spec.
_CATEGORY_ORDER: tuple[str, ...] = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)


class AggregatorError(RuntimeError):
    """Raised when aggregation cannot proceed (missing file, I/O, lock)."""


# Git-Bash on Windows auto-converts a leading-slash argv argument into
# the Bash install root prefix (e.g. ``--bullet /shipwright-adopt`` becomes
# ``C:/Program Files/Git/shipwright-adopt`` before the receiving Python
# script ever sees it). Drop files written via that mangled argv carry
# the prefix verbatim and would publish into CHANGELOG.md unless caught
# at release time. The pattern matches the directory-component path that
# Git-for-Windows installs to by default; portable Git installs that
# write a different prefix are not covered (would require detecting the
# active MSYS root, which we don't try here).
_MSYS_MANGLE_RE = re.compile(
    r"^C:/Program Files/Git/[A-Za-z0-9._-]+(?=[\s/]|$)"
)


def _detect_msys_mangled_bullets(
    by_category: dict[str, list[tuple[str, str]]],
    project_root: Path,
) -> list[tuple[str, str, str]]:
    """Return ``(category, source_relpath, bullet_text)`` for every drop
    file whose bullet text starts with the Git-Bash mangle prefix.

    Reports only the prefix-on-line-one case — that is the documented
    production failure mode (one-bullet-per-drop file, content =
    bullet text). Mid-text occurrences of ``C:/Program Files/Git/`` are
    left alone since they could legitimately reference a real path
    under the Git install dir.
    """
    findings: list[tuple[str, str, str]] = []
    drops_root = drop_dir(project_root)
    for category, bullets in by_category.items():
        for stem, content in bullets:
            first_line = content.lstrip().splitlines()[0] if content.strip() else ""
            if _MSYS_MANGLE_RE.match(first_line):
                drop_relpath = (
                    drops_root / category / f"{stem}.md"
                ).relative_to(project_root)
                findings.append(
                    (category, str(drop_relpath), first_line)
                )
    return findings


def _snapshot_drop_files(project_root: Path) -> tuple[dict[str, list[tuple[str, str]]], list[Path]]:
    """Read all drop files under ``CHANGELOG-unreleased.d/<category>/``.

    Returns ``(by_category, processed_files)``. ``processed_files`` is the
    exact list of paths that ended up in ``by_category`` — only these
    get deleted in the cleanup phase, so a drop file written between the
    snapshot and the cleanup survives into the next release.

    Filenames sort as ``<run_id>_<counter>.md`` lexicographically, which
    preserves insertion order within a single run_id.
    """
    base = drop_dir(project_root)
    by_category: dict[str, list[tuple[str, str]]] = {}
    processed: list[Path] = []
    if not base.is_dir():
        return by_category, processed

    for category in _CATEGORY_ORDER:
        cat_dir = base / category
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.iterdir()):
            if not path.is_file() or path.is_symlink():
                continue
            if not path.name.endswith(".md"):
                continue
            if path.name.startswith("_") or path.name == ".gitkeep":
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > MAX_DROP_FILE_BYTES:
                print(
                    f"[aggregate_changelog] skip oversized drop file {path}: {size} bytes",
                    file=sys.stderr,
                )
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                print(
                    f"[aggregate_changelog] skip unreadable drop {path}: {exc}",
                    file=sys.stderr,
                )
                continue
            if not content:
                continue
            by_category.setdefault(category, []).append((path.stem, content))
            processed.append(path)

    return by_category, processed


def _render_versioned_section(
    version: str,
    release_date: str,
    by_category: dict[str, list[tuple[str, str]]],
) -> str:
    """Render a Keep-a-Changelog versioned section from a category map."""
    lines: list[str] = [f"## [{version}] - {release_date}", ""]
    any_content = False
    for category in _CATEGORY_ORDER:
        bullets = by_category.get(category) or []
        if not bullets:
            continue
        any_content = True
        lines.append(f"### {category}")
        lines.append("")
        for _stem, content in bullets:
            # Each drop file holds raw bullet text without the leading "- ".
            # If a drop accidentally starts with "- " already, don't double it.
            stripped = content.lstrip()
            prefix = "" if stripped.startswith("- ") else "- "
            lines.append(f"{prefix}{stripped}")
        lines.append("")
    if not any_content:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def _find_structural_insertion_line(lines: list[str]) -> int:
    """Return the line index where a new ``## [version]`` section should go.

    Keep-a-Changelog convention: ``## [Unreleased]`` stays at the top; new
    released versions go BELOW it in descending chronological order.

    Preference order:
      1. Immediately above the first existing ``## [vX.Y.Z]`` (versioned)
         heading — ``## [Unreleased]`` is skipped so it stays on top
         of the file as the spec dictates.
      2. If ``## [Unreleased]`` exists but no prior versioned section does,
         place the new section directly AFTER the [Unreleased] block
         (next blank after the last [Unreleased] bullet).
      3. Otherwise, after the standard Keep-a-Changelog header block —
         the line right after the first blank-line paragraph that follows
         the ``# Changelog`` title.
      4. End of file if none of the above match.
    """
    # ``## [ANYTHING-OTHER-THAN-Unreleased])``
    version_pattern = re.compile(r"^##\s+\[(?!Unreleased\])")
    unreleased_pattern = re.compile(r"^##\s+\[Unreleased\]")
    any_section_pattern = re.compile(r"^##\s+\[")

    # 1: first versioned (non-Unreleased) heading.
    for i, line in enumerate(lines):
        if version_pattern.match(line):
            return i

    # 2: only [Unreleased] exists — place after its block ends.
    for i, line in enumerate(lines):
        if unreleased_pattern.match(line):
            j = len(lines)
            for k in range(i + 1, len(lines)):
                if any_section_pattern.match(lines[k]):
                    j = k
                    break
            # Back up over trailing blank lines so we don't stack blanks.
            while j - 1 > i and lines[j - 1].strip() == "":
                j -= 1
            return j

    # 3: after header paragraph. Find first blank line after line 0.
    for i in range(1, len(lines)):
        if lines[i].strip() == "":
            # Walk forward over contiguous blanks to the next non-blank.
            j = i
            while j + 1 < len(lines) and lines[j + 1].strip() == "":
                j += 1
            return j + 1

    # 4: end of file.
    return len(lines)


def _insert_section(changelog_text: str, new_section: str) -> str:
    """Insert ``new_section`` at the structural point in ``changelog_text``."""
    # Preserve the line-ending-with-newline convention by splitting via
    # splitlines(keepends=True).
    lines = changelog_text.splitlines(keepends=True)
    idx = _find_structural_insertion_line(
        [line.rstrip("\n") for line in lines]
    )

    separator = "" if idx < len(lines) else "\n"
    new_block = new_section
    if not new_block.endswith("\n"):
        new_block += "\n"
    new_block += "\n"  # blank line separator before the following content

    before = "".join(lines[:idx])
    after = "".join(lines[idx:])
    # Guard: don't emit three consecutive blank lines.
    if before.endswith("\n\n") and new_block.startswith("\n"):
        new_block = new_block.lstrip("\n")
    return before + new_block + separator + after


def _atomic_write(path: Path, content: str) -> None:
    """Durable atomic write (tmp + fsync + os.replace) via the shared
    :func:`durable_atomic_write`."""
    durable_atomic_write(path, content)


def _warn_if_legacy_unreleased_has_bullets(changelog_text: str) -> int:
    """Return the count of bullets under legacy ``## [Unreleased]``.

    When non-zero, the aggregator prints a prominent warning to stderr so
    the operator can decide whether to manually fold those bullets into
    the new version or accept the temporary split-brain.
    """
    match = re.search(
        r"^##\s+\[Unreleased\][^\n]*\n(.*?)(?=\n##\s+\[|\Z)",
        changelog_text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if not match:
        return 0
    section = match.group(1)
    return len(re.findall(r"^\s*-\s+", section, flags=re.MULTILINE))


def aggregate(
    project_root: Path,
    version: str,
    *,
    release_date: str | None = None,
    dry_run: bool = False,
    strict: bool = False,
    lock_timeout_seconds: float = 10.0,
) -> dict[str, object]:
    """Run one aggregation pass.

    Returns a result dict with ``version``, ``release_date``,
    ``section_written`` (the rendered Markdown — empty when no drops
    found), ``processed_files`` (relative paths), and
    ``legacy_unreleased_bullets`` (count, for operator awareness).

    ``strict``: when True, any MSYS path-mangling finding (Git-Bash on
    Windows converted a leading-slash bullet into ``C:/Program Files/
    Git/...``) raises ``AggregatorError`` instead of just warning. Use
    in release CI to fail-fast.
    """
    project_root = project_root.resolve()
    release_date = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    changelog_path = project_root / CHANGELOG_NAME

    lock_path = project_root / CHANGELOG_LOCK_NAME
    with file_lock(lock_path, timeout_seconds=lock_timeout_seconds):
        by_category, processed = _snapshot_drop_files(project_root)

        # MSYS path-mangling linter — runs BEFORE rendering so strict
        # mode aborts without a half-written CHANGELOG.md.
        msys_findings = _detect_msys_mangled_bullets(by_category, project_root)
        for category, relpath, first_line in msys_findings:
            print(
                f"[aggregate_changelog] WARNING: MSYS/Git-Bash path "
                f"mangling detected in {relpath} ({category}): "
                f"bullet starts with {first_line!r}. The leading "
                f"'C:/Program Files/Git/' prefix is almost certainly "
                f"a Git-Bash auto-conversion of a leading slash in the "
                f"original --bullet argv. Edit the drop file and strip "
                f"the prefix before publishing.",
                file=sys.stderr,
            )
        if msys_findings and strict:
            raise AggregatorError(
                f"refusing to aggregate: {len(msys_findings)} drop file(s) "
                f"contain MSYS/Git-Bash path-mangling; strict mode is on"
            )

        section = _render_versioned_section(version, release_date, by_category)

        if not section:
            return {
                "version": version,
                "release_date": release_date,
                "section_written": "",
                "processed_files": [],
                "legacy_unreleased_bullets": 0,
                "msys_mangled_findings": [],
                "changelog_updated": False,
            }

        changelog_text = (
            changelog_path.read_text(encoding="utf-8")
            if changelog_path.exists()
            else "# Changelog\n\n"
        )
        legacy_bullets = _warn_if_legacy_unreleased_has_bullets(changelog_text)
        if legacy_bullets > 0:
            print(
                f"[aggregate_changelog] WARNING: CHANGELOG.md still contains "
                f"{legacy_bullets} bullet(s) under the legacy [Unreleased] "
                f"section. These are NOT included in version {version}. "
                f"Merge them manually or accept the split-brain.",
                file=sys.stderr,
            )

        new_text = _insert_section(changelog_text, section)

        if not dry_run:
            _atomic_write(changelog_path, new_text)
            for p in processed:
                try:
                    p.unlink()
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    print(
                        f"[aggregate_changelog] warn: could not unlink {p}: {exc}",
                        file=sys.stderr,
                    )

        return {
            "version": version,
            "release_date": release_date,
            "section_written": section,
            "processed_files": [
                str(p.relative_to(project_root)) for p in processed
            ],
            "legacy_unreleased_bullets": legacy_bullets,
            "msys_mangled_findings": [
                {"category": cat, "drop_file": rp, "first_line": fl}
                for cat, rp, fl in msys_findings
            ],
            "changelog_updated": not dry_run,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True, help="e.g. 0.3.0")
    parser.add_argument("--release-date", help="YYYY-MM-DD (default: today UTC)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render section and report would-be-deletions without modifying disk",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Treat MSYS/Git-Bash path-mangling findings as errors: refuse "
            "to aggregate (exit 1) instead of just warning. Recommended "
            "for release CI."
        ),
    )
    parser.add_argument("--lock-timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        result = aggregate(
            Path(args.project_root),
            args.version,
            release_date=args.release_date,
            dry_run=args.dry_run,
            strict=args.strict,
            lock_timeout_seconds=args.lock_timeout,
        )
    except LockTimeout as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except AggregatorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
