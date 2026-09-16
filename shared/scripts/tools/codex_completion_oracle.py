#!/usr/bin/env python3
"""Read-only completion verdicts for WebUI-launched Codex runs.

Usage:
    uv run shared/scripts/tools/codex_completion_oracle.py \
        --project-root <root> --phase <phase> --session <session> [--since <iso>]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers.common import (  # noqa: E402
    check_c1_run_scoped,
    read_run_events,
)

EXIT_DONE = 0
EXIT_NOT_DONE = 1
EXIT_DELIVERY_PENDING = 2
EXIT_NO_ORACLE = 3

_C1_PHASES = frozenset({"changelog", "deploy", "design", "plan", "project", "test"})
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WATCHER_STATUS_CODES = {
    "merged": 0,
    "checks_failed": 2,
    "closed": 3,
    "ready": 4,
    "refresh_needed": 4,
    "pending": 4,
}


def _parse_since(value: str) -> str:
    """Accept only timezone-aware ISO-8601 launch instants."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a timezone")
    return value


def _event_stamp(event: dict[str, Any]) -> datetime:
    value = event.get("ts") or event.get("timestamp") or ""
    if not isinstance(value, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _evidence(events: list[dict[str, Any]], *, session: str, since: str | None) -> dict[str, Any]:
    exact = sum(event.get("session") == session for event in events)
    fallback = len(events) - exact
    result: dict[str, Any] = {
        "events": len(events),
        "exact_session_events": exact,
        "scope": "exact" if fallback == 0 else "since_fallback",
    }
    if fallback:
        result["since_fallback_events"] = fallback
        result["since"] = since
    return result


def _event_for_source(events: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    matches = [
        event for event in events
        if event.get("type") == "work_completed" and event.get("source") == source
    ]
    return max(matches, key=_event_stamp, default=None)


def _roots(project_root: Path) -> list[Path]:
    roots = [project_root]
    worktrees = project_root / ".worktrees"
    if worktrees.is_dir():
        try:
            roots.extend(path for path in sorted(worktrees.iterdir()) if path.is_dir())
        except OSError:
            pass
    return roots


def _iterate_branch(project_root: Path, run_id: str) -> str | None:
    if not _SAFE_RUN_ID.fullmatch(run_id) or ".." in run_id:
        return None
    for root in _roots(project_root):
        entry = root / ".shipwright" / "agent_docs" / "iterates" / f"{run_id}.json"
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        branch = payload.get("branch")
        if isinstance(branch, str) and branch:
            return branch
    return None


def _delivery_status(project_root: Path, branch: str) -> dict[str, Any] | None:
    command = [
        sys.executable,
        str(Path(__file__).with_name("watch_pr_delivery.py")),
        "--pr",
        branch,
        "--once",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=70,
            check=False,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    # ``watch_pr_delivery.py`` uses non-zero exits for valid non-merged
    # delivery states.  Trust only its documented status/exit-code pair, so
    # a stale JSON ``merged`` payload paired with a failed invocation cannot
    # certify delivery.
    if _WATCHER_STATUS_CODES.get(status) != result.returncode:
        return None
    return payload


def _iterate_verdict(project_root: Path, events: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    completed = _event_for_source(events, "iterate")
    if completed is None:
        return "not_done"
    run_id = completed.get("adr_id")
    if not isinstance(run_id, str) or not run_id:
        evidence["reason"] = "iterate work_completed event has no adr_id run id"
        return "not_done"
    if not _SAFE_RUN_ID.fullmatch(run_id) or ".." in run_id:
        evidence["reason"] = "iterate work_completed event has unsafe adr_id run id"
        return "not_done"
    branch = _iterate_branch(project_root, run_id)
    if branch is None:
        evidence["reason"] = f"no iterate entry with branch for run_id={run_id}"
        return "not_done"
    if branch.startswith("-"):
        evidence["reason"] = "iterate entry has an unsafe branch name"
        return "not_done"
    evidence["run_id"] = run_id
    evidence["branch"] = branch
    delivery = _delivery_status(project_root, branch)
    if delivery is None:
        evidence["reason"] = "watch_pr_delivery produced no JSON verdict"
        # ``work_completed[source=iterate]`` marks F5b, which precedes the
        # commit and PR-delivery steps.  Without a valid watcher verdict we
        # have no proof that F11 created a PR, so the agent may still have
        # required work.  Keep it nudgeable rather than masking that gap as
        # external delivery wait.
        evidence["delivery_state"] = "indeterminate"
        return "not_done"
    evidence["delivery"] = delivery
    status = delivery.get("status")
    if status == "merged":
        return "done"
    if status in {"pending", "ready", "refresh_needed"}:
        return "delivery_pending"
    if status in {"checks_failed", "closed"}:
        # These are positive proof of a created PR, so its error state is
        # external delivery work rather than unfinished agent work.  Keep
        # the four-verdict CLI contract and preserve the exact status.
        evidence["delivery_state"] = "error"
        return "delivery_pending"
    evidence["reason"] = f"watch_pr_delivery returned unrecognized status={status!r}"
    evidence["delivery_state"] = "indeterminate"
    return "not_done"


def evaluate(
    project_root: Path,
    phase: str,
    *,
    session: str,
    since: str | None = None,
) -> dict[str, Any]:
    """Return one serializable oracle verdict without modifying the project."""
    if since is not None:
        try:
            _parse_since(since)
        except argparse.ArgumentTypeError:
            return {
                "verdict": "not_done",
                "phase": phase,
                "session": session,
                "evidence": {"reason": "invalid since timestamp", "since_parse_failed": True},
            }
    events = read_run_events(project_root, session=session, since=since)
    evidence = _evidence(events, session=session, since=since)
    exact_events = [event for event in events if event.get("session") == session]
    completion_events = exact_events or events
    evidence["completion_scope"] = "exact" if exact_events else evidence["scope"]
    if phase in _C1_PHASES:
        result = check_c1_run_scoped(project_root, phase, session=session, since=since)
        evidence["check"] = result.detail
        verdict = "done" if result.ok else "not_done"
    elif phase == "build":
        completed = _event_for_source(completion_events, "build")
        evidence["check"] = "work_completed[source=build]"
        verdict = "done" if completed is not None else "not_done"
    elif phase == "iterate":
        verdict = _iterate_verdict(project_root, completion_events, evidence)
    else:
        evidence["reason"] = "no run-scoped completion oracle for this phase"
        verdict = "no_oracle"
    return {"verdict": verdict, "phase": phase, "session": session, "evidence": evidence}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--session", required=True)
    # Keep validation in ``evaluate`` rather than argparse's type conversion:
    # every invocation of this machine-facing command must emit one JSON
    # verdict, including a malformed optional timestamp.
    parser.add_argument("--since", default=None)
    args = parser.parse_args(argv)

    payload = evaluate(
        Path(args.project_root).resolve(),
        args.phase,
        session=args.session,
        since=args.since,
    )
    print(json.dumps(payload, sort_keys=True))
    return {
        "done": EXIT_DONE,
        "not_done": EXIT_NOT_DONE,
        "delivery_pending": EXIT_DELIVERY_PENDING,
        "no_oracle": EXIT_NO_ORACLE,
    }.get(payload["verdict"], EXIT_NOT_DONE)


if __name__ == "__main__":
    raise SystemExit(main())
