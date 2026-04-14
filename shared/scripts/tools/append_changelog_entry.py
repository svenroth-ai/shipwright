"""Append a bullet to ``CHANGELOG.md`` ``[Unreleased]`` under a category.

Iterate 12.0 (ADR-027) replaces free-text CHANGELOG edits with this
helper so every Canon C5 caller goes through the same deterministic
write path: acquire lock → read → parse ``[Unreleased]`` → find/create
``### <Category>`` → dedupe → append → atomic rename.

The categories are the Keep-a-Changelog standard set:
``Added``, ``Changed``, ``Fixed``, ``Removed``, ``Security``,
``Deprecated``. ``BREAKING CHANGE`` commits stay in their primary
category (Added or Changed) but the caller should prefix the bullet
text with ``**BREAKING:**``.

Usage:

    uv run shared/scripts/tools/append_changelog_entry.py \\
        --project-root . \\
        --category Added \\
        --entry "Iterate 12.0: modular verifier package (ADR-027)"

Flags:

- ``--dedup`` (default: on) — skip if the exact bullet already exists in
  the target category.
- ``--changelog-path`` — override the CHANGELOG.md location (default:
  ``<project_root>/CHANGELOG.md`` or ``<project_root>/../CHANGELOG.md``).

Exit codes:

- 0 — entry appended, or dedup hit (entry already present, nothing to do)
- 1 — lock timeout, I/O error, or unknown category
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

# Bootstrap: make lib.file_lock importable when this file is run
# directly via `uv run`.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402


KEEP_A_CHANGELOG_CATEGORIES = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)


def find_changelog(project_root: Path) -> Path:
    """Return the CHANGELOG.md that applies to ``project_root``.

    Prefers ``<project_root>/CHANGELOG.md``; falls back to the repo root
    one level up (monorepo layout). If neither exists, returns the
    project-root path — the helper will create it.
    """
    direct = project_root / "CHANGELOG.md"
    if direct.exists():
        return direct
    parent = project_root.parent / "CHANGELOG.md"
    if parent.exists():
        return parent
    return direct


def _unreleased_span(content: str) -> tuple[int, int] | None:
    """Return ``(start, end)`` line indices of the ``## [Unreleased]``
    section body, or None if not present.

    ``start`` is the line *after* the header; ``end`` is the line of the
    next ``## [v...]`` heading (exclusive) or ``len(lines)``.
    """
    lines = content.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^## \[Unreleased\]", line):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^## \[", lines[j]):
            end = j
            break
    return (start, end)


def _ensure_unreleased(lines: list[str]) -> list[str]:
    """If the file lacks an ``## [Unreleased]`` header, insert one after
    the top-level heading.
    """
    if any(re.match(r"^## \[Unreleased\]", ln) for ln in lines):
        return lines

    insert_at = 0
    for i, ln in enumerate(lines):
        if ln.startswith("# "):
            insert_at = i + 1
            break
    new_section = ["", "## [Unreleased]", ""]
    return lines[:insert_at] + new_section + lines[insert_at:]


def _find_or_create_category(
    lines: list[str],
    unreleased_start: int,
    unreleased_end: int,
    category: str,
) -> tuple[int, int, list[str]]:
    """Return (cat_body_start, cat_body_end, updated_lines).

    ``cat_body_start`` is the line index immediately after the
    ``### <Category>`` header. ``cat_body_end`` is the line index of the
    next ``### `` header inside the [Unreleased] section, or
    ``unreleased_end`` if this is the last category.

    If the category doesn't exist, inserts it in alphabetical order
    according to ``KEEP_A_CHANGELOG_CATEGORIES``.
    """
    # Locate existing category sub-headers inside [Unreleased].
    existing: list[tuple[int, str]] = []
    for i in range(unreleased_start, unreleased_end):
        m = re.match(r"^### (\w+)", lines[i])
        if m:
            existing.append((i, m.group(1)))

    for i, name in existing:
        if name == category:
            body_start = i + 1
            body_end = unreleased_end
            for j, other_name in existing:  # noqa: B007
                if j > i:
                    body_end = j
                    break
            return body_start, body_end, lines

    # Category missing — decide insertion point in KaC order.
    order = {c: idx for idx, c in enumerate(KEEP_A_CHANGELOG_CATEGORIES)}
    my_rank = order[category]

    insert_at = unreleased_end
    for i, name in existing:
        if order.get(name, 999) > my_rank:
            insert_at = i
            break

    # Ensure a blank line before the new section (readability).
    prefix = []
    if insert_at > 0 and lines[insert_at - 1].strip() != "":
        prefix.append("")
    new_block = prefix + [f"### {category}", ""]

    updated = lines[:insert_at] + new_block + lines[insert_at:]
    body_start = insert_at + len(prefix) + 1  # line after the ### header
    body_end = body_start  # empty body for now
    return body_start, body_end, updated


def append_entry(
    changelog_path: Path,
    category: str,
    entry: str,
    *,
    dedup: bool = True,
) -> dict[str, object]:
    """Append ``- <entry>`` to ``[Unreleased]`` / ``### <category>``.

    Atomic write via tempfile + os.replace. Caller is responsible for
    holding the lock around this function — that lives in ``main()``.
    """
    if category not in KEEP_A_CHANGELOG_CATEGORIES:
        raise ValueError(f"unknown category: {category}")

    existed = changelog_path.exists()
    if existed:
        content = changelog_path.read_text(encoding="utf-8")
    else:
        content = "# Changelog\n\nAll notable changes to this project are documented here.\n"

    lines = content.splitlines()
    lines = _ensure_unreleased(lines)

    span = _unreleased_span("\n".join(lines))
    assert span is not None  # _ensure_unreleased guarantees it
    unreleased_start, unreleased_end = span

    cat_start, cat_end, lines = _find_or_create_category(
        lines, unreleased_start, unreleased_end, category
    )

    bullet = f"- {entry}"

    if dedup:
        # Check the current category body for an exact match.
        for i in range(cat_start, cat_end):
            if lines[i].strip() == bullet:
                return {
                    "status": "dedup",
                    "changelog_path": str(changelog_path),
                    "category": category,
                    "entry": entry,
                }

    # Insert at the end of the category body, before the next ### or the
    # section boundary. Trim any trailing empty lines inside the category
    # so appends don't create growing whitespace gaps.
    insert_at = cat_end
    while insert_at > cat_start and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines.insert(insert_at, bullet)

    new_content = "\n".join(lines)
    if not new_content.endswith("\n"):
        new_content += "\n"

    _atomic_write(changelog_path, new_content)

    return {
        "status": "created" if not existed else "appended",
        "changelog_path": str(changelog_path),
        "category": category,
        "entry": entry,
    }


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Write to a sibling temp file and rename — gives best-effort
    # atomicity on both POSIX and Windows.
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--category",
        required=True,
        choices=KEEP_A_CHANGELOG_CATEGORIES,
    )
    parser.add_argument("--entry", required=True, help="Bullet text (without leading '- ')")
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Append even if the exact entry already exists in the category",
    )
    parser.add_argument(
        "--changelog-path",
        default="",
        help="Explicit CHANGELOG.md path (overrides auto-detection)",
    )
    parser.add_argument("--lock-timeout", type=float, default=5.0)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    changelog_path = (
        Path(args.changelog_path).resolve()
        if args.changelog_path
        else find_changelog(project_root)
    )
    lock_path = changelog_path.with_suffix(changelog_path.suffix + ".lock")

    try:
        with file_lock(lock_path, timeout_seconds=args.lock_timeout):
            result = append_entry(
                changelog_path,
                args.category,
                args.entry,
                dedup=not args.no_dedup,
            )
    except LockTimeout as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # JSON-line output for programmatic callers; human-readable on stderr.
    import json
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
