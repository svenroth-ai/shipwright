"""routing — authoritative-vs-heuristic contract (defined in G1, wired in G4).

A target with a real, healthy ``.shipwright/`` event log / RTM is an
**authoritative** source (the grade could be read from Shipwright's own
records). Everything else is a **heuristic** synthetic projection from git
history, stamped as such.

The contract — and its behaviour for the partial / stale / malformed / mixed
cases — is defined and tested NOW (GPT #5/#17). G1 always *grades* via the
heuristic projector (``effective_mode == "heuristic"``); the ``detected_mode``
records whether an authoritative source is present so the report can honestly
say "authoritative source available — ingestion lands in G4" without claiming a
grade it did not compute.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Recognised states of a target's `.shipwright/` directory.
STATE_ABSENT = "absent"
STATE_VALID = "valid"
STATE_PARTIAL = "partial"
STATE_STALE = "stale"
STATE_MALFORMED = "malformed"
STATE_MIXED = "mixed"

_MODE_AUTHORITATIVE = "authoritative"
_MODE_HEURISTIC = "heuristic"


@dataclass(frozen=True)
class RoutingDecision:
    """The routing verdict for a target."""

    detected_mode: str    # what the target *could* support
    effective_mode: str   # what the grader actually used (heuristic in G1)
    state: str            # one of the STATE_* constants
    reason: str

    @property
    def is_authoritative_source(self) -> bool:
        return self.detected_mode == _MODE_AUTHORITATIVE


def _read(path: Path, limit: int = 65536) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _classify_shipwright(sw_dir: Path) -> tuple[str, str]:
    """Return (state, reason) for a `.shipwright/` directory."""
    if not sw_dir.is_dir():
        return STATE_ABSENT, "no .shipwright/ directory"

    events = sw_dir / "events.jsonl"
    events_text = _read(events) if events.is_file() else ""
    # These reference the GRADED TARGET repo's .shipwright/, not this project's
    # canonical compliance dir — the canon lint can't tell them apart.
    rtm_candidates = [
        sw_dir / "compliance" / "rtm.md",  # artifact-path-canon: legacy
        sw_dir / "compliance" / "traceability_matrix.md",  # artifact-path-canon: legacy
    ]
    has_rtm = any(p.is_file() for p in rtm_candidates)
    has_events = bool(events_text.strip())

    if not has_events and not has_rtm:
        return STATE_PARTIAL, ".shipwright/ present but no event log or RTM"

    if has_events:
        # Malformed if the first non-empty line is not JSON-object-shaped.
        first = next((ln for ln in events_text.splitlines() if ln.strip()), "")
        stripped = first.strip()
        if stripped and not (stripped.startswith("{") and stripped.endswith("}")):
            return STATE_MALFORMED, "events.jsonl is not JSON-lines shaped"

    if has_events and not has_rtm:
        return STATE_MIXED, "event log present but no RTM"
    if has_rtm and not has_events:
        return STATE_MIXED, "RTM present but no event log"
    return STATE_VALID, "healthy .shipwright/ event log + RTM"


# States that would (in G4) support an authoritative read.
_AUTHORITATIVE_STATES = frozenset({STATE_VALID})


def decide_routing(root: Path) -> RoutingDecision:
    """Decide authoritative-vs-heuristic routing for a target root.

    G1 always grades heuristically; only ``detected_mode`` reflects an
    authoritative-capable source. Any degraded state (partial / stale /
    malformed / mixed / absent) falls back to heuristic, labelled.
    """
    state, reason = _classify_shipwright(root / ".shipwright")
    detected = _MODE_AUTHORITATIVE if state in _AUTHORITATIVE_STATES else _MODE_HEURISTIC
    if detected == _MODE_AUTHORITATIVE:
        reason = (
            "authoritative source detected — ingestion lands in G4; "
            "grading heuristically for now"
        )
    return RoutingDecision(
        detected_mode=detected,
        effective_mode=_MODE_HEURISTIC,
        state=state,
        reason=reason,
    )
