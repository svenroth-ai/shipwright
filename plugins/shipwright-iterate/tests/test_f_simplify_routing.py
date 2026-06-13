"""Drift-protection for OS1 / P3.2 — the code-simplify sub-skill (F-simplify.md)
and its SIMPLIFY-mode routing in the iterate Kern.

Mirrors test_f_debug_routing.py. Pins:

1. `references/F-simplify.md` exists, is non-empty, carries the Five Osmani
   Principles, the Chesterton-Fence check, and "fewer lines is not the goal".
2. F-simplify.md carries an MIT attribution footer to addyosmani/agent-skills.
3. F-simplify.md stays within the 400-LOC runtime-prompt budget.
4. The iterate Kern routes SIMPLIFY mode through F-simplify (link resolves) AND
   states the behavior-preserving reviewer gate (reject on behavior drift /
   removed coverage). The `behavior_snapshot.py` gate is referenced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"
REFERENCES_DIR = SKILL_MD.parent / "references"
F_SIMPLIFY = REFERENCES_DIR / "F-simplify.md"
# plugins/shipwright-iterate -> plugins -> repo root
REPO_ROOT = PLUGIN_ROOT.parent.parent
# behavior_snapshot.py is the shared SSoT gate (relocated from the iterate plugin
# in iterate-2026-06-13-unify-simplify-reducibility so the reducibility catalog
# can cite it without an inverted plugin->shared dependency).
SNAPSHOT_TOOL = REPO_ROOT / "shared" / "scripts" / "tools" / "behavior_snapshot.py"
GUIDE_MD = REPO_ROOT / "docs" / "guide.md"
CATALOG = REPO_ROOT / "shared" / "reducibility-catalog.md"

# The Five Osmani Principles — short keywords so prose edits still match.
FIVE_PRINCIPLES = [
    "preserve behavior",
    "follow conventions",
    "clarity over cleverness",
    "maintain balance",
    "scope to what changed",
]


def _f_simplify_text() -> str:
    return F_SIMPLIFY.read_text(encoding="utf-8")


def _kern_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _path_b_body() -> str:
    """Body of `## Path B: CHANGE ...` until the next H2. Simplify is a
    behavior-preserving CHANGE sub-mode, so its routing lives here (the Kern
    is at its 300-LOC cap — detail lives in references/F-simplify.md)."""
    pattern = re.compile(r"^## Path B: CHANGE.*?(?=\n## )", flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(_kern_text())
    return match.group(0) if match else ""


# --- F-simplify.md content --------------------------------------------------


def test_f_simplify_exists() -> None:
    assert F_SIMPLIFY.is_file(), (
        f"F-simplify.md missing at {F_SIMPLIFY}. OS1 (code-simplify) was never "
        "established — see Spec/external-frameworks-integration.md §OS1 + §6 (P3.2)."
    )


def test_f_simplify_not_empty() -> None:
    assert _f_simplify_text().strip(), "F-simplify.md is empty"


@pytest.mark.parametrize("principle", FIVE_PRINCIPLES)
def test_f_simplify_has_five_principles(principle: str) -> None:
    assert principle in _f_simplify_text().lower(), (
        f"Osmani principle '{principle}' not found in F-simplify.md."
    )


def test_f_simplify_has_chesterton_fence() -> None:
    assert "chesterton" in _f_simplify_text().lower(), (
        "F-simplify.md must carry the Chesterton-Fence pre-flight check."
    )


def test_f_simplify_has_fewer_lines_rule() -> None:
    assert "fewer lines is not the goal" in _f_simplify_text().lower(), (
        "F-simplify.md must state 'fewer lines is not the goal' (Osmani)."
    )


def test_f_simplify_has_mit_attribution() -> None:
    text = _f_simplify_text().lower()
    assert "addyosmani" in text and "addy osmani" in text and "mit" in text, (
        "F-simplify.md must carry an MIT attribution footer to "
        "addyosmani/agent-skills (© Addy Osmani) per Spec §7.2 license discipline."
    )


def test_f_simplify_under_loc_budget() -> None:
    loc = sum(1 for _ in _f_simplify_text().splitlines())
    assert loc <= 400, f"F-simplify.md is {loc} LOC, must be <= 400 (runtime-prompt budget)."


def test_f_simplify_references_snapshot_tool() -> None:
    assert SNAPSHOT_TOOL.is_file(), f"behavior_snapshot.py missing at {SNAPSHOT_TOOL}"
    assert "behavior_snapshot.py" in _f_simplify_text(), (
        "F-simplify.md must reference the behavior_snapshot.py gate."
    )


# --- Kern routing -----------------------------------------------------------


def test_kern_links_f_simplify() -> None:
    assert "references/F-simplify.md" in _kern_text(), (
        "Iterate Kern SKILL.md must link references/F-simplify.md so SIMPLIFY "
        "mode routes through the behavior-preserving wrap."
    )


def test_path_b_routes_simplify_through_f_simplify() -> None:
    body = _path_b_body()
    assert body, "Could not extract `## Path B: CHANGE` body from Kern SKILL.md."
    lowered = body.lower()
    assert "simplify" in lowered, "Path B must describe the SIMPLIFY sub-mode."
    assert "f-simplify" in lowered, "Path B must route the SIMPLIFY sub-mode through F-simplify."
    assert "behavior" in lowered and ("coverage" in lowered or "snapshot" in lowered), (
        "Path B SIMPLIFY routing must state the behavior-preserving gate (reject "
        "on behavior drift / removed coverage)."
    )


def test_guide_documents_simplify_submode() -> None:
    """Doc-follow (AC8): docs/guide.md must document the simplify sub-mode."""
    assert GUIDE_MD.is_file(), f"guide.md missing at {GUIDE_MD}"
    text = GUIDE_MD.read_text(encoding="utf-8").lower()
    assert "behavior-snapshot" in text, "guide.md must describe the Behavior-Snapshot wrap."
    assert "behavior_snapshot.py" in text, "guide.md must reference the behavior_snapshot.py gate."
    assert "fewer lines is not the goal" in text, "guide.md must carry the Osmani principle."
