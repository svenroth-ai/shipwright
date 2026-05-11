#!/usr/bin/env python3
"""Scaffold the triage-inbox runtime files into a target project.

AC-6 of iterate-2026-05-11-triage-inbox-1a. Idempotent — safe to re-run.

Files touched:
- ``.shipwright/triage.jsonl``                — schema header if missing
- ``.shipwright/agent_docs/triage_inbox.md``  — empty skeleton if missing
- ``.gitignore``                              — append ``.shipwright/triage.jsonl``
                                                and ``.shipwright/triage.jsonl.lock``
                                                if those lines aren't present
                                                (LOW-14 + Gemini LOW-4)

Returns a dict summarising what changed so adopt's Step E.16 can surface
it in the handoff banner.

Usage (CLI):
    uv run shared/scripts/tools/scaffold_triage_inbox.py --project-root .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import SCHEMA_VERSION, TRIAGE_FILE, _ensure_header  # noqa: E402
from tools.aggregate_triage import render_markdown  # noqa: E402

_AGENT_DOCS_DIRNAME = ".shipwright/agent_docs"
TRIAGE_MD_REL = Path(_AGENT_DOCS_DIRNAME) / "triage_inbox.md"
GITIGNORE_LINES = (
    ".shipwright/triage.jsonl",
    ".shipwright/triage.jsonl.lock",
)


def _scaffold_jsonl(project_root: Path) -> dict[str, str]:
    """Ensure .shipwright/triage.jsonl exists with the schema header."""
    triage_path = project_root / ".shipwright" / TRIAGE_FILE
    existed = triage_path.exists()
    _ensure_header(project_root)
    action = "preserved" if existed else "created"
    return {
        "path": str(triage_path.relative_to(project_root)),
        "action": action,
        "schema_version": str(SCHEMA_VERSION),
    }


def _scaffold_markdown(project_root: Path, *, now: str = "scaffold") -> dict[str, str]:
    """Write the empty-state triage_inbox.md skeleton if missing."""
    md_path = project_root / TRIAGE_MD_REL
    if md_path.exists():
        return {"path": str(TRIAGE_MD_REL), "action": "preserved"}
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown([], now=now), encoding="utf-8")
    return {"path": str(TRIAGE_MD_REL), "action": "created"}


def _scaffold_gitignore(project_root: Path) -> dict[str, object]:
    """Append triage.jsonl + .lock to .gitignore if missing. Idempotent."""
    gi_path = project_root / ".gitignore"
    existing_lines: set[str] = set()
    existing_text = ""
    if gi_path.exists():
        existing_text = gi_path.read_text(encoding="utf-8")
        existing_lines = {
            L.strip() for L in existing_text.splitlines() if L.strip()
        }

    needed = [line for line in GITIGNORE_LINES if line not in existing_lines]
    if not needed:
        return {
            "path": ".gitignore",
            "action": "already-present",
            "added": [],
        }

    # Ensure file ends with newline before appending
    new_text = existing_text
    if new_text and not new_text.endswith("\n"):
        new_text += "\n"
    if needed:
        if existing_text:
            new_text += "\n# Triage Inbox (shipwright)\n"
        else:
            new_text = "# Triage Inbox (shipwright)\n"
        new_text += "\n".join(needed) + "\n"

    gi_path.write_text(new_text, encoding="utf-8")
    return {
        "path": ".gitignore",
        "action": "appended" if existing_text else "created",
        "added": needed,
    }


def scaffold_triage_inbox(project_root: Path) -> dict[str, object]:
    """Run the three scaffolding steps. Return a summary dict suitable
    for adopt's results.<key> handoff banner.
    """
    project_root = Path(project_root).resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    results = {
        "jsonl": _scaffold_jsonl(project_root),
        "markdown": _scaffold_markdown(project_root),
        "gitignore": _scaffold_gitignore(project_root),
    }
    return {
        "wrote": True,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Initial-adopt-time scaffolder for the triage inbox. "
            "Creates .shipwright/triage.jsonl with header, "
            ".shipwright/agent_docs/triage_inbox.md skeleton, and ensures "
            ".gitignore covers the JSONL + lock files. Idempotent."
        ),
    )
    p.add_argument("--project-root", default=".", help="Project root (default: .)")
    p.add_argument(
        "--json", action="store_true",
        help="Emit the scaffolding summary as JSON on stdout "
             "(default: human-readable on stderr).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root)
    result = scaffold_triage_inbox(project_root)

    if args.json:
        # JSON only — operators can pipe this into adopt's results bag
        print(json.dumps(result, indent=2))
    else:
        # Human summary on stderr so the CLI is safe under Stop-hook semantics
        # (matches aggregate_triage convention).
        sys.stderr.write("[scaffold_triage_inbox]\n")
        for key, info in result["results"].items():
            sys.stderr.write(f"  {key}: {info}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
