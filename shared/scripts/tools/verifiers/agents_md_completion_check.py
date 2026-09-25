"""AGENTS.md completion gate — split out of ``project_checks.py`` (which sits
at the shared bloat gate's 300-line cap) the same way that module's own
docstring already splits sibling checks out under ``verifiers/`` (e.g. the
``silent_revert*`` family).

Greenfield AGENTS.md generation (``project-scaffolding.md`` step 2) is agent-
instruction-driven prose, unlike adopt's brownfield path (a deterministic
``agents_md_renderer.write_agents_md`` call). The required PR-review CI gate
BLOCKed this twice on iterate-2026-09-23-m5-agents-md-generation-drift (R4):
first because nothing executable proved AGENTS.md was written at all, then —
after a marker-presence-only check — because nothing proved the file's
*content* actually got the documented substitutions right rather than merely
containing the appendix marker somewhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import CheckResult

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.agents_md_substitutions import apply_codex_substitutions  # noqa: E402

_NAME = "AGENTS.md completion (Codex appendix present)"


def _read_codex_appendix_marker() -> str | None:
    """The Codex appendix's idempotency marker, read from the template
    itself rather than duplicated as a second hardcoded literal (the
    same value ``plugins/shipwright-adopt/scripts/lib/agents_md_renderer.py``
    defines as ``CODEX_APPENDIX_MARKER`` — not imported directly because
    ``shared/`` must not depend on a specific plugin, ADR-045). Returns
    ``None`` when the template cannot be found or read, so the caller can
    report that as its own distinct failure rather than a false negative.
    """
    template = _SCRIPTS_ROOT.parent / "templates" / "codex-agents-md-appendix.md"
    try:
        first_line = template.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    return first_line.strip() or None


def _content_mismatch_reason(agents_body: str, claude_content: str) -> str:
    """A specific diagnosis for why AGENTS.md's body isn't CLAUDE.md's
    content with the three documented substitutions applied — checked in
    order of how likely each is to be the actual slip, so the message names
    the real problem instead of a generic "differs" (the exact gap the
    required PR-review gate's second BLOCK named: "validate required
    shared-body content and the Codex-specific substitutions").
    """
    from lib.agents_md_substitutions import (
        DOC_TITLE_CLAUDE,
        GROWTH_GATE_CLAUDE,
        STANDING_REQUEST_CLAUDE,
    )

    if len(agents_body.strip()) < 0.5 * len(claude_content.strip()):
        return (
            "AGENTS.md has little or no CLAUDE.md-derived content before the "
            "Codex appendix — the greenfield step must reuse the filled "
            "CLAUDE.md content, not just append the appendix to a near-empty "
            "or unrelated file"
        )
    if STANDING_REQUEST_CLAUDE in agents_body:
        return (
            "AGENTS.md's body still says "
            f"{STANDING_REQUEST_CLAUDE!r} — the host-name substitution "
            "(Claude Code -> Codex, in the standing-request section) was not applied"
        )
    if DOC_TITLE_CLAUDE in agents_body:
        return (
            f"AGENTS.md's body still opens with {DOC_TITLE_CLAUDE!r} — the "
            "'Editing this file' section's doc-title substitution was not applied"
        )
    if GROWTH_GATE_CLAUDE in agents_body:
        return (
            "AGENTS.md's body still carries CLAUDE.md's growth-gate bullet "
            "(SHIPWRIGHT_CLAUDE_MD_GROWTH_OK) instead of the Codex-appropriate "
            "wording — that bullet names an enforcement that only ever applies "
            "to CLAUDE.md"
        )
    return (
        "AGENTS.md's body diverges from CLAUDE.md's content beyond the three "
        "documented substitutions — project-scaffolding.md states those are "
        "'the only host-specific content in the whole shared body'"
    )


def check_agents_md_completion(project_root: Path) -> CheckResult:
    """AGENTS.md (Codex CLI's counterpart to CLAUDE.md) must actually be
    written for a Full Application project, must carry the shared Codex
    appendix, AND its body (everything before the appendix) must actually be
    CLAUDE.md's content with the three documented substitutions applied —
    not merely a file that happens to contain the appendix marker somewhere.

    Deliberately exact-match (after trailing-whitespace normalization), not a
    fuzzy/partial check: ``project-scaffolding.md`` itself states the three
    substitutions are "the only host-specific content in the whole shared
    body", so any OTHER divergence (a dropped section, an unrelated edit) is
    exactly the class of slip this check exists to catch, not a false
    positive to tolerate.

    Does NOT require CLAUDE.md to match a fresh ``_render_claude_md`` call
    byte-for-byte — CLAUDE.md's own greenfield generation is separately
    instruction-driven and may carry legitimate hand-edits. This check only
    proves AGENTS.md = CLAUDE.md (substituted) + appendix; it does not
    re-validate CLAUDE.md itself. ERROR severity, like C1/C4/C5: a Full
    Application project without a correct AGENTS.md is not actually done.
    """
    path = project_root / "shipwright_project_config.json"
    if not path.exists():
        return CheckResult(_NAME, True, "no project config yet — nothing to check")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(_NAME, False, f"malformed project config: {exc}")
    if data.get("scope") != "full_app":
        return CheckResult(_NAME, True, "extension scope — CLAUDE.md/AGENTS.md not required")

    agents_md = project_root / "AGENTS.md"
    if not agents_md.exists():
        return CheckResult(_NAME, False, "AGENTS.md missing (Full Application scope requires it)")

    marker = _read_codex_appendix_marker()
    if marker is None:
        return CheckResult(
            _NAME, False,
            "cannot resolve shared/templates/codex-agents-md-appendix.md to read its marker",
        )
    content = agents_md.read_text(encoding="utf-8", errors="replace")
    if marker not in content:
        return CheckResult(
            _NAME, False,
            f"AGENTS.md exists but is missing the Codex appendix marker ({marker!r}) — "
            "the greenfield step must append shared/templates/codex-agents-md-appendix.md verbatim",
        )

    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return CheckResult(
            _NAME, False,
            "cannot validate AGENTS.md's shared-body content — CLAUDE.md is missing "
            "(AGENTS.md's expected body is derived from CLAUDE.md's own content)",
        )
    claude_content = claude_md.read_text(encoding="utf-8", errors="replace")
    agents_body = content.split(marker, 1)[0]
    expected_body = apply_codex_substitutions(claude_content)
    if agents_body.rstrip() != expected_body.rstrip():
        return CheckResult(_NAME, False, _content_mismatch_reason(agents_body, claude_content))

    return CheckResult(_NAME, True, "AGENTS.md present with Codex appendix and correctly substituted body")
