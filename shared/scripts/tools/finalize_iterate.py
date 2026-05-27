#!/usr/bin/env python3
"""Deterministic iterate finalization — replaces manual F5a/F5b/F7/F11.

Runs all iterate finalization steps in correct order:
  1. Update build dashboard  (F5b)
  2. Update compliance docs  (F5a)
  3. Record work_completed event  (F7, if --commit given)
  4. Generate session handoff  (F11)

Each step is idempotent and best-effort: a failure in one step does not
block the others.  Returns structured JSON result on stdout.

Usage:
    uv run finalize_iterate.py --project-root <path> --run-id <id> [--commit <sha>] [--reason <text>]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.artifact_paths import (  # noqa: E402
    runtime_path,
    tracked_path,
)


def _atomic_replace(content_bytes: bytes, destination: Path) -> None:
    """Atomic same-filesystem write via NamedTemporaryFile + os.replace.

    Partial-failure safe: tempfile lives in destination.parent so rename
    is atomic; on rename failure the tempfile is unlinked (would otherwise
    leak as ".name.…tmp" cruft into tracked agent_docs). See ADR 089.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as fh:
        tmp_path = Path(fh.name)
        fh.write(content_bytes)
    try:
        os.replace(tmp_path, destination)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _refuse_symlink(path: Path) -> bool:
    """True iff ``path`` is a symlink (finalize refuses these targets)."""
    try:
        if path.is_symlink():
            print(
                f"[finalize_iterate] refusing symlinked artifact: {path}",
                file=sys.stderr,
            )
            return True
    except OSError:
        return True
    return False


def _unlink_runtime_artifacts(project_root: Path) -> dict[str, str]:
    """Wipe runtime/{session_handoff,build_dashboard}.md after direct-write.

    These two carry iterate-specific context (canon marker, run_id) that
    the runtime Stop-hook variant lacks — they're regenerated to tracked
    above; this just cleans up stale runtime. See ADR 089.
    """
    results: dict[str, str] = {}
    for name in ("session_handoff", "build_dashboard"):
        rp = runtime_path(project_root, name)
        if not rp.exists():
            results[name] = "skipped (no runtime)"
            continue
        if _refuse_symlink(rp):
            results[name] = "skipped (symlink)"
            continue
        try:
            rp.unlink(missing_ok=True)
            results[name] = "unlinked"
        except OSError as exc:
            print(
                f"[finalize_iterate] unlink runtime {name} failed: {exc}",
                file=sys.stderr,
            )
            results[name] = f"error: {exc}"
    return results


def _snapshot_triage_runtime(project_root: Path) -> str:
    """Atomic copy of runtime/triage_inbox.md → tracked; seed via aggregate_triage if absent.

    Triage carries no iterate-specific context so copy-snapshot is safe.
    See ADR 089 for the per-file decision rationale.
    """
    rp = runtime_path(project_root, "triage_inbox")
    tp = tracked_path(project_root, "triage_inbox")

    if rp.exists():
        if _refuse_symlink(rp) or _refuse_symlink(tp):
            return "skipped (symlink)"
        try:
            _atomic_replace(rp.read_bytes(), tp)
            rp.unlink(missing_ok=True)
            return "copied"
        except OSError as exc:
            print(
                f"[finalize_iterate] snapshot triage failed: {exc}",
                file=sys.stderr,
            )
            return f"error: {exc}"

    try:
        from tools import aggregate_triage

        rc = aggregate_triage.main(["--project-root", str(project_root)])
        return "seeded" if rc == 0 else f"seeded (rc={rc})"
    except Exception as exc:  # noqa: BLE001 best-effort
        print(f"[finalize_iterate] triage seed failed: {exc}", file=sys.stderr)
        return f"seed-error: {exc}"


def _update_dashboard(project_root: Path, session_id: str, run_id: str) -> str | None:
    """Update tracked build_dashboard.md (always — runtime variant lacks run_id).

    ``run_id`` is embedded so F11's check_build_dashboard_has_run_id
    succeeds (F5b runs BEFORE F6 commit + F7 event, so SHA isn't yet
    available). The Stop-hook runtime variant doesn't carry run_id; this
    direct-write is canonical, runtime gets wiped after. See ADR 089.
    """
    try:
        from tools.update_build_dashboard import generate_dashboard

        content = generate_dashboard(
            project_root, phase="iterate", session_id=session_id, run_id=run_id
        )
        out_path = tracked_path(project_root, "build_dashboard")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return str(out_path.relative_to(project_root))
    except Exception as exc:
        print(f"[finalize_iterate] dashboard failed: {exc}", file=sys.stderr)
        return None


def _update_compliance(project_root: Path) -> list[str]:
    """Regenerate compliance reports. Returns list of written paths."""
    # _SCRIPTS_DIR = shared/scripts → parent.parent = repo root
    compliance_plugin = _SCRIPTS_DIR.parent.parent / "plugins" / "shipwright-compliance"
    script = compliance_plugin / "scripts" / "tools" / "update_compliance.py"

    if not script.exists():
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(script),
             "--project-root", str(project_root),
             "--phase", "iterate"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            compliance_dir = project_root / ".shipwright" / "compliance"
            if compliance_dir.is_dir():
                return [str(f.relative_to(project_root)) for f in compliance_dir.iterdir() if f.is_file()]
        else:
            print(f"[finalize_iterate] compliance failed: {result.stderr[:200]}", file=sys.stderr)
    except Exception as exc:
        print(f"[finalize_iterate] compliance failed: {exc}", file=sys.stderr)
    return []


def _record_event(
    project_root: Path,
    commit: str,
    run_id: str,
    description: str,
    event_extras: dict | None = None,
) -> str | None:
    """Record work_completed event. Returns event ID or None.

    Post-iterate-2026-05-23: ``commit`` may be the empty string for the
    F5b-pre call (the F6 commit hasn't happened yet). The event is still
    recorded with ``commit=""`` so it lands in events.jsonl BEFORE the
    compliance regen — making the iterate's own event visible to the
    snapshot that F6 commits. After F6, the caller invokes
    :func:`attach_commit_after_finalize` to backfill the SHA.

    ``event_extras`` (optional) is merged into the event so the F11
    verifier's spec-impact / FR / change-type fields are present from the
    start. Caller-supplied keys override the defaults built here EXCEPT
    for the system-owned identity fields (``id``, ``ts``, ``type``,
    ``source``, ``adr_id``, ``commit``).

    Idempotent per ``run_id``: a second call with the same ``run_id`` does
    NOT duplicate the event — the existing event_id is returned. This
    matters because finalize may be invoked multiple times (operator
    re-run, generic Stop-hook fallback) and we don't want each call to
    add another ``work_completed`` row to ComplianceData.
    """
    try:
        from tools.record_event import append_event, generate_event_id, read_events
    except Exception as exc:
        print(f"[finalize_iterate] event recording failed: {exc}", file=sys.stderr)
        return None

    try:
        # Idempotency: scan for an existing work_completed event for this run_id.
        for prior in read_events(project_root):
            if (
                prior.get("type") == "work_completed"
                and prior.get("source") == "iterate"
                and prior.get("adr_id") == run_id
            ):
                # Already recorded by an earlier finalize call — return that
                # event's ID so callers can still patch the commit SHA later.
                return prior.get("id")

        event: dict = {}
        # Caller-supplied fields land FIRST so the system fields below
        # override them (we don't let callers spoof identity / source).
        if event_extras:
            for k, v in event_extras.items():
                if k in {"id", "ts", "type", "source", "adr_id", "commit"}:
                    continue
                event[k] = v

        event.update({
            "v": 1,
            "id": generate_event_id(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "work_completed",
            "source": "iterate",
            # Always set "commit" so the schema is consistent across
            # pre/post-commit calls; "" is the documented placeholder
            # that attach_commit_after_finalize later patches.
            "commit": commit or "",
            # Idempotency key — matches the SKILL.md F7 convention of
            # storing run_id as adr_id (see record_event.py --adr-id).
            "adr_id": run_id,
        })
        if description and "description" not in event:
            event["description"] = description
        session = os.environ.get("SHIPWRIGHT_SESSION_ID", "")
        if session and "session" not in event:
            event["session"] = session

        return append_event(project_root, event)
    except Exception as exc:
        print(f"[finalize_iterate] event recording failed: {exc}", file=sys.stderr)
        return None


def attach_commit_after_finalize(
    project_root: Path,
    event_id: str,
    commit_sha: str,
) -> bool:
    """Patch the post-F6 commit SHA into the event recorded by
    :func:`run`'s F5b-pre step.

    Thin wrapper around :func:`record_event.attach_commit_to_event` so
    iterate finalize's API surface is self-contained — callers
    (SKILL.md F6.5, plus future automation) import this from
    ``finalize_iterate`` and don't need to know which module owns the
    line-replacement logic.

    Returns ``True`` on success, ``False`` if the event_id wasn't found
    in the log (e.g. when the F5b-pre call was skipped or the log was
    rotated). Best-effort: failures are non-blocking.
    """
    try:
        from tools.record_event import attach_commit_to_event
    except ImportError as exc:
        print(f"[finalize_iterate] attach_commit import failed: {exc}", file=sys.stderr)
        return False
    try:
        return attach_commit_to_event(project_root, event_id, commit_sha)
    except Exception as exc:  # noqa: BLE001 — best-effort post-commit patch
        print(f"[finalize_iterate] attach_commit failed: {exc}", file=sys.stderr)
        return False


def _generate_handoff(project_root: Path, session_id: str, run_id: str, reason: str) -> str | None:
    """Generate tracked session handoff with canon marker.

    Always writes the tracked variant — the Stop-hook-written runtime
    variant does NOT carry the canon-frontmarker the F11 verifier
    (check_session_handoff_fresh) keys on. The subsequent
    :func:`_unlink_runtime_artifacts` wipes the stale runtime variant.
    """
    try:
        from lib.events_log import latest_event_dt
        from tools.generate_session_handoff import generate_handoff

        # Deterministic canon-frontmatter timestamp — see
        # iterate-2026-05-22-deterministic-render-timestamps. Wall-clock
        # here re-dirtied session_handoff.md on every finalize_iterate call.
        _canon_dt = latest_event_dt(project_root)
        canon_fm = {
            "run_id": run_id,
            "phase": "iterate",
            "reason": reason,
            "timestamp": (
                _canon_dt.isoformat() if _canon_dt is not None
                else "(no events)"
            ),
        }
        content = generate_handoff(
            project_root, session_id,
            reason=reason,
            canon_frontmatter=canon_fm,
        )
        out_path = tracked_path(project_root, "session_handoff")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        return str(out_path.relative_to(project_root))
    except Exception as exc:
        print(f"[finalize_iterate] handoff failed: {exc}", file=sys.stderr)
        return None


def run(
    project_root: Path,
    run_id: str,
    commit: str = "",
    reason: str = "iterate finalization",
    event_extras: dict | None = None,
) -> dict:
    """Run all finalization steps. Returns structured result dict.

    Order (iterate-2026-05-23-compliance-md-single-producer):

      1. Record ``work_completed`` event into events.jsonl. If ``commit``
         is empty (the common F5b-pre case), the event lands with
         ``commit=""`` placeholder — caller patches via
         :func:`attach_commit_after_finalize` once F6 produces a SHA.
         ``event_extras`` (optional) supplies the F11-mandated fields
         (``intent``, ``spec_impact``, ``affected_frs``, ``new_frs``,
         ``change_type``, ``none_reason``, ``description``,
         ``changed_files``) so the event is COMPLETE at recording time
         and the F11 verifier passes without a second record_event call.
      2. Regenerate compliance MDs. They now reflect the just-recorded
         event, so the F6 commit snapshot is self-consistent.
      3. Regenerate build dashboard.
      4. Generate session handoff.

    The returned ``result["steps"]["event"]["id"]`` is the event_id F6.5
    must pass back to :func:`attach_commit_after_finalize`.
    """
    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "unknown")
    result: dict = {"steps": {}, "project_root": str(project_root)}

    # Step 1: record the work_completed event BEFORE compliance regen so
    # the regenerated MDs include the iterate's own event.
    event_id = _record_event(
        project_root, commit, run_id, reason, event_extras=event_extras,
    )
    if event_id:
        result["steps"]["event"] = {"id": event_id, "commit": commit or ""}
    else:
        result["steps"]["event"] = {"skipped": True, "reason": "record_event failed"}

    # Step 2: regenerate compliance MDs (consume the event recorded above).
    compliance_paths = _update_compliance(project_root)
    result["steps"]["compliance"] = (
        {"written": compliance_paths} if compliance_paths else {"skipped": True}
    )

    # Step 3: regenerate build dashboard.
    dashboard_path = _update_dashboard(project_root, session_id, run_id)
    result["steps"]["dashboard"] = (
        {"written": dashboard_path} if dashboard_path else {"skipped": True}
    )

    # Step 4: session handoff (after record_event so the handoff timestamp
    # reflects the event we just wrote — see iterate-2026-05-22 docs).
    handoff_path = _generate_handoff(project_root, session_id, run_id, reason)
    result["steps"]["handoff"] = (
        {"written": handoff_path} if handoff_path else {"skipped": True}
    )

    # Step 5 (iterate-2026-05-27): snapshot the runtime triage aggregation
    # into the tracked snapshot, then wipe any remaining runtime artifacts
    # so Stop hooks fired after F5b but before F11 don't re-dirty main.
    # Triage is the only artifact where runtime → tracked is a safe COPY;
    # session_handoff and build_dashboard carry iterate-specific context
    # that the runtime variant lacks, so they're regenerated above and
    # their runtime variants are wiped here.
    result["steps"]["triage_snapshot"] = {
        "outcome": _snapshot_triage_runtime(project_root),
    }
    result["steps"]["runtime_cleanup"] = _unlink_runtime_artifacts(project_root)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize iterate run")
    sub = parser.add_subparsers(dest="cmd")

    # Default subcommand-less invocation = run finalize. Kept as the
    # top-level args for backwards compatibility with existing callers.
    parser.add_argument("--project-root", help="Project root directory")
    parser.add_argument("--run-id", help="Iterate run ID")
    parser.add_argument("--commit", default="", help="Final commit SHA (optional)")
    parser.add_argument("--reason", default="iterate finalization", help="Handoff reason")
    parser.add_argument(
        "--event-extras-json",
        default="",
        help=(
            "JSON object merged into the work_completed event "
            "(intent / spec_impact / affected_frs / new_frs / change_type "
            "/ none_reason / description / changed_files). Required at "
            "F5b time so the F11 spec-impact verifier passes without a "
            "separate record_event call."
        ),
    )

    # New attach-commit subcommand: F6.5 in the SKILL.md.
    attach = sub.add_parser(
        "attach-commit",
        help="Patch the F6 commit SHA into a previously-recorded event.",
    )
    attach.add_argument("--project-root", required=True, help="Project root directory")
    attach.add_argument("--event-id", required=True, help="Event id returned from F5b")
    attach.add_argument("--commit", required=True, help="Git commit SHA from F6")

    args = parser.parse_args(argv)

    if args.cmd == "attach-commit":
        project_root = Path(args.project_root).resolve()
        ok = attach_commit_after_finalize(project_root, args.event_id, args.commit)
        print(json.dumps({"attached": bool(ok)}, ensure_ascii=False))
        return 0 if ok else 1

    # Default: run() invocation. project-root and run-id are mandatory here.
    if not args.project_root or not args.run_id:
        parser.error("--project-root and --run-id are required for the default invocation")

    project_root = Path(args.project_root).resolve()

    event_extras: dict | None = None
    if args.event_extras_json:
        try:
            event_extras = json.loads(args.event_extras_json)
            if not isinstance(event_extras, dict):
                parser.error("--event-extras-json must be a JSON object")
        except json.JSONDecodeError as exc:
            parser.error(f"--event-extras-json failed to parse: {exc}")

    result = run(
        project_root, args.run_id, args.commit, args.reason,
        event_extras=event_extras,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
