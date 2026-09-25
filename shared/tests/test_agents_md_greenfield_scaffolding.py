"""Greenfield AGENTS.md generation: project-scaffolding.md's agent-instruction-
driven "### 2. AGENTS.md" step (R4, iterate-2026-09-23-m5-agents-md-generation-
drift).

Kept OUT of test_claude_md_template.py deliberately — that file is pinned as
the regression proof that CLAUDE.md's own (unrelated) generation stays
untouched; adding AGENTS.md coverage there would make that guarantee no
longer hold as stated (external code-review cascade, R4, both reviewers).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.agents_md_substitutions import (  # noqa: E402
    DOC_TITLE_CLAUDE,
    DOC_TITLE_CODEX,
    GROWTH_GATE_CLAUDE,
    GROWTH_GATE_CODEX,
    STANDING_REQUEST_CLAUDE,
    STANDING_REQUEST_CODEX,
    apply_codex_substitutions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "shared" / "templates" / "claude-md-template.md"
PROJECT_SCAFFOLDING_PATH = (
    REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
    / "references" / "project-scaffolding.md"
)
CODEX_APPENDIX_PATH = REPO_ROOT / "shared" / "templates" / "codex-agents-md-appendix.md"


def test_project_scaffolding_references_the_real_codex_appendix_path() -> None:
    """Greenfield AGENTS.md generation is agent-instruction-driven prose, not
    code — a rename of codex-agents-md-appendix.md would silently orphan the
    instruction with nothing to catch it. Pin the real filename here so a
    rename must touch this test deliberately."""
    assert CODEX_APPENDIX_PATH.exists(), (
        "shared/templates/codex-agents-md-appendix.md does not exist — "
        "project-scaffolding.md's AGENTS.md step points at a file that isn't "
        "there."
    )
    body = PROJECT_SCAFFOLDING_PATH.read_text(encoding="utf-8")
    assert "codex-agents-md-appendix.md" in body, (
        "project-scaffolding.md no longer names codex-agents-md-appendix.md "
        "by its real path — greenfield AGENTS.md generation would silently "
        "stop appending the Codex-specific content."
    )
    assert "### 2. AGENTS.md" in body, (
        "project-scaffolding.md's dedicated AGENTS.md generation step is "
        "gone — a bare 'AGENTS.md' substring elsewhere (e.g. the config-"
        "output example) would pass even if the whole step were deleted "
        "(external code-review cascade, R4, low)."
    )
    assert "AGENTS.md" in body, (
        "project-scaffolding.md no longer mentions generating AGENTS.md at "
        "all."
    )


def test_greenfield_agents_md_substitution_instructions_match_the_render_path() -> None:
    """Greenfield's AGENTS.md step (project-scaffolding.md's '### 2. AGENTS.md')
    is agent-instruction-driven prose, not code — an LLM performs two literal
    substitutions on the CLAUDE.md content it just filled, rather than calling
    `_render_claude_md(..., host_name="Codex")` the way adopt's code path does.
    There is no runtime guard that the two paths stay in sync (doubt-reviewer,
    R4, low). This cannot prove an executing agent will actually perform the
    substitutions, but it CAN prove the substitutions the instructions
    literally describe are not stale — i.e. applying them mechanically,
    exactly as written, to the template's own text yields the identical
    host-specific fragments `_render_claude_md` produces for AGENTS.md. If a
    future edit to either side drifts the wording, this test catches it."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert DOC_TITLE_CLAUDE in template
    assert STANDING_REQUEST_CLAUDE in template
    assert GROWTH_GATE_CLAUDE in template

    # The three substitutions project-scaffolding.md's step "### 2. AGENTS.md"
    # instructs, applied via the SAME canonical pairs the completion check
    # uses (shared/scripts/lib/agents_md_substitutions.py) — one definition,
    # not a second inline copy that could drift from what the check enforces.
    substituted = apply_codex_substitutions(template)
    assert "CLAUDE.md is **orientation" not in substituted
    assert "Claude Code withholds subagent spawning" not in substituted
    assert "SHIPWRIGHT_CLAUDE_MD_GROWTH_OK" not in substituted

    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace("\\", "\\\\")
        + "');\n"
        "from lib.claude_md_renderer import _render_claude_md\n"
        "out = _render_claude_md(\n"
        "    project_name='Demo', profile='vite-hono',\n"
        "    stack={'runtime': {}, 'frontend': {}, 'backend': {},\n"
        "           'database': {}, 'auth': {}},\n"
        "    commands={'build': 'x', 'test': 'x', 'dev': 'x'},\n"
        "    product_description='demo', host_name='Codex',\n"
        ")\n"
        "import sys; sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", helper],
        capture_output=True, check=True,
    )
    rendered = result.stdout.decode("utf-8")
    assert DOC_TITLE_CODEX in rendered
    assert STANDING_REQUEST_CODEX in rendered
    assert GROWTH_GATE_CODEX in rendered
    for fragment in (DOC_TITLE_CODEX, STANDING_REQUEST_CODEX, GROWTH_GATE_CODEX):
        assert fragment in substituted, (
            f"literal instruction-driven substitution produced {fragment!r} "
            f"missing text — but the code path (_render_claude_md) has it; "
            f"project-scaffolding.md's wording has drifted from the render path."
        )
