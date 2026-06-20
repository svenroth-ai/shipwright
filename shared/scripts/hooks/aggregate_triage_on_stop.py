#!/usr/bin/env python3
"""Stop hook: regenerate `.shipwright/agent_docs/triage_inbox.md`.

AC-3 of iterate-2026-05-11-triage-inbox-1a. Wraps
`shared/scripts/tools/aggregate_triage.py:main` for invocation from
plugin `hooks.json`.

Contract:
- **Never blocks.** Always exits 0, even on internal errors.
- **Greenfield-safe.** Silent no-op when project_root isn't a
  Shipwright-managed project (no `shipwright_run_config.json`).
- **Schema-compliant Stop output** (ADR-042). NO `additionalContext`;
  diagnostics → stderr.
- **Order:** registered after the triage producer `audit_compliance_on_stop`
  in every plugin's Stop array, so the aggregate observes the settled triage.
  (It is no longer literally last — `bloat_gate_on_stop` +
  `plugin_sync_reminder_on_stop` follow it — but neither writes triage.)
- **Fan-out dedup** (iterate-2026-06-20-aggregate-triage-stop-fanout-dedup):
  registered in all 12 plugins → fires ~12× per Stop. A once-per-(Stop, session)
  `event_once.claim_once_for_event` claim makes exactly one invocation
  regenerate; a failed winner releases the claim so a sibling retries.

Usage (from `hooks.json`):

    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/aggregate_triage_on_stop.py"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.artifact_paths import runtime_dir  # noqa: E402
from lib.event_once import claim_once_for_event, event_claim_path  # noqa: E402
from lib.project_root import is_shipwright_project, resolve_project_root  # noqa: E402

# aggregate_triage lives at shared/scripts/tools/aggregate_triage.py
from tools import aggregate_triage  # noqa: E402


def _resolve_project_root() -> Path:
    try:
        return resolve_project_root()
    except Exception:  # noqa: BLE001
        return Path.cwd()


def _read_payload() -> dict:
    """Hook protocol sends a JSON payload on stdin; parse it (``{}`` on error).

    Unlike the old consume-and-discard, the payload's ``session_id`` keys the
    fan-out dedup claim below.
    """
    try:
        data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _session_id(payload: dict) -> str:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def main() -> int:
    payload = _read_payload()

    project_root = _resolve_project_root()
    if not is_shipwright_project(project_root):
        # Greenfield-safe — silent no-op (canonical predicate, lib.project_root).
        return 0

    # Fan-out dedup: the hook is registered in every plugin, so one Stop event
    # fires it ~12×, each unconditionally regenerating the triage_inbox.md
    # derived cache (a non-atomic write_text). Claim once per (Stop, session) —
    # the first invocation regenerates; the rest skip. Taken AFTER the
    # is_shipwright_project no-op guard so a greenfield invocation never consumes
    # the claim. Serializing to one writer also closes the non-atomic-write
    # parallel-corruption window. Winner still observes the settled triage:
    # aggregate_triage runs after the producer audit_compliance_on_stop in every
    # plugin's Stop array, and audit_compliance's marker makes the first plugin's
    # invocation the audit. sid=="unknown" → helper regenerates N× (fail-open).
    sid = _session_id(payload)
    if not claim_once_for_event(project_root, "stop-triage-inbox", sid):
        sys.stderr.write(
            "[aggregate_triage_on_stop] fan-out dedup: already regenerated "
            "this stop — skipped\n"
        )
        return 0

    ok = False
    try:
        # Reuse the public CLI entry point so behavior is identical to
        # `uv run shared/scripts/tools/aggregate_triage.py`. Write to the
        # gitignored runtime/ subdir; iterate-finalize is the single
        # producer of the tracked variant
        # (iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox).
        rt = runtime_dir(project_root)
        rt.mkdir(parents=True, exist_ok=True)
        rc = aggregate_triage.main([
            "--project-root", str(project_root),
            "--out-dir", str(rt),
        ])
        ok = rc == 0
        if ok:
            sys.stderr.write("[aggregate_triage_on_stop] regenerated triage_inbox.md\n")
        else:
            sys.stderr.write(
                f"[aggregate_triage_on_stop] regen failed (exit {rc})\n"
            )
    except Exception as exc:  # noqa: BLE001 — never block Stop chain
        # ADR-042: diagnostics on Stop go to stderr, not additionalContext.
        sys.stderr.write(
            f"[aggregate_triage_on_stop] error: {type(exc).__name__}: {exc}\n"
        )
        # Always exit 0 — observability hook, not gate.
    finally:
        # A failed winner must NOT keep the claim, or it starves every other
        # fan-out invocation (and later stops within the TTL) of the regen,
        # leaving triage_inbox.md stale for the whole event. Release the claim
        # so a sibling / later stop retries (external review gpt#1). Safe to
        # retry because aggregate_triage's only non-zero rc path (--out-dir
        # rejection) returns BEFORE any write — a released claim never leaves a
        # partially-written cache behind.
        if not ok:
            try:
                event_claim_path(project_root, "stop-triage-inbox", sid).unlink(
                    missing_ok=True,
                )
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
