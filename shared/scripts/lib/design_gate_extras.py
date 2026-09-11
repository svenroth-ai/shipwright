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
from dataclasses import dataclass
from pathlib import Path

try:
    from .html_tag_scanner import parse_tags  # loaded as lib.design_gate_extras (shared/tests)
except ImportError:
    # loaded as top-level design_gate_extras — check-design-gates.py puts
    # shared/scripts/lib itself on sys.path.
    from html_tag_scanner import parse_tags

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


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str
    warnings: tuple[str, ...] = ()


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
# #5 — shared chrome from one definition
# --------------------------------------------------------------------------- #


def _nav_targets(html: str) -> set[str]:
    targets = set()
    for attrs in parse_tags(html):
        classes = attrs.get("class", "").split()
        href = attrs.get("href")
        if href and ("nav-item" in classes or "topnav-link" in classes):
            targets.add(href)
    return targets


def screen_declares_nav(html: str) -> bool:
    """Whether a screen's markup carries any ``nav-item``/``topnav-link``
    anchor at all — tells "genuinely no shared chrome" apart from "no chrome
    definition despite screens plainly using one" (external review)."""
    return bool(_nav_targets(html))


def chrome_nav_targets_consistent(chrome_definition_html: str, screen_html: str) -> GateResult:
    """**#5** — a screen's nav targets (``href`` values on its ``nav-item``/
    ``topnav-link`` anchors) must be the SAME SET the chrome definition
    declares — byte-identical markup isn't required, a different target set
    is. No-nav screens (Layout C / auth) are exempt. An EXISTING but empty/
    malformed definition is NOT itself an exemption — a screen that plainly
    uses nav markup still has to draw it from somewhere (round 9)."""
    chrome_targets = _nav_targets(chrome_definition_html)
    screen_targets = _nav_targets(screen_html)
    if not chrome_targets:
        if screen_targets:
            return GateResult(
                False,
                f"chrome definition declares no nav targets, but the screen "
                f"declares {sorted(screen_targets)} — not drawn from it",
            )
        return GateResult(True, "chrome definition declares no nav targets to compare")
    if not screen_targets:
        return GateResult(True, "screen has no nav markup (e.g. an auth/Layout-C screen) — exempt")
    if screen_targets != chrome_targets:
        return GateResult(
            False,
            f"nav targets {sorted(screen_targets)} do not match the chrome "
            f"definition's {sorted(chrome_targets)}",
        )
    return GateResult(True, f"{len(screen_targets)} nav target(s) match the chrome definition")


# --------------------------------------------------------------------------- #
# #6 — standalone HTML
# --------------------------------------------------------------------------- #

#: Google Fonts is the one documented exception (`step-4-generate-screens.md`
#: "no external dependencies except optional CDN font").
_ALLOWED_EXTERNAL_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

_WHITESPACE_STRIP_RE = re.compile(r"[\t\n\r]")


def _external_host(raw: str) -> str | None:
    """The value's hostname if external (``http``/``https`` or protocol-
    relative), else ``None``. Decided by SCHEME, not leading-slash count —
    a real browser also resolves ``https:evil.example`` (0 slashes) and
    ``https:/evil.example`` (1) externally (round 8b). Tab/newline are
    stripped from anywhere in the value, not just the ends, since a literal
    one inside a quoted attribute is valid HTML. Never a substring match —
    ``https://evil.example/?=fonts.googleapis.com`` must not pass."""
    from urllib.parse import urlparse

    normalized = _WHITESPACE_STRIP_RE.sub("", raw).strip().replace("\\", "/")
    if not normalized:
        return None
    if normalized.startswith("//"):
        parsed = urlparse(f"https:{normalized}")
    else:
        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https"):
            return None
    return (parsed.hostname or "").lower()


def standalone_html_violations(html: str) -> list[str]:
    """**#6** — every external ``src``/``href`` reference outside the one
    allowed font-CDN exception. Empty list means the file is standalone."""
    violations = []
    for attrs in parse_tags(html):
        for name in ("src", "href"):
            raw = attrs.get(name)
            if not raw:
                continue
            host = _external_host(raw)
            if host is not None and host not in _ALLOWED_EXTERNAL_HOSTS:
                violations.append(raw)
    return violations


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
    if modified:
        return GateResult(False, f"{len(modified)} uploaded file(s) modified after being supplied: {modified[:3]}")
    return GateResult(True, "no supplied upload was modified")


# --------------------------------------------------------------------------- #
# #9 — iteration touches only the flagged screen(s)
# --------------------------------------------------------------------------- #

_ROUND_ENTRY_RE = re.compile(
    r"^###\s+#\d+\s+.+?\s+—\s+(?P<status>CHANGES|REJECTED|APPROVED|REVIEWED)\s*$"
    r"\n\n\*\*File:\*\*\s*(?P<file>\S+)",
    re.MULTILINE,
)


def parse_feedback_round(content: str) -> list[tuple[str, str]]:
    """``[(file, status)]`` for every per-screen entry in a
    ``design-feedback-round{N}.md`` export (format:
    ``review-viewer-template.md``'s ``exportFeedback``)."""
    return [(m.group("file"), m.group("status")) for m in _ROUND_ENTRY_RE.finditer(content)]


def iteration_touched_flagged_screens(
    flagged_files: list[str], git_modified_files: list[str]
) -> GateResult:
    """**#9** — every screen flagged CHANGES/REJECTED in this round must
    actually have been touched. Extra modified files beyond the flagged set
    are a warning, not a failure: Chrome Change Propagation legitimately
    touches every screen in one round, indistinguishable from a drive-by
    change without reading the decision log."""
    modified = set(git_modified_files)
    untouched = [f for f in flagged_files if f not in modified]
    if untouched:
        return GateResult(
            False,
            f"{len(untouched)} flagged screen(s) were not actually regenerated: {untouched}",
        )
    extra = sorted(modified - set(flagged_files))
    warnings = (
        (f"{len(extra)} screen(s) changed beyond the flagged set: {extra} — "
         "legitimate if this round was a chrome-wide propagation",)
        if extra else ()
    )
    return GateResult(True, f"all {len(flagged_files)} flagged screen(s) were touched", warnings)
