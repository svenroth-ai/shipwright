"""Reconcile architecture-impact decision-drops against ``architecture.md``.

Single source of truth shared by:

- the compliance Group F detective (F5) — loaded from the plugin via
  ``audit_adapters.load_shared_lib("architecture_doc")``;
- the iterate F11 finalize gate ``check_architecture_documented`` — imported as
  ``from lib.architecture_doc import ...``;
- their tests.

The module is deliberately **pure**: it takes a ``decision-drops`` directory and
the architecture.md *text*, and never shells out to git or resolves worktree
roots. Each caller does its own main-repo / worktree path resolution (the
detective via ``events_log.resolve_main_repo_root``, the finalizer the same) and
hands the resolved inputs in. That keeps the matching rule + impact vocabulary
in one place — the detective and the finalizer cannot drift apart — while
remaining trivially testable with ``tmp_path`` fixtures.

Origin: iterate-2026-06-06-arch-drift-detector (external-review #2 / #4).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# Canonical ``architecture_impact`` values that REQUIRE an architecture.md
# entry. ``write_decision_drop.py`` accepts exactly these plus ``none``.
REAL_IMPACTS = frozenset({"component", "data-flow", "convention"})

# The no-op default written when no ``--architecture-impact`` flag is passed.
NULL_IMPACTS = frozenset({"none", ""})


@dataclass(frozen=True)
class DropRecord:
    """One parsed decision-drop, with its impact normalized to lowercase."""

    drop_file: str
    run_id: str
    impact: str


def normalize_impact(raw: object) -> str:
    """Lowercase + strip an ``architecture_impact`` value; non-str → ``""``.

    Case-insensitivity matters: a drop carrying ``Convention`` must be treated
    as ``convention`` rather than slipping past the ``REAL_IMPACTS`` membership
    check (external-review Gemini #3).
    """
    return raw.strip().lower() if isinstance(raw, str) else ""


def run_id_documented(arch_text: str, run_id: str) -> bool:
    """True iff ``run_id`` appears in ``arch_text`` as a standalone token.

    ``run_id``s contain hyphens, so a plain ``\\b`` word boundary is unreliable
    and a bare substring test would let a prefix run_id (``iter-1``) be
    satisfied by a longer one (``iter-12``). We require the match to not be
    flanked by ``[\\w-]`` on either side (external-review OpenAI #1 / Gemini #2).
    """
    if not run_id:
        return False
    return re.search(rf"(?<![\w-]){re.escape(run_id)}(?![\w-])", arch_text) is not None


def scan_drops(drops_dir: Path) -> tuple[list[DropRecord], list[str]]:
    """Parse every ``*.json`` under ``drops_dir``.

    Returns ``(records, corrupt_filenames)`` where ``records`` carries EVERY
    drop (impact normalized, including ``none`` / unknown values) and
    ``corrupt_filenames`` lists files that failed to parse — surfaced rather
    than silently swallowed, so a malformed drop can't hide real drift.
    """
    drops_dir = Path(drops_dir)
    if not drops_dir.is_dir():
        return [], []
    records: list[DropRecord] = []
    corrupt: list[str] = []
    for fp in sorted(drops_dir.glob("*.json")):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            corrupt.append(fp.name)
            continue
        if not isinstance(payload, dict):
            corrupt.append(fp.name)
            continue
        run_id = payload.get("run_id") or payload.get("runId") or ""
        impact = normalize_impact(
            payload.get("architecture_impact", payload.get("architectureImpact"))
        )
        records.append(DropRecord(drop_file=fp.name, run_id=str(run_id), impact=impact))
    return records, corrupt


def arch_impact_records(records: list[DropRecord]) -> list[DropRecord]:
    """Records whose impact is one of ``REAL_IMPACTS``."""
    return [r for r in records if r.impact in REAL_IMPACTS]


def unknown_impact_records(records: list[DropRecord]) -> list[DropRecord]:
    """Records whose impact is neither a real impact nor a null default.

    A non-empty value outside the canonical vocabulary (typo, schema drift) is
    a blind-spot risk — callers surface it instead of ignoring it.
    """
    return [
        r for r in records
        if r.impact not in REAL_IMPACTS and r.impact not in NULL_IMPACTS
    ]


def missing_entries(records: list[DropRecord], arch_text: str) -> list[DropRecord]:
    """Arch-impact records whose ``run_id`` is absent from ``arch_text``."""
    return [
        r for r in arch_impact_records(records)
        if r.run_id and not run_id_documented(arch_text, r.run_id)
    ]


def records_for_run(records: list[DropRecord], run_id: str) -> list[DropRecord]:
    """Records whose ``run_id`` matches exactly (not a prefix)."""
    return [r for r in records if r.run_id == run_id]


def corrupt_for_run(corrupt_filenames: list[str], run_id: str) -> list[str]:
    """Corrupt drop filenames belonging to ``run_id`` (matched by filename).

    Drops are named ``<run_id>.json`` or ``<run_id>_NNN.json``; the ``_`` /
    ``.`` separator means a prefix run_id can't claim a longer run_id's file.
    """
    if not run_id:
        return []
    exact = f"{run_id}.json"
    prefix = f"{run_id}_"
    return [
        name for name in corrupt_filenames
        if name == exact or name.startswith(prefix)
    ]
