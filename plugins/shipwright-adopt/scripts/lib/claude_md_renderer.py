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

import re
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

#: The standing-request grant. ONE source, parameterized on which host tool
#: it names (the only sentence in it that's runtime-specific — R4,
#: iterate-2026-09-23-m5-agents-md-generation-drift, plan-review round 1,
#: glm medium: reusing this verbatim for a Codex-read AGENTS.md would ship
#: "Claude Code withholds..." into a file Claude Code never reads under that
#: name). The f-string below interpolates the default (``"Claude Code"``),
#: and ``write_claude_md``/``write_agents_md`` each append their own
#: host-flavored copy to a preserved load-bearing file. Both reviewers
#: originally asked for a single definition rather than hand-mirrored
#: copies — this keeps that: one function, one call site per host.
STANDING_REQUEST_HEADING = "## Review subagents: standing request."


def _standing_request_section(host_name: str = "Claude Code") -> str:
    return (
        "## Review subagents: standing request. Workflows: ask every time.\n\n"
        "**The review cascade is requested by default — spawn it, never pause to ask, and never record a review `not_run` citing a session policy.** "
        "That is `spec-reviewer` → `code-reviewer` → `doubt-reviewer` plus the review subagents other phase skills prescribe (build Step 6, campaign review). "
        f"{host_name} withholds subagent spawning until the user asks; **this file is that request, and it stands for every session.** "
        "**The grant covers reviewers, not fan-out.** Dynamic workflows, deep-research, and parallel implementation subagents (build's `section-builder` loop) "
        "spend openly and stay the operator's call — ask explicitly, every time, and never infer them from the grant above. A project that does not want this "
        "can delete the section; it is deliberately plain and must not be compressed further, because it has to read as the user's request at runtime."
    )


#: Back-compat: existing callers (`_append_standing_request`'s default,
#: any external import) get the exact same text as before this change.
STANDING_REQUEST_SECTION = _standing_request_section()


AGENT_DOCS_DIR = ".shipwright/agent_docs"


def _render_claude_md(
    *,
    project_name: str,
    profile: str,
    stack: dict[str, Any],
    commands: dict[str, str | None],
    product_description: str,
    host_name: str = "Claude Code",
) -> str:
    runtime = _fmt_stack_line(stack.get("runtime", {}))
    frontend = _fmt_stack_line(stack.get("frontend", {}))
    backend = _fmt_stack_line(stack.get("backend", {}))
    database = _fmt_stack_line(stack.get("database", {}))
    auth = _fmt_stack_line(stack.get("auth", {}))
    build_cmd = commands.get("build") or "—"
    test_cmd = commands.get("test") or "—"
    dev_cmd = commands.get("dev") or "—"
    # The "Editing this file" section names the file it's actually in and the
    # growth-gate enforcement (`check_agent_doc_budget.py`) only reads
    # CLAUDE.md, never AGENTS.md — both must stay tied to host_name, not
    # hardcoded, or a generated AGENTS.md misnames itself and cites an env
    # var that does nothing for it (doubt-reviewer, R4, high-severity).
    doc_filename = "CLAUDE.md" if host_name == "Claude Code" else "AGENTS.md"
    growth_gate_line = (
        "- **Growth is gated:** iterate finalization flags a change that net-grows this\n"
        "  file by more than 30 lines (deliberate exception:\n"
        "  `SHIPWRIGHT_CLAUDE_MD_GROWTH_OK=1`)."
        if doc_filename == "CLAUDE.md" else
        "- **No automated growth gate for this file yet** — keep it lean by the\n"
        "  same restraint CLAUDE.md's line-cap enforces; watch it by hand."
    )
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

{_standing_request_section(host_name)}


## Editing this file (keep it lean)

{doc_filename} is **orientation + a terse invariant index** — it is loaded into
every session, so every line here costs context on every future change.

- **New invariant / DO-NOT rule:** add **one line + a pointer** to the ADR or
  conventions entry that carries the rationale (e.g. `- Never bypass X — see
  ADR-012`). The full reasoning lives in
  `{AGENT_DOCS_DIR}/decision_log.md` or `conventions.md`, **not here**.
- **Exception — the standing-request section above** is deliberately one dense line: it must read as the user's request at runtime, and its length is what keeps this file under the hygiene cap. Leave it as it is. **No inline rationale:** if a rule needs more than ~2 lines to state, the
  extra lines belong in the ADR it cites. Keep lines short — a long paragraph
  on one line is still rationale.
- **Prefer updating an existing line** over adding a new one.
{growth_gate_line}

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


def _append_section_if_missing(path: Path, heading: str, section: str) -> bool:
    """Append `section` to a PRESERVED file, unless `heading` is already
    present in it. The load-bearing branch deliberately does not overwrite
    an existing file — that policy exists because adopt once destroyed a
    16 KB CLAUDE.md. But writing the rendered content to a side-file the
    harness never loads means the section never reaches the real file at
    all, so appending it is additive: nothing existing is touched, and the
    operator keeps the backup `preserve_if_exists` already took.

    Idempotent by heading, so re-running adopt does not stack duplicates.
    Returns True when it wrote, False when the section was already present.

    The presence check is anchored to a LINE START (``re.MULTILINE``), not a
    bare substring search — a heading string could otherwise appear mid-line
    in quoted prose and be falsely counted "already present" (external code-
    review cascade, R4, low). It does NOT rule out a fenced-code-block false
    positive — accepted as a narrow, pre-existing risk shared with CLAUDE.md's
    own standing-request heading, not one this diff introduces (external
    code-review cascade, R4, medium/low, both legs).

    Reads and writes with ``newline=""`` (no universal-newline translation)
    so a file's PRE-EXISTING line endings survive byte-for-byte — the default
    translate-on-read/re-encode-on-write behavior would otherwise flip an
    LF-only preserved file to CRLF on Windows, contradicting "nothing
    existing is touched" with a full-file line-ending rewrite (doubt-
    reviewer, R4, medium). Only the newly appended text is LF-terminated.
    """
    # Path.read_text() has no `newline` parameter (unlike write_text) — only
    # a raw file handle can disable universal-newline translation on read.
    with path.open(encoding="utf-8", newline="") as fh:
        body = fh.read()
    if re.search(r"^" + re.escape(heading), body, re.MULTILINE):
        return False
    if body.endswith("\n\n"):
        separator = ""
    elif body.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    path.write_text(body + separator + section + "\n", encoding="utf-8", newline="")
    return True


def _append_standing_request(path: Path, host_name: str = "Claude Code") -> bool:
    return _append_section_if_missing(
        path, STANDING_REQUEST_HEADING, _standing_request_section(host_name),
    )


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
