"""The code-reviewer agent checks the architecture-rules block, and the docs example rules are real."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_architecture_rules as par  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC34", "FR-01.01/AC35")
ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "plugins" / "shipwright-build" / "agents" / "code-reviewer.md"
DOC = ROOT / "docs" / "building-skills-plugins-agents.md"
BRIEF = ROOT / ".shipwright" / "planning" / "campaigns" / "2026-10-25-dfp-pilot-changelog-BRIEF.md"
HEADING = "## How to add an architecture rule"


def _agent() -> str:
    return " ".join(AGENT.read_text(encoding="utf-8").split())


def _frontmatter_tools() -> list[str]:
    head = AGENT.read_text(encoding="utf-8").split("---")[1]
    line = next(x for x in head.splitlines() if x.startswith("tools:"))
    return [t.strip() for t in line.split(":", 1)[1].split(",")]


def test_agent_checks_the_rules_block_of_conventions_md():
    text = _agent()
    for word in (
        ".shipwright/agent_docs/conventions.md",
        "shipwright:architecture-rules:begin",
        "shipwright:architecture-rules:end",
        "names the rule id",
        "instruction only",
        "offending line",
        "none are declared",
        "could not run",
        "never waive another axis",
        "edits the block",
        "outside any",
        "Project root:",
        "uncheckable here",
        "rule id twice",
        "ids that differ from",
        "mechanism file is missing",
        "never \"none declared\"",
        "some rules were not checked",
        "stale or duplicated",
        "render_architecture_rules.py --check",
    ):
        assert word in text, word


def test_agent_can_read_conventions_md():
    assert "Read" in _frontmatter_tools()


def test_markers_named_in_the_agent_are_the_ones_the_renderer_writes():
    tools = str(ROOT / "shared" / "scripts" / "tools")
    sys.path.append(tools)
    try:
        import render_architecture_rules as rar
    finally:
        sys.path.remove(tools)
    assert rar.BEGIN in _agent() and rar.END in _agent()


def _section() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.index(HEADING)
    return text[start : text.index("\n## ", start + 1)]


def test_docs_example_rules_validate_with_the_real_loader():
    blocks = re.findall(r"```json\s*(.*?)```", _section(), re.DOTALL)
    assert len(blocks) >= 2
    rules = par.load_rules([json.loads(b) for b in blocks])
    assert rules.errors == [] and len(rules.rules) == len(blocks)
    assert par.check_paths(rules.rules, ROOT) == []


def test_docs_section_names_the_closed_vocabulary_and_the_limits():
    sec = _section()
    for value in par.ENFORCEMENT:
        assert f"`{value}`" in sec
    for word in ("render_architecture_rules.py", "union", "eslint.config", "stack-profiles.md"):
        assert word in sec


def test_spawn_sites_hand_the_reviewer_its_project_root():
    root = ROOT / "plugins"
    for rel in (
        "shipwright-iterate/skills/iterate/references/iteration-reviews.md",
        "shipwright-iterate/skills/iterate/references/campaign-step-3-7-internal-reviews.md",
        "shipwright-iterate/skills/iterate/references/campaign-mode.md",
        "shipwright-build/skills/build/references/code-review-protocol.md",
    ):
        assert "Project root:" in (root / rel).read_text(encoding="utf-8"), rel


def test_pilot_p1_plan_links_the_section():
    if not BRIEF.exists():  # a finished campaign brief is deleted by the repo's own rule
        pytest.skip("pilot brief no longer in the tree")
    text = BRIEF.read_text(encoding="utf-8")
    p1 = text[text.index("\n### P1") : text.index("\n### P2a")]
    link = re.search(r"\]\((\.\./[^)#]+)#how-to-add-an-architecture-rule\)", p1)
    assert link
    assert (BRIEF.parent / link.group(1)).resolve() == DOC
