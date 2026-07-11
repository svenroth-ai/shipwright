"""Generate session_handoff.md from current project state.

Reads git status, config files, and decision log to produce a
human-readable handoff document for session recovery.

Usage (from target project root):
    uv run <SHIPWRIGHT_PLUGIN_ROOT>/../../shared/scripts/tools/generate_session_handoff.py

Writes to: .shipwright/agent_docs/session_handoff.md
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Add shared lib to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import read_all_configs, read_events
from lib.events_log import latest_event_dt
from lib.iterate_entry import (
    MIGRATION_QUARANTINE_REPORT_KEY,
    MIGRATION_QUARANTINED_COUNT_KEY,
    last_iterate_entry,
)
from lib.state import get_checkpoint


# ---------------------------------------------------------------------------
# Iterate A.4 — Session-id fallback chain
# ---------------------------------------------------------------------------
#
# Pre-A.4 behavior: if the capture-hook hadn't run yet, the handoff carried
# the literal string ``"unknown"`` as the session id. That made the handoff
# undebuggable in retrospect and broke any consumer trying to correlate the
# handoff with the actual session.
#
# A.4 introduces a 4-stage fallback. Each non-primary stage:
#   1. resolves to a deterministic-looking id (so consumers can recognise it),
#   2. emits a `hook_warning` event with `source=session_id_fallback` +
#      `stage=A|B|C` so the failure is visible in the audit log,
#   3. is recorded under "Session Info" in the rendered handoff so a human
#      reader sees which level kicked in.
#
# Stage precedence:
#   0 / env       → SHIPWRIGHT_SESSION_ID env var (set by the capture hook;
#                   no warning).
#   A / derived   → `derived-<run_id>`, with `-2 / -3 / ...` collision suffix
#                   when the same run_id has previously been "derived".
#   B / persisted → once-per-process UUID, persisted to
#                   `.shipwright/session_fallback.json` so subsequent calls in
#                   the same process keep the same id.
#   C / literal   → the literal `"no-session-id"` sentinel with WARN banner.
#                   This is the absolute floor — only reached if writing the
#                   persistence file itself fails (read-only FS, missing
#                   `.shipwright/`, etc.).
SESSION_FALLBACK_FILE = ".shipwright/session_fallback.json"
LITERAL_NO_SESSION_ID = "no-session-id"
_NULLISH_ENV_VALUES = {"", "unknown", "none", "null"}


@dataclass(frozen=True)
class SessionIdResolution:
    """Result of :func:`resolve_session_id`.

    ``stage`` is the human-readable identifier (``env``, ``derived``,
    ``persisted``, ``literal``) used to caption the "Session Info" block.
    ``warning_stage`` is the A/B/C wire value emitted into the audit event;
    ``None`` for the primary path (env), which is not a warning.
    """

    session_id: str
    stage: str
    warning_stage: str | None
    detail: str = ""


def _load_fallback_state(project_root: Path) -> dict:
    path = project_root / SESSION_FALLBACK_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_fallback_state(project_root: Path, state: dict) -> bool:
    """Best-effort persistence — returns False on any I/O failure."""
    path = project_root / SESSION_FALLBACK_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        return True
    except OSError:
        return False


def _derive_with_collision_suffix(run_id: str, prior: list[str]) -> str:
    """Return ``derived-<run_id>`` or ``derived-<run_id>-N`` on collision.

    Two iterates with the same run_id are impossible by construction (run_id
    is unique per-iterate), but the suffix logic is the documented contract
    from the plan — exercise it via repeated calls in tests.
    """
    base = f"derived-{run_id}"
    if base not in prior:
        return base
    counter = 2
    while f"{base}-{counter}" in prior:
        counter += 1
    return f"{base}-{counter}"


def _emit_session_id_fallback_warning(
    project_root: Path,
    *,
    stage: str,
    session_id: str,
    detail: str,
) -> None:
    """Best-effort `hook_warning` event so the fallback is auditable."""
    try:
        from tools.record_event import append_event, generate_event_id

        append_event(project_root, {
            "v": 1,
            "id": generate_event_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "hook_warning",
            "source": "session_id_fallback",
            "stage": stage,
            "session": session_id,
            "detail": detail,
        })
    except Exception as exc:  # noqa: BLE001 — fail-soft, hooks must never crash
        print(
            f"[generate_session_handoff] event emit failed for stage={stage}: "
            f"{exc!r}",
            file=sys.stderr,
        )


def resolve_session_id(
    project_root: Path | str,
    *,
    env_session_id: str | None = None,
    run_id: str | None = None,
    uuid_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    emit_warning: Callable[[str, str, str], None] | None = None,
) -> SessionIdResolution:
    """Resolve the effective session id via the A.4 fallback chain.

    Pure helper — does NOT print anything (callers render warnings into the
    handoff body). ``emit_warning`` is the side-effecting audit-event hook,
    injectable to keep tests deterministic. Defaults to
    :func:`_emit_session_id_fallback_warning` when ``None``.
    """
    project_root = Path(project_root)
    emitter: Callable[[str, str, str], None]
    if emit_warning is None:
        emitter = lambda st, sid, det: _emit_session_id_fallback_warning(
            project_root, stage=st, session_id=sid, detail=det,
        )
    else:
        emitter = emit_warning

    # Stage 0 / env — primary path
    env_value = (env_session_id or "").strip()
    if env_value and env_value.lower() not in _NULLISH_ENV_VALUES:
        return SessionIdResolution(env_value, "env", None, detail="from SHIPWRIGHT_SESSION_ID")

    # Stage A / derived from run_id
    state = _load_fallback_state(project_root)
    rid = (run_id or "").strip()
    if rid:
        prior_derived: list[str] = list(state.get("derived_history", []) or [])
        derived = _derive_with_collision_suffix(rid, prior_derived)
        prior_derived.append(derived)
        state["derived_history"] = prior_derived
        _save_fallback_state(project_root, state)
        detail = f"derived from run_id={rid!r}"
        emitter("A", derived, detail)
        return SessionIdResolution(derived, "derived", "A", detail=detail)

    # Stage B / persisted UUID
    persisted = state.get("process_uuid")
    if not (isinstance(persisted, str) and persisted.strip()):
        persisted = uuid_factory()
        state["process_uuid"] = persisted
        saved = _save_fallback_state(project_root, state)
        if not saved:
            # Stage C — persistence failed, fall through to literal
            detail = "fallback persistence write failed (read-only FS?)"
            emitter("C", LITERAL_NO_SESSION_ID, detail)
            return SessionIdResolution(LITERAL_NO_SESSION_ID, "literal", "C", detail=detail)
    detail = f"once-per-process UUID @ {SESSION_FALLBACK_FILE}"
    emitter("B", persisted, detail)
    return SessionIdResolution(persisted, "persisted", "B", detail=detail)


def get_git_info(project_root: Path) -> dict[str, str]:
    """Get current git state. WP7/F26: `encoding="utf-8",
    errors="replace"` pins the decode so a non-ASCII commit subject is not
    mojibaked into the tracked session_handoff.md under the cp1252 default.
    """
    info = {}
    enc = {"capture_output": True, "text": True, "encoding": "utf-8",
           "errors": "replace", "cwd": project_root}
    try:
        info["branch"] = subprocess.run(
            ["git", "branch", "--show-current"], **enc).stdout.strip()
        info["last_commit"] = subprocess.run(
            ["git", "log", "-1", "--oneline"], **enc).stdout.strip()
        info["uncommitted_changes"] = subprocess.run(
            ["git", "status", "--porcelain"], **enc).stdout.strip()
    except FileNotFoundError:
        info["error"] = "git not found"
    return info


def _current_iterate_progress(project_root: Path, git_info: dict) -> list[str]:
    """Return lines describing in-progress iterate state.

    Step B1 Resume in the iterate skill needs reliable evidence for which
    mandatory phases still need to run when a previous session was
    interrupted. The rest of the handoff is an overview of completed work
    (iterate_history, recent events); it does not track in-flight phase
    markers. This block fills that gap by inspecting the iterate branch +
    the run-scoped marker files directly — agents reading the handoff on
    Resume should trust this section over heuristics.

    Returns an empty list if not on an iterate branch.
    """
    branch = git_info.get("branch") or ""
    if not branch.startswith("iterate/"):
        return []

    iterate_dir = project_root / ".shipwright" / "planning" / "iterate"
    short = branch.removeprefix("iterate/").split("/")[-1].lower()

    spec_path: Path | None = None
    run_id: str = ""
    complexity: str = ""
    if iterate_dir.exists():
        candidates = [
            p for p in iterate_dir.glob("*.md")
            if "miniplan" not in p.name.lower() and short and short in p.name.lower()
        ]
        if candidates:
            spec_path = max(candidates, key=lambda p: p.stat().st_mtime)
            try:
                header = spec_path.read_text(encoding="utf-8", errors="ignore")[:1200]
                for line in header.splitlines():
                    low = line.strip().lower()
                    if low.startswith("- **run id:**") or low.startswith("- **run-id:**"):
                        run_id = line.split(":**", 1)[1].strip()
                    elif low.startswith("- **complexity:**"):
                        complexity = line.split(":**", 1)[1].strip().lower()
            except OSError:
                pass

    # Look for the external review marker. Two filename conventions are
    # acceptable (see iteration-planning.md Step 5): a run-scoped file or
    # the shared state file. Prefer run-scoped if both exist.
    marker_status = "missing"
    marker_detail = ""
    marker_candidates: list[Path] = []
    if run_id:
        marker_candidates.append(iterate_dir / f"{run_id}-external-review.json")
    marker_candidates.append(iterate_dir / "external_review_state.json")
    for candidate in marker_candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        status = data.get("status", "unknown")
        ts_raw = data.get("timestamp", "")
        # Shared marker is stale if it predates the current iterate spec —
        # otherwise it proves review for a prior run, not this one.
        if candidate.name == "external_review_state.json" and spec_path and ts_raw:
            try:
                marker_ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                spec_ts = datetime.fromtimestamp(spec_path.stat().st_mtime, tz=timezone.utc)
                if marker_ts < spec_ts:
                    marker_status = "stale"
                    marker_detail = f"predates spec ({ts_raw[:19]})"
                    continue
            except (ValueError, OSError):
                pass
        marker_status = status
        marker_detail = f"{candidate.name} @ {ts_raw[:19]}" if ts_raw else candidate.name
        break

    lines: list[str] = ["## Current Iterate Progress", ""]
    lines.append(f"- **Branch**: {branch}")
    if run_id:
        lines.append(f"- **Run ID**: {run_id}")
    if spec_path:
        try:
            rel = spec_path.relative_to(project_root).as_posix()
        except ValueError:
            rel = str(spec_path)
        lines.append(f"- **Spec**: {rel}")
    if complexity:
        lines.append(f"- **Complexity**: {complexity}")
    review_line = f"- **External Review Marker**: {marker_status}"
    if marker_detail:
        review_line += f" ({marker_detail})"
    lines.append(review_line)

    replay: list[str] = []
    if complexity in ("medium", "large") and marker_status in ("missing", "stale"):
        replay.append("Step 4 — External LLM Review (marker missing/stale)")
    if git_info.get("uncommitted_changes"):
        replay.append("Finalization (F0–F11) after all mandatory phases pass")

    if replay:
        lines.append("")
        lines.append("### Mandatory replay on Resume")
        lines.append("")
        lines.append("Before dispatching to the handoff's Remaining phase, run these if missing:")
        for item in replay:
            lines.append(f"- {item}")

    lines.append("")
    return lines


def generate_handoff(
    project_root: str | Path,
    session_id: str = "unknown",
    reason: str = "context compaction",
    *,
    canon_frontmatter: dict[str, str] | None = None,
    session_resolution: SessionIdResolution | None = None,
) -> str:
    """Generate session handoff markdown content.

    ``canon_frontmatter``: when set (iterate 12.1+), prepend a YAML
    frontmatter block that marks the handoff as canon-generated so the
    Stop hook's conditional-skip logic can recognise it and avoid
    overwriting. The dict must contain ``run_id``, ``phase``, ``reason``,
    and ``timestamp`` keys. The caller is responsible for populating
    these — most callers go through ``main()`` which reads
    ``SHIPWRIGHT_RUN_ID`` from the environment and refuses to write the
    marker if it is missing (safe degrade, GPT R3 finding).

    ``session_resolution``: A.4 — when the caller went through
    :func:`resolve_session_id`, pass the result so the rendered handoff
    captions which fallback stage produced the session id (and renders a
    WARN banner for stage C). When ``None`` and ``session_id`` matches
    the literal ``no-session-id`` sentinel, the banner is rendered anyway
    (defensive — callers that bypass the resolver still get the warning).
    """
    project_root = Path(project_root)
    configs = read_all_configs(project_root)
    checkpoint = get_checkpoint(project_root)
    git_info = get_git_info(project_root)
    # Deterministic banner — see iterate-2026-05-22-deterministic-render-timestamps.
    # `datetime.now()` made every handoff re-render mutate this line, leaving
    # the file `M` in `git status`.
    _ts_dt = latest_event_dt(project_root)
    timestamp = (
        _ts_dt.strftime("%Y-%m-%d %H:%M:%S UTC") if _ts_dt is not None
        else "(no events)"
    )

    # Read decision log if it exists
    decision_log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    recent_decisions = ""
    if decision_log.exists():
        content = decision_log.read_text(encoding="utf-8")
        # Extract last ADR entry (supports both compact ### ADR- and old ## ADR- format)
        for prefix in ("\n### ADR-", "\n## ADR-"):
            entries = content.split(prefix)
            if len(entries) > 1:
                recent_decisions = prefix.lstrip("\n") + entries[-1][:500]
                break

    lines: list[str] = []

    # Iterate 12.1: canon frontmatter. Order matters — YAML block MUST be
    # at the very top of the file so `parse_canon_frontmatter` (stop-hook)
    # can read it without scanning the rest of the doc.
    if canon_frontmatter:
        lines.append("---")
        lines.append("canon_generated: true")
        for key in ("run_id", "phase", "reason", "timestamp"):
            value = canon_frontmatter.get(key, "")
            lines.append(f'{key}: "{value}"')
        lines.append("---")
        lines.append("")

    lines += [
        "# Session Handoff",
        "",
        f"> Auto-generated {timestamp}",
        "",
        "## Session Info",
        "",
        f"- **Session ID**: {session_id}",
        f"- **Timestamp**: {timestamp}",
        f"- **Reason**: {reason}",
    ]

    # A.4 — surface the fallback stage so a human reader sees that the id
    # was synthesized rather than supplied by the capture hook.
    if session_resolution is not None and session_resolution.stage != "env":
        lines.append(
            f"- **Session ID Source**: fallback stage {session_resolution.warning_stage} "
            f"({session_resolution.stage}) — {session_resolution.detail}"
        )
    is_literal_floor = (
        session_id == LITERAL_NO_SESSION_ID
        or (session_resolution is not None and session_resolution.stage == "literal")
    )
    if is_literal_floor:
        lines += [
            "",
            "> ⚠ **WARN — no session id available.** All fallback stages "
            "failed. The capture hook didn't fire and the persistence file "
            f"`{SESSION_FALLBACK_FILE}` could not be written. Cross-session "
            "correlation will be impossible until this is fixed.",
        ]
    lines.append("")

    # Iterate 11.3 + file-per-iterate refactor — render "## Last Iterate"
    # from the merged iterate entry store (legacy array + per-file dir).
    # ``last_iterate_entry`` returns ``None`` on a fresh project, which
    # suppresses the whole block rather than rendering placeholders.
    last = last_iterate_entry(Path(project_root))
    if last:
        lines += [
            "## Last Iterate",
            "",
            f"- **Run ID**: {last.get('run_id', 'N/A')}",
        ]
        if last.get("date"):
            lines.append(f"- **Date**: {last['date']}")
        if last.get("type"):
            lines.append(f"- **Type**: {last['type']}")
        if last.get("complexity"):
            lines.append(f"- **Complexity**: {last['complexity']}")
        if last.get("branch"):
            lines.append(f"- **Branch**: {last['branch']}")
        # Support both modern "adr" and legacy "adr_id" field names.
        adr_value = last.get("adr") or last.get("adr_id")
        if adr_value:
            lines.append(f"- **ADR**: {adr_value}")
        if last.get("description"):
            lines.append(f"- **Description**: {last['description']}")
        if "tests_passed" in last:
            lines.append(f"- **Tests passed**: {last['tests_passed']}")
        if last.get("spec"):
            lines.append(f"- **Spec**: {last['spec']}")
        lines.append("")

    # Migration-quarantine visibility: loud warning so quarantined losses
    # don't go unnoticed between finalize and next session.
    run_cfg = configs.get("run") or {}
    quarantined = run_cfg.get(MIGRATION_QUARANTINED_COUNT_KEY, 0)
    if isinstance(quarantined, int) and quarantined > 0:
        report_path = run_cfg.get(MIGRATION_QUARANTINE_REPORT_KEY, "<unknown>")
        lines += [
            "## ⚠ Iterate-History Migration Quarantine",
            "",
            f"{quarantined} legacy iterate entr{'y' if quarantined == 1 else 'ies'} "
            f"could not be migrated automatically.",
            f"See: `{report_path}`",
            "",
        ]

    # Iterate 14.15: surface in-progress iterate state so B1 Resume has
    # reliable evidence for mandatory phase replay (External Review,
    # Self-Review). Without this, Resume can fall through to Build and
    # silently skip medium+ review gates — the bug that motivated this fix.
    lines.extend(_current_iterate_progress(project_root, git_info))

    lines += [
        "## Legacy build state",
        "",
        f"- **Phase**: {checkpoint['phase']}",
        f"- **Current Split**: {checkpoint.get('current_split', 'N/A')}",
        f"- **Current Section**: {checkpoint.get('current_section', 'N/A')}",
        "",
    ]

    if checkpoint.get("total_splits"):
        lines.append(f"- **Splits**: {checkpoint['completed_splits']}/{checkpoint['total_splits']} complete")
    if checkpoint.get("total_sections"):
        lines.append(f"- **Sections**: {checkpoint['completed_sections']}/{checkpoint['total_sections']} complete")

    lines += [
        "",
        "## Git State",
        "",
        f"- **Branch**: {git_info.get('branch', 'N/A')}",
        f"- **Last Commit**: {git_info.get('last_commit', 'N/A')}",
        f"- **Uncommitted Changes**: {'Yes' if git_info.get('uncommitted_changes') else 'None'}",
        "",
        "## Config Files to Read",
        "",
    ]

    for skill, config in configs.items():
        if skill == "events":
            continue  # Listed separately below
        status = "exists" if config else "missing"
        lines.append(f"- `shipwright_{skill}_config.json` — {status}")

    # Event log section (if exists)
    events = read_events(project_root)
    if events:
        # Show last 5 events
        recent = events[-5:]
        lines += [
            "",
            "## Last Events",
            "",
            "| Event | Type | Source | Date |",
            "|-------|------|--------|------|",
        ]
        for e in reversed(recent):
            eid = e.get("id", "—")
            etype = e.get("type", "—")
            source = e.get("source", e.get("phase", "—"))
            if etype == "work_completed":
                source = f"{e.get('source', '—')} ({e.get('section', e.get('description', '—'))})"
            ts = e.get("ts", "—")[:10]
            lines.append(f"| {eid} | {etype} | {source} | {ts} |")

        # Summary
        work_events = [e for e in events if e.get("type") == "work_completed"]
        iterate_events = [e for e in work_events if e.get("source") == "iterate"]
        # Count DISTINCT phase names: a multi-split phase now records one
        # phase_completed PER split (iterate-2026-07-11-phase-completed-per-split),
        # so a raw list length would overcount "N phases completed".
        completed_phases = {e.get("phase") for e in events if e.get("type") == "phase_completed"}

        lines += [
            "",
            "## Recovery",
            "",
            f"- **Pipeline**: {len(completed_phases)} phases completed",
            f"- **Total work events**: {len(work_events)}",
        ]
        if iterate_events:
            last_iter = iterate_events[-1]
            lines.append(f"- **Last iterate**: {last_iter.get('intent', 'change')} — {last_iter.get('description', '—')} ({last_iter.get('ts', '')[:10]})")
        lines.append("- **Resume**: `/shipwright-iterate` for next change, or `/shipwright-run` for new pipeline")
    else:
        # Legacy: config file listing only
        pass

    if recent_decisions:
        lines += [
            "",
            "## Recent Decisions",
            "",
            recent_decisions,
        ]

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Generate session_handoff.md from project state")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project directory (default: CWD). Iterate 11 added this so the "
        "iterate skill's F11 step writes to the right project instead of "
        "whatever directory the skill was invoked from.",
    )
    parser.add_argument(
        "--reason",
        default="context compaction",
        help="Why this handoff was generated (shown in the output)",
    )
    parser.add_argument(
        "--canon-marker",
        action="store_true",
        help=(
            "Iterate 12.1: write a YAML frontmatter block marking this "
            "handoff as canon-generated (C3 step of a phase finalization). "
            "The Stop hook skips regeneration for handoffs whose canon "
            "frontmatter run_id matches the current SHIPWRIGHT_RUN_ID env "
            "var. Requires SHIPWRIGHT_RUN_ID to be set — otherwise the "
            "marker is dropped with a warning and the handoff is written "
            "without frontmatter (safe degrade)."
        ),
    )
    parser.add_argument(
        "--phase",
        default="",
        help="Phase name to record in the canon frontmatter (project, design, …)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve() if args.project_root else Path(os.getcwd())

    env_run_id = os.environ.get("SHIPWRIGHT_RUN_ID", "").strip()
    resolution = resolve_session_id(
        project_root,
        env_session_id=os.environ.get("SHIPWRIGHT_SESSION_ID"),
        run_id=env_run_id or None,
    )

    canon_frontmatter: dict[str, str] | None = None
    if args.canon_marker:
        if not env_run_id:
            print(
                "WARN: --canon-marker requested but SHIPWRIGHT_RUN_ID is unset — "
                "writing handoff WITHOUT canon frontmatter (Stop hook will regenerate "
                "normally). Set SHIPWRIGHT_RUN_ID before calling this to enable the skip.",
                file=sys.stderr,
            )
        else:
            # Deterministic frontmatter timestamp — see iterate-2026-05-22.
            # Using datetime.now() here was the second-most-common source of
            # session_handoff.md drift after the rendered banner. Fall back
            # to a placeholder so the frontmatter still has a `timestamp`
            # key (Stop hook's conditional-skip logic keys on its presence).
            _canon_dt = latest_event_dt(project_root)
            canon_frontmatter = {
                "run_id": env_run_id,
                "phase": args.phase,
                "reason": args.reason,
                "timestamp": (
                    _canon_dt.isoformat() if _canon_dt is not None
                    else "(no events)"
                ),
            }

    content = generate_handoff(
        project_root,
        resolution.session_id,
        args.reason,
        canon_frontmatter=canon_frontmatter,
        session_resolution=resolution,
    )

    # Ensure .shipwright/agent_docs/ exists
    agent_docs = project_root / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)

    handoff_path = agent_docs / "session_handoff.md"
    handoff_path.write_text(content, encoding="utf-8")
    print(f"Session handoff written to {handoff_path}")


if __name__ == "__main__":
    main()
