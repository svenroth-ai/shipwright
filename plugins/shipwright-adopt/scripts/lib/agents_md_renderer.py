"""Render AND write the adopted-project ``AGENTS.md``.

Split out of ``claude_md_renderer.py`` (300-line source cap) — this module
owns everything specific to the Codex-read file: the shared-templates
resource lookup, the Codex-only appendix, and the load-bearing-preservation
write path. It deliberately does NOT re-derive the shared body: it calls
``claude_md_renderer._render_claude_md`` — the exact function CLAUDE.md's
own writer calls — with ``host_name="Codex"``, so there is nothing here
that can drift against CLAUDE.md's content (R4,
iterate-2026-09-23-m5-agents-md-generation-drift; architecture-review round
2, both reviewers approve: "single render source, one small appendix file,
no second template").
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.claude_md_renderer import (  # noqa: E402
    _append_section_if_missing,
    _append_standing_request,
    _render_claude_md,
)
from lib.preserve_existing import (  # noqa: E402
    LOADBEARING_CLAUDE_BYTE_THRESHOLD,
    SUGGESTED_AGENTS_REL,
    is_loadbearing_claude_md as is_loadbearing_agents_md,
    preserve_if_exists,
    record_preservation_action,
)


@lru_cache(maxsize=1)
def _find_shared_templates() -> Path:
    """Locate shared/templates/ by walking up from this file — robust to
    plugin-layout depth (mirrors ``codex_activation_mint.py``'s
    ``_find_shared_scripts()``: the monorepo checkout and the installed
    plugin cache put ``shared/`` a different number of directories above
    this file — the cache inserts an extra ``<version>/`` level — so a
    fixed ``parents[N]`` index is wrong for one of the two layouts)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "templates"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "templates"  # historical fallback


def _read_codex_appendix() -> str:
    path = _find_shared_templates() / "codex-agents-md-appendix.md"
    return path.read_text(encoding="utf-8").rstrip("\n")


#: Append-idempotency marker — an inert HTML comment (invisible when
#: rendered, e.g. on GitHub), NOT the appendix's own human-readable heading
#: (external code-review cascade, R4, medium: "## Codex operating policy" is
#: generic enough that a project could plausibly already have hand-written a
#: section of that exact name before ever adopting Shipwright, which would
#: make `_append_codex_appendix` treat Shipwright's own appendix as already
#: present and silently never deliver it). Mirrors the
#: `<!-- Adoption merge marker ... -->` HTML-comment convention
#: `preserve_existing.merge_decision_log` already uses for the same kind of
#: purpose. Embedded as the appendix file's own first line, so there is only
#: one source — reading the appendix and checking for the marker can never
#: desync the way a hand-duplicated constant could.
CODEX_APPENDIX_MARKER = "<!-- shipwright:codex-agents-md-appendix -->"


def _append_codex_appendix(path: Path) -> bool:
    appendix = _read_codex_appendix()
    return _append_section_if_missing(path, CODEX_APPENDIX_MARKER, appendix)


def _render_agents_md(
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> str:
    shared_body = _render_claude_md(
        project_name=project_name, profile=profile, stack=stack,
        commands=commands, product_description=product_description,
        host_name="Codex",
    )
    return shared_body + "\n\n" + _read_codex_appendix() + "\n"


def write_agents_md(
    project_root: Path,
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> Path:
    """Write AGENTS.md with load-bearing-content protection — same policy
    as ``write_claude_md`` (same 1 KB threshold, same preserve/backup/
    suggested-side-file shape), reusing the SAME generic helpers.

    A preserved, over-threshold existing AGENTS.md gets BOTH the
    review-cascade standing-request section AND the Codex appendix
    idempotently appended (not just the standing-request one) — otherwise a
    project sophisticated enough to already carry its own large AGENTS.md
    would never receive the activation-gate guidance, defeating this
    feature for exactly the users most likely to already run Codex
    (plan-review round 1, openai medium).
    """
    content = _render_agents_md(
        project_name=project_name, profile=profile, stack=stack,
        commands=commands, product_description=product_description,
    )
    path = project_root / "AGENTS.md"
    backup = preserve_if_exists(project_root, "AGENTS.md")
    if path.exists() and is_loadbearing_agents_md(path):
        suggested = project_root / SUGGESTED_AGENTS_REL
        suggested.parent.mkdir(parents=True, exist_ok=True)
        suggested.write_text(content, encoding="utf-8")
        appended_standing_request = _append_standing_request(path, host_name="Codex")
        appended_codex_appendix = _append_codex_appendix(path)
        notes = [
            f"existing AGENTS.md > {LOADBEARING_CLAUDE_BYTE_THRESHOLD} bytes; "
            f"adopt suggestion at {SUGGESTED_AGENTS_REL}",
        ]
        notes.append(
            "; standing-request section APPENDED (additive, nothing overwritten)"
            if appended_standing_request else "; standing-request section already present"
        )
        notes.append(
            "; Codex appendix APPENDED (additive, nothing overwritten)"
            if appended_codex_appendix else "; Codex appendix already present"
        )
        record_preservation_action(
            project_root,
            file="AGENTS.md",
            action="skipped_loadbearing",
            backup_path=backup,
            note="".join(notes),
        )
        return suggested
    path.write_text(content, encoding="utf-8")
    record_preservation_action(
        project_root,
        file="AGENTS.md",
        action=("overwritten_with_backup" if backup else "written_fresh"),
        backup_path=backup,
    )
    return path
