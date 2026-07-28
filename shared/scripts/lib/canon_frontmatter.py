"""The canon frontmatter block at the top of ``.shipwright/agent_docs/session_handoff.md``.

Written by ``tools/generate_session_handoff.py --canon-marker``; it records which
run last generated the handoff, so a later reader can tell "this run wrote it"
from "something else did".

Two consumers depend on that answer and must agree on it exactly:

* ``hooks/generate_handoff_on_stop.py`` — skips regeneration when the marker names
  the current run, so a session-end handoff cannot clobber a canon one.
* ``tools/verifiers/handoff_freshness.py`` — the F11 check that the handoff names
  the run currently finishing.

The parser used to be a private copy inside the Stop hook. It moved here in
iterate-2026-07-27-name-the-blocker when the verifier became the second reader:
two implementations of one format drift, and here they would drift on the meaning
of "fresh". Semantics are carried over verbatim — only a top-of-file block that
declares ``canon_generated: true`` counts.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

#: The four fields a canon marker carries, in render order.
CANON_MARKER_KEYS: tuple[str, ...] = ("run_id", "phase", "reason", "timestamp")

#: The frontmatter block itself — anchored at the very start of the file so a
#: fenced YAML sample further down can never be read as the marker.
_CANON_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

#: One ``key: value`` line, with optional surrounding quotes on the value.
_CANON_FIELD_RE = re.compile(r'^(?P<key>[a-z_]+):\s*"?(?P<value>[^"\n]*?)"?\s*$')


def parse_canon_frontmatter(content: str) -> dict[str, str] | None:
    """Return the parsed canon frontmatter dict, or ``None``.

    Only returns a dict if the top-of-file block is present AND it contains
    ``canon_generated: true``. Anything else (no frontmatter, manual YAML for
    other purposes, malformed) is treated as "no canon marker — regenerate as
    normal". Unparsable lines inside an otherwise valid block are skipped rather
    than failing the whole read.
    """
    m = _CANON_FRONTMATTER_RE.match(content)
    if not m:
        return None
    parsed: dict[str, str] = {}
    for line in m.group(1).splitlines():
        fm = _CANON_FIELD_RE.match(line)
        if fm:
            parsed[fm.group("key")] = fm.group("value")
    if parsed.get("canon_generated", "").lower() != "true":
        return None
    return parsed


def marker_value(value: str) -> str:
    """One marker value, made safe to render as ``key: "<value>"``.

    The renderer quotes but does not escape, and the parser assigns keys in file
    order, so a newline inside any value lets later text be read as further
    marker fields. ``reason`` is free text interpolated from skill state
    ("mid-build handoff: section {name}"), and since
    iterate-2026-07-27-c3-phase-history-join ``phase`` and ``timestamp`` decide
    whether C3 passes — so an unescaped newline stopped being a formatting
    quirk and became a way to forge a PASS for a phase that wrote nothing.
    Collapse whitespace (which removes newlines and the ``---`` terminator's
    line of its own) and drop the quote character that would close the value.
    """
    return " ".join(str(value).replace('"', "").split())


def build_marker(*, run_id: str, phase: str, reason: str, timestamp: str) -> dict[str, str]:
    """The marker a phase finalization stamps (C3) — the ONE constructor.

    The ``timestamp`` is supplied by the caller and is deliberately the newest
    EVENT time, not wall clock — see iterate-2026-05-22-deterministic-render-
    timestamps: ``datetime.now()`` here re-dirtied ``session_handoff.md`` on
    every regeneration, leaving the file permanently ``M`` in ``git status``.
    Callers pass a placeholder when the project has no events yet, so the key is
    always present (the Stop hook's conditional-skip keys on its presence).
    Canon C3 compares it against a completion's ``event_at``, which is stamped
    from the same function — see ``lib/phase_history.py``.

    Every value goes through :func:`marker_value`, so the one place that builds a
    marker is also the one place that makes it safe to render.
    """
    return {
        "run_id": marker_value(run_id),
        "phase": marker_value(phase),
        "reason": marker_value(reason),
        "timestamp": marker_value(timestamp),
    }


def carry_forward_marker(handoff_path: Path) -> dict[str, str] | None:
    """The marker already on disk at ``handoff_path``, or ``None``.

    Lets a NON-canon write preserve a marker it would otherwise drop. ``build``
    Step 11 writes a mid-split handoff to the same tracked path without
    ``--canon-marker`` because it is not a canon closure; before
    iterate-2026-07-27-c3-phase-history-join that write erased the marker the
    split-level C3 step had just recorded, and Canon C3 then reported "no canon
    marker" for every phase until the next split closed.

    It carries a marker of ANY age and ANY phase, unchanged — no filtering, and
    deliberately so. This function only preserves what a write was about to
    delete; it never lengthens a marker's life beyond the file it already sits
    in. Dropping a stale marker would not make C3 stricter, it would make C3
    blind: "no canon marker" replaces a verdict C3 can reach from the marker's
    own phase and timestamp with one it cannot. Judging age is C3's job, and
    C3 does it against the phase's completion record — see
    ``tools/verifiers/handoff_phase_canon.py``.

    Returns ``None`` for an absent, unreadable, or unmarked file — carrying
    nothing forward is always safe, whereas INVENTING a marker would let one
    outlive the run that earned it, which is the staleness C3 exists to detect.
    """
    try:
        text = handoff_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    existing = parse_canon_frontmatter(text)
    if not existing:
        return None
    return {key: existing.get(key, "") for key in CANON_MARKER_KEYS}


def marker_timestamp(project_root: Path) -> str:
    """The value a fresh marker stamps: the newest EVENT time, never wall clock.

    Canon C3 compares this against a completion's ``event_at``, which
    ``append_phase_history`` stamps from this same function — see
    ``lib/phase_history.py`` for why the two must share a clock. The placeholder
    keeps the key present on a project with no events yet, because the Stop
    hook's conditional-skip keys on its presence.
    """
    from .events_log import latest_event_dt

    moment = latest_event_dt(project_root)
    return moment.isoformat() if moment is not None else "(no events)"


def resolve_marker_for_write(
    handoff_path: Path,
    *,
    canon_marker: bool,
    preserve: bool,
    run_id: str,
    phase: str,
    reason: str,
    timestamp: Callable[[], str],
) -> tuple[dict[str, str] | None, str]:
    """Which marker a handoff write should carry, and the warning it earned.

    ``timestamp`` is a THUNK, called only when a marker is actually built:
    resolving it eagerly made every handoff write — including the mid-build,
    per-section and F11 writes that pass only ``--preserve-canon-marker`` —
    scan the whole (unbounded) event log for a value they discard.

    Returns ``(marker, warning)``; an empty warning means nothing to report.
    Policy lives here beside the format because both degrade paths turn on what
    the marker MEANS, and a caller re-deriving that is a caller that will get it
    subtly wrong — the preserve branch already did once.

    Two ways a requested marker is refused rather than written wrong:

    * no ``run_id`` — the Stop hook's skip and the F11 check both key on it;
    * no ``phase`` — Canon C3 keys on it, and an empty one routes every phase
      to "(unnamed) wrote the note, so this phase left none of its own", a
      misattributed WARN no remedy clears.

    Preservation is for a write that never ASKED for a marker. Keying it on
    "no marker was produced" would also fire on the two refusals above, handing
    the previous run's marker to a write that just failed to earn one — the
    exact staleness C3 exists to detect, laundered into a pass.
    """
    if canon_marker:
        # Validate what will LAND on disk, not what was passed: `--phase '"'`
        # survives a raw truthiness test and `marker_value` then reduces it to
        # the empty string, stamping exactly the unevaluable marker the refusal
        # below exists to prevent.
        if not marker_value(run_id):
            return None, (
                "WARN: --canon-marker requested but SHIPWRIGHT_RUN_ID is unset — "
                "writing handoff WITHOUT canon frontmatter (Stop hook will regenerate "
                "normally). Set SHIPWRIGHT_RUN_ID before calling this to enable the skip."
            )
        if not marker_value(phase):
            return None, (
                "WARN: --canon-marker requested but --phase is empty — writing handoff "
                "WITHOUT canon frontmatter (Stop hook will regenerate normally). Canon "
                "C3 keys on the phase; a marker without one is unevaluable. "
                "Pass --phase <phase>."
            )
        return build_marker(
            run_id=run_id, phase=phase, reason=reason, timestamp=timestamp(),
        ), ""
    if preserve:
        return carry_forward_marker(handoff_path), ""
    return None, ""


__all__ = [
    "CANON_MARKER_KEYS",
    "build_marker",
    "carry_forward_marker",
    "marker_timestamp",
    "marker_value",
    "parse_canon_frontmatter",
    "resolve_marker_for_write",
]
