"""Repo-agnostic budget gate for the always-loaded agent docs.

Flags an over-budget entry under ``## Architecture Updates`` /
``## Convention Updates`` / ``## Learnings`` (architecture.md / conventions.md).
Runs in ANY project — the monorepo AND every adopted repo (it ships via the
plugin cache) — giving the "one-line pointer" rule the programmatic enforcement
the prose-only instruction never had.

Modes:
- forward-only (default): only entries NEW/changed vs the git base are checked,
  so a legacy over-budget entry you did not touch never blocks. The base is the
  ``merge-base`` of HEAD with ``--base`` (or, unset, the first resolvable of
  origin/HEAD, origin/main, origin/master, main, master). When no base is
  resolvable (no git / no remote) the check is a no-op success — use ``--all``
  to force a full scan.
- full-corpus (``--all``): every dated entry is checked (optionally ``>= --since``).

Exit 0 = clean (or skipped), 1 = violations, 2 = usage error.

  uv run shared/scripts/tools/check_agent_doc_budget.py --project-root .
  uv run shared/scripts/tools/check_agent_doc_budget.py --all   # full scan
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.agent_doc_budget import (  # noqa: E402
    ENTRY_MAX_CHARS,
    SECTIONS,
    iter_entries,
    new_over_budget,
    over_budget,
)
from tools.verifiers.git_helpers import _run_git  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402

_AGENT_DOCS_REL = ".shipwright/agent_docs"
_BASE_CANDIDATES = ("origin/HEAD", "origin/main", "origin/master", "main", "master")


def _read(project_root: Path, filename: str) -> str | None:
    p = project_root / _AGENT_DOCS_REL / filename
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else None


def _base_text(project_root: Path, base: str, filename: str) -> str:
    """The agent-doc file as it was at ``base`` ("" if absent / git failure)."""
    rc, out, _ = _run_git(project_root, "show", f"{base}:{_AGENT_DOCS_REL}/{filename}")
    return out if rc == 0 else ""


def resolve_base(project_root: Path, ref: str = "") -> str | None:
    """The merge-base commit of HEAD with ``ref`` (or the first resolvable
    default-branch candidate). None when no base can be resolved."""
    candidates = (ref,) if ref else _BASE_CANDIDATES
    for cand in candidates:
        rc, out, _ = _run_git(project_root, "merge-base", "HEAD", cand)
        if rc == 0 and out.strip():
            return out.strip()
    return None


def find_violations(
    project_root: Path,
    *,
    full_corpus: bool = False,
    base_ref: str = "",
    since: date | None = None,
    max_chars: int = ENTRY_MAX_CHARS,
) -> tuple[list[tuple[str, str, str]], str | None]:
    """Return ``(violations, base)``. ``violations`` is a list of
    ``(filename, header, message)``. ``base`` is the resolved git base (None in
    full-corpus mode or when unresolvable)."""
    violations: list[tuple[str, str, str]] = []
    if full_corpus:
        for filename, header in SECTIONS:
            text = _read(project_root, filename)
            if text is None:
                continue
            for v in over_budget(iter_entries(text, header), max_chars, since):
                violations.append((filename, header, v))
        return violations, None

    base = resolve_base(project_root, base_ref)
    if base is None:
        return [], None
    for filename, header in SECTIONS:
        text = _read(project_root, filename)
        if text is None:
            continue
        for v in new_over_budget(text, _base_text(project_root, base, filename), header, max_chars):
            violations.append((filename, header, v))
    return violations, base


def main() -> int:
    ensure_utf8_stdout()  # the report carries '…' / '→'; cp1252 console crashes otherwise
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".", help="Project directory")
    parser.add_argument("--base", default="", help="Git ref to diff against (default: auto)")
    parser.add_argument("--all", action="store_true", help="Full-corpus scan (every dated entry)")
    parser.add_argument("--since", default="", help="Full-corpus cutoff ISO date (with --all)")
    parser.add_argument("--max-chars", type=int, default=ENTRY_MAX_CHARS)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    since = None
    if args.since:
        try:
            since = date.fromisoformat(args.since)
        except ValueError:
            print(f"check_agent_doc_budget: invalid --since '{args.since}' (want YYYY-MM-DD)")
            return 2

    violations, base = find_violations(
        project_root,
        full_corpus=args.all,
        base_ref=args.base,
        since=since,
        max_chars=args.max_chars,
    )

    if not args.all and base is None:
        print("check_agent_doc_budget: no git base resolvable — skipped (use --all for a full scan)")
        return 0

    if violations:
        n = len(violations)
        print(f"agent-doc entry budget: {n} over-budget entr{'y' if n == 1 else 'ies'} "
              f"(> {args.max_chars} chars). Keep each a one-line 'what + ADR pointer'; "
              "move detail to the ADR / .shipwright/planning/adr/ "
              "(see references/F2.md, references/reflection.md):")
        for filename, header, msg in violations:
            print(f"  - {filename} '{header}': {msg}")
        return 1

    print("agent-doc entry budget: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
