#!/usr/bin/env python3
"""Durable follow-up for a unit that was red in parallel and GREEN when run alone.

The F0 suite runner re-runs such a unit alone and treats THAT verdict as
authoritative, so the gate stays green. That is deliberate: the re-run exists so a
race cannot false-STOP the gate. But the observation is real and expensive to
reproduce, and until this module existed it was only a `print` - it died with the
session that made it, and a race nobody wrote down comes back when it is expensive.

`suite_report.py` composes what the card says; this module owns the side effects:

- the entry lands in the run's TRACKED `.shipwright/triage.jsonl` (never the outbox),
  the same routing as the other phase-invoked emitters (security / performance / F1).
  F6 already stages that path, so it ships in the iterate PR and reaches `main`;
- one OPEN entry per unit (`f0-race:<unit-id>`, commit-independent, window-less), and
  it is NEVER auto-dismissed: a race is intermittent, so one clean parallel run is not
  evidence it is gone. Dismissing it on the next green run would re-create the very
  "the record disappears" failure this closes. An entry an operator already CLOSED
  does not suppress a fresh one (`triage` dedups against OPEN items only);
- the APPEND is the authority on whether the record exists (it fsyncs inside the
  triage writer's own lock, which also serialises concurrent producers). The read-back
  only resolves the id of an already-open entry for the console line, so a damaged or
  unreadable store can never turn a green gate red;
- nothing here classifies. `run_test_suite.unrecorded_races()` decides what counts as
  a race and passes the confirmed list in, so there is exactly one owner of that rule.
"""

from __future__ import annotations

import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Resolve `shared/` so the sibling imports under the SAME dotted name the runner and
# the tests use (scripts.tools.*) -> one module object, not two (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_report import (  # noqa: E402
    dedup_key, entry_detail, entry_title, facts, launch_payload,
)
from scripts.tools.suite_report import suite_command as default_suite_command  # noqa: E402

#: producer identity on the wire (schema: shared/schemas/triage_item.schema.json)
TRIAGE_SOURCE = "f0-suite"
#: high (-> P1) on purpose: the gate declined to stop, so this entry is the ONLY
#: record that anything was observed. A P2 in a long backlog is "skimmed past",
#: which is the exact failure mode being closed.
SEVERITY = "high"
KIND = "bug"


@dataclass
class RaceFollowupReport:
    """What became of each confirmed race. `recorded` and `failed` are disjoint."""

    #: sentinel: recorded, but the id could not be read back for display
    UNRESOLVED = "<open, id unresolved>"

    #: unit id -> its durable handle (a `trg-` id, or UNRESOLVED)
    recorded: dict[str, str] = field(default_factory=dict)
    #: unit id -> why no handle could be established
    failed: dict[str, str] = field(default_factory=dict)


def resolve_commit(project_root) -> str | None:
    """Best-effort HEAD sha. A missing git, a non-repo root or a hang yields no
    commit - never an exception, never a failed run (the sha is evidence, not a key).
    `encoding="utf-8"`: `text=True` alone decodes with the locale codec (cp1252)."""
    try:
        proc = subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["git", "rev-parse", "HEAD"], cwd=str(project_root), shell=False,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = (proc.stdout or "").strip()
    return sha if proc.returncode == 0 and sha else None


def _load_triage():
    """Lazy import of the triage store API.

    `shared/scripts` is inserted at call time so this file stays cheap to import from
    the runner, and so the top-level `triage` name matches every other producer
    (ADR-045: triage.py lives OUTSIDE `lib/` precisely so it can be imported this way
    without colliding on `sys.modules['lib']`).
    """
    scripts_dir = str(Path(__file__).resolve().parents[1])  # shared/scripts
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import triage  # noqa: PLC0415
    return triage


def _open_ids(triage, project_root, keys: set[str]) -> dict[str, str]:
    """dedupKey -> id, for OPEN entries of THIS producer only.

    Exception-guarded on purpose: the append already proved the record exists, so a
    damaged or unreadable store must not turn a green gate red (external review R1).
    """
    try:
        items = triage.read_all_items(project_root)
    except Exception:  # noqa: BLE001 - display-only lookup, never a verdict
        return {}
    return {
        item["dedupKey"]: item["id"] for item in items
        if item.get("source") == TRIAGE_SOURCE
        and item.get("status") == "triage"
        and item.get("dedupKey") in keys
        and isinstance(item.get("id"), str)
    }


def emit_race_followups(project_root, races, xdist_ids, *,
                        run_id: str | None = None,
                        commit: str | None = None,
                        suite_command: str = "") -> RaceFollowupReport:
    """Record one durable follow-up per CONFIRMED race. Never raises.

    Every failure degrades into a REPORTED failure rather than an exception: the
    caller turns an unrecorded race into an explicit stop, and a traceback here would
    discard the whole suite's results along with it.
    """
    report = RaceFollowupReport()
    if not races:
        return report
    suite_cmd = suite_command or default_suite_command(project_root, run_id)
    try:
        triage = _load_triage()
    except Exception as exc:  # noqa: BLE001
        for res in races:
            report.failed[res.unit_id] = f"triage API unavailable ({type(exc).__name__})"
        return report

    suppressed: dict[str, str] = {}
    for res in races:
        f = facts(res, xdist_ids)
        key = dedup_key(f)
        try:
            new_id = triage.append_triage_item_idempotent(
                project_root,
                source=TRIAGE_SOURCE, severity=SEVERITY, kind=KIND,
                title=entry_title(f), detail=entry_detail(f, suite_cmd),
                dedup_key=key,
                run_id=run_id, commit=commit,
                match_commit=False,      # the unit races, not the commit
                window_seconds=None,     # one open entry until an operator closes it
                launch_payload=launch_payload(f, suite_cmd),
                suite_id=f.unit_key,
                evidence_path=getattr(res, "evidence_path", None),
                to_outbox=False,         # tracked: F6 stages it, it ships in the PR
            )
        except Exception as exc:  # noqa: BLE001 - a lost record must be REPORTED
            report.failed[res.unit_id] = f"append failed ({type(exc).__name__})"
            continue
        if new_id:
            report.recorded[res.unit_id] = new_id
        else:
            suppressed[res.unit_id] = key  # an OPEN entry already exists

    if suppressed:
        found = _open_ids(triage, project_root, set(suppressed.values()))
        for unit_id, key in suppressed.items():
            report.recorded[unit_id] = found.get(key, RaceFollowupReport.UNRESOLVED)
    return report
