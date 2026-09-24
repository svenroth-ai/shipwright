"""Pin the root AGENTS.md / CLAUDE.md pair against silent drift.

Claude Code 2.1.277 (2026-09-18) added a CLAUDE.md-absent fallback to
AGENTS.md, so AGENTS.md is no longer Codex-only content anywhere it might
be adopted without a CLAUDE.md alongside it. Both files are hand-maintained
prose (no generator produces either), so nothing previously caught them
drifting apart. This test closes three concrete gaps found by audit
(iterate-2026-09-23-m5-agents-md-generation-drift):

1. AGENTS.md's `templates/` Structure line once claimed a template file
   that was never built.
2. Two shared, non-runtime-specific prose blocks (the `verify_local.py`
   description, "When editing plugin-side files") had drifted apart in
   wording/detail with nothing to notice.
3. AGENTS.md's "Codex operating policy" section used to hardcode Codex model
   slugs/reasoning effort in prose, duplicating real Python constants that
   `codex_review_model_resolution.py` already resolves dynamically per
   project/session — a value prose can only ever show a stale snapshot of.
   That prose was removed; this closes the gap by guarding it never returns.

The Codex appendix's runtime-specific content (model policy prose, "Codex"
vs "Claude Code" wording) is intentionally NOT required to match — only the
shared substance and the review-cascade contract are.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD_PATH = REPO_ROOT / "CLAUDE.md"
AGENTS_MD_PATH = REPO_ROOT / "AGENTS.md"
TEMPLATES_DIR = REPO_ROOT / "shared" / "templates"

#: What each prose label on the `templates/` Structure line actually maps to
#: under shared/templates/ — a label with no entry here fails loudly instead
#: of silently passing (external code-review cascade, medium, 2026-09-23: the
#: first cut of this check special-cased the string "AGENTS.md" instead of
#: validating every named label, exactly the "one-off string fix" the
#: sub-iterate spec said not to do).
TEMPLATE_LABEL_TO_PATH = {
    "CLAUDE.md": "claude-md-template.md",
    "codex-agents-md-appendix.md": "codex-agents-md-appendix.md",
    ".shipwright/agent_docs": "agent-docs",
    "CI templates": "github-actions",
}

def _heading_index(body: str, heading: str, label: str, *, after: int = 0) -> int:
    """Find `heading` anchored at the start of a line (not merely anywhere
    in the body, e.g. as a prefix of a longer heading or a TOC mention —
    external code-review cascade, low, 2026-09-23). `heading` may be a
    prefix of the full line (some headings carry trailing text)."""
    match = re.search(
        r"^" + re.escape(heading), body[after:], re.MULTILINE,
    )
    assert match, f"{label}: heading {heading!r} not found as a line start"
    return after + match.start()


def _section(body: str, start: str, end: str, *, label: str) -> str:
    """Return body[start_heading : end_heading), both anchored at a line
    start so a same-prefix heading elsewhere can't produce a silently wrong
    (or vacuously matching) slice."""
    i = _heading_index(body, start, label)
    j = _heading_index(body, end, label, after=i)
    return body[i:j]


def test_templates_line_names_only_real_templates() -> None:
    """Every label on the templates/ Structure line must map to a real path
    under shared/templates/ — in both files, for every label, not just a
    single hardcoded string (external code-review cascade, medium x2,
    2026-09-23)."""
    for path in (CLAUDE_MD_PATH, AGENTS_MD_PATH):
        body = path.read_text(encoding="utf-8")
        match = re.search(r"^\s*templates/\s*#\s*(.+)$", body, re.MULTILINE)
        assert match, f"{path.name} is missing its templates/ Structure line"
        labels = [s.strip() for s in match.group(1).split(",")]
        for lbl in labels:
            mapped = TEMPLATE_LABEL_TO_PATH.get(lbl)
            assert mapped is not None, (
                f"{path.name}'s templates/ line names {lbl!r}, which has no "
                f"entry in TEMPLATE_LABEL_TO_PATH — add one, or fix the prose "
                f"if the label was a typo."
            )
            assert (TEMPLATES_DIR / mapped).exists(), (
                f"{path.name}'s templates/ line claims {lbl!r} "
                f"(shared/templates/{mapped}), which does not exist on disk."
            )


def test_development_verify_local_section_is_byte_identical() -> None:
    claude = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    agents = AGENTS_MD_PATH.read_text(encoding="utf-8")
    claude_section = _section(
        claude, "### Development", "### Plugin Structure", label="CLAUDE.md",
    )
    agents_section = _section(
        agents, "### Development", "### Plugin Structure", label="AGENTS.md",
    )
    assert claude_section == agents_section, (
        "CLAUDE.md and AGENTS.md's Development sections (incl. the "
        "verify_local.py description) have drifted apart in wording — sync "
        "them (iterate-2026-09-23-m5-agents-md-generation-drift)."
    )


def test_plugin_side_files_section_is_byte_identical() -> None:
    claude = CLAUDE_MD_PATH.read_text(encoding="utf-8")
    agents = AGENTS_MD_PATH.read_text(encoding="utf-8")
    claude_section = _section(
        claude, "### When editing plugin-side files", "### Documentation Guide",
        label="CLAUDE.md",
    )
    agents_section = _section(
        agents, "### When editing plugin-side files", "### Documentation Guide",
        label="AGENTS.md",
    )
    assert claude_section == agents_section, (
        "CLAUDE.md and AGENTS.md's 'When editing plugin-side files' sections "
        "have drifted apart in wording — sync them "
        "(iterate-2026-09-23-m5-agents-md-generation-drift)."
    )


#: The exact prose this repo deliberately removed from AGENTS.md
#: (iterate-2026-09-23-m5-agents-md-generation-drift, round 2): a Codex
#: model slug or reasoning-effort default hardcoded here duplicates a value
#: `codex_review_model_resolution.py` already resolves dynamically (explicit
#: flag -> session env var -> `shipwright_model_config.json` -> hardcoded
#: default) — prose can only ever show a stale snapshot of that. A regression
#: guard, not a positive-content check: the real values live in code and are
#: never restated here.
_EXECUTION_BULLET_RE = re.compile(
    r"Use `([^`]+)` with `([^`]+)` reasoning for ordinary implementation and finalization",
)
_REVIEW_BULLET_RE = re.compile(
    r"Use `([^`]+)` with `([^`]+)` reasoning for required review subagents",
)


def test_agents_md_does_not_hardcode_codex_review_models() -> None:
    """AGENTS.md must not restate a Codex model slug/reasoning-effort
    default anywhere — resolving it is `codex_review_model_resolution.py`'s
    job, and prose here would only ever be a stale snapshot of it."""
    body = AGENTS_MD_PATH.read_text(encoding="utf-8")
    assert _EXECUTION_BULLET_RE.search(body) is None, (
        "AGENTS.md hardcodes an execution/finalization Codex model+effort "
        "again — that's deliberately unenforced operator guidance, drop it "
        "rather than restate a snapshot."
    )
    assert _REVIEW_BULLET_RE.search(body) is None, (
        "AGENTS.md hardcodes a review-subagent Codex model+effort again — "
        "that value is resolved dynamically by codex_review_model_resolution.py; "
        "restating it here goes stale the moment a project overrides it."
    )
    assert "gpt-5.6" not in body, (
        "AGENTS.md names a specific Codex model slug — the resolved value is "
        "never a compile-time constant this file can safely quote."
    )


def test_review_cascade_order_and_core_guarantee_present_in_both() -> None:
    # Split into the two clauses the failure message actually claims to check
    # (external code-review cascade, medium x2, 2026-09-23: the message named
    # "spawn by default" but only the never-pause/not_run clause was asserted
    # — a deleted "spawn by default" sentence would have passed silently).
    spawn_by_default = "requested by default — spawn it"
    guarantee = (
        "never pause to ask, and never record a review `not_run` citing a "
        "session policy."
    )
    cascade_chain = "`spec-reviewer` → `code-reviewer` → `doubt-reviewer`"
    for path in (CLAUDE_MD_PATH, AGENTS_MD_PATH):
        body = path.read_text(encoding="utf-8")
        section = _section(
            body,
            "## Review subagents: standing request",
            "## Asking the user questions",
            label=path.name,
        )
        # Markdown line-wrapping alone (not wording/order) must never fail
        # this check -- collapse whitespace before comparing. The cascade
        # chain is matched as one anchored substring (not three independent
        # `.index()` first-occurrence lookups), so an incidental earlier
        # mention of a role name elsewhere in the section can't fake order
        # (external code-review cascade, low, 2026-09-23).
        normalized = " ".join(section.split())
        assert spawn_by_default in normalized, (
            f"{path.name}'s review-cascade section is missing the "
            f"'requested by default — spawn it' opening guarantee."
        )
        assert guarantee in normalized, (
            f"{path.name}'s review-cascade section is missing the core "
            f"'never pause to ask, never not_run on session policy' guarantee."
        )
        assert cascade_chain in normalized, (
            f"{path.name}: review cascade order (spec -> code -> doubt) drifted "
            f"or was reworded."
        )
