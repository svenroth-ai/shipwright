"""The provenance header every compliance evidence document opens with.

Card ``trg-4d5b6a56`` (FR-01.10). A document used to carry only
``Generated: <timestamp>``, which says *when* it was written but not *which state*
it describes — and a timestamp cannot distinguish a document regenerated from an
old state from one regenerated from the current one.

The two lines are emitted **as a pair, from one place**, so they cannot drift apart
across the five renderers and cannot come from two different events: both are read
off the single work event resolved by ``collectors.change_history.latest_work_event``
(``timestamp`` and ``run_id`` on :class:`ComplianceData`).

The shape itself lives in ``shared/scripts/source_state.py`` — one mechanism, two
producers (the other is the test-results record). This module is only the local
adapter: it does the ADR-045-safe ``sys.path`` bootstrap once, on behalf of all
five renderers, instead of five times.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Cross-cutting helper lives at shared/scripts/source_state.py — OUTSIDE the
# `lib/` namespace per ADR-045, so importing it here cannot collide with this
# plugin's own `lib/` regular package.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from source_state import SourceState, banner_line, strip_banner  # noqa: E402

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def provenance_lines(data: ComplianceData, *, generated_suffix: str = "") -> list[str]:
    """The provenance header block, currently ``[Generated:…, Source-State:…]``.

    Deterministic: both values come from the event log, never from the clock, so two
    renders against the same ``events.jsonl`` are byte-identical and the tracked
    documents do not go permanently dirty in ``git status``
    (iterate-2026-05-22-deterministic-render-timestamps).

    An unresolved run id renders ``run=(unknown)`` rather than being omitted or
    guessed — see ``source_state.banner_line``.

    **Callers must splat this, never destructure it.** The list length is not part of
    the contract: card ``trg-a1fd8125`` plans a third line here ("when did the
    cross-check last run"), and a caller that unpacked two names would raise at render
    time the moment it lands. ``generated_suffix`` exists so the one document that
    annotates its own ``Generated:`` line (the SBOM) can do so without unpacking.
    """
    generated = f"Generated: {data.timestamp}{generated_suffix}"
    return [generated, banner_line(SourceState(run_id=data.run_id))]


# Re-exported so the Group E staleness normaliser reaches the banner's ONE owning
# definition through this same bootstrap, instead of re-declaring the regex (AC1).
__all__ = ["provenance_lines", "strip_banner"]
