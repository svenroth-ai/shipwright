#!/usr/bin/env python3
"""Convert existing shipwright config files to shipwright_events.jsonl.

Reads shipwright_run_config.json, shipwright_build_config.json, and
shipwright_test_results.json from a project and generates equivalent events.

Usage:
    uv run convert_configs_to_events.py --project-root <path> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1


def _eid() -> str:
    return f"evt-{uuid4().hex[:8]}"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _commit_date(project_root: Path, commit_hash: str) -> str | None:
    """Get ISO timestamp for a commit hash from git log."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", commit_hash],
            cwd=project_root, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _section_to_event(section: dict, split_name: str, project_root: Path) -> dict:
    """Convert a build config section entry to a work_completed event."""
    commit = section.get("commit", "")
    ts = _commit_date(project_root, commit) if commit else None
    if not ts:
        ts = datetime.now(timezone.utc).isoformat()

    event: dict = {
        "v": SCHEMA_VERSION,
        "id": _eid(),
        "ts": ts,
        "type": "work_completed",
        "source": "build",
        "split": split_name,
        "section": section.get("name", ""),
        "commit": commit,
    }

    # Tests
    tests: dict = {}
    if "tests_passed" in section:
        tests["passed"] = section["tests_passed"]
    if "tests_total" in section:
        tests["total"] = section["tests_total"]
    if tests:
        event["tests"] = tests

    # Review
    review: dict = {}
    if section.get("review_type"):
        review["type"] = section["review_type"]
    findings = section.get("code_review_findings", [])
    review["findings"] = len(findings)
    review["fixed"] = sum(1 for f in findings if isinstance(f, dict) and f.get("status") == "fixed")
    if review:
        event["review"] = review

    # FR mapping — we don't have this in old configs, leave empty
    event["affected_frs"] = []

    return event


def convert(project_root: Path) -> list[dict]:
    """Convert all config state to events."""
    events: list[dict] = []

    run_config = _read_json(project_root / "shipwright_run_config.json")
    build_config = _read_json(project_root / "shipwright_build_config.json")
    project_config = _read_json(project_root / "shipwright_project_config.json")

    # Build split name lookup from project config
    splits = project_config.get("splits", [])
    split_by_prefix: dict[str, str] = {}
    for sp in splits:
        name = sp.get("name", "")
        prefix = name.split("-", 1)[0]
        if prefix:
            split_by_prefix[prefix] = name

    # Phase events from completed_steps
    completed_steps = run_config.get("completed_steps", [])
    pipeline = run_config.get("pipeline", [])

    # We don't have exact timestamps for phase transitions, use updated_at as fallback
    base_ts = run_config.get("updated_at", datetime.now(timezone.utc).isoformat())

    for step in pipeline:
        if step in completed_steps:
            events.append({
                "v": SCHEMA_VERSION, "id": _eid(), "ts": base_ts,
                "type": "phase_completed", "phase": step,
            })

    # Archived splits — split_NN_sections keys
    for key, sections in sorted(build_config.items()):
        if not (key.startswith("split_") and key.endswith("_sections") and isinstance(sections, list)):
            continue
        prefix = key.split("_")[1]  # "split_01_sections" → "01"
        split_name = split_by_prefix.get(prefix, prefix)

        for section in sections:
            events.append(_section_to_event(section, split_name, project_root))

        # Split completed event
        events.append({
            "v": SCHEMA_VERSION, "id": _eid(), "ts": base_ts,
            "type": "split_completed", "split": split_name,
        })

    # Current split sections
    current_split = build_config.get("current_split", "")
    current_sections = build_config.get("sections", [])
    for section in current_sections:
        events.append(_section_to_event(section, current_split, project_root))

    # If current split is in completed_splits, add split_completed
    if current_split and current_split in build_config.get("completed_splits", []):
        events.append({
            "v": SCHEMA_VERSION, "id": _eid(), "ts": base_ts,
            "type": "split_completed", "split": current_split,
        })

    # Test results
    for test_file in sorted(project_root.glob("*test_results.json")):
        tr = _read_json(test_file)
        if not tr:
            continue
        layers: dict = {}
        unit = tr.get("unit", {})
        if unit:
            layers["unit"] = {"passed": unit.get("passed", 0), "total": unit.get("total", 0)}
        e2e = tr.get("e2e", {})
        if e2e:
            layers["e2e"] = {"passed": e2e.get("passed", 0), "total": e2e.get("total", 0)}
        smoke = tr.get("smoke", {})
        if smoke:
            layers["smoke"] = {"status": smoke.get("status", "")}
        if layers:
            events.append({
                "v": SCHEMA_VERSION, "id": _eid(), "ts": base_ts,
                "type": "test_run", "trigger": "migration",
                "layers": layers,
            })

    # Sort by timestamp for chronological order
    events.sort(key=lambda e: e.get("ts", ""))

    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert configs to event log")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    parser.add_argument("--dry-run", action="store_true", help="Print events without writing")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    events = convert(project_root)

    if args.dry_run:
        for event in events:
            print(json.dumps(event, ensure_ascii=False))
        print(f"\n--- {len(events)} events would be written ---")
        return 0

    # Write
    out_path = project_root / "shipwright_events.jsonl"
    if out_path.exists():
        print(f"ERROR: {out_path} already exists. Delete it first or use --dry-run.")
        return 1

    with open(out_path, "w", encoding="utf-8") as fp:
        for event in events:
            fp.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    # Verify
    section_count = 0
    for key, val in _read_json(project_root / "shipwright_build_config.json").items():
        if key == "sections" and isinstance(val, list):
            section_count += len(val)
        elif key.startswith("split_") and key.endswith("_sections") and isinstance(val, list):
            section_count += len(val)

    work_events = [e for e in events if e["type"] == "work_completed"]

    output = {
        "success": True,
        "events_written": len(events),
        "work_completed_events": len(work_events),
        "sections_in_config": section_count,
        "match": len(work_events) == section_count,
        "path": str(out_path),
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
