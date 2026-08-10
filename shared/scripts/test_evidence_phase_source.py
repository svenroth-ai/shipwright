"""Phase-run provenance contract for ``test-evidence.md``.

``Source-State`` names the latest work event and is intentionally broad.  I2
instead needs to know which *phase invocation* produced a test-evidence render,
so it consumes this separate, phase-scoped marker.  The latest matching event is
authoritative even when its identity is malformed: never fall back to an older
run and silently validate the wrong invocation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from source_state import safe_run_id


PHASE_SOURCE_PREFIX = "Test-Evidence-Phase:"
I2_PHASES = ("build", "test", "iterate")
PHASE_SOURCE_STRIP_RE = re.compile(r"(?m)^Test-Evidence-Phase:.*\n?")
_PHASE_SOURCE_RE = re.compile(r"^Test-Evidence-Phase:\s+phase=(\S+)\s+run=(\S+)\s*$")


@dataclass(frozen=True)
class PhaseRunSource:
    """The phase and run identity named by a test-evidence render."""

    phase: str
    run_id: str


def _phase_of(event: dict[str, Any]) -> str | None:
    return safe_run_id(event.get("phase") or event.get("source"))


def _detail_object(detail: Any) -> dict[str, Any] | None:
    if isinstance(detail, dict):
        return detail
    if not isinstance(detail, str):
        return None
    try:
        parsed = json.loads(detail)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def latest_phase_source(
    events: Iterable[dict[str, Any]], phase: str,
) -> PhaseRunSource | None:
    """Resolve the latest ``phase_started`` identity for ``phase``.

    Events are ordered by their timestamp field, as the existing phase-event
    helpers are.  Once the latest matching event is selected, an absent or bad
    ``detail.runId`` returns ``None`` instead of consulting an older event.
    """
    wanted_phase = safe_run_id(phase)
    if wanted_phase is None:
        return None
    latest: dict[str, Any] | None = None
    latest_ts = ""
    for event in events:
        if event.get("type") != "phase_started" or _phase_of(event) != wanted_phase:
            continue
        timestamp = str(event.get("ts") or event.get("timestamp") or "")
        # JSONL append order resolves equal timestamps: the later event is the
        # newer phase invocation, including when it is malformed and must cause
        # an explicit unverified result rather than fallback to the old run.
        if latest is None or timestamp >= latest_ts:
            latest, latest_ts = event, timestamp
    if latest is None:
        return None
    detail = _detail_object(latest.get("detail"))
    run_id = safe_run_id(detail.get("runId")) if detail else None
    return PhaseRunSource(wanted_phase, run_id) if run_id else None


def phase_source_line(source: PhaseRunSource) -> str:
    """Render one safe, parseable phase-source header line."""
    phase = safe_run_id(source.phase)
    run_id = safe_run_id(source.run_id)
    if phase is None or run_id is None:
        raise ValueError("phase source requires safe phase and run identifiers")
    return f"{PHASE_SOURCE_PREFIX} phase={phase} run={run_id}"


def parse_phase_source(text: str, phase: str | None = None) -> PhaseRunSource | None:
    """Read an anchored phase-source line, optionally for one exact phase."""
    wanted_phase = safe_run_id(phase) if phase is not None else None
    if phase is not None and wanted_phase is None:
        return None
    if not isinstance(text, str):
        return None
    for line in text.splitlines():
        match = _PHASE_SOURCE_RE.fullmatch(line)
        if match is None:
            continue
        phase, run_id = (safe_run_id(value) for value in match.groups())
        if phase and run_id and (wanted_phase is None or phase == wanted_phase):
            return PhaseRunSource(phase, run_id)
    return None


def stamp_phase_source(path: Path, source: PhaseRunSource) -> None:
    """Add or replace the phase marker directly below the evidence headers."""
    line = phase_source_line(source)
    phase_pattern = re.compile(
        rf"(?m)^Test-Evidence-Phase:\s+phase={re.escape(source.phase)}\s+.*\n?"
    )
    text = phase_pattern.sub("", path.read_text(encoding="utf-8"))
    lines = text.splitlines(keepends=True)
    insertion = 0
    for index, existing in enumerate(lines):
        if (existing.startswith("Source-State:") or existing.startswith("Generated:")
                or existing.startswith(PHASE_SOURCE_PREFIX)):
            insertion = index + 1
    lines.insert(insertion, line + "\n")
    path.write_text("".join(lines), encoding="utf-8")


def strip_phase_source(text: str) -> str:
    """Remove anchored phase markers for Group E snapshot normalization."""
    return PHASE_SOURCE_STRIP_RE.sub("", text)


__all__ = [
    "PHASE_SOURCE_PREFIX",
    "I2_PHASES",
    "PhaseRunSource",
    "latest_phase_source",
    "parse_phase_source",
    "phase_source_line",
    "stamp_phase_source",
    "strip_phase_source",
]
