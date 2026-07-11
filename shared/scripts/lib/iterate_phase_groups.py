#!/usr/bin/env python3
"""Iterate-Rail phase-timing SSoT + boundary-mark sidecar (M-Pre-1 iterate half).

Follow-up to campaign monorepo-wow-usability-2026-07-10 sub-iterate B1
(triage trg-8efeb3d7). B1 gave the *pipeline* rail real per-phase durations via
paired ``phase_started``/``phase_completed`` events. The *iterate* flow writes a
single ``work_completed`` event at F5b, and its ~20 phases are LLM-executed
SKILL steps — not program-orchestrated boundaries — so there is no cheap
deterministic per-phase timestamp.

Design (user-approved: "5-step real durations"): the iterate emits one
lightweight *mark* as it crosses each of the 5 WebUI Iterate-Rail group
boundaries into a gitignored per-run sidecar
``<project_root>/.shipwright/agent_docs/iterates/<run_id>.phase_timings.jsonl``.
``finalize_iterate.py`` (F5b) reads the sidecar, computes per-group
``{phase, started, duration_ms}`` and folds it — additively — into the single
``work_completed`` event as ``phase_timings``. A run predating this simply has no
sidecar; the WebUI reads the field if present and degrades gracefully.

Boundary (touches_io_boundary):
    Producer: ``iterate_phase_timing.py mark`` (SKILL boundary calls).
    File:     ``<run_id>.phase_timings.jsonl`` — GITIGNORED transient run state,
              sibling of ``<run_id>.plan.json`` (session_plan.py).
    Consumer: ``finalize_iterate`` -> ``work_completed.phase_timings`` -> WebUI.

The 5 group ids are the SAME vocabulary as
``session_plan._PHASE_CATALOG`` (concept §5a: scope -> build -> review -> test
-> finalize), so the WebUI can join phases-per-group (Plan-Card) with
duration-per-group (this). ``tests/test_iterate_phase_timing.py`` pins the two
against drift — session_plan is the plugin-local Plan-Card catalog, this is the
shared timing SSoT; they must stay in lock-step.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ordered SSoT — the 5 WebUI Iterate-Rail display nodes (concept §5a). Pinned to
# session_plan._PHASE_CATALOG's group order by the test suite.
ITERATE_PHASE_GROUPS: tuple[str, ...] = ("scope", "build", "review", "test", "finalize")


def sidecar_path(project_root, run_id: str) -> Path:
    """On-disk location of the phase-timing sidecar for ``run_id``.

    ``Path(run_id).name`` strips any directory components so a crafted run_id
    (e.g. ``../../etc/x``) can never escape the iterates directory — mirrors
    ``session_plan.plan_path`` defense-in-depth.
    """
    safe = Path(str(run_id)).name
    return (
        Path(project_root) / ".shipwright" / "agent_docs" / "iterates"
        / f"{safe}.phase_timings.jsonl"
    )


def read_marks(project_root, run_id: str) -> list[dict]:
    """Read boundary marks for ``run_id``. Returns ``[{"phase", "ts"}, ...]``.

    File-order, first-wins per group (a group starts once; a re-mark on resume is
    ignored). Missing sidecar -> ``[]``. Malformed / off-vocabulary lines are
    skipped, never fatal — a partial sidecar still yields the groups it has.
    """
    path = sidecar_path(project_root, run_id)
    if not path.exists():
        return []
    seen: set[str] = set()
    marks: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        phase = obj.get("phase")
        ts = obj.get("ts")
        if phase not in ITERATE_PHASE_GROUPS or not isinstance(ts, str):
            continue
        if phase in seen:
            continue
        seen.add(phase)
        marks.append({"phase": phase, "ts": ts})
    return marks


def append_mark(project_root, run_id: str, phase: str, ts: str | None = None) -> Path:
    """Append a boundary mark for ``phase``. First-wins: a re-mark is a no-op.

    Raises ``ValueError`` on an unknown group id. ``ts`` defaults to now (UTC,
    ISO-8601). Single-writer append — the iterate runs one session per run_id.

    ``run_id`` is trusted at this lib boundary: path containment
    (``sidecar_path`` -> ``Path(run_id).name``) is the safety guarantee, and the
    canonical-form check (``RUN_ID_STRICT``) is enforced one layer up in the
    ``iterate_phase_timing`` CLI. The only production caller (``fold_into_event``
    via finalize) passes an already-validated run_id.
    """
    if phase not in ITERATE_PHASE_GROUPS:
        raise ValueError(
            f"unknown iterate phase group {phase!r}; expected one of "
            f"{', '.join(ITERATE_PHASE_GROUPS)}"
        )
    path = sidecar_path(project_root, run_id)
    if any(m["phase"] == phase for m in read_marks(project_root, run_id)):
        return path  # first-wins — a group boundary is crossed once
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = ts if ts is not None else datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"phase": phase, "ts": stamp}, ensure_ascii=False) + "\n")
    return path


def _parse_dt(value) -> datetime | None:
    """Parse an ISO-8601 string (or pass a datetime through). Naive -> UTC."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_phase_timings(marks: list[dict], end_ts) -> list[dict]:
    """Fold boundary marks into ``[{phase, started, duration_ms}, ...]``.

    Each group's duration runs until the NEXT chronological mark; the last
    group's end is ``end_ts`` (finalize time). Output is chronological (which,
    for a well-formed run, is the canonical scope..finalize order). Durations are
    non-negative ints (a clock skew / out-of-order mark clamps to 0). Empty marks
    -> ``[]`` (finalize then omits the field entirely — additive).

    ``end_ts`` may be a ``datetime`` or ISO string; a **naive** value is assumed
    UTC (both live callers pass ``datetime.now(timezone.utc)``). Pass UTC — a
    naive *local* time would offset the last group's duration by the UTC offset
    (and clamp to 0 if it goes negative).
    """
    end_dt = _parse_dt(end_ts)
    parsed: list[tuple[datetime, str, str]] = []
    seen: set[str] = set()
    for m in marks:
        phase = m.get("phase")
        started = m.get("ts")
        dt = _parse_dt(started)
        if phase not in ITERATE_PHASE_GROUPS or dt is None or phase in seen:
            continue
        seen.add(phase)
        parsed.append((dt, phase, started))
    parsed.sort(key=lambda t: t[0])

    out: list[dict] = []
    for i, (dt, phase, started) in enumerate(parsed):
        boundary = parsed[i + 1][0] if i + 1 < len(parsed) else end_dt
        if boundary is None:
            duration_ms = 0
        else:
            duration_ms = max(0, int((boundary - dt).total_seconds() * 1000))
        out.append({"phase": phase, "started": started, "duration_ms": duration_ms})
    return out


def normalize_phase_timings(value) -> list[dict]:
    """Validate a ``phase_timings`` block (parity with fr_impact validation).

    Requires a list of ``{phase in groups, started: str, duration_ms: int>=0}``.
    Raises ``ValueError`` on any malformed entry — a bad block is a producer bug,
    fail closed rather than write a corrupt event. Returns the block unchanged.
    """
    if not isinstance(value, list):
        raise ValueError("phase_timings must be a list")
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError(f"phase_timings entry must be an object: {entry!r}")
        phase = entry.get("phase")
        if phase not in ITERATE_PHASE_GROUPS:
            raise ValueError(f"phase_timings entry has unknown group {phase!r}")
        if not isinstance(entry.get("started"), str):
            raise ValueError(f"phase_timings[{phase}] 'started' must be a string")
        dur = entry.get("duration_ms")
        if isinstance(dur, bool) or not isinstance(dur, int) or dur < 0:
            raise ValueError(
                f"phase_timings[{phase}] 'duration_ms' must be a non-negative int"
            )
    return value


def fold_into_event(event: dict, project_root, run_id: str) -> dict:
    """Fold this run's boundary-mark durations into ``event['phase_timings']``.

    Called by ``finalize_iterate`` (F5b). Best-effort + additive: computes from
    the sidecar, validates via :func:`normalize_phase_timings`, and sets the
    field only when non-empty and not already present. A missing / empty sidecar
    (or any error) leaves ``event`` unchanged — timing is a non-load-bearing
    WebUI nicety and must never break finalize. Returns ``event`` for chaining.
    """
    if "phase_timings" in event:
        return event
    try:
        timings = compute_phase_timings(
            read_marks(project_root, run_id), datetime.now(timezone.utc)
        )
        if timings:
            event["phase_timings"] = normalize_phase_timings(timings)
    except Exception as exc:  # noqa: BLE001 — timing must never break finalize
        print(
            f"[iterate_phase_groups] phase_timings fold skipped: {exc}",
            file=sys.stderr,
        )
    return event
