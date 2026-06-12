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

# Canonical routing SSoT: ``architecture_impact`` → (doc filename under
# ``.shipwright/agent_docs/``, section header). ONE home per impact. Consumed by
# this oracle (F11 gate + Group-F detective), by ``write_decision_log.py`` (the
# direct-append producer), and pinned to ``F2.md`` by a routing drift test, so
# the producer, the verifier, and the skill instruction cannot diverge again.
IMPACT_TARGETS: dict[str, tuple[str, str]] = {
    "component": ("architecture.md", "## Architecture Updates"),
    "data-flow": ("architecture.md", "## Architecture Updates"),
    "convention": ("conventions.md", "## Convention Updates"),
}
# Invariant: every real impact routes somewhere (pinned by test_impact_targets).
assert set(IMPACT_TARGETS) == REAL_IMPACTS

# Transitional back-compat: before this routing was fixed (the agent-doc-entry-
# rules split, 2026-06-12), iterate ``convention`` entries were hand-written to
# ``architecture.md ## Architecture Updates`` to satisfy the old architecture.md-
# only gate. Until the follow-up compression iterate migrates those legacy
# entries to ``## Convention Updates``, a ``convention`` run_id documented in
# architecture.md is still accepted. NEW entries route via ``IMPACT_TARGETS``
# (producer + F2.md + the entry-budget gate); this fallback never relaxes the
# canonical routing, only tolerates the un-migrated backlog.
_LEGACY_CONVENTION_DOC = "architecture.md"


def target_for_impact(impact: object) -> tuple[str, str] | None:
    """Return ``(filename, section_header)`` for ``impact``, or ``None``.

    Normalizes case/whitespace first, so ``"Convention"`` resolves like
    ``"convention"``. ``None`` for null/unknown impacts.
    """
    return IMPACT_TARGETS.get(normalize_impact(impact))


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


def _coerce_texts(texts: dict[str, str] | str) -> dict[str, str]:
    """Accept either a ``{filename: text}`` mapping or a legacy single string.

    A bare string is interpreted as ``architecture.md`` text (the pre-routing
    signature) so any un-updated caller degrades to the old architecture.md-only
    behavior via the convention fallback rather than crashing.
    """
    if isinstance(texts, str):
        return {"architecture.md": texts}
    return texts


def impact_documented(impact: str, run_id: str, texts: dict[str, str] | str) -> bool:
    """True iff ``run_id`` is documented in the doc that ``impact`` routes to.

    ``texts`` maps the target filename (``architecture.md`` / ``conventions.md``)
    to that doc's content. ``component`` / ``data-flow`` resolve to
    ``architecture.md``; ``convention`` resolves to ``conventions.md`` — with a
    transitional fallback to ``architecture.md`` for the un-migrated legacy
    backlog (see ``_LEGACY_CONVENTION_DOC``).
    """
    doc = _coerce_texts(texts)
    target = IMPACT_TARGETS.get(normalize_impact(impact))
    if target is None:
        return False
    if run_id_documented(doc.get(target[0], ""), run_id):
        return True
    if normalize_impact(impact) == "convention":
        return run_id_documented(doc.get(_LEGACY_CONVENTION_DOC, ""), run_id)
    return False


def read_target_texts(agent_docs_dir: Path) -> dict[str, str]:
    """Read every doc some impact routes to, keyed by filename.

    Reads BOTH canonical agent docs (the distinct target filenames in
    ``IMPACT_TARGETS``) so callers feed a complete ``texts`` map to
    ``missing_entries`` / ``impact_documented`` — including the
    convention→architecture.md legacy fallback. An unreadable doc → ``""`` (the
    run_id then reads as undocumented there, surfaced rather than masked).
    """
    agent_docs_dir = Path(agent_docs_dir)
    out: dict[str, str] = {}
    for filename in {target[0] for target in IMPACT_TARGETS.values()}:
        try:
            out[filename] = (agent_docs_dir / filename).read_text(
                encoding="utf-8", errors="ignore"
            )
        except OSError:
            out[filename] = ""
    return out


def missing_entries(
    records: list[DropRecord], texts: dict[str, str] | str
) -> list[DropRecord]:
    """Arch-impact records whose ``run_id`` is absent from their TARGET doc.

    Routing is per ``IMPACT_TARGETS`` (``convention`` → ``conventions.md``;
    ``component`` / ``data-flow`` → ``architecture.md``). ``texts`` is a
    ``{filename: text}`` mapping (a bare string is treated as architecture.md
    for back-compat). A record whose target doc is absent from ``texts`` counts
    as undocumented.
    """
    doc = _coerce_texts(texts)
    return [
        r for r in arch_impact_records(records)
        if r.run_id and not impact_documented(r.impact, r.run_id, doc)
    ]


def records_for_run(records: list[DropRecord], run_id: str) -> list[DropRecord]:
    """Records whose ``run_id`` matches exactly (not a prefix)."""
    return [r for r in records if r.run_id == run_id]


def records_in_run_set(
    records: list[DropRecord], allowed: set[str]
) -> list[DropRecord]:
    """Records whose ``run_id`` is in ``allowed`` (exact set membership).

    The set-valued analogue of :func:`records_for_run`. Scopes the *whole-set*
    arch-drift checkers — the Group-F ``F5`` detective and
    ``test_architecture_md_reflects_arch_impact`` — to drops OWNED by the current
    tree's lineage, where ``allowed`` is the run_id set from this tree's committed
    ``shipwright_events.jsonl`` (``events_log.finalized_run_ids``). This excludes
    cross-branch campaign sibling drops that bleed through the shared main-rooted
    ``decision-drops`` dir: the sibling's doc entry lives only on its own unmerged
    branch, so without scoping the drop reads as undocumented drift on every other
    branch. The F11 finalize gate scopes to ONE run_id via ``records_for_run``;
    this is its whole-set counterpart. Matching stays in ``missing_entries`` — the
    "cannot diverge" contract is on matching, not on which drops are in scope.
    """
    return [r for r in records if r.run_id in allowed]


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
