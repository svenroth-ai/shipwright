"""Copy-parity: the run + iterate skill banners surface plain-language glosses
that EQUAL the shared Plain-Language Index in docs/guide.md Appendix A (K4b).

One source, no drift. The WebUI glossary and both skill banners draw from the
same bank (docs/guide.md Appendix A). This test binds each banner gloss to that
index VERBATIM, so a future edit to one surface that isn't mirrored on the other
FAILS here — the drift is detectable, not merely hoped-away
(iterate-2026-07-10-adopt-brief-plainbank).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE = REPO_ROOT / "docs" / "guide.md"
RUN_SKILL = (
    REPO_ROOT / "plugins" / "shipwright-run" / "skills" / "run" / "SKILL.md"
)
ITERATE_SKILL = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"
)

# The banner block starts on the line carrying this marker; the indented
# "  <Term>: <gloss>" lines that follow are the surfaced glosses, until the
# banner border (a non-matching line) ends the block.
_MARKER = "In plain words (shared index"
_GLOSS_RE = re.compile(r"^\s+([^:]+?):\s+(.+?)\s*$")
_BOLD_TERM_RE = re.compile(r"\*\*(.+?)\*\*")


def _plain_language_index() -> dict[str, str]:
    """Parse docs/guide.md Appendix A -> {bare official term: plain description}."""
    lines = GUIDE.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, ln in enumerate(lines)
        if ln.strip() == "### Plain-Language Index"
    )
    index: dict[str, str] = {}
    for ln in lines[start + 1:]:
        if ln.startswith("### "):
            break  # next subsection ends the table
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        plain, official = cells
        if not plain or set(plain) <= {"-", ":"}:
            continue  # separator row
        m = _BOLD_TERM_RE.search(official)
        if not m:
            continue  # header row ("Official term") — no bold term
        index[m.group(1).strip()] = plain
    return index


def _banner_glosses(skill_path: Path) -> dict[str, str]:
    """Extract {term: gloss} from the banner 'In plain words' block."""
    lines = skill_path.read_text(encoding="utf-8").splitlines()
    out: dict[str, str] = {}
    collecting = False
    for ln in lines:
        if _MARKER in ln:
            collecting = True
            continue
        if collecting:
            m = _GLOSS_RE.match(ln)
            if m:
                out[m.group(1).strip()] = m.group(2).strip()
            else:
                collecting = False  # border line ends the block
    return out


# --- The index itself is well-formed -----------------------------------------

def test_index_parses_and_has_core_terms():
    index = _plain_language_index()
    assert len(index) >= 7, f"expected >=7 index rows, got {len(index)}: {index}"
    for term in ("IREB-Spec", "ADR", "Conventional Commits"):
        assert term in index, f"Plain-Language Index missing '{term}'"


# --- Both banners surface at least one gloss ---------------------------------

def test_run_banner_has_glosses():
    assert _banner_glosses(RUN_SKILL), "run banner surfaces no plain-language glosses"


def test_iterate_banner_has_glosses():
    assert _banner_glosses(ITERATE_SKILL), (
        "iterate banner surfaces no plain-language glosses"
    )


# --- Copy-parity: every banner gloss EQUALS the shared index -----------------

def _assert_parity(skill_path: Path):
    index = _plain_language_index()
    glosses = _banner_glosses(skill_path)
    for term, gloss in glosses.items():
        assert term in index, (
            f"{skill_path.name} banner surfaces term '{term}' that is not in the "
            f"shared Plain-Language Index (docs/guide.md Appendix A). Add it to "
            f"the index or fix the banner term."
        )
        assert index[term] == gloss, (
            f"{skill_path.name} banner gloss for '{term}' has drifted from the "
            f"shared Plain-Language Index.\n  banner: {gloss!r}\n  index : "
            f"{index[term]!r}\nKeep the two identical (one source, no drift)."
        )


def test_run_banner_matches_index():
    _assert_parity(RUN_SKILL)


def test_iterate_banner_matches_index():
    _assert_parity(ITERATE_SKILL)


# --- A term surfaced on BOTH surfaces is worded identically -------------------

def test_shared_terms_identical_across_surfaces():
    """A term the run AND iterate banners both surface (e.g. ADR) must carry
    identical wording — the concrete proof that both draw from one bank."""
    run = _banner_glosses(RUN_SKILL)
    it = _banner_glosses(ITERATE_SKILL)
    shared = set(run) & set(it)
    assert shared, "expected at least one term surfaced on BOTH banners (e.g. ADR)"
    for term in shared:
        assert run[term] == it[term], (
            f"'{term}' is worded differently on the two banners:\n"
            f"  run    : {run[term]!r}\n  iterate: {it[term]!r}"
        )
