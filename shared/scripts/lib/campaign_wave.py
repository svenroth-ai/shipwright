"""The wave-scoped ``SHIPWRIGHT_LOOP_UNIT_ID`` sentinel (campaign-dag-scheduler
R5a — "the flip: wave-based concurrent build").

Before R5a, ``SHIPWRIGHT_LOOP_UNIT_ID`` carried a genuine per-unit identity:
the orchestrator spawned one `sub-iterate-runner` at a time and exported this
var set to THAT unit's own id. R5a spawns a whole wave of runners in one
message instead, and every consumer of that variable that only checks
TRUTHINESS (``ci_supplychain_authorship_guard.py``) is unaffected — but a
consumer that reads the *value* as identity (``phase_quality._run_id``'s
tier-3 fallback, ``generate_handoff_on_stop.py``'s handoff namespacing) would
have every unit in the wave collide on the SAME value, since one shared
``export`` now covers the whole wave (see ``references/campaign-mode.md``'s
"Security" note on why a per-runner self-export cannot substitute for it —
``capture_session_id.py``'s ``CLAUDE_ENV_FILE`` is shared across concurrent
runners the same way a raw env var would be).

This module is the one place both fixed call sites recognise the sentinel,
so the two never drift apart on its literal spelling.
"""

from __future__ import annotations

from pathlib import Path

#: The fixed, non-identity-bearing value the orchestrator exports for the
#: WHOLE wave, once, before spawning (`references/campaign-mode.md` step 1).
#: Deliberately not a real identity — nothing must ever derive per-unit
#: behavior from its VALUE, only from its presence (the authorship guard).
WAVE_UNIT_ID_SENTINEL = "__campaign_wave__"


def resolve_wave_safe_unit_value(value: str) -> str:
    """`value` unchanged, unless it IS the wave sentinel — then `""`.

    The one-line shape both fixed call sites share (`_run_id.py` tier-3,
    `generate_handoff_on_stop.py`'s handoff namespacing): treat the sentinel
    as though the variable were never set, rather than as a real identity.
    """
    return "" if is_wave_sentinel(value) else value


def is_wave_sentinel(value: str | None) -> bool:
    """``True`` iff `value` is the wave-scoped sentinel, not a genuine
    per-unit id. A genuine campaign sub-iterate id never equals this
    sentinel: ``lib.campaign_graph.id_charset_ok``'s charset DOES allow an
    underscore mid-string, but rejects a value whose FIRST or LAST character
    is a separator (``._-``) — and the sentinel is bracketed by underscores
    on both ends (``id_charset_ok("__campaign_wave__") is False``, asserted
    in `test_campaign_wave.py`), so no real id accepted at write time can
    collide with it. A shipwright-build ``--autonomous`` section id (that
    loop is untouched by R5a and still exports a real per-unit value into
    this same env var) is drawn from a different, but similarly
    non-colliding, id space."""
    return value == WAVE_UNIT_ID_SENTINEL


def per_unit_worktree_identity(project_root: Path) -> str | None:
    """The per-unit worktree's OWN directory basename
    (``campaign-{slug}--{unit_id}[-a{attempt}]``), or ``None`` when
    `project_root` is not shaped like one.

    External code review (glm + openai, round 2): `resolve_run_id`'s pointer
    tier is keyed by ``session_id`` (`write_run_pointer`), and every unit in
    a wave shares the SAME `SHIPWRIGHT_SESSION_ID` — so N concurrent
    `setup_unit_worktree.py` calls all write to the ONE file
    `<main_root>/.shipwright/iterate_active/<session_id>.json`,
    last-writer-wins. That tier is NOT safe to trust for per-unit identity
    under the wave model, worse than the "falls back to loop_id" risk both
    reviews originally flagged. This directory basename is the one value
    that is BOTH already unique per unit (`check_worktree_location.py`'s own
    guard depends on it) and requires no change to session/lock/lease
    semantics elsewhere — used as the FIRST resort, ahead of the
    session-keyed pointer, whenever `project_root` looks like a per-unit
    worktree.
    """
    name = Path(project_root).name
    if name.startswith("campaign-") and "--" in name:
        return name
    return None


def write_wave_aware_handoff(project_root: Path, session_id: str, content: str,
                              loop_id: str | None, loop_unit: str | None,
                              runtime_dir: Path, handoff_path: Path) -> Path:
    """`generate_handoff_on_stop.py`'s own namespaced-vs-runtime write,
    extracted so the R5a sentinel fix lives in ONE place rather than growing
    that hook past its already-filed bloat exception.

    Namespaces under `.shipwright/planning/handoffs/{loop_id}/{unit}.md` when
    both `loop_id` and a resolved `unit` are available (a campaign context);
    else writes the plain runtime path (the standalone-iterate default).
    `loop_unit` is resolved through the wave sentinel first — a genuine
    per-unit id (a campaign sub-iterate, or a still-unaffected
    shipwright-build `--autonomous` section) passes through unchanged; the
    sentinel resolves through `per_unit_worktree_identity` first (safe under
    concurrency — see its own docstring), falling back to
    `lib.phase_quality.resolve_run_id` only when `project_root` is not a
    per-unit worktree shape (a genuinely standalone run, never concurrent).
    """
    unit = resolve_wave_safe_unit_value(loop_unit) if loop_unit else loop_unit
    if loop_unit and not unit:
        unit = per_unit_worktree_identity(Path(project_root))
    if loop_unit and not unit:
        from lib import phase_quality as pq
        unit = pq.resolve_run_id(Path(project_root), session_id)
    if loop_id and unit:
        namespaced_dir = Path(project_root) / ".shipwright" / "planning" / "handoffs" / loop_id
        namespaced_dir.mkdir(parents=True, exist_ok=True)
        namespaced_path = namespaced_dir / f"{unit}.md"
        namespaced_path.write_text(content, encoding="utf-8")
        return namespaced_path
    runtime_dir.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(content, encoding="utf-8")
    return handoff_path


__all__ = [
    "WAVE_UNIT_ID_SENTINEL",
    "is_wave_sentinel",
    "per_unit_worktree_identity",
    "resolve_wave_safe_unit_value",
    "write_wave_aware_handoff",
]
