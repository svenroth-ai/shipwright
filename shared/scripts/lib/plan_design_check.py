"""Plan-phase check: do the sections agree with the approved screens?

A section whose text contradicts an approved screen used to reach Build, where the
spec-reviewer stopped and a person was asked (e2e run 20: six gates). This module is the
deterministic half of the autonomous resolution rule (``section-writer.md``):

* **Rule.** When a brief package governs the run, or the run is autonomous
  (:func:`is_autonomous_design_run`), the approved screen wins over section/spec text; a brief
  value that deliberately overrides the screen wins over the screen. Either outcome is written
  into the section as ``Design decision: <what> -> <winner>, <reason>`` and logged. Only a case
  the rule cannot decide stays a ``Design contradiction: ... rule cannot decide`` and a question.
* **Check.** :func:`design_findings` compares the double-quoted UI text a section names, the
  breakpoint widths it states and the colors it names with ALL screens its Design Reference
  names (one combined model: a value right for any of them passes). It does NOT compare
  per-state content (the writer does that by reading). Conservative on purpose: a quoted string
  is compared only when it is on no screen but a screen string is a near miss of it (a new
  string, an identifier, a digits-only difference or a script-held string is never a finding).
* **Mode.** :func:`design_problems` returns gate problems only for an autonomous design run;
  an interactive run gets notes, never a failure -- its behaviour is unchanged.
"""
from __future__ import annotations

import difflib
import html as _html
import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Finding", "design_findings", "design_problems", "is_autonomous_design_run",
           "section_decisions", "section_contradictions", "undecided_marker"]

#: A contradiction line carrying this phrase is the rule's "cannot decide" outcome: it stays a
#: stop-and-ask in Build. Any other contradiction line in an autonomous run is a problem.
undecided_marker = "rule cannot decide"

_LINE = r"^[\s>*_\-]*Design {}[\s*_`]*:\s*(?P<t>.+)$"
_DECISION_RE = re.compile(_LINE.format("decision"), re.I | re.M)
_CONTRA_RE = re.compile(_LINE.format("contradiction"), re.I | re.M)
_NOTE_LINE_RE = re.compile(r"^[\s>*_\-]*Design (decision|extension|contradiction)", re.I)
_SCREEN_RE = re.compile(r"[\w./\\-]*designs[/\\]screens[/\\]([\w.\-]+\.html)", re.I)
_FENCE_RE = re.compile(r"```.*?```", re.S)
_LITERAL_RE = re.compile(r'"([^"\n]{3,60})"|“([^”\n]{3,60})”')
_PLAIN_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.'’&!?+–—-]*$")
#: kebab/snake/dotted ids and camelCase/PascalCase names: component and test-id names, not UI text
_IDENT_RE = re.compile(r"^[a-z0-9]+(?:[-_.][a-z0-9]+)+$|^[a-z]+[A-Z]\w*$|^[A-Z][a-z0-9]+[A-Z]\w*$")
_MEDIA_RULE_RE = re.compile(r"@media([^{]*)\{", re.I)
_WIDTH_RE = re.compile(r"(?:max|min)-width\s*:\s*(\d+)px", re.I)
_SCRIPT_STR_RE = re.compile(r"""(["'`])((?:(?!\1)[^\n]){3,200})\1""")
_LINK_RE = re.compile(r"<link\b[^>]*>", re.I)
_FONT_HOST_RE = re.compile(r"fonts\.(?:googleapis|gstatic)\.com|css2?\?family=", re.I)
_PX_RE = re.compile(r"\b(\d{3,4})\s*px\b")
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
_ATTR_RE = re.compile(r'\b(?:aria-label|title|alt)\s*=\s*"([^"]*)"', re.I)
_VISATTR_RE = re.compile(r'\b(?:placeholder|value)\s*=\s*"([^"]*)"', re.I)
_WS_RE = re.compile(r"\s+")
_ATTR_ONLY_WORDS = re.compile(r"\b(button|label|text|reads?|says?|shows?|caption)\b", re.I)
_ATTR_EXCUSE = re.compile(r"aria|title|tooltip|placeholder|\balt\b|accessible|screen.?reader|sr-only", re.I)
_BP_WORDS = re.compile(r"breakpoint|@media", re.I)
_COLOR_WORDS = re.compile(r"colou?r|background|border|accent|teal|text", re.I)

NEAR_RATIO = 0.75
COLOR_NEAR = 24  # max per-channel distance for "same token, typed wrong"


@dataclass(frozen=True)
class Finding:
    kind: str  # unresolved_contradiction | text_mismatch | visible_vs_attribute | breakpoint_mismatch | color_mismatch
    screen: str
    section_says: str
    screen_shows: str

    def text(self, section: str) -> str:
        return (f"{section}: {self.kind} vs {self.screen}: section says '{self.section_says}', "
                f"screen shows '{self.screen_shows}' -- apply the design rule and write a "
                f"'Design decision:' line (or fix the section)")


def is_autonomous_design_run(project_root: Path) -> bool:
    """True when a brief package governs the run or its autonomy is not interactive.

    ``autonomy: guided`` WITHOUT a ``brief_package`` is the interactive run: unchanged. Any
    unreadable config is "not autonomous" (the old behaviour), never a crash.
    """
    try:
        cfg = json.loads((Path(project_root) / "shipwright_run_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(cfg, dict):
        return False
    if cfg.get("brief_package"):
        return True
    return str(cfg.get("autonomy", "")).strip().lower() in ("autonomous", "unattended")


def _norm(s: str) -> str:
    return _WS_RE.sub(" ", _html.unescape(s).replace(" ", " ").replace("’", "'")).strip().lower()


def section_decisions(text: str) -> list[str]:
    return [m.group("t").strip() for m in _DECISION_RE.finditer(text)]


def section_contradictions(text: str) -> list[str]:
    return [m.group("t").strip() for m in _CONTRA_RE.finditer(text)]


@dataclass
class _Model:
    frags: list[str]
    vis: str
    attr: str
    known: str  # visible text + script/template strings: never a "mismatch" target
    media: set[int]
    colors: set[str]
    external_css: bool


def _combined_model(htmls: list[str]) -> _Model:
    """ONE model over all referenced screens: a value right for any of them passes."""
    frags: list[str] = []
    attrs: list[str] = []
    scripts: list[str] = []
    media: set[int] = set()
    colors: set[str] = set()
    ext = False
    for html in htmls:
        attrs += [_norm(a) for a in _ATTR_RE.findall(html)]
        media |= {int(w) for pre in _MEDIA_RULE_RE.findall(html) for w in _WIDTH_RE.findall(pre)}
        colors |= {c.lower() for c in _HEX_RE.findall(html)}
        ext = ext or any("stylesheet" in k.lower() and not _FONT_HOST_RE.search(k) for k in _LINK_RE.findall(html))
        for blk in re.findall(r"<(?:script|template)\b[^>]*>(.*?)</(?:script|template)>", html, re.S | re.I):
            scripts += [_norm(pc) for _q, lit in _SCRIPT_STR_RE.findall(blk) for pc in re.split(r"<[^>]*>", lit)]
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        frags += [_norm(t) for t in re.split(r"<[^>]*>", body)]
        frags += [_norm(v) for v in _VISATTR_RE.findall(html)]
    frags = [f for f in frags if len(f) >= 2]
    vis = " | ".join(frags)
    return _Model(frags, vis, " | ".join(attrs), vis + " | " + " | ".join(scripts), media, colors, ext)


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _literals(text: str) -> list[tuple[str, str]]:
    """(literal, its line) for double-quoted plain UI-looking strings, code fences removed."""
    out: list[tuple[str, str]] = []
    for line in _FENCE_RE.sub("", text).splitlines():
        if _NOTE_LINE_RE.match(line):
            continue
        for m in _LITERAL_RE.finditer(line):
            lit = next(g for g in m.groups() if g)
            if _PLAIN_TEXT_RE.match(lit) and any(c.isalpha() for c in lit) and not _IDENT_RE.match(lit):
                out.append((lit, line))
    return out


def _covered(note_lines: list[str], *needles: str) -> bool:
    """A recorded decision/extension/contradiction line that names the item."""
    hay = _norm(" ".join(note_lines))
    return any(n and _norm(n) in hay for n in needles)


def _digits_only_diff(a: str, b: str) -> bool:
    return re.sub(r"\d+", "#", a) == re.sub(r"\d+", "#", b)


def design_findings(text: str, screens: dict[str, str], guideline_text: str = "") -> list[Finding]:
    """Findings for one section's text against ALL its referenced screens (name -> html)."""
    notes = section_decisions(text)  # only a recorded decision resolves a mismatch
    findings: list[Finding] = [
        Finding("unresolved_contradiction", "-", c, "-") for c in section_contradictions(text)
        if undecided_marker not in c.lower()
    ]
    if not screens:
        return findings
    names = "+".join(sorted(screens))
    m = _combined_model(list(screens.values()))
    guide = _norm(guideline_text)
    body = _FENCE_RE.sub("", text)
    for lit, line in _literals(text):
        n = _norm(lit)
        if _covered(notes, lit) or n in guide or n in m.known:
            continue
        if n in m.attr:
            if not _ATTR_EXCUSE.search(line) and _ATTR_ONLY_WORDS.search(line):
                findings.append(Finding("visible_vs_attribute", names, lit, "(only as aria-label/title)"))
            continue
        near = max(m.frags, key=lambda f: difflib.SequenceMatcher(None, n, f).ratio(), default="")
        if (near and n != near and difflib.SequenceMatcher(None, n, near).ratio() >= NEAR_RATIO
                and not _digits_only_diff(n, near)):
            findings.append(Finding("text_mismatch", names, lit, near))
    if m.media and not m.external_css:
        for line in body.splitlines():
            if not _BP_WORDS.search(line) or _NOTE_LINE_RE.match(line):
                continue
            for w in map(int, _PX_RE.findall(line)):
                if w not in m.media and not _covered(notes, str(w)):
                    findings.append(Finding("breakpoint_mismatch", names, f"{w}px",
                                            "/".join(f"{x}px" for x in sorted(m.media))))
    known = m.colors | {c.lower() for c in _HEX_RE.findall(guideline_text)}
    for line in body.splitlines():
        if not _COLOR_WORDS.search(line):
            continue
        for c in (x.lower() for x in _HEX_RE.findall(line)):
            if c in known or _covered(notes, c) or not known:
                continue
            near_c = [k for k in sorted(known) if max(abs(a - b) for a, b in zip(_rgb(c), _rgb(k))) <= COLOR_NEAR]
            if near_c:
                findings.append(Finding("color_mismatch", names, c, near_c[0]))
    out: list[Finding] = []
    for f in findings:
        if f not in out:
            out.append(f)
    return out


def _screens_for(text: str, project_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _SCREEN_RE.finditer(text):
        p = Path(project_root) / ".shipwright" / "designs" / "screens" / m.group(1)
        if m.group(1) not in out and p.is_file():
            out[m.group(1)] = p.read_text(encoding="utf-8", errors="ignore")
    return out


def design_problems(planning_dir: Path, project_root: Path, autonomous: bool | None = None
                    ) -> tuple[list[str], list[str]]:
    """(problems, notes). Problems only for an autonomous design run; notes otherwise
    (the notes are shown by ``check-design-contradictions.py``, not by the plan gate)."""
    auto = is_autonomous_design_run(project_root) if autonomous is None else autonomous
    guide = Path(project_root) / ".shipwright" / "designs" / "visual-guidelines.md"
    gtext = guide.read_text(encoding="utf-8", errors="ignore") if guide.is_file() else ""
    lines: list[str] = []
    for sec in sorted((Path(planning_dir) / "sections").glob("*.md")):
        text = sec.read_text(encoding="utf-8", errors="ignore")
        if "design reference" not in text.lower():
            continue
        screens = _screens_for(text, project_root)
        lines += [f"{sec.stem}: referenced screen not found: {n}"
                  for n in sorted({m.group(1) for m in _SCREEN_RE.finditer(text)} - set(screens))]
        lines += [f.text(sec.stem) for f in design_findings(text, screens, gtext)]
    return (lines, []) if auto else ([], lines)
