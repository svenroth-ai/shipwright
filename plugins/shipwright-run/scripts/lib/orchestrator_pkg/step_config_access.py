"""How the v1 step-advance path OBTAINS a config — the two strict chokepoints.

``update_step`` reads the run config twice: once before the lock, to learn
whether this is a standalone run, and once inside it, to apply its changes. Both
reads are on a path that can advance or change a run, so both use the STRICT
reader and refuse an unusable config rather than guessing at it.

Concentrating them here is what makes that claim checkable: this module and
``step_planning`` import ``read_run_config`` and never the tolerant
``load_run_config``, so "no mutating path reaches a tolerant read" is a property
of two short files rather than of a convention. Pinned by
``test_no_mutating_path_reaches_a_tolerant_read``.

Kept out of ``step_planning`` for the same reason ``validation_record`` was: that
module sits against its 300-LOC budget, and these are small functions over a
config dict, testable without the advisory lock or a pipeline.

The defect that motivated the strictness — an unusable config reading as
``standalone`` and then being overwritten — is recorded in
``.shipwright/planning/iterate/iterate-2026-08-05-standalone-flag-corrupt-config.md``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_factory import build_pipeline

# STRICT only. A tolerant ``load_run_config`` import here would silently reopen
# the defect this module exists to close.
from .config_io import read_run_config


def _bootstrap_standalone_config(step: str) -> dict[str, Any]:
    """Synthesise a standalone config for a bare phase invocation (no /shipwright-run)."""
    return {
        "pipeline": build_pipeline(),
        "status": "in_progress",
        "current_step": step,
        "completed_steps": [],
        "standalone": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        # Iterate 12.0 (ADR-027): empty phase_history on bootstrap so
        # append_phase_history.py never has to synthesise the schema.
        "phase_history": {},
    }


def _load_or_bootstrap(project_root: Path, step: str) -> dict[str, Any]:
    """Load the on-disk config fresh, or bootstrap a standalone one if ABSENT.

    Bootstrap is for a config that is not there — never for one that is there and
    unusable. The old test was ``if config else bootstrap``, i.e. TRUTHINESS, so a
    real file holding ``{}`` was indistinguishable from no file at all and got
    atomically replaced along with everything an unparseable one held.

    **The anti-data-loss guarantee**, stated precisely: a config observed
    unreadable by THIS read is not overwritten by this operation. The read runs
    inside ``run_config_lock`` with the ``save_run_config`` that follows, so our
    own writers are serialised against it — it is not a claim about an outside
    process replacing the file in between.
    """
    config, present = read_run_config(project_root)
    return config if present else _bootstrap_standalone_config(step)


def _read_standalone_flag(project_root: Path) -> bool:
    """Return the ``standalone`` flag WITHOUT triggering the legacy-migration
    write that a full load would perform UNLOCKED.

    ``standalone`` is invariant under migration (which only rewrites
    ``pipeline`` / ``phase_tasks``), so the raw read matches the migrated value —
    that invariance is what makes ``migrate=False`` sound here, and it relies on
    the field being present in the raw dict. The migration still runs later, on
    the in-lock ``_load_or_bootstrap`` reload (audit WP2/F11 residual window).

    Mirrors ``_load_or_bootstrap(...).get("standalone", False)`` **for an absent
    config and for a boolean ``standalone``** — and deliberately NOT beyond that:
    for `standalone: "false"` this returns ``False`` while that expression returns
    the truthy string, which is the whole point of the second bullet below.

    Two things it deliberately does NOT do:

    * **Answer for a config it cannot read.** It returned ``True``, and
      ``update_step`` reads standalone as "skip the phase gate, let ``--force``
      pass without a reason, write no ``validation_overrides[]`` entry" — so an
      unusable config switched off all three at once. It raises instead.
    * **Trust a non-boolean.** Annotated ``-> bool`` but returned
      ``config.get("standalone", False)`` RAW, so ``"false"`` — a truthy string —
      read as standalone. ``is True`` fails safe: anything else runs the gate.
    """
    config, present = read_run_config(project_root, migrate=False)
    if not present:
        return True
    return config.get("standalone") is True
