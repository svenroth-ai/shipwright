#!/usr/bin/env python3
"""Canonical SessionStart hook for all Shipwright plugins.

Injects Shipwright environment variables into Claude's session context:
- SHIPWRIGHT_SESSION_ID: current session id (from hook payload)
- SHIPWRIGHT_PLUGIN_ROOT: active plugin directory (from CLAUDE_PLUGIN_ROOT)
- SHIPWRIGHT_PROJECT_ROOT: resolved via resolve_project_root() for
  subdirectory-safe monorepo support. Falls back to cwd on failure.
- SHIPWRIGHT_ROOT_SESSION_ID / SHIPWRIGHT_LOOP_ID / SHIPWRIGHT_LOOP_UNIT_ID:
  autonomous-loop env vars, only emitted when set by the parent runner.

Also writes SHIPWRIGHT_SESSION_ID into CLAUDE_ENV_FILE (if provided) so
bash subprocesses inherit it — additionalContext alone does not reach
child processes spawned by Claude's Bash tool.

**Phase-Quality injection (PR 4, Szenario C):** at SessionStart this
hook reads ``.shipwright/agent_docs/skill-compliance-findings.md`` and appends up
to 5 Tier-1 FAILs as ``additionalContext``. Only Tier-1 FAILs are
injected; Tier-2 (heuristic) is silent (plan § 4.3).

**Default is ON** (``audit_inject``) since the Phase-Quality epic
completed — rollout calculus shifted from "wait 6 weeks, opt in" to
"flip now, opt out on noise." Set
``SHIPWRIGHT_PHASE_QUALITY_MODE=audit_only`` to disable injection and
fall back to silent-file-only observability.

This replaces the 8 per-plugin copies that used to live in
plugins/*/scripts/hooks/capture-session-id.py. All plugin hooks.json
files now reference this single canonical implementation.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Make shared lib importable regardless of which plugin invokes this hook.
# This file lives at shared/scripts/hooks/, so parents[1] is shared/scripts/
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _resolve_root() -> str:
    """Find the Shipwright project root, tolerating subdirectory layouts."""
    try:
        from lib.project_root import resolve_project_root
        return str(resolve_project_root())
    except (ImportError, ValueError):
        return os.getcwd()


# Default ON: injection is enabled unless the user explicitly opts out
# via SHIPWRIGHT_PHASE_QUALITY_MODE=audit_only. Plan § 9.1 originally
# defaulted this OFF during the 6-week staggered rollout; post-epic the
# calculus flipped to "trust the rollback lever, ship the signal" for
# small/solo setups.
_OFF_MODE = "audit_only"

# Cap at 5 FAILs so a full phase-cluster (e.g. C1 + I1-I3 + W3) can
# surface in one SessionStart without blowing Claude's first-response
# context budget. Plan § 4.3 / R20 originally specified 3; raised after
# rollout to 5 for better phase coverage while staying below the
# "wall-of-text" threshold.
_MAX_INJECTED_FAILS = 5

# Tier-2 IDs that MUST never reach injection (even if the summary file
# contains them). Mirrors TIER_2_CHECK_IDS in shared.scripts.lib.phase_quality.
_TIER_2_IDS: frozenset[str] = frozenset({
    "W1", "I4", "T2", "Q1", "S3", "S4", "S5", "S7", "S9", "S10",
    "Cmp1", "D2",
})

# Match a bullet like `  - **W2** evidence text here.` in the summary
# file (written by rewrite_session_findings_summary).
_FAIL_BULLET_RE = re.compile(
    r"^\s{2,}- \*\*(?P<id>[A-Za-z][A-Za-z0-9]*\d+)\*\* (?P<evidence>.+)$"
)
_RUN_HEADER_RE = re.compile(r"^##\s+(?P<phase>[A-Za-z]+) — (?P<run>\S+)\s*$")


def _phase_quality_inject_enabled() -> bool:
    """Return True unless SHIPWRIGHT_PHASE_QUALITY_MODE == audit_only.

    Default ON — injection is the normal mode post-epic. The env var is
    the documented opt-out lever (``audit_only`` → silent-file-only,
    no SessionStart noise).
    """
    mode = os.environ.get("SHIPWRIGHT_PHASE_QUALITY_MODE", "").strip().lower()
    return mode != _OFF_MODE


def _collect_tier1_fails(summary_text: str) -> list[dict[str, str]]:
    """Parse skill-compliance-findings.md and return up to N Tier-1 FAILs.

    The summary file groups runs under ``## {phase} — {run_id}`` headers
    and lists open FAILs as bulleted lines under ``- open FAILs:``.
    Multiple runs might be present; we read them in file order (newest
    first since rewrite_session_findings_summary sorts by ``audited_at``
    descending). A FAIL id in ``_TIER_2_IDS`` is filtered out.
    """
    fails: list[dict[str, str]] = []
    current_phase = ""
    current_run = ""
    in_fails_section = False

    for raw in summary_text.splitlines():
        header = _RUN_HEADER_RE.match(raw)
        if header:
            current_phase = header.group("phase")
            current_run = header.group("run")
            in_fails_section = False
            continue
        stripped = raw.strip()
        if stripped.startswith("- open FAILs:"):
            in_fails_section = True
            continue
        if not in_fails_section:
            continue
        if stripped and not stripped.startswith("-"):
            # End of the fails block.
            in_fails_section = False
            continue
        m = _FAIL_BULLET_RE.match(raw)
        if not m:
            continue
        check_id = m.group("id")
        if check_id in _TIER_2_IDS:
            continue
        fails.append({
            "id": check_id,
            "phase": current_phase,
            "run": current_run,
            "evidence": m.group("evidence").strip(),
        })
        if len(fails) >= _MAX_INJECTED_FAILS:
            break
    return fails


def _format_injection(fails: list[dict[str, str]]) -> str:
    """Return the additionalContext block shown at SessionStart."""
    count = len(fails)
    lines = [
        f"[Shipwright Phase-Quality] Letzte Phase(n) hatten {count} "
        f"offene Tier-1 FAIL(s):",
    ]
    for f in fails:
        phase = f["phase"] or "unknown"
        evidence = f["evidence"]
        lines.append(f"• {f['id']} ({phase}): {evidence}")
    lines.append(
        "Bitte vor weiteren Schritten adressieren — oder override via "
        "SHIPWRIGHT_SKIP_QUALITY_CHECK + SHIPWRIGHT_AUDIT_OVERRIDE_REASON "
        "dokumentieren."
    )
    return "\n".join(lines)


def _build_phase_quality_injection(project_root: str) -> str:
    """Return the injection string, or empty when not applicable."""
    if not _phase_quality_inject_enabled():
        return ""
    pr = Path(project_root)
    # Monorepo auto-descent guard — mirrors the audit hook. If cwd is a
    # strict ancestor of project_root (resolver auto-descended into a
    # managed subfolder while the user worked at a parent level), skip
    # injection to avoid off-scope Tier-1 FAIL noise. Explicit opt-in via
    # SHIPWRIGHT_PROJECT_ROOT env var pointing exactly at project_root.
    try:
        from lib.phase_quality import (
            cwd_is_strict_ancestor_of,
            project_root_was_explicitly_selected,
        )
    except ImportError:
        pass
    else:
        cwd = Path.cwd()
        if cwd_is_strict_ancestor_of(cwd, pr) \
                and not project_root_was_explicitly_selected(pr):
            return ""
    summary_path = pr / ".shipwright" / "agent_docs" / "skill-compliance-findings.md"
    try:
        text = summary_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""
    fails = _collect_tier1_fails(text)
    if not fails:
        return ""
    return _format_injection(fails)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Hooks should never fail

    session_id = payload.get("session_id")
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")

    if not session_id:
        return 0

    context_parts: list[str] = []

    if os.environ.get("SHIPWRIGHT_SESSION_ID") != session_id:
        context_parts.append(f"SHIPWRIGHT_SESSION_ID={session_id}")

    if plugin_root:
        context_parts.append(f"SHIPWRIGHT_PLUGIN_ROOT={plugin_root}")

    project_root = _resolve_root()
    context_parts.append(f"SHIPWRIGHT_PROJECT_ROOT={project_root}")

    # Autonomous-loop propagation (only emitted when parent runner set them).
    for var in (
        "SHIPWRIGHT_ROOT_SESSION_ID",
        "SHIPWRIGHT_LOOP_ID",
        "SHIPWRIGHT_LOOP_UNIT_ID",
    ):
        value = os.environ.get(var)
        if value:
            context_parts.append(f"{var}={value}")

    # Phase-Quality Tier-1 FAIL injection. The hook is registered in every
    # plugin, so one SessionStart event fires it ~12x with the identical
    # block. Dedup to once-per-event via claim_once (event-scoped on the
    # session id, TTL-armed so a later resume/compact re-emits). Fail-open:
    # claim_once returns True on any guard error, so a real FAIL is never
    # dropped. Only the block is gated — env context is emitted every time.
    # audit_only short-circuits before claiming so the opt-out leaves no
    # cache file. Non-blocking; injection errors never propagate.
    if _phase_quality_inject_enabled():
        try:
            from lib.event_once import claim_once
            claim_path = (
                Path(project_root) / ".shipwright" / ".cache"
                / f"sessionstart-{session_id}.claim"
            )
            may_emit = claim_once(claim_path)
        except Exception:  # noqa: BLE001
            may_emit = True
        if may_emit:
            try:
                injection = _build_phase_quality_injection(project_root)
            except Exception:  # noqa: BLE001
                injection = ""
            if injection:
                context_parts.append(injection)

    if context_parts:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(context_parts),
            }
        }))

    # CLAUDE_ENV_FILE fallback so SHIPWRIGHT_SESSION_ID reaches bash subprocesses.
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            existing = ""
            try:
                with open(env_file, encoding="utf-8") as f:
                    existing = f.read()
            except FileNotFoundError:
                pass
            if f"SHIPWRIGHT_SESSION_ID={session_id}" not in existing:
                with open(env_file, "a", encoding="utf-8") as f:
                    f.write(f"export SHIPWRIGHT_SESSION_ID={session_id}\n")
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
