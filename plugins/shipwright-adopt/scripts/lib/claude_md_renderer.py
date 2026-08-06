"""Render AND write the adopted-project ``CLAUDE.md``.

Extracted from ``artifact_writer.py`` (bloat-baseline ceiling) — the render
is a hardcoded f-string that MUST stay mirrored with the greenfield template
``shared/templates/claude-md-template.md``; drift between the two is caught by
``shared/tests/test_claude_md_template.py``. ``artifact_writer`` re-exports
``_render_claude_md`` and ``write_claude_md`` so existing importers keep working.

The **writer** moved here alongside the render: once the load-bearing branch
gained the standing-request append, the deciding logic and the constant it
appends were in two different modules, and ``artifact_writer`` crossed its
grandfathered ceiling again. One module now owns the whole CLAUDE.md concern.

``AGENT_DOCS_DIR`` is defined locally here (the same self-contained pattern
``known_issues_inventory.py`` / ``visual_docs_generator.py`` use). This stays a
leaf — ``render_helpers`` and ``preserve_existing`` are both leaves themselves,
so there is still no cycle back into ``artifact_writer``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Importable both via package-relative path (when called from
# generate_adoption_artifacts.py which adds scripts/lib to sys.path) and via
# direct test imports (`from lib.render_helpers import ...`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.render_helpers import _fmt_stack_line, _utc_today  # noqa: E402
from lib.preserve_existing import (  # noqa: E402
    SUGGESTED_CLAUDE_REL,
    is_loadbearing_claude_md,
    preserve_if_exists,
    record_preservation_action,
)

#: The standing-request grant, verbatim. ONE source: the f-string below
#: interpolates it, and ``write_claude_md`` appends it to a preserved
#: load-bearing CLAUDE.md. Both reviewers asked for a single
#: definition rather than three hand-mirrored copies.
STANDING_REQUEST_HEADING = "## Review subagents: standing request."
STANDING_REQUEST_SECTION = """## Review subagents: standing request. Workflows: ask every time.

**The review cascade is requested by default — spawn it, never pause to ask, and never record a review `not_run` citing a session policy.** That is `spec-reviewer` → `code-reviewer` → `doubt-reviewer` plus the review subagents other phase skills prescribe (build Step 6, campaign review). Claude Code withholds subagent spawning until the user asks; **this file is that request, and it stands for every session.** **The grant covers reviewers, not fan-out.** Dynamic workflows, deep-research, and parallel implementation subagents (build's `section-builder` loop) spend openly and stay the operator's call — ask explicitly, every time, and never infer them from the grant above. A project that does not want this can delete the section; it is deliberately plain and must not be compressed further, because it has to read as the user's request at runtime."""


AGENT_DOCS_DIR = ".shipwright/agent_docs"


def _render_claude_md(
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> str:
    runtime = _fmt_stack_line(stack.get("runtime", {}))
    frontend = _fmt_stack_line(stack.get("frontend", {}))
    backend = _fmt_stack_line(stack.get("backend", {}))
    database = _fmt_stack_line(stack.get("database", {}))
    auth = _fmt_stack_line(stack.get("auth", {}))
    build_cmd = commands.get("build") or "—"
    test_cmd = commands.get("test") or "—"
    dev_cmd = commands.get("dev") or "—"
    return f"""# {project_name}

## WHAT
{product_description}

## Stack
- **Runtime**: {runtime}
- **Frontend**: {frontend}
- **Backend**: {backend}
- **Database**: {database}
- **Auth**: {auth}
- **Profile**: `{profile}`

## HOW

### Development
```bash
{dev_cmd}
```

### Build
```bash
{build_cmd}
```

### Test
```bash
{test_cmd}
```

## Ongoing Changes
This project was adopted into Shipwright on {_utc_today()}. Prior code history is preserved.

**Use `/shipwright-iterate` for code changes — Do NOT edit code directly.**
The skill keeps specs, tests, ADRs, and the CHANGELOG in sync.

What `/shipwright-iterate` automates:
- ADR entry in `{AGENT_DOCS_DIR}/decision_log.md`
- CHANGELOG fragment under `CHANGELOG-unreleased.d/<category>/`
- Conventional Commits on an `iterate/<slug>` branch, merged to main on green tests
- FR / acceptance-criteria sync in `.shipwright/planning/`
- Compliance + dashboard refresh **in your working tree** (see below for what is committed)

Do NOT invoke `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` directly — those are pre-onboarding phases.

## How current is the audit evidence?

**Working tree:** current. **Committed on the default branch:** as of the last release or refresh, not continuously — each document's `Source-State:` line names the commit it was computed from. Iterate branches deliberately do not carry them (a branch derives them from its own history and is wrong for the default branch).

Refresh with `/shipwright-changelog` (a release checks them in) or `/shipwright-compliance --refresh-pr` (a documents-only PR in between). The moment you need current evidence is the moment to run it.


See `{AGENT_DOCS_DIR}/decision_log.md` for the adoption ADR (the topmost
`Adopt this repository into the Shipwright SDLC` entry — its id is the
next-free 3-digit number after any pre-existing ADRs).

{STANDING_REQUEST_SECTION}


## Editing this file (keep it lean)

CLAUDE.md is **orientation + a terse invariant index** — it is loaded into
every session, so every line here costs context on every future change.

- **New invariant / DO-NOT rule:** add **one line + a pointer** to the ADR or
  conventions entry that carries the rationale (e.g. `- Never bypass X — see
  ADR-012`). The full reasoning lives in
  `{AGENT_DOCS_DIR}/decision_log.md` or `conventions.md`, **not here**.
- **Exception — the standing-request section above** is deliberately one dense line: it must read as the user's request at runtime, and its length is what keeps this file under the hygiene cap. Leave it as it is. **No inline rationale:** if a rule needs more than ~2 lines to state, the
  extra lines belong in the ADR it cites. Keep lines short — a long paragraph
  on one line is still rationale.
- **Prefer updating an existing line** over adding a new one.
- **Growth is gated:** iterate finalization flags a change that net-grows this
  file by more than 30 lines (deliberate exception:
  `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1`).

## Asking the user questions (plain language)

When you ask the user a question — a clarification, a choice between options,
or a confirmation — phrase it so a **non-senior developer or a normal user**
can understand, from a functional standpoint, what is actually being decided.
The person answering may not know the internals; do not make them decode
jargon to reply.

- **Lead with the functional meaning:** say what the choice changes about how
  the app behaves or what the user gets — not the implementation detail.
- **Avoid unexplained jargon.** If a technical term is unavoidable, add a short
  plain-language gloss in parentheses (e.g. "idempotent — safe to run twice
  without doubling the effect").
- **Make options concrete and comparable.** Give each option in plain words
  with its real-world trade-off ("Option A is simpler but slower; Option B is
  faster but adds a setup step"), not a raw technical menu.
- **Rule of thumb:** a product owner should be able to answer without asking
  "what does that mean?". If they couldn't, rewrite it.

This governs *phrasing only* — the rigor of the work is unchanged.
"""


def _append_standing_request(path: Path) -> bool:
    """Append the review-subagent standing request to a PRESERVED CLAUDE.md.

    The load-bearing branch deliberately does not overwrite an existing
    CLAUDE.md — that policy exists because adopt once destroyed a 16 KB one.
    But writing the rendered file to a side-file the harness never loads meant
    the standing request never reached an adopted project at all, and every
    repo mature enough to be worth adopting has a >1 KB CLAUDE.md. Appending
    one section is additive: nothing existing is touched, and the operator
    keeps the backup ``preserve_if_exists`` already took.

    Idempotent by heading, so re-running adopt does not stack duplicates.
    Returns True when it wrote, False when the section was already present.
    """
    body = path.read_text(encoding="utf-8")
    if STANDING_REQUEST_HEADING in body:
        return False
    if body.endswith("\n\n"):
        separator = ""
    elif body.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    path.write_text(
        body + separator + STANDING_REQUEST_SECTION + "\n", encoding="utf-8"
    )
    return True


def write_claude_md(
    project_root: Path,
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
) -> Path:
    """Write CLAUDE.md with load-bearing-content protection.

    If an existing CLAUDE.md is larger than the load-bearing threshold
    (~1 KB), it's preserved untouched and the adopt-generated content
    is written to `.shipwright/adopt/CLAUDE.md.adopt-suggested` instead.
    Smaller existing files are backed up to `.preserved` and then
    overwritten. The returned path is the file that actually received
    the new content (either the real CLAUDE.md or the suggested side-file).
    """
    content = _render_claude_md(
        project_name=project_name, profile=profile, stack=stack,
        commands=commands, product_description=product_description,
    )
    path = project_root / "CLAUDE.md"
    backup = preserve_if_exists(project_root, "CLAUDE.md")
    if path.exists() and is_loadbearing_claude_md(path):
        suggested = project_root / SUGGESTED_CLAUDE_REL
        suggested.parent.mkdir(parents=True, exist_ok=True)
        suggested.write_text(content, encoding="utf-8")
        appended = _append_standing_request(path)
        record_preservation_action(
            project_root,
            file="CLAUDE.md",
            action="skipped_loadbearing",
            backup_path=backup,
            note=(
                f"existing CLAUDE.md > {is_loadbearing_claude_md.__defaults__[0] if is_loadbearing_claude_md.__defaults__ else 1024} bytes; "
                f"adopt suggestion at {SUGGESTED_CLAUDE_REL}"
                + ("; standing-request section APPENDED (additive, nothing overwritten)"
                   if appended else "; standing-request section already present")
            ),
        )
        return suggested
    path.write_text(content, encoding="utf-8")
    record_preservation_action(
        project_root,
        file="CLAUDE.md",
        action=("overwritten_with_backup" if backup else "written_fresh"),
        backup_path=backup,
    )
    return path
