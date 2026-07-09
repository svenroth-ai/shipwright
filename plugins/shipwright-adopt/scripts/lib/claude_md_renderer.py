"""Render the adopted-project ``CLAUDE.md`` body.

Extracted from ``artifact_writer.py`` (bloat-baseline ceiling) — the render
is a hardcoded f-string that MUST stay mirrored with the greenfield template
``shared/templates/claude-md-template.md``; drift between the two is caught by
``shared/tests/test_claude_md_template.py``. ``artifact_writer`` re-exports
``_render_claude_md`` so existing importers keep working.

``AGENT_DOCS_DIR`` is defined locally here (the same self-contained pattern
``known_issues_inventory.py`` / ``visual_docs_generator.py`` use) to keep this
a neutral leaf that only imports the shared ``render_helpers`` — no cycle back
into ``artifact_writer``.
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
- Compliance + dashboard refresh

Do NOT invoke `/shipwright-project`, `/shipwright-plan`, or `/shipwright-build` directly — those are pre-onboarding phases.

See `{AGENT_DOCS_DIR}/decision_log.md` for the adoption ADR (the topmost
`Adopt this repository into the Shipwright SDLC` entry — its id is the
next-free 3-digit number after any pre-existing ADRs).

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
