#!/usr/bin/env python3
"""Refuse a `main`-repair that makes the test suite prove less.

The enforcement half of AC-6 (FR-01.19). `lib.assertion_weakening` decides; this
is the git shell around it plus an exit-code contract, so the rule can be a
**gate** rather than an instruction an agent is trusted to follow.

Wired into `.github/workflows/ci.yml` as a step of the already-required `CI`
job, conditional on the repair-branch grammar. **That step runs this file out of
the pull request's BASE revision, not the checked-out head** — a repair that
edits the checker would otherwise be judged by the checker it just edited, which
is not an enforcement boundary at all. See the workflow comment.

Exit codes: ``0`` clear (or findings that only need review) · ``2`` blocked ·
``3`` the diff could not be read (fails closed — an unreadable diff is not a
clean one).

Usage::

    uv run shared/scripts/tools/check_repair_safety.py \\
      --project-root . --base origin/main
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.assertion_weakening import (  # noqa: E402
    FileChange,
    detect_weakening,
    verdict,
)


#: What a ref may look like before it is handed to git. Every call here already
#: uses an argv LIST, so there is no shell to inject into — this is the second
#: fence: it refuses a value that is not ref-shaped at all, rather than letting
#: git interpret it (a leading `-` would be read as an OPTION, not a revision).
#: Deliberately permissive about the characters git itself allows in a revision
#: (`refs/heads/x`, `origin/main`, `HEAD~2`, `v1.0^{commit}`).
_REF_SHAPE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./:@^~{}-]*$")


class GitError(RuntimeError):
    """Any git call that did not succeed — never swallowed into a clean answer."""


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise GitError((proc.stderr or f"git {' '.join(args)} failed").strip()[:300])
    return proc.stdout


def _show(root: Path, ref: str, path: str) -> str | None:
    """File content at a revision, or None when it did not exist there."""
    try:
        return _git(root, "show", f"{ref}:{path}")
    except GitError:
        return None


def collect_changes(root: Path, base: str) -> list[FileChange]:
    """Every changed file between the merge-base and the working tree.

    Discovery is `--name-status --find-renames`, so a deletion is read from the
    base tree and a rename keeps its identity instead of reading as a deletion
    plus an unrelated addition.
    """
    merge_base = _git(root, "merge-base", base, "HEAD").strip() or base
    raw = _git(root, "diff", "--name-status", "--find-renames", merge_base)
    changes: list[FileChange] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0][:1].upper()
        if status == "R" and len(parts) >= 3:
            old_path, path = parts[1], parts[2]
        else:
            old_path, path = None, parts[-1]
        before_path = old_path or path
        changes.append(
            FileChange(
                status=status,
                path=path,
                old_path=old_path,
                before=None if status == "A" else _show(root, merge_base, before_path),
                after=None if status == "D" else _read(root / path),
            )
        )
    return changes


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Refuse a main-repair that weakens the test suite"
    )
    ap.add_argument("--project-root", default=".")
    ap.add_argument(
        "--base", required=True,
        help="the branch/ref this change is proposed against (a merge-base is "
             "computed from it, so a moved base cannot invent findings)",
    )
    args = ap.parse_args(argv)
    root = Path(args.project_root).resolve()

    if not _REF_SHAPE.match(args.base or ""):
        print(json.dumps({"verdict": "unreadable", "error": "base is not ref-shaped"},
                         indent=2))
        print(
            f"STOP: --base {args.base!r} is not a ref. Refusing before any git "
            "call — an unreadable diff is not a clean one.",
            file=sys.stderr,
        )
        return 3

    try:
        changes = collect_changes(root, args.base)
    except GitError as exc:
        print(json.dumps({"verdict": "unreadable", "error": str(exc)}, indent=2))
        print(
            f"STOP: the diff against {args.base} could not be read ({exc}). An "
            "unreadable diff is not a clean one.",
            file=sys.stderr,
        )
        return 3

    findings = detect_weakening(changes)
    result = verdict(findings)
    print(json.dumps(
        {
            "verdict": result,
            "base": args.base,
            "files_examined": len(changes),
            "findings": [
                {"kind": f.kind, "blocking": f.blocking,
                 "subject": f.subject, "detail": f.detail}
                for f in findings
            ],
        },
        indent=2,
    ))

    if result == "blocked":
        print(
            "STOP: this repair would make the test suite prove less.\n"
            "  " + "\n  ".join(f"{f.kind}: {f.subject} — {f.detail}"
                               for f in findings if f.blocking) + "\n"
            "Never adjust a test until it is green. If the failure is real and "
            "cannot be repaired without removing coverage, that is the "
            "escalation case: file a card (references/main-repair.md, "
            "'When to escalate') instead of shipping this.",
            file=sys.stderr,
        )
        return 2
    if result == "review":
        print(
            "NOTE: an assertion's expectation changed. That is allowed — it is "
            "the commonest honest repair — but the pull request must say why "
            "the NEW value is the truth.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
