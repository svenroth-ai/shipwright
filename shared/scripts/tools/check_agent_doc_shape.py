"""Repo-agnostic canonical-SHAPE gate for the agent-doc changelog sections.

Companion to ``check_agent_doc_budget`` (length). Flags any dated bullet under
``## Architecture Updates`` / ``## Convention Updates`` that is not the canonical
``- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — <sentence>. → <pointer>`` form
(a Campaign / sub_iterate / free-text anchor, or a missing Impact separator /
arrow pointer). ``## Learnings`` (date-first grammar) is out of scope. Ships via
the plugin cache, so it enforces in the monorepo AND every adopted repo.

Modes (identical semantics to check_agent_doc_budget):
- forward-only (default): only entries NEW/anchor-changed vs the git base, so a
  legacy non-canonical entry you did not touch never blocks. No base resolvable
  → no-op success (use --all for a full scan).
- full-corpus (--all): every dated entry on/after the cutoff (or --since).

Exit 0 = clean/skipped, 1 = violations, 2 = usage error.

  uv run shared/scripts/tools/check_agent_doc_shape.py --project-root .
  uv run shared/scripts/tools/check_agent_doc_shape.py --all
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.agent_doc_budget import iter_entries  # noqa: E402
from lib.agent_doc_shape import (  # noqa: E402
    ENFORCED_FROM,
    SHAPE_SECTIONS,
    new_non_canonical,
    non_canonical,
)
# Reuse the sibling gate's git-base + agent-doc read helpers (same docs, same
# forward-only diff) rather than duplicate them.
from tools.check_agent_doc_budget import _base_text, _read, resolve_base  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402


def find_violations(
    project_root: Path,
    *,
    full_corpus: bool = False,
    base_ref: str = "",
    since: date | None = ENFORCED_FROM,
) -> tuple[list[tuple[str, str, str]], str | None]:
    """Return ``(violations, base)``. ``violations`` = ``(filename, header, msg)``;
    ``base`` is the resolved git base (None in full-corpus mode or unresolvable)."""
    violations: list[tuple[str, str, str]] = []
    if full_corpus:
        for filename, header in SHAPE_SECTIONS:
            text = _read(project_root, filename)
            if text is None:
                continue
            for v in non_canonical(iter_entries(text, header), since):
                violations.append((filename, header, v))
        return violations, None

    base = resolve_base(project_root, base_ref)
    if base is None:
        return [], None
    for filename, header in SHAPE_SECTIONS:
        text = _read(project_root, filename)
        if text is None:
            continue
        base_text = _base_text(project_root, base, filename)
        for v in new_non_canonical(text, base_text, header):
            violations.append((filename, header, v))
    return violations, base


def main() -> int:
    ensure_utf8_stdout()  # report carries '—' / '→'; cp1252 console crashes otherwise
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".", help="Project directory")
    parser.add_argument("--base", default="", help="Git ref to diff against (default: auto)")
    parser.add_argument("--all", action="store_true", help="Full-corpus scan (every dated entry)")
    parser.add_argument("--since", default="", help="Full-corpus cutoff ISO date (default: enforced_from)")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    since: date | None = ENFORCED_FROM
    if args.since:
        try:
            since = date.fromisoformat(args.since)
        except ValueError:
            print(f"check_agent_doc_shape: invalid --since '{args.since}' (want YYYY-MM-DD)")
            return 2

    violations, base = find_violations(
        project_root, full_corpus=args.all, base_ref=args.base, since=since,
    )
    if not args.all and base is None:
        print("check_agent_doc_shape: no git base resolvable — skipped (use --all for a full scan)")
        return 0
    if violations:
        n = len(violations)
        print(f"agent-doc shape: {n} non-canonical entr{'y' if n == 1 else 'ies'}. Every dated "
              "changelog bullet must read '- **<run_id|ADR-NNN>** (YYYY-MM-DD): <Impact> — "
              "<sentence>. → <pointer>' (no Campaign/sub_iterate/free-text anchor; references/F2.md):")
        for filename, header, msg in violations:
            print(f"  - {filename} '{header}': {msg}")
        return 1
    print("agent-doc entry shape: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
