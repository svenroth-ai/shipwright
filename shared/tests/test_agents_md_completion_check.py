"""Tests for ``check_agents_md_completion``
(``tools/verifiers/agents_md_completion_check.py``).

Split into its own file rather than added to ``test_verifiers_project.py``
for the same reason that file's own docstring already gives for
``test_project_gate_basis_and_guidance.py`` /
``test_project_gate_no_empty_split.py``: staying under the shared bloat
gate's 300-line limit.

This is the executable backstop the required PR-review gate asked for
twice on iterate-2026-09-23-m5-agents-md-generation-drift (R4): first,
that nothing proved a real scaffolding run produced an AGENTS.md carrying
the shared Codex appendix at all; second, that a marker-presence-only check
"accepts any file containing the appendix marker" without validating the
required shared-body content and the Codex-specific substitutions. These
tests cover both gaps.
"""

from __future__ import annotations

import json

import pytest

from lib.agents_md_substitutions import (
    DOC_TITLE_CLAUDE,
    GROWTH_GATE_CLAUDE,
    STANDING_REQUEST_CLAUDE,
    apply_codex_substitutions,
)
from tools.verifiers.agents_md_completion_check import (
    _read_codex_appendix_marker,
    check_agents_md_completion,
)

#: A realistic CLAUDE.md body carrying all three substitution anchors, so
#: the correctly-substituted AGENTS.md fixture below is what the greenfield
#: step's instructions actually describe producing — not a synthetic
#: shortcut that only happens to satisfy the check.
_CLAUDE_MD_CONTENT = f"""# Demo

## WHAT
A demo project.

## Review subagents: standing request. Workflows: ask every time.

The review cascade is requested by default. {STANDING_REQUEST_CLAUDE}.

## Editing this file (keep it lean)

{DOC_TITLE_CLAUDE} — it is loaded into every session.

{GROWTH_GATE_CLAUDE}
"""


@pytest.mark.parametrize("scope,agents_md,expect_ok,expect_in_detail", [
    ("extension", None, True, "extension"),
    (None, None, True, ""),  # no project config yet — nothing to check
    ("full_app", None, False, "missing"),
    ("full_app", "# AGENTS\n\nno appendix here.\n", False, "marker"),
])
def test_agents_md_completion(tmp_path, scope, agents_md, expect_ok, expect_in_detail):
    if scope is not None:
        (tmp_path / "shipwright_project_config.json").write_text(json.dumps({"scope": scope}), encoding="utf-8")
    if agents_md is not None:
        (tmp_path / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    r = check_agents_md_completion(tmp_path)
    assert r.ok is expect_ok
    if expect_in_detail:
        assert expect_in_detail in r.detail.lower()


def _write_full_app(tmp_path, agents_body: str) -> str:
    marker = _read_codex_appendix_marker()
    assert marker, "shared/templates/codex-agents-md-appendix.md must be readable"
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        f"{agents_body}\n\n{marker}\n## Codex operating policy\n", encoding="utf-8",
    )
    return marker


def test_appendix_only_agents_md_is_rejected(tmp_path):
    """No CLAUDE.md-derived body at all — just the marker/appendix."""
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    _write_full_app(tmp_path, "")
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "little or no claude.md-derived content" in r.detail.lower()


def test_missing_claude_md_is_rejected(tmp_path):
    """Marker present, but nothing to derive the expected body from."""
    _write_full_app(tmp_path, apply_codex_substitutions(_CLAUDE_MD_CONTENT))
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "claude.md is missing" in r.detail.lower()


def test_unapplied_standing_request_substitution_is_rejected(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    _write_full_app(tmp_path, _CLAUDE_MD_CONTENT)  # no substitutions applied at all
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "host-name substitution" in r.detail.lower()


def test_unapplied_doc_title_substitution_is_rejected(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    # Apply only the standing-request substitution — doc-title left stale.
    body = _CLAUDE_MD_CONTENT.replace(STANDING_REQUEST_CLAUDE, "Codex withholds subagent spawning until the user asks")
    _write_full_app(tmp_path, body)
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "doc-title substitution" in r.detail.lower()


def test_unapplied_growth_gate_substitution_is_rejected(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    almost = apply_codex_substitutions(_CLAUDE_MD_CONTENT).replace(
        "- **No automated growth gate for this file yet** — keep it lean by the\n"
        "  same restraint CLAUDE.md's line-cap enforces; watch it by hand.",
        GROWTH_GATE_CLAUDE,
    )
    _write_full_app(tmp_path, almost)
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "growth-gate" in r.detail.lower()


def test_unrelated_body_divergence_is_rejected(tmp_path):
    """Correct substitutions, but some OTHER, unrelated content diverges —
    project-scaffolding.md states the three substitutions are the only
    host-specific content in the whole shared body, so any other difference
    is a defect this check should catch, not a tolerated variance."""
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    body = apply_codex_substitutions(_CLAUDE_MD_CONTENT).replace("A demo project.", "A totally different project.")
    _write_full_app(tmp_path, body)
    r = check_agents_md_completion(tmp_path)
    assert r.ok is False
    assert "diverges from claude.md's content" in r.detail.lower()


def test_correctly_substituted_body_passes(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(_CLAUDE_MD_CONTENT, encoding="utf-8")
    _write_full_app(tmp_path, apply_codex_substitutions(_CLAUDE_MD_CONTENT))
    r = check_agents_md_completion(tmp_path)
    assert r.ok is True
    assert "correctly substituted" in r.detail.lower()
