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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1
EVENT_FILE = "shipwright_events.jsonl"


# ---------------------------------------------------------------------------
# File locking (cross-platform)
# ---------------------------------------------------------------------------

class _FileLock:
    """Cross-platform file lock using a separate .lock file.

    msvcrt.locking on Windows is unreliable in append mode, so we use
    a dedicated lock file for mutual exclusion on all platforms.
    """

    def __init__(self, lock_path: str | Path):
        self._lock_path = Path(lock_path)
        self._fp = None

    def __enter__(self):
        self._fp = open(self._lock_path, "w", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt
            # Lock byte 0 of the lock file (not the data file)
            while True:
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    import time
                    time.sleep(0.001)
        else:
            import fcntl
            fcntl.flock(self._fp, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fp:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def generate_event_id() -> str:
    """Generate a unique event ID: evt- + 8 hex chars from UUID4."""
    return f"evt-{uuid4().hex[:8]}"


def read_events(project_root: Path) -> list[dict]:
    """Tolerant reader — skips corrupt lines instead of crashing."""
    path = project_root / EVENT_FILE
    if not path.exists():
        return []
    events: list[dict] = []
    for i, line in enumerate(path.open("r", encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            warnings.warn(f"Corrupt event at line {i + 1} in {EVENT_FILE}, skipping")
    return events


def has_commit(project_root: Path, commit: str) -> bool:
    """Check if a work_completed event with this commit already exists."""
    for event in read_events(project_root):
        if event.get("type") == "work_completed" and event.get("commit") == commit:
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
        if args.adr_id:
            event["adr_id"] = args.adr_id

    elif args.type in ("phase_started", "phase_completed"):
        event["phase"] = args.phase
        if args.detail:
            event["detail"] = args.detail

    elif args.type == "split_completed":
        event["split"] = args.split

    elif args.type == "test_run":
        if args.trigger:
            event["trigger"] = args.trigger
        layers: dict = {}
        if args.unit_passed is not None or args.unit_total is not None:
            layers["unit"] = {}
            if args.unit_passed is not None:
                layers["unit"]["passed"] = args.unit_passed
            if args.unit_total is not None:
                layers["unit"]["total"] = args.unit_total
        if args.e2e_passed is not None or args.e2e_total is not None:
            layers["e2e"] = {}
            if args.e2e_passed is not None:
                layers["e2e"]["passed"] = args.e2e_passed
            if args.e2e_total is not None:
                layers["e2e"]["total"] = args.e2e_total
        if args.smoke_status:
            layers["smoke"] = {"status": args.smoke_status}
        if layers:
            event["layers"] = layers

    elif args.type == "event_amended":
        event["amends"] = args.amends
        if args.fields:
            event["fields"] = json.loads(args.fields)

    return event


def append_event(project_root: Path, event: dict) -> str:
    """Atomically append an event to the JSONL log. Returns the event ID."""
    path = project_root / EVENT_FILE
    lock_path = project_root / (EVENT_FILE + ".lock")
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(lock_path):
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())

    return event["id"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record a Shipwright event")
    p.add_argument("--project-root", required=True, help="Project root directory")
    p.add_argument("--type", required=True,
                   choices=["task_created", "work_completed", "phase_started",
                            "phase_completed", "split_completed", "test_run",
                            "event_amended"],
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
    p.add_argument("--spec-updated", help="Path to updated spec file")
    p.add_argument("--adr-id", help="ADR reference (e.g. ADR-055)")

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
    p.add_argument("--unit-passed", type=int, help="Unit tests passed")
    p.add_argument("--unit-total", type=int, help="Unit tests total")
    p.add_argument("--e2e-passed", type=int, help="E2E tests passed")
    p.add_argument("--e2e-total", type=int, help="E2E tests total")
    p.add_argument("--smoke-status", help="Smoke test status: pass | fail")

    # event_amended
    p.add_argument("--amends", help="ID of event to amend")
    p.add_argument("--fields", help="JSON string of fields to override")

    # Deduplication
    p.add_argument("--deduplicate-by-commit", action="store_true",
                   help="Skip if a work_completed event with same commit exists")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()

    # Deduplication checks
    if args.deduplicate_by_commit and args.commit:
        if has_commit(project_root, args.commit):
            result = {"success": True, "skipped": True, "reason": "duplicate_commit",
                      "commit": args.commit}
            print(json.dumps(result, indent=2))
            return 0

    if args.type == "phase_completed" and args.phase:
        if has_phase_event(project_root, args.phase):
            result = {"success": True, "skipped": True, "reason": "duplicate_phase",
                      "phase": args.phase}
            print(json.dumps(result, indent=2))
            return 0

    event = build_event(args)
    event_id = append_event(project_root, event)

    result = {"success": True, "id": event_id, "type": args.type}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
