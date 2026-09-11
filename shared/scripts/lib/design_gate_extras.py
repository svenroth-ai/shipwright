"""Six /shipwright-design gates the ledger walk found nowhere in code
(``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
FR-01.04). Each function is named for, and enforces, exactly one criterion:

* :func:`visual_tokens_present` — **#2** "Design tokens (colours/typography/
  spacing) exist as one definition." Existence of ``visual-guidelines.md``
  was checked (file presence); its CONTENT never was.
* :func:`flows_present_for_multi_screen_app` — **#3** "Flows between journey
  screens are shown." Nothing required a flow to exist at all once a project
  has more than one screen — the floor this enforces.
* :func:`chrome_nav_targets_consistent` — **#5** "Shared chrome from one
  definition." ``chrome-definition.md`` is a prompt artifact; nothing
  checked a screen actually drew its navigation from it.
* :func:`standalone_html_violations` — **#6** "Mockups open standalone in a
  browser." A grep for an external ``src=``/``href=`` reference outside the
  one allowed font-CDN exception.
* :func:`uploads_preserved` — **#8** "Supplied mockups preserved, only
  missing generated." Uses git as the historical record rather than a
  hand-rolled baseline file: an uploaded file must never show as *modified*.
* :func:`iteration_touched_flagged_screens` — **#9** "Feedback regenerates
  only that screen." The *at-least* direction is hard-enforced (every
  flagged screen was actually touched); a *drive-by* change to an unflagged
  screen is reported as a warning, not a hard failure, because Chrome Change
  Propagation (``iteration-mode.md``) is a legitimate reason for every screen
  to change in the same round.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "GateResult",
    "chrome_nav_targets_consistent",
    "flows_present_for_multi_screen_app",
    "iteration_touched_flagged_screens",
    "parse_feedback_round",
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

#: One tag at a time, then attribute-by-attribute — the earlier single regex
#: anchored ``nav-item``/``topnav-link`` to the START of the class value, so
#: ``class="active nav-item"`` (the target class not first) false-PASSed as
#: having no nav (external Tier-3 review, PR #726 round 8).
_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_RE = re.compile(r'''([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))''')


def _tag_attrs(tag: str) -> dict[str, str]:
    return {
        name.lower(): dq if dq else (sq if sq else uq)
        for name, dq, sq, uq in _ATTR_RE.findall(tag)
    }


def _nav_targets(html: str) -> set[str]:
    targets = set()
    for tag in _TAG_RE.findall(html):
        attrs = _tag_attrs(tag)
        classes = attrs.get("class", "").split()
        if ("nav-item" in classes or "topnav-link" in classes) and attrs.get("href"):
            targets.add(attrs["href"])
    return targets


def screen_declares_nav(html: str) -> bool:
    """Whether a screen's markup carries any ``nav-item``/``topnav-link``
    anchor at all — tells "genuinely no shared chrome" apart from "no chrome
    definition despite screens plainly using one" (external review)."""
    return bool(_nav_targets(html))


def chrome_nav_targets_consistent(chrome_definition_html: str, screen_html: str) -> GateResult:
    """**#5** — a screen's nav targets (the set of ``href`` values on its
    ``nav-item``/``topnav-link`` anchors) must be the SAME SET the chrome
    definition declares. Byte-identical markup is not required — icons and
    labels differ by design — but a different target set did not draw from
    the one definition. Screens with no nav markup (Layout C / auth) are
    exempt — nothing to compare."""
    chrome_targets = _nav_targets(chrome_definition_html)
    if not chrome_targets:
        return GateResult(True, "chrome definition declares no nav targets to compare")
    screen_targets = _nav_targets(screen_html)
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

#: A quote-only pattern false-PASSed an unquoted ``src=https://evil...``
#: (valid HTML) as non-external (external Tier-3 review, PR #726 round 8) —
#: ``_tag_attrs`` above already tokenizes quoted AND unquoted values alike.
_ABSOLUTE_OR_PROTOCOL_RELATIVE_RE = re.compile(r'^(?:https?:)?//', re.IGNORECASE)


def _hostname(url: str) -> str:
    """The URL's host, exactly — never a substring match (a hostile URL
    embedding an allowed host in its path/query, e.g.
    ``https://evil.example/?=fonts.googleapis.com``, must not pass)."""
    from urllib.parse import urlparse

    parsed = urlparse(url if "://" in url else f"https:{url}")
    return (parsed.hostname or "").lower()


def standalone_html_violations(html: str) -> list[str]:
    """**#6** — every external ``src``/``href`` reference outside the one
    allowed font-CDN exception. Empty list means the file is standalone."""
    violations = []
    for tag in _TAG_RE.findall(html):
        attrs = _tag_attrs(tag)
        for name in ("src", "href"):
            url = attrs.get(name)
            if url and _ABSOLUTE_OR_PROTOCOL_RELATIVE_RE.match(url):
                if _hostname(url) not in _ALLOWED_EXTERNAL_HOSTS:
                    violations.append(url)
    return violations


# --------------------------------------------------------------------------- #
# #8 — uploads preserved
# --------------------------------------------------------------------------- #


def uploads_preserved(project_root: Path, uploads_dir: Path) -> GateResult:
    """**#8** — an uploaded mockup, once committed, must never show as
    MODIFIED. Uses git's own status as the historical record rather than a
    hand-rolled baseline file. New files (never-yet-committed uploads) and
    deletions are not this criterion's concern — only "was a supplied file
    changed" is.
    """
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
    are reported as a warning, not a failure: Chrome Change Propagation
    legitimately touches every screen in the same round, and that is not
    distinguishable from a drive-by change without reading the decision log.
    """
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
