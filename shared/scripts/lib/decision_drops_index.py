#!/usr/bin/env python3
"""Render and refresh ``.shipwright/agent_docs/decision-drops/INDEX.md``.

Same render/rebuild split as ``lib/adr_index.py`` and ``lib/decision_log_index``,
with one deliberate divergence: ``INDEX.md`` itself stays **gitignored**
(since iterate-2026-08-08-track-decision-drops, the *directory* is tracked —
only this generated render is not), so it is a per-checkout convenience,
never a committed artifact. That changes which pieces of the ADR pattern
apply:

- **No ``CHURN_ALLOWLIST`` entry.** That registry exists because ``git merge``
  can report a CONFLICT on a path both branches touched — a gitignored path is
  never part of a commit, so git can never conflict on it in the first place.
  An allowlist entry here would be dead code the resolver's ``classify()`` would
  never see exercised. (The tracked ``*.json`` drops it lists don't need one
  either: each is a uniquely-named new file per run, so two branches adding
  different ones merges cleanly — the same shape ``CHANGELOG-unreleased.d/``
  already relies on.)
- **No CI byte-equality drift guard against a committed copy** (mirrors
  ``test_adr_index_producers.test_committed_index_is_not_stale``): there is no
  committed ``decision-drops/INDEX.md`` in this checkout to compare against —
  CI's clean clone never has one. The equivalent guard here runs against a
  ``tmp_path`` fixture instead (``test_decision_drops_index_producers.py``),
  proving the writer stays byte-exact, not that a specific commit is fresh.
- **``drop_dir()`` resolves against ``project_root`` directly** — the calling
  iterate's own worktree, not a shared main-repo location. A refresh from
  inside an active iterate therefore only ever sees that run's own new drop
  (correct: nothing else is committed to that branch yet); a refresh from
  ``/shipwright-changelog`` (always run on the real main checkout) sees every
  merged drop. ``file_lock`` + ``durable_atomic_write`` still guard the
  write itself, now against a single-writer worktree race rather than a
  cross-worktree one.

``drop_dir`` / ``DROP_DIRNAME`` are a THIRD independent copy of the same
resolution already in ``write_decision_drop.py`` and ``aggregate_decisions.py``
— not centralized here, deliberately. ``test_decision_drop_ssot.py``'s
``_WORKTREE_LOCAL`` registry pins all three files' shared behavior: NONE of
them may resolve against the main repo for decision-drops.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .atomic_write import durable_atomic_write
from .file_lock import LockTimeout, file_lock

DROP_DIRNAME = "decision-drops"  # under .shipwright/agent_docs/, TRACKED
DROP_INDEX_FILENAME = "INDEX.md"

REGEN_TOOL_RELPATH = "scripts/tools/rebuild_decision_drops_index.py"
REGEN_COMMAND = f"uv run {{shared_root}}/{REGEN_TOOL_RELPATH} --project-root ."


def regen_command_resolved() -> str:
    """:data:`REGEN_COMMAND` with ``{shared_root}`` filled in from this file."""
    shared_root = Path(__file__).resolve().parents[2]
    return REGEN_COMMAND.replace("{shared_root}", shared_root.as_posix())


def drop_dir(project_root: Path | str) -> Path:
    """Resolve ``.shipwright/agent_docs/decision-drops/`` under ``project_root``.

    Identical resolution to the sibling copies in ``write_decision_drop.py``
    and ``aggregate_decisions.py`` — the directory is tracked, so a drop
    written from an iterate worktree lives IN that worktree until its PR
    merges. No main-root redirect (see module docstring).
    """
    return Path(project_root) / ".shipwright" / "agent_docs" / DROP_DIRNAME


def _pending_drops(dd: Path) -> list[tuple[str, dict]]:
    """``(filename, payload)`` for every pending drop in ``dd``, sorted by the
    drop's own ``date`` field (filename as tiebreaker) — NOT filename order.
    Filenames are ``<sanitized_run_id>_<counter>.json``; a non-date-prefixed
    run_id (e.g. a ``trg-*`` campaign sub-iterate) sorts nowhere near its
    actual date lexicographically, so callers that want recency (chiefly
    :func:`render_recent_drops_summary`) need the parsed field, not the name.

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
    out.sort(key=lambda item: (str(item[1].get("date", "")), item[0]))
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
        "_Auto-generated — do not edit by hand. This file (only) is gitignored",
        "(local per-checkout convenience); the directory it lists is tracked.",
        "Regenerate:_",
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


def render_recent_drops_summary(dd: Path, *, limit: int = 20) -> str:
    """One line per pending drop (title/date/section), most-recent-last capped
    at ``limit``. For iterate's Layer-1 context loading (context-loading.md
    item 4a) — bounded so a growing between-release backlog stays a fixed
    context cost, not a linear one. Pure — no writes. ``""`` when there are
    no pending drops (caller treats that as "nothing to show", not an error).
    """
    drops = _pending_drops(dd)[-limit:]
    lines = []
    for name, data in drops:
        date = _one_line(data.get("date", ""))
        section = _one_line(data.get("section", ""))
        title = _one_line(data.get("title") or str(data.get("decision") or "")[:60])
        lines.append(f"- `{name}` — {date} — {section} — {title}")
    return "\n".join(lines)


def rebuild_decision_drops_index(project_root: Path | str) -> Path | None:
    """Refresh ``INDEX.md`` for ``project_root``'s decision-drops dir.

    A missing directory is a strict no-op — never minted before the first
    drop is ever written. Lock + :func:`durable_atomic_write` guard a refresh
    against a concurrent write within the SAME checkout (e.g. this run's own
    F3 write racing a manual regen) — no longer a cross-worktree concern
    now that each worktree has its own drop_dir (see module docstring).
    """
    dd = drop_dir(project_root)
    if not dd.is_dir():
        return None
    index_path = dd / DROP_INDEX_FILENAME
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
