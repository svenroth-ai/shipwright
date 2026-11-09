#!/usr/bin/env python3
"""Health-check for shipwright_events.jsonl.

Validates:
  1. All lines are valid JSON
  2. All events have required fields (v, id, ts, type)
  3. No duplicate event IDs
  4. No duplicate commits in work_completed events
  5. Conventional Commits in git log have matching work_completed events

Usage:
    uv run validate_event_log.py --project-root <path>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # shared/scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.events_log import EVENT_FILE, event_files  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402

REQUIRED_FIELDS = {"v", "id", "ts", "type"}


def _scan_file(path: Path, events: list[dict], seen_ids: dict[str, str], seen_commits: set[str],
               issues: list[dict], project_root: Path) -> None:
    where = {} if path.parent == project_root else {"file": path.name}
    for i, line in enumerate(path.open("r", encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue

        # 1. Valid JSON
        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append({"severity": "error", "line": i, **where, "message": f"Invalid JSON: {e}"})
            continue

        events.append(event)

        # 2. Required fields
        missing = REQUIRED_FIELDS - set(event.keys())
        if missing:
            issues.append({"severity": "warn", "line": i, **where,
                           "message": f"Missing fields: {', '.join(sorted(missing))}"})

        # 3. Duplicate IDs (same id + same content in different files is the fold-race duplicate: fine)
        eid = event.get("id", "")
        body = json.dumps({k: v for k, v in event.items() if k != "run"}, sort_keys=True)
        if eid in seen_ids and (path.parent == project_root or seen_ids[eid] != body):
            issues.append({"severity": "warn", "line": i, **where,
                           "message": f"Duplicate event ID: {eid}"})
        seen_ids.setdefault(eid, body)

        # 4. Duplicate commits
        if event.get("type") == "work_completed":
            commit = event.get("commit", "")
            if commit and commit in seen_commits:
                issues.append({"severity": "info", "line": i, **where,
                               "message": f"Duplicate commit in work_completed: {commit}"})
            if commit:
                seen_commits.add(commit)


def validate(project_root: Path) -> list[dict]:
    """Validate the event log. Returns list of issues."""
    issues: list[dict] = []
    files = [p for p in event_files(project_root) if p.exists()]

    if not files:
        issues.append({"severity": "error", "message": f"{EVENT_FILE} not found"})
        return issues

    events: list[dict] = []
    seen_ids: dict[str, str] = {}  # id -> canonical content (the stamped ``run`` is not content)
    seen_commits: set[str] = set()

    # Layout-aware: the legacy log, then archive and drop files. A non-ok DROP file is an error here
    # (it would block its run's absence gates); a damaged legacy/archive file is reported by line below.
    for status in read_events_assembled(project_root).files:
        if status.kind == "drop" and status.status != "ok":
            issues.append({"severity": "error", "file": Path(status.path).name,
                           "message": f"Drop file is {status.status}"})

    for path in files:
        _scan_file(path, events, seen_ids, seen_commits, issues, project_root)

    # 5. Check git conventional commits have matching events
    try:
        result = subprocess.run(
            ["git", "log", "--no-merges", "--format=%H|%s"],
            cwd=project_root, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            event_commits = seen_commits
            for line in result.stdout.strip().splitlines():
                if "|" not in line:
                    continue
                commit_hash, subject = line.split("|", 1)
                # Only check conventional commits (feat:, fix:, refactor:, etc.)
                if ":" in subject and any(subject.startswith(t) for t in
                        ("feat", "fix", "refactor", "test", "docs", "chore", "style", "perf", "ci", "build")):
                    short_hash = commit_hash[:12]
                    # Check if any event commit starts with or matches
                    matched = any(c.startswith(short_hash[:7]) or short_hash.startswith(c[:7])
                                  for c in event_commits)
                    if not matched:
                        issues.append({"severity": "info",
                                       "message": f"Commit {short_hash} ({subject[:50]}) has no matching event"})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # Git not available, skip this check

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate shipwright event log")
    parser.add_argument("--project-root", required=True, help="Project root directory")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    issues = validate(project_root)

    if not issues:
        print(json.dumps({"valid": True, "issues": []}, indent=2))
        return 0

    errors = [i for i in issues if i["severity"] == "error"]
    warns = [i for i in issues if i["severity"] == "warn"]
    infos = [i for i in issues if i["severity"] == "info"]

    print(json.dumps({
        "valid": len(errors) == 0,
        "errors": len(errors),
        "warnings": len(warns),
        "info": len(infos),
        "issues": issues,
    }, indent=2))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
