#!/usr/bin/env python3
"""Append a structured event to shipwright_events.jsonl.

Atomic, file-locked, deduplicated event writer. Used by Build, Iterate,
Orchestrator, and Test phases to record work into the unified event log.

Usage:
    uv run record_event.py --project-root <path> --type <event_type> [options]

Event types:
    task_created     -- A new task/issue was created (user or pipeline)
    work_completed   -- A build section or iterate change finished
    phase_started    -- Pipeline phase began
    phase_completed  -- Pipeline phase validated and complete
    split_completed  -- All sections of a split are done
    test_run         -- Full test suite execution
    event_amended    -- Correction of a previous event

Never CLI/smoke-verify against a live project: ``--project-root .`` appends
real events that surface as phantom work in the RTM (the 2026-05-21 campaign
leaked two; one neutralized via ``event_amended``). Use ``--project-root
"$(mktemp -d)"``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Wire up shared/scripts so `lib.events_log` resolves whether this file is
# run as a script (`uv run .../record_event.py`) or imported as a module
# (`tools.record_event` via finalize_iterate, `scripts.tools.record_event`
# via tests) — both invocation paths are exercised in CI.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402
# Re-export the single tolerant event-log reader (SSOT in lib.config) so module
# attributes `record_event.read_events` / `from record_event import read_events`
# keep resolving for callers and the F14 lifecycle test. Direction tools->lib.
from lib.config import read_events  # noqa: E402,F401 — re-exported SSOT
# Cross-platform append-log mutex (impl in lib/file_lock.py); aliased to the
# historical private name so `record_event._FileLock` stays monkeypatchable
# (F14 lifecycle test) and the `with _FileLock(...)` call sites resolve it.
from lib.file_lock import FileLock as _FileLock  # noqa: E402
# SSOT for FR-classification (BP-1). The gate below and the compliance
# Control-Grade adapter share these so "classified" (gate) and "traced" (grade)
# can never drift. Aliased to the historical private names so existing call
# sites + tests (record_event._CHANGE_TYPE_VALUES, ._is_valid_none_reason, …)
# keep resolving.
from lib.fr_classification import (  # noqa: E402
    CHANGE_TYPE_VALUES as _CHANGE_TYPE_VALUES,
    NONE_REASON_MAX_LEN as _NONE_REASON_MAX_LEN,
    is_behavior_affecting as _is_behavior_affecting,
    is_non_empty_fr_list as _is_non_empty_fr_list,
    is_valid_none_reason as _is_valid_none_reason,
    normalize_fr_impact as _normalize_fr_impact,
)

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def generate_event_id() -> str:
    """Generate a unique event ID: evt- + 8 hex chars from UUID4."""
    return f"evt-{uuid4().hex[:8]}"


def _non_negative_int(value: str) -> int:
    """argparse type guard — reject negatives + non-integer strings.

    Iterate B.3 (ADR-057) — reviewer-flagged H3: layer counts must be
    non-negative or the downstream FAIL-triage producer renders
    nonsense (`-2/0 failing`). Argparse's default ``type=int`` accepts
    negatives; this wrapper raises ``ArgumentTypeError`` so invalid
    inputs surface at the CLI boundary, not deep in the producer.
    """
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"expected non-negative integer, got {value!r}") from exc
    if n < 0:
        raise argparse.ArgumentTypeError(f"expected non-negative integer, got {n}")
    return n


def _parse_changed_files(raw: str) -> list[str]:
    """Parse the `--changed-files` argument.

    Accepts either:
      - A JSON array literal:  '["a.py","b.py"]'
      - A comma-separated list: 'a.py,b.py'
      - A newline-separated list (e.g. from `git diff --name-only` piped
        through `tr '\\n' ','`): one path per line.

    Empty / whitespace-only entries are dropped. Backslashes are
    normalized to forward slashes so cross-platform consumers
    (`is_io_boundary_change`) see a uniform shape.
    """
    if not raw:
        return []
    raw = raw.strip()
    # JSON-array form.
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    str(p).replace("\\", "/").strip()
                    for p in parsed
                    if str(p).strip()
                ]
        except json.JSONDecodeError:
            # Fall through to comma-split below.
            pass
    # Comma- or newline-separated.
    parts: list[str] = []
    for line in raw.replace("\r", "").splitlines():
        for chunk in line.split(","):
            chunk = chunk.strip()
            if chunk:
                parts.append(chunk.replace("\\", "/"))
    return parts


def has_commit(project_root: Path, commit: str, section: str | None = None) -> bool:
    """Check if a work_completed event with this commit (and section) already exists.

    When *section* is provided, deduplication checks (section, commit) tuple.
    This prevents collapsing multiple sections that share the same commit hash.
    Without section, falls back to commit-only check (backwards compat).
    """
    for event in read_events(project_root):
        if event.get("type") == "work_completed" and event.get("commit") == commit:
            if section is None or event.get("section") == section:
                return True
    return False


def has_phase_event(project_root: Path, phase: str) -> bool:
    """Check if a phase_completed event for this phase already exists."""
    for event in read_events(project_root):
        if event.get("type") == "phase_completed" and event.get("phase") == phase:
            return True
    return False


def build_event(args: argparse.Namespace) -> dict:
    """Build the event dict from parsed CLI arguments."""
    event: dict = {
        "v": SCHEMA_VERSION,
        "id": generate_event_id(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": args.type,
    }

    # Session ID from environment
    session = os.environ.get("SHIPWRIGHT_SESSION_ID", "")
    if session:
        event["session"] = session

    # Type-specific fields
    if args.type == "task_created":
        event["description"] = args.description
        if args.intent:
            event["intent"] = args.intent
        if args.priority:
            event["priority"] = args.priority

    elif args.type == "work_completed":
        event["source"] = args.source
        event["commit"] = args.commit
        # Tests block
        tests: dict = {}
        if args.tests_passed is not None:
            tests["passed"] = args.tests_passed
        if args.tests_total is not None:
            tests["total"] = args.tests_total
        if args.tests_new is not None:
            tests["new"] = args.tests_new
        if args.tests_modified is not None:
            tests["modified"] = args.tests_modified
        if args.e2e_run is not None:
            tests["e2e_run"] = args.e2e_run
        if tests:
            event["tests"] = tests
        # FRs
        if args.affected_frs:
            event["affected_frs"] = [fr.strip() for fr in args.affected_frs.split(",") if fr.strip()]
        # Non-FR change classification (Phase 0 prep for Iterate C.1 FR-gate).
        # Read-side only at this stage — no validation. C.1 will enforce
        # "affected_frs OR change_type+none_reason" at finalize.
        if args.change_type:
            event["change_type"] = args.change_type
        if args.none_reason:
            event["none_reason"] = args.none_reason
        # Build-specific
        if args.split:
            event["split"] = args.split
        if args.section:
            event["section"] = args.section
        # Review block
        review: dict = {}
        if args.review_type:
            review["type"] = args.review_type
        if args.review_findings is not None:
            review["findings"] = args.review_findings
        if args.review_fixed is not None:
            review["fixed"] = args.review_fixed
        if review:
            event["review"] = review
        # Iterate-specific
        if args.intent:
            event["intent"] = args.intent
        if args.description:
            event["description"] = args.description
        if args.new_frs:
            event["new_frs"] = [fr.strip() for fr in args.new_frs.split(",") if fr.strip()]
        if args.spec_updated:
            event["spec_updated"] = args.spec_updated
        # Spec-impact classification (iterate-2026-05-16-spec-impact-gate).
        # Enforced for feature/change iterates by _spec_impact_gate_error.
        if args.spec_impact:
            event["spec_impact"] = args.spec_impact
        if args.spec_impact_justification:
            event["spec_impact_justification"] = args.spec_impact_justification
        # BP-2: per-FR behavior impact map (validated via the shared SSOT).
        if args.fr_impact:
            event["fr_impact"] = _normalize_fr_impact(json.loads(args.fr_impact))
        if args.adr_id:
            event["adr_id"] = args.adr_id
        # E spec MEDIUM-D1: changed_files is required by D's drift detection
        # (`is_io_boundary_change`) and HIGH-5's round-trip heuristic
        # scoping. Accept either a comma-separated string or a JSON array.
        if args.changed_files:
            event["changed_files"] = _parse_changed_files(args.changed_files)

    elif args.type in ("phase_started", "phase_completed",
                       "phase_failed", "stale_stop_rejected"):
        # phase_failed + stale_stop_rejected (deep-audit F15): the phase Stop hook
        # emits these for a failed phase / an owner-CAS-rejected stale stop. They
        # carry phase + (JSON) detail like phase_completed but are NOT phase-deduped.
        event["phase"] = args.phase
        if args.detail:
            event["detail"] = args.detail

    elif args.type == "split_completed":
        event["split"] = args.split

    elif args.type == "test_run":
        if args.trigger:
            event["trigger"] = args.trigger
        layers: dict = {}
        # Iterate B.3 (ADR-057): test_run events carry first-class
        # `integration` and `pgtap` keys alongside `unit` / `e2e`. The
        # optional ``failed`` key inside each layer lets producers
        # express explicit failure counts so the downstream FAIL-triage
        # producer doesn't mistake skipped tests for failures
        # (reviewer-flagged H1).
        for layer_name, passed, total, failed in (
            ("unit",        args.unit_passed,        args.unit_total,        args.unit_failed),
            ("integration", args.integration_passed, args.integration_total, args.integration_failed),
            ("pgtap",       args.pgtap_passed,       args.pgtap_total,       args.pgtap_failed),
            ("e2e",         args.e2e_passed,         args.e2e_total,         args.e2e_failed),
        ):
            if passed is None and total is None and failed is None:
                continue
            entry: dict = {}
            if passed is not None:
                entry["passed"] = passed
            if total is not None:
                entry["total"] = total
            if failed is not None:
                entry["failed"] = failed
            # Reviewer-flagged H3 + M2: validate cross-field invariants
            # at the CLI boundary so corrupt event payloads never land
            # on disk.
            if "passed" in entry and "total" in entry and entry["passed"] > entry["total"]:
                raise ValueError(
                    f"{layer_name} passed ({entry['passed']}) > total ({entry['total']})"
                )
            if "failed" in entry and "total" in entry and entry["failed"] > entry["total"]:
                raise ValueError(
                    f"{layer_name} failed ({entry['failed']}) > total ({entry['total']})"
                )
            layers[layer_name] = entry
        if args.smoke_status:
            layers["smoke"] = {"status": args.smoke_status}
        if layers:
            event["layers"] = layers

    elif args.type == "event_amended":
        event["amends"] = args.amends
        if args.fields:
            event["fields"] = json.loads(args.fields)

    elif args.type == "compliance_update_failed":
        if args.phase:
            event["phase"] = args.phase
        if args.detail:
            event["detail"] = args.detail

    elif args.type == "pipeline_migration":
        if args.detail:
            event["detail"] = args.detail

    elif args.type == "adopted":
        # Written once per /shipwright-adopt run. Fields are best-effort:
        # the skill-layer populates them from snapshot/run-config.
        if args.source:
            event["source"] = args.source
        if args.commit:
            event["commit_at_adoption"] = args.commit
        if args.detail:
            event["detail"] = args.detail

    return event


def append_event(project_root: Path, event: dict) -> str:
    """Atomically append an event to the JSONL log. Returns the event ID.

    Unconditional append — no dedup. Direct callers are single-writer
    (e.g. ``finalize_iterate`` emits a run-id-idempotent ``work_completed``).
    Concurrent dedup (``phase_completed`` / by-commit) lives in
    ``append_event_idempotent`` (deep-audit F14); the CLI routes through it.

    Resolves the per-tree event log via ``resolve_events_path``. Under a
    ``/shipwright-iterate`` run this is the worktree-local copy: the append
    lands there and F6 commits it, so the event ships through the iterate PR
    rather than being orphaned in the main tree. The ``.lock`` mutex is derived
    from the resolved path. See ``lib.events_log`` for the model + history.
    """
    path = resolve_events_path(project_root)
    lock_path = path.with_name(path.name + ".lock")
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(lock_path):
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())

    return event["id"]


def append_event_idempotent(
    project_root: Path,
    event: dict,
    *,
    deduplicate_by_commit: bool = False,
) -> tuple[str | None, dict | None]:
    """Scan-for-duplicate then append **inside one ``_FileLock``** (deep-audit F14).

    The CLI used to run the ``phase_completed`` / ``--deduplicate-by-commit`` scan
    BEFORE ``append_event`` took the lock, so two concurrent phase-Stop firings
    could both pass the scan before either append landed → permanent duplicate
    events. This mirrors ``triage.append_triage_item_idempotent``: the dedup
    decision and the write share a single critical section, so a second writer
    that wins the lock sees the first's append and skips.

    Returns ``(event_id, None)`` on append, or ``(None, skip)`` where ``skip`` is
    a JSON-serialisable dict describing the duplicate (``reason`` + keys) so the
    caller can render the existing ``skipped`` CLI output verbatim.
    """
    path = resolve_events_path(project_root)
    lock_path = path.with_name(path.name + ".lock")
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(lock_path):
        # Dedup scan UNDER the lock — readers see every prior append.
        if deduplicate_by_commit and event.get("commit"):
            section = event.get("section")
            if has_commit(project_root, event["commit"], section=section):
                return None, {"reason": "duplicate_commit",
                              "commit": event["commit"], "section": section}
        if event.get("type") == "phase_completed" and event.get("phase"):
            if has_phase_event(project_root, event["phase"]):
                return None, {"reason": "duplicate_phase", "phase": event["phase"]}
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())

    return event["id"], None


def attach_commit_to_event(
    project_root: Path,
    event_id: str,
    commit_sha: str,
) -> bool:
    """Patch the ``commit`` field of a previously-recorded event in place.

    **Legacy / non-worktree only.** The standard ``/shipwright-iterate`` worktree
    flow no longer calls this: events.jsonl is committed by F6 within the
    worktree, so an in-place SHA patch *after* F6 would re-dirty the
    just-committed file. That flow ships the event with ``commit=""`` (linkage
    via the F6 commit's ``Run-ID:`` footer + the event's ``adr_id == run_id``).
    See iterate-2026-05-29-events-jsonl-worktree-commit. When used (out-of-band
    recording), the SHA is backfilled without touching any other line, without
    breaking corrupt-line tolerance, and without re-ordering events.

    Atomicity: writes to ``shipwright_events.jsonl.tmp`` then renames
    over the live log under the same ``.lock`` mutex as ``append_event``.
    A crash mid-write leaves the original log readable.

    Returns ``True`` if the event was found and patched, ``False`` if:
      * the log doesn't exist (no events recorded yet),
      * no line parses to JSON with ``id == event_id``.

    Worktree-aware via ``resolve_events_path``.
    """
    path = resolve_events_path(project_root)
    if not path.exists():
        return False

    lock_path = path.with_name(path.name + ".lock")
    tmp_path = path.with_name(path.name + ".tmp")

    patched = False
    with _FileLock(lock_path):
        # Read every line, decide line-by-line whether to rewrite or
        # pass through verbatim (corrupt lines included).
        with path.open("r", encoding="utf-8", newline="") as fp:
            lines = fp.readlines()

        new_lines: list[str] = []
        for raw in lines:
            if patched:
                # Already patched — pass everything else through verbatim.
                new_lines.append(raw)
                continue
            stripped = raw.rstrip("\n").rstrip("\r")
            if not stripped:
                new_lines.append(raw)
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                # Corrupt line — preserve verbatim (matches read_events tolerance).
                new_lines.append(raw)
                continue
            if isinstance(event, dict) and event.get("id") == event_id:
                event["commit"] = commit_sha
                # Re-serialize WITHOUT trailing whitespace; preserve the
                # original line terminator if it was a \n (default for
                # append_event-written lines).
                new_lines.append(
                    json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
                patched = True
            else:
                new_lines.append(raw)

        if not patched:
            # Nothing to do — leave the log untouched.
            return False

        with tmp_path.open("w", encoding="utf-8", newline="") as fp:
            fp.writelines(new_lines)
            fp.flush()
            os.fsync(fp.fileno())

        os.replace(tmp_path, path)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record a Shipwright event")
    p.add_argument("--project-root", required=True, help="Project root directory")
    p.add_argument("--type", required=True,
                   choices=["task_created", "work_completed", "phase_started",
                            "phase_completed", "phase_failed", "stale_stop_rejected",
                            "split_completed", "test_run",
                            "event_amended",
                            "compliance_update_failed", "pipeline_migration",
                            "adopted"],
                   help="Event type")

    # work_completed
    p.add_argument("--source", help="Event source: build | iterate")
    p.add_argument("--commit", help="Git commit hash")
    p.add_argument("--split", help="Split name (e.g. 01-foundation)")
    p.add_argument("--section", help="Section name (e.g. 01-project-setup)")
    p.add_argument("--intent", help="Iterate intent: feature | change | bug")
    p.add_argument("--description", help="Task or iterate change description")
    p.add_argument("--priority", help="Task priority: high | medium | low")
    p.add_argument("--affected-frs", help="Comma-separated FR IDs")
    p.add_argument("--new-frs", help="Comma-separated new FR IDs")
    p.add_argument("--change-type", choices=["docs", "tooling", "compliance", "infra"],
                   help="Non-FR change classification: docs | tooling | compliance | infra. "
                        "Use when an iterate touches no FR (test infra, scanner fixes, build "
                        "pipeline, doc-only). Iterate C.1 will require this OR --affected-frs "
                        "for every iterate work_completed event.")
    p.add_argument("--none-reason",
                   help="One-line justification for --change-type. Required by Iterate C.1 "
                        "FR-gate when --affected-frs is empty.")
    p.add_argument("--spec-updated", help="Path to updated spec file")
    p.add_argument("--spec-impact", choices=["add", "modify", "remove", "none"],
                   help="Iterate spec-impact classification (feature/change): "
                        "add=new FR appended, modify=existing FR changed, "
                        "remove=FR retired, none=no spec change (then "
                        "--spec-impact-justification is required).")
    p.add_argument("--spec-impact-justification",
                   help="Why a feature/change iterate touches no FR. "
                        "Required when --spec-impact is none.")
    p.add_argument("--fr-impact",
                   help="JSON {FR-id: add|modify|remove|none} per-FR behavior impact (BP-2)")
    p.add_argument("--adr-id", help="ADR reference (e.g. ADR-055)")
    p.add_argument(
        "--changed-files",
        help=(
            "Files actually changed in this commit. Required by D's "
            "boundary drift detection (E spec MEDIUM-D1). Accepts a JSON "
            "array literal, comma-separated list, or newline-separated "
            "list. Typical source: `git diff --name-only ${prev}..${commit}`."
        ),
    )

    # Tests
    p.add_argument("--tests-passed", type=int, help="Tests passed count")
    p.add_argument("--tests-total", type=int, help="Tests total count")
    p.add_argument("--tests-new", type=int, help="New tests added")
    p.add_argument("--tests-modified", type=int, help="Tests modified")
    p.add_argument("--e2e-run", type=lambda x: x.lower() == "true", help="E2E tests run (true/false)")

    # Review
    p.add_argument("--review-type", help="Review type: self-review | full-review")
    p.add_argument("--review-findings", type=int, help="Review findings count")
    p.add_argument("--review-fixed", type=int, help="Review findings fixed count")

    # phase_started / phase_completed
    p.add_argument("--phase", help="Phase name (project, plan, build, ...)")
    p.add_argument("--detail", help="Phase detail (e.g. deploy URL, PR URL)")

    # test_run
    p.add_argument("--trigger", help="What triggered the test run")
    p.add_argument("--unit-passed",        type=_non_negative_int, help="Unit tests passed")
    p.add_argument("--unit-total",         type=_non_negative_int, help="Unit tests total")
    p.add_argument("--unit-failed",        type=_non_negative_int, help="Unit tests failed (Iterate B.3 — explicit fail count; otherwise inferred as total-passed)")
    p.add_argument("--integration-passed", type=_non_negative_int, help="Integration tests passed (Iterate B.3)")
    p.add_argument("--integration-total",  type=_non_negative_int, help="Integration tests total (Iterate B.3)")
    p.add_argument("--integration-failed", type=_non_negative_int, help="Integration tests failed (Iterate B.3)")
    p.add_argument("--pgtap-passed",       type=_non_negative_int, help="pgTAP tests passed (Iterate B.3)")
    p.add_argument("--pgtap-total",        type=_non_negative_int, help="pgTAP tests total (Iterate B.3)")
    p.add_argument("--pgtap-failed",       type=_non_negative_int, help="pgTAP tests failed (Iterate B.3)")
    p.add_argument("--e2e-passed",         type=_non_negative_int, help="E2E tests passed")
    p.add_argument("--e2e-total",          type=_non_negative_int, help="E2E tests total")
    p.add_argument("--e2e-failed",         type=_non_negative_int, help="E2E tests failed (Iterate B.3)")
    p.add_argument("--smoke-status", help="Smoke test status: pass | fail")

    # event_amended
    p.add_argument("--amends", help="ID of event to amend")
    p.add_argument("--fields", help="JSON string of fields to override")

    # Deduplication
    p.add_argument("--deduplicate-by-commit", action="store_true",
                   help="Skip if a work_completed event with same commit exists")

    return p.parse_args(argv)


def _fr_or_change_type_gate_error(event) -> dict | None:
    """Iterate C.1 (ADR-059) FR-gate. Hard-enforce forward-only.

    Every ``work_completed`` event with ``source == "iterate"`` MUST
    record either:

    - ``affected_frs`` non-empty list (or ``new_frs`` non-empty list
      — both forms tie the iterate to one or more FRs), OR
    - ``change_type`` ∈ ``{docs, tooling, compliance, infra}`` AND
      ``none_reason`` is a valid one-line justification (see
      ``_is_valid_none_reason``).

    BP-1 (campaign 2026-06-27) adds one rule: a **behavior-affecting**
    change (``spec_impact`` ∈ ``{add, modify, remove}``) MUST link an FR
    — the no-FR ``change_type`` branch is reserved for behavior-preserving
    changes. Unlike the CLI-only, intent-gated ``_spec_impact_gate_error``,
    this rule runs at finalize too (F5b parity) and is intent-independent.

    Additional consistency check (reviewer-flagged Gemini-M2 /
    OpenAI-L4): if ``change_type`` is present at all (even alongside
    valid FRs), it must be a recognized value. A malformed
    ``change_type`` value is invalid input regardless of FR presence
    — cleaner data on disk.

    Hard-rejects otherwise (returns an error dict; ``main`` exits 1
    and writes nothing to the log).

    Defensive ``.get()`` lookups throughout: a directly-constructed
    event dict missing ``type`` or ``source`` doesn't crash — it
    cleanly bypasses (deterministic behavior for malformed input).

    Read-side stays tolerant: events written before this gate
    landed continue to parse as ``change_type=None`` and
    ``none_reason=None`` (no schema break).

    Build events (``source != "iterate"``) and non-work_completed
    events bypass the gate entirely. Phase 0 of the artifact-polish
    plan retroactively classified every pre-existing iterate event
    so this hard-enforcement is risk-free in the monorepo + webui.

    Scope: the gate runs at the CLI boundary (``record_event.main``)
    AND, since iterate-2026-06-05-fr-linkage-lifecycle, inside
    ``finalize_iterate._record_event`` (the worktree F5b / Stop-hook
    write-path), which calls this same function before its
    ``append_event`` — that bypass is now closed (ADR-059 parity). The
    spec-impact gate (``_spec_impact_gate_error``) stays CLI-only.

    Origin: iterate-2026-05-21-c1-fr-gate-finalize.
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed":
        return None
    if event.get("source") != "iterate":
        return None

    change_type = event.get("change_type")
    none_reason = event.get("none_reason")
    has_frs = (
        _is_non_empty_fr_list(event.get("affected_frs"))
        or _is_non_empty_fr_list(event.get("new_frs"))
    )

    # BP-1 (campaign 2026-06-27): a behavior-affecting change (spec_impact ∈
    # add/modify/remove) MUST link an FR — the no-FR change_type branch is not
    # available to it. Closes two holes the CLI-only, intent-gated
    # _spec_impact_gate_error left open: this runs at finalize too (F5b parity)
    # AND is intent-independent (catches BUG + intent-less events). Without it a
    # behavior change could dodge FR-linkage by self-labeling "tooling", which
    # would also starve BP-2's per-FR reconciliation.
    if _is_behavior_affecting(event.get("spec_impact")) and not has_frs:
        return {
            "error": "fr_gate_behavior_affecting_requires_fr",
            "detail": (
                f"spec_impact={event.get('spec_impact')!r} is behavior-"
                "affecting but no --affected-frs/--new-frs was recorded. A "
                "behavior-affecting change must link the FR(s) it touches; the "
                "no-FR change_type branch is only for behavior-preserving "
                "(spec_impact none) changes. See SKILL.md step F4."
            ),
        }

    # Defense in depth: if change_type is present at all, the FULL
    # pair must be valid — both a recognized value AND a non-empty
    # one-line none_reason. Reviewer-flagged Gemini-M12 (iterate review)
    # + Gemini-M1 (code review): if the operator bothered to classify
    # via change_type, the metadata must be internally consistent. FRs
    # being present too is not a "free pass" to skip the reason.
    if change_type is not None:
        if change_type not in _CHANGE_TYPE_VALUES:
            return {
                "error": "fr_gate_unclassified",
                "detail": (
                    f"change_type={change_type!r} is not one of "
                    f"{list(_CHANGE_TYPE_VALUES)}. See SKILL.md step F4."
                ),
            }
        if not _is_valid_none_reason(none_reason):
            return {
                "error": "fr_gate_unclassified",
                "detail": (
                    "change_type is set but none_reason is missing or "
                    "malformed (require a non-empty single-line string, "
                    f"max {_NONE_REASON_MAX_LEN} chars, no control chars "
                    "except tab). See SKILL.md step F4."
                ),
            }
        # Pair is valid — the change_type path provides classification.
        return None

    # No change_type → must classify via FRs.
    if has_frs:
        return None

    return {
        "error": "fr_gate_unclassified",
        "detail": (
            "An iterate work_completed event must record either "
            "--affected-frs (or --new-frs) with at least one FR, OR "
            "--change-type ∈ {docs, tooling, compliance, infra} together "
            "with --none-reason '<one-line justification, max "
            f"{_NONE_REASON_MAX_LEN} chars, no newlines>'. "
            "See SKILL.md step F4 (FR capture)."
        ),
    }


def _spec_impact_gate_error(event: dict) -> dict | None:
    """Return an error payload if a feature/change iterate work event is not
    spec-impact-classified, else None.

    Every FEATURE/CHANGE iterate either names the FRs it touched
    (``affected_frs`` or ``new_frs``) or records ``spec_impact == "none"``
    with a justification. Build events (``source != "iterate"``),
    intent-less events, and BUG iterates are exempt — a bug fix need not
    touch the spec. Origin: iterate-2026-05-16-spec-impact-gate.
    """
    if event.get("type") != "work_completed":
        return None
    if event.get("source") != "iterate":
        return None
    if str(event.get("intent", "")).lower() not in ("feature", "change"):
        return None
    if str(event.get("spec_impact", "")).lower() == "none":
        if not event.get("spec_impact_justification"):
            return {
                "error": "spec_impact_none_requires_justification",
                "detail": (
                    "A feature/change iterate recording --spec-impact none "
                    "must also pass --spec-impact-justification."
                ),
            }
        return None
    if not event.get("affected_frs") and not event.get("new_frs"):
        return {
            "error": "spec_impact_unclassified",
            "detail": (
                "A feature/change iterate work_completed event must record "
                "--affected-frs or --new-frs (the FRs it added or modified), "
                "or --spec-impact none with a --spec-impact-justification. "
                "See SKILL.md Step 2 (ADD/MODIFY/REMOVE/NONE)."
            ),
        }
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()

    event = build_event(args)

    # Iterate C.1 FR-gate (ADR-059): every iterate work_completed event
    # must either name the FRs it touched or classify as
    # docs/tooling/compliance/infra with a one-line justification.
    # Hard-enforce forward-only — Phase 0 classified all pre-existing
    # events. Runs BEFORE spec_impact gate so an unclassified iterate
    # surfaces the broader requirement first.
    fr_gate_error = _fr_or_change_type_gate_error(event)
    if fr_gate_error is not None:
        print(json.dumps({"success": False, **fr_gate_error}, indent=2))
        return 1

    # Spec-impact gate: a FEATURE/CHANGE iterate must name the FRs it touched
    # or explicitly record --spec-impact none with a justification. Fail
    # closed (exit 1, nothing written) otherwise.
    gate_error = _spec_impact_gate_error(event)
    if gate_error is not None:
        print(json.dumps({"success": False, **gate_error}, indent=2))
        return 1

    # F14: the dedup scan (phase_completed / --deduplicate-by-commit) and the
    # append share ONE lock so concurrent phase-Stop firings can't both append.
    event_id, skipped = append_event_idempotent(
        project_root, event,
        deduplicate_by_commit=bool(args.deduplicate_by_commit and args.commit),
    )
    if skipped is not None:
        print(json.dumps({"success": True, "skipped": True, **skipped}, indent=2))
        return 0

    result = {"success": True, "id": event_id, "type": args.type}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
