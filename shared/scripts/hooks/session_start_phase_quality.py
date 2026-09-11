"""Phase-Quality Tier-1 FAIL injection for capture_session_id.py's SessionStart hook.

Split out of capture_session_id.py (bloat gate) — this is a self-contained
concern (PR 4, Szenario C): at SessionStart, read the transient findings
summary (``phase_quality.SUMMARY_PATH``, under the gitignored
``skill-compliance`` dir since iterate-2026-06-09) and format up to 5 Tier-1
FAILs as an ``additionalContext`` block. Only Tier-1 FAILs are injected;
Tier-2 (heuristic) is silent (plan § 4.3).

**Default is ON** (``audit_inject``) since the Phase-Quality epic completed —
rollout calculus shifted from "wait 6 weeks, opt in" to "flip now, opt out on
noise." Set ``SHIPWRIGHT_PHASE_QUALITY_MODE=audit_only`` to disable injection
and fall back to silent-file-only observability.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

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


def phase_quality_inject_enabled() -> bool:
    """Return True unless SHIPWRIGHT_PHASE_QUALITY_MODE == audit_only.

    Default ON — injection is the normal mode post-epic. The env var is
    the documented opt-out lever (``audit_only`` → silent-file-only,
    no SessionStart noise).
    """
    mode = os.environ.get("SHIPWRIGHT_PHASE_QUALITY_MODE", "").strip().lower()
    return mode != _OFF_MODE


def _collect_tier1_fails(summary_text: str) -> list[dict[str, str]]:
    """Parse the findings digest (``_findings.md``) and return its Tier-1 FAILs.

    The summary file groups runs under ``## {phase} — {run_id}`` headers
    and lists open FAILs as bulleted lines under ``- open FAILs:``.
    Multiple runs might be present; we read them in file order (newest
    first since rewrite_session_findings_summary sorts by ``audited_at``
    descending). A FAIL id in ``_TIER_2_IDS`` is filtered out. RAW parse — each
    FAIL keeps its ``run`` id so the caller applies the sentinel-run policy
    (mirrors the writer's ``load_findings`` vs ``load_actionable_findings``).
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


def build_phase_quality_injection(project_root: str) -> str:
    """Return the injection string, or empty when not applicable."""
    if not phase_quality_inject_enabled():
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
    # The findings summary is a transient derived cache under the gitignored
    # skill-compliance dir (relocated in iterate-2026-06-09 so idle main stays
    # clean). Follow the SSoT constant; if phase_quality can't be imported in
    # this minimal hook context there is nothing meaningful to inject.
    try:
        from lib.phase_quality import SUMMARY_PATH as _PQ_SUMMARY_REL
        from lib.phase_quality import is_sentinel_run
    except ImportError:
        return ""
    summary_path = pr / _PQ_SUMMARY_REL
    try:
        text = summary_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""
    # Actionability policy (mirrors the writer's load_actionable_findings): drop
    # sentinel-run snapshots so a stale on-Stop-only digest can't cry wolf at
    # SessionStart, THEN cap — so sentinels can't starve real FAILs out of the
    # budget (iterate-2026-06-15-sessionstart-sentinel-filter).
    fails = [
        f for f in _collect_tier1_fails(text) if not is_sentinel_run(f.get("run"))
    ][:_MAX_INJECTED_FAILS]
    if not fails:
        return ""
    return _format_injection(fails)
