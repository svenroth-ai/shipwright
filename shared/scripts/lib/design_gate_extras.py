"""Six /shipwright-design gates the ledger walk found nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
FR-01.04). Each function enforces exactly one criterion:

* :func:`visual_tokens_present` — **#2** design tokens exist as one
  definition (file presence was checked before; its content never was).
* :func:`flows_present_for_multi_screen_app` — **#3** a multi-screen app
  must show >=1 flow between its screens.
* :func:`chrome_nav_targets_consistent` — **#5** shared chrome from one
  definition — a screen's nav must actually draw from it.
* :func:`standalone_html_violations` — **#6** mockups open standalone in a
  browser — no external ``src``/``href`` outside the one font-CDN exception.
* :func:`uploads_preserved` — **#8** supplied mockups preserved (git as the
  historical record: an uploaded file must never show as *modified*).
* :func:`iteration_touched_flagged_screens` — **#9** feedback regenerates
  only that screen (every flagged screen touched is hard-enforced; a
  drive-by change beyond it is a warning — Chrome Change Propagation is a
  legitimate reason for every screen to change in one round).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

try:
    # loaded as lib.design_gate_extras (shared/tests)
    from .brief_upload_accounting import accounted_by_applied_package
    from .design_gate_feedback import iteration_touched_flagged_screens, parse_feedback_round
    from .design_gate_html import (
        chrome_nav_targets_consistent,
        screen_declares_nav,
        standalone_html_violations,
    )
    from .design_gate_result import GateResult
except ImportError:
    # loaded as top-level design_gate_extras — check-design-gates.py puts
    # shared/scripts/lib itself on sys.path.
    from brief_upload_accounting import accounted_by_applied_package
    from design_gate_feedback import iteration_touched_flagged_screens, parse_feedback_round
    from design_gate_html import (
        chrome_nav_targets_consistent,
        screen_declares_nav,
        standalone_html_violations,
    )
    from design_gate_result import GateResult

__all__ = [
    "GateResult",
    "chrome_nav_targets_consistent",
    "flows_present_for_multi_screen_app",
    "iteration_touched_flagged_screens",
    "parse_feedback_round",
    "screen_declares_nav",
    "standalone_html_violations",
    "uploads_preserved",
    "visual_tokens_present",
]


# --------------------------------------------------------------------------- #
# #2 — visual design tokens
# --------------------------------------------------------------------------- #

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*#*\s*$")
_TOKEN_HEADING_PATTERNS = {
    "colours": re.compile(r"colou?rs?", re.IGNORECASE),
    "typography": re.compile(r"typography", re.IGNORECASE),
    "spacing": re.compile(r"spacing", re.IGNORECASE),
}


def _headings(content: str) -> dict[str, str]:
    """Map heading title (as written) → its body text up to the next heading."""
    out: dict[str, str] = {}
    title: str | None = None
    buf: list[str] = []
    for line in content.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if title is not None:
                out[title] = "\n".join(buf)
            title = m.group("title").strip()
            buf = []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out[title] = "\n".join(buf)
    return out


def visual_tokens_present(visual_guidelines_path: Path) -> GateResult:
    """**#2** — the file must exist AND actually carry non-empty Colours,
    Typography and Spacing content, not merely exist."""
    if not visual_guidelines_path.exists():
        return GateResult(False, f"{visual_guidelines_path.name} does not exist")
    try:
        content = visual_guidelines_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return GateResult(False, f"{visual_guidelines_path.name} unreadable: {exc}")

    headings = _headings(content)
    missing = []
    for label, pattern in _TOKEN_HEADING_PATTERNS.items():
        body = next((v for k, v in headings.items() if pattern.search(k)), None)
        if not body or not body.strip():
            missing.append(label)
    if missing:
        return GateResult(
            False,
            f"{visual_guidelines_path.name} is missing non-empty content for: {', '.join(missing)}",
        )
    return GateResult(True, "Colours, Typography and Spacing all present and non-empty")


# --------------------------------------------------------------------------- #
# #3 — flows between journey screens
# --------------------------------------------------------------------------- #


def flows_present_for_multi_screen_app(screen_count: int, flow_count: int) -> GateResult:
    """**#3** — a multi-screen app (a "journey" needs at least two screens)
    must show at least one flow. A single-screen app has no journey to show."""
    if screen_count < 2:
        return GateResult(True, f"{screen_count} screen(s) — no journey to show a flow for")
    if flow_count < 1:
        return GateResult(
            False,
            f"{screen_count} screens but 0 flows — a journey with no flow between its screens",
        )
    return GateResult(True, f"{screen_count} screens, {flow_count} flow(s)")


# --------------------------------------------------------------------------- #
# #8 — uploads preserved
# --------------------------------------------------------------------------- #


def uploads_preserved(project_root: Path, uploads_dir: Path) -> GateResult:
    """**#8** — an uploaded mockup, once committed, must never show as
    MODIFIED. Uses git's own status as the historical record. New files
    (never-yet-committed) and deletions are not this criterion's concern —
    only "was a supplied file changed" is."""
    try:
        rel_uploads = uploads_dir.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return GateResult(False, f"uploads dir {uploads_dir} is outside project root {project_root}")
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "status", "--porcelain", "--", rel_uploads],
            capture_output=True, text=True, check=False,
        )
    except (OSError, FileNotFoundError):
        return GateResult(True, "no git evidence available")
    if proc.returncode != 0:
        return GateResult(True, "no git evidence available")

    # X in "MU" (staged modify/unmerged) OR (Y=='M' AND X!='A', excludes "AM"
    # staged-add-then-edited, not "supplied" — Stage-2) is "modified".
    modified = [
        line[3:].strip().strip('"') for line in proc.stdout.splitlines()
        if line and ((line[0] in "MU") or (len(line) > 1 and line[1] == "M" and line[0] != "A"))
    ]
    # a Brief-package re-apply (the documented recovery after a re-approved package) accounts for its own uploads
    modified = [m for m in modified if not accounted_by_applied_package(project_root, uploads_dir / Path(m).name)]
    if modified:
        return GateResult(False, f"{len(modified)} uploaded file(s) modified after being supplied: {modified[:3]}")
    return GateResult(True, "no supplied upload was modified")
