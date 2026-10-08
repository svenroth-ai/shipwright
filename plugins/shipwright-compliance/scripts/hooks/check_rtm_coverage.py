#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""PreToolUse hook: Soft-block git commit when RTM coverage is below threshold.

Measures REQUIREMENT coverage -- the share of active requirements (and, reported
separately, acceptance criteria) with an executed-passing bound test -- from the
``.shipwright/compliance/test-traceability.json`` being COMMITTED: the staged
(index) copy, else the one at ``HEAD``; the working-tree copy, which the local
pipeline regenerates fail-closed as all ``not_run``, is read silently only outside
a repo or when git has no such file (any other git failure: one WARN). It never
regenerates the manifest (it fires on every ``git commit``); a stale or
provenance-unknown manifest is a WARN, and a non-current schema or a manifest with
no executed result is unmeasurable (WARN + allow), never 0%. Only when no manifest
exists does it fall back to the RTM's legacy "Traceability coverage" line (build
sections with a commit). Cases that cannot be measured emit a visible WARN
(``additionalContext``) instead of allowing silently.

Fires only for a real ``git ... commit`` invocation (:func:`is_git_commit`), not for
any command whose text merely contains "git commit".

**Ordering limit.** PreToolUse runs BEFORE the Bash command, so the index is read as
it stands then: a manifest staged by the same command (``git add <manifest> && git
commit``, ``git commit -a``, ``git commit <pathspec>``, ``-o``, ``-i``) is measured
from its previous index / HEAD copy. The block says so: stage the corrected
manifest in a separate command first. Claude Code shows STDERR to the model on exit
2 (the stdout JSON is kept for compatibility), so the block is written to both.

Exit codes:
  0 = allow (no compliance data yet, coverage sufficient, or unmeasurable + WARN)
  2 = soft-block (user can say "Continue anyway", gets logged)

The user can override by saying "Continue anyway". If they do, Claude should
log the override to .shipwright/agent_docs/compliance_overrides.log.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _resolve_project_root() -> str:
    """Resolve the managed project root.

    Hooks fire with cwd = workspace root, which in a subdirectory-project
    layout (e.g. ``webui/`` inside a monorepo) is one level ABOVE the managed
    project. ``os.getcwd()`` therefore found no ``traceability-matrix.md`` and
    the gate silently failed open (F5). ``resolve_project_root`` auto-descends
    into the single managed subdir (and honors ``SHIPWRIGHT_PROJECT_ROOT``),
    falling back to cwd for a standalone / not-yet-initialized project.
    """
    try:
        shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return str(resolve_project_root())
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return env_root if env_root else os.getcwd()


def _lib():
    """Import the sibling support module lazily, inside ``main()``'s own try/except.

    A top-level import failure would crash the hook process and hard-block every
    Bash call; here it surfaces as a visible WARN and an ALLOW."""
    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import rtm_gate_support  # noqa: PLC0415

    return rtm_gate_support


def is_git_commit(command: str) -> bool:
    """True for a real ``git ... commit`` invocation (``lib/git_commit_command``).

    If the parser module cannot be imported, the substring test keeps the gate firing.
    """
    try:
        lib_dir = Path(__file__).resolve().parent.parent / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        import git_commit_command  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - never let the parser's import hard-block Bash
        return "git commit" in command
    return git_commit_command.is_git_commit(command)


STAGING_HINT = (
    "This hook runs before the command, so a manifest staged by the same command "
    "(git add <manifest> && git commit, commit -a, commit <pathspec>, -o, -i) is "
    "measured from its previous index / HEAD copy: stage the corrected manifest in a "
    "separate command first, then commit."
)
RATCHET_HINT = (
    "A project far below target records its measured value as "
    "enforcement.rtm_coverage_baseline in shipwright_compliance_config.json; "
    "the gate then ratchets from there. The hook never writes it."
)
OVERRIDE_HINT = (
    "The user may say 'Continue anyway' to override this check. "
    "If they do, log the override to .shipwright/agent_docs/compliance_overrides.log "
    "with timestamp, hook name 'check_rtm_coverage', and reason."
)


def _hook_block(reason: str, details: dict[str, Any]) -> dict[str, Any]:
    """Build soft-block hook output with override support."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"BLOCKED: {reason}\n\n{OVERRIDE_HINT}\n\n"
                "Note: Coverage gap will be flagged again at next compliance checkpoint."
            ),
            "blocked": True,
            "reason": reason,
            "details": details,
        }
    }


def _read_threshold(project_root: str) -> tuple[float, list[str], float | None]:
    return _lib().read_threshold(project_root)


def get_threshold(project_root: str) -> float:
    """Load RTM coverage threshold from compliance config."""
    return _read_threshold(project_root)[0]


def _measure(project_root: str) -> tuple[dict[str, Any] | None, list[str]]:
    return _lib().measure(project_root)


def _warn_output(warnings: list[str], info: str | None = None) -> None:
    parts = [f"check_rtm_coverage: {info}"] if info else []
    if warnings:
        parts.append("WARN (check_rtm_coverage): " + "; ".join(warnings))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "\n".join(parts),
    }}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        return 0  # Can't parse payload, allow

    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not is_git_commit(command):
        return 0

    # Resolve the managed project root (auto-descends in subdir layouts).
    project_root = _resolve_project_root()

    try:
        measure, warnings = _measure(project_root)
        threshold, config_warnings, baseline = _read_threshold(project_root)
    except Exception as exc:  # noqa: BLE001 - a broken gate must say so, then allow
        _warn_output([
            f"coverage measurement failed ({type(exc).__name__}: {str(exc)[:120]}); "
            "the 80% commit gate is NOT evaluating"
        ])
        return 0
    warnings += config_warnings
    if measure is None:
        if warnings:
            _warn_output(warnings)
        return 0

    lib = _lib()
    threshold_pct = lib.pct_text(threshold)
    if not lib.meets(measure, threshold):
        details: dict[str, Any] = {
            "coverage_pct": measure["pct"],
            "threshold_pct": float(threshold_pct),
            "metric": measure["kind"],
            "warnings": warnings,
            "ratchet_hint": RATCHET_HINT,
        }
        # the ordering limit concerns the staged manifest: the legacy RTM line has none
        hints = [RATCHET_HINT]
        if measure["kind"] == "requirements":
            details["staging_hint"] = STAGING_HINT
            hints.append(STAGING_HINT)
            details["fr"] = measure["coverage"]["fr"]
            details["ac"] = measure["coverage"]["ac"]
            details["source_commit"] = measure["source_commit"]
            details["uncovered_requirements"] = measure["coverage"]["uncovered_requirements"]
        else:
            details["uncovered_sections"] = lib.find_uncovered_sections(project_root)
        reason = f"{lib.describe(measure)} < {threshold_pct}% threshold"
        print(json.dumps(_hook_block(reason=reason, details=details)))
        # exit 2: Claude Code shows the model STDERR and ignores the stdout JSON
        print("\n".join([f"BLOCKED (check_rtm_coverage): {reason}", *hints, OVERRIDE_HINT]),
              file=sys.stderr)
        return 2

    if baseline is not None and lib.above_baseline(measure, baseline):
        warnings.append(
            f"measured {measure['pct']}% is above the recorded rtm_coverage_baseline "
            f"({lib.pct_text(baseline)}%); raise it in shipwright_compliance_config.json "
            "so the ratchet only moves up"
        )
    # the number and its definition are visible on every evaluated commit
    _warn_output(warnings, info=f"{lib.describe(measure)} >= {threshold_pct}% threshold")
    return 0


def _run() -> int:
    """Entrypoint with fail-open semantics.

    A PreToolUse ``Bash`` hook fires on every Bash call; an unhandled crash here
    would make Claude Code hard-block the unrelated command. Route ``main()``
    through ``run_failopen`` so any internal error logs + ALLOWs (exit 0). The
    deliberate soft-block (``main`` returns 2) passes through unchanged. Even the
    guard's own import failing must not hard-block — fall back to ALLOW.
    """
    try:
        lib_dir = Path(__file__).resolve().parent.parent / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from hook_failopen import run_failopen  # noqa: PLC0415

        return run_failopen("check_rtm_coverage", main)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(_run())
