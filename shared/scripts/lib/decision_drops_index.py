#!/usr/bin/env python3
"""Render and refresh ``.shipwright/agent_docs/decision-drops/INDEX.md``.

Same render/rebuild split as ``lib/adr_index.py`` and ``lib/decision_log_index``,
with one deliberate divergence: the decision-drops directory is **gitignored**
(``glossary.md`` — "gitignored, main-repo path"), so this index is a per-checkout
convenience, never a committed artifact. That changes which pieces of the ADR
pattern apply:

- **No ``CHURN_ALLOWLIST`` entry.** That registry exists because ``git merge``
  can report a CONFLICT on a path both branches touched — a gitignored path is
  never part of a commit, so git can never conflict on it in the first place.
  An allowlist entry here would be dead code the resolver's ``classify()`` would
  never see exercised.
- **No CI byte-equality drift guard against a committed copy** (mirrors
  ``test_adr_index_producers.test_committed_index_is_not_stale``): there is no
  committed ``decision-drops/INDEX.md`` in this checkout to compare against —
  CI's clean clone never has one. The equivalent guard here runs against a
  ``tmp_path`` fixture instead (``test_decision_drops_index_producers.py``),
  proving the writer stays byte-exact, not that a specific commit is fresh.
- **Real concurrency, but a local one.** ``drop_dir()`` resolves to the MAIN
  repo root (git-worktree-aware), so every parallel iterate — each in its own
  worktree — writes into the SAME shared local directory. That is a real race
  between concurrent local writers, not a git merge conflict, and it is exactly
  what ``file_lock`` + ``durable_atomic_write`` already guard against here, the
  same way they guard the ADR index against two release passes.

``drop_dir`` / ``DROP_DIRNAME`` are a THIRD independent copy of the same
resolution already in ``write_decision_drop.py`` and ``aggregate_decisions.py``
— not centralized here, deliberately. ``test_decision_drop_ssot.py`` pins
those two files' own ``resolve_main_repo_root`` usage by name; a real
centralization would need to update that registry too, which is out of scope
for adding an index. The SSoT meta-test already tolerates independent copies
as long as each resolves worktree-aware, which this one does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lib.atomic_write import durable_atomic_write
from lib.file_lock import LockTimeout, file_lock
from lib.repo_root import resolve_main_repo_root

DROP_DIRNAME = "decision-drops"  # under .shipwright/agent_docs/, GITIGNORED
DROP_INDEX_FILENAME = "INDEX.md"

REGEN_TOOL_RELPATH = "scripts/tools/rebuild_decision_drops_index.py"
REGEN_COMMAND = f"uv run {{shared_root}}/{REGEN_TOOL_RELPATH} --project-root ."


def regen_command_resolved() -> str:
    """:data:`REGEN_COMMAND` with ``{shared_root}`` filled in from this file."""
    shared_root = Path(__file__).resolve().parents[2]
    return REGEN_COMMAND.replace("{shared_root}", shared_root.as_posix())


def drop_dir(project_root: Path | str) -> Path:
    """Resolve ``.shipwright/agent_docs/decision-drops/``, git-worktree-aware.

    Identical resolution to the pre-existing copies in ``write_decision_drop.py``
    and ``aggregate_decisions.py`` — a drop written from an iterate worktree
    lives next to the MAIN repo, the directory this index and the aggregator
    both read.
    """
    project_root = Path(project_root)
    root = resolve_main_repo_root(project_root) or project_root
    return root / ".shipwright" / "agent_docs" / DROP_DIRNAME


def _pending_drops(dd: Path) -> list[tuple[str, dict]]:
    """``(filename, payload)`` for every pending drop in ``dd``, file order.

    Same filter as ``aggregate_decisions._snapshot_drops``: only ``*.json``,
    skip ``_``-prefixed scaffolding and ``.gitkeep``. An unreadable/malformed
    drop is skipped rather than raising — a corrupt file must not blank the
    whole index; the aggregator is the one place that hard-fails on it.
    """
    if not dd.is_dir():
        return []
    out: list[tuple[str, dict]] = []
    for f in sorted(dd.iterdir()):
        if f.suffix != ".json" or f.is_symlink() or not f.is_file():
            continue
        if f.name.startswith("_") or f.name == ".gitkeep":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append((f.name, data))
    return out


_MARKDOWN_ACTIVE_RE = re.compile(r"([\\\[\]()*_`])")


def _one_line(text: str) -> str:
    """Collapse whitespace (incl. embedded newlines) and neutralize Markdown
    syntax, so a drop's fields — agent-authored JSON, not markdown-safe by
    construction — cannot turn into a live link/image, emphasis, or a code
    span that swallows the rest of the row when rendered."""
    collapsed = " ".join(str(text).split())
    return _MARKDOWN_ACTIVE_RE.sub(r"\\\1", collapsed)


def render_decision_drops_index(dd: Path) -> str:
    """Render the pending-drops index for ``dd``. Pure — LF-only, no writes."""
    lines = [
        "# Decision Drops — INDEX (pending, not yet folded into decision_log.md)",
        "",
        "_Auto-generated — do not edit by hand. This directory is gitignored",
        "(local per-checkout staging); this index is local-only and is never",
        "committed. Regenerate:_",
        f"`{REGEN_COMMAND}`",
        "",
    ]
    drops = _pending_drops(dd)
    if not drops:
        lines += ["_No pending decision-drops._", ""]
        return "\n".join(lines)
    for name, data in drops:
        date = _one_line(data.get("date", ""))
        section = _one_line(data.get("section", ""))
        title = _one_line(data.get("title") or str(data.get("decision") or "")[:60])
        lines.append(f"- `{name}` — {date} — {section} — {title}")
    lines.append("")
    return "\n".join(lines)


def rebuild_decision_drops_index(project_root: Path | str) -> Path | None:
    """Refresh ``INDEX.md`` for ``project_root``'s decision-drops dir.

    A missing directory is a strict no-op — never minted before the first
    drop is ever written. Lock + :func:`durable_atomic_write` guard against
    two parallel iterate worktrees refreshing the same shared local file at
    once (see module docstring — a local race, not a git conflict).
    """
    dd = drop_dir(project_root)
    if not dd.is_dir():
        return None
    index_path = dd / DROP_INDEX_FILENAME
    # Lock at dd's OWN resolved root (the main repo), not project_root: a caller
    # in a worktree resolves the same dd via resolve_main_repo_root() but would
    # otherwise take a lock file in ITS OWN .shipwright/locks/, leaving two
    # parallel worktrees contending on two different locks for one shared file.
    lock_root = dd.parents[2]
    lock_path = lock_root / ".shipwright" / "locks" / "decision_drops_index.lock"
    with file_lock(str(lock_path), timeout_seconds=10.0):
        durable_atomic_write(index_path, render_decision_drops_index(dd))
    return index_path


def refresh_best_effort(project_root: Path | str) -> str | None:
    """Refresh the index, returning a warning message instead of raising."""
    try:
        rebuild_decision_drops_index(project_root)
    except (OSError, LockTimeout) as exc:
        return (
            f"refreshing decision-drops/{DROP_INDEX_FILENAME} failed: {exc}\n"
            f"         Regenerate it with:\n         {regen_command_resolved()}"
        )
    return None
