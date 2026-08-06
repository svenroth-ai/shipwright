#!/usr/bin/env python3
"""Check inline `# nosemgrep` suppressions against the anti-ratchet baseline.

Two subcommands, both read-only:

``check``  the gate. Fails when a rule exceeds its ``max_sites``, when a rule
           has no baseline entry, when any file could not be read (a partial
           count in a security gate is a bypass, not a warning), or when an
           entry is DEAD — its rule suppressed nowhere, so nothing in the tree
           corresponds to it any more. A count that merely shrinks is
           advisory.
``scan``   discovery only — prints what is in the tree and, with
           ``--as-baseline``, a ready-to-edit baseline document. Useful when
           adding a legitimate suppression: you still have to write the
           ``statement`` and cite a real decision by hand, which is the point.

**This CLI is an operator front-end, not the enforcement path.** What binds in
CI is ``shared/tests/test_inline_suppressions_repo_guard.py``, which calls
``inline_suppressions.reconcile`` directly; both entry points run the same rule
over the same code, and this file's own exit-code contract is pinned by
``shared/tests/test_inline_suppressions_cli.py``. Stated precisely because the
imprecise version ("the CLI is wired into the guard") claims a wiring that does
not exist — and a run whose whole premise is *a gate nothing invokes constrains
nothing* has no business being vague about which thing CI actually invokes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from inline_suppressions import (  # noqa: E402
    BASELINE_NAME,
    BaselineError,
    baseline_path,
    format_report,
    reconcile,
    scan,
    seed_baseline,
)


def cmd_check(project_root: Path) -> int:
    result = reconcile(project_root)
    n_sites = sum(len(v) for v in result["sites"].values())
    n_rules = len(result["sites"])

    # The file count is not decoration: without it "0 suppressions" cannot be
    # told apart from "0 files examined", and the latter — a fresh `git init`,
    # a sub-directory holding no tracked files — read as a clean bill of health
    # for a tree nothing was read from (Stage-3 doubt review, D3).
    scanned = f"{result['files_examined']} file(s) examined"
    if result["baseline_present"]:
        print(
            f"inline-suppressions check: {scanned}; {n_sites} inline "
            f"suppression(s) across {n_rules} rule(s), "
            f"{len(result['entries'])} baseline entr"
            f"{'y' if len(result['entries']) == 1 else 'ies'}."
        )
    else:
        # Reconciled anyway. Passing on the MISSING file would mean deleting it
        # silences the gate while every suppression stays live — the hole the
        # register closed in iterate-2026-07-31-accepted-risk-gate-holes.
        print(
            f"inline-suppressions check: no {BASELINE_NAME} at {project_root} - "
            f"{scanned}; reconciling {n_sites} suppression(s) against an "
            "empty baseline."
        )
    if not result["files_examined"]:
        print(
            "  NOTE  no files were examined at all - this is not a clean "
            "result, it is an empty one. Check that --project-root points at "
            "a repository with tracked files."
        )
    if result["mode"] != "git":
        # Never let a narrowed scope read as a clean result.
        print(
            "  NOTE  not a git tree - the file set came from a filesystem walk "
            "with a fixed exclusion list, which is broader and less precise "
            "than `git ls-files`."
        )

    problems = format_report(result)
    if problems:
        # The header must not read as a failure when every line is advisory —
        # a shrinking count is the outcome this gate exists to encourage.
        header = ("Inline-suppression baseline drift:" if not result["ok"]
                  else "Inline-suppression baseline is loose (advisory only):")
        print(f"\n{header}\n")
        for problem in problems:
            print(problem)
        return 0 if result["ok"] else 1
    print("  no drift.")
    return 0


def cmd_scan(project_root: Path, *, as_baseline: bool) -> int:
    if as_baseline:
        # A skeleton seeded from a PARTIAL count would freeze numbers that are
        # too low, and `seed_baseline` discards `unreadable` (Stage-3 doubt
        # review, D11). Refuse rather than emit counts the docstring promises
        # are exact.
        unreadable = scan(project_root)["unreadable"]
        if unreadable:
            print(
                "inline-suppressions: refusing to seed a baseline from a "
                "PARTIAL count — these file(s) could not be read, so the "
                "numbers would be too low:\n  "
                + "\n  ".join(unreadable),
                file=sys.stderr,
            )
            return 2
        # Both placeholders must FAIL validation, or this output could be piped
        # straight into the baseline and yield a green gate carrying no real
        # governance. `ADR-000` would have passed `DECISION_REF_RE` and a
        # sentence-length TODO would have passed the statement minimum — the
        # skeleton has to be unusable until a human fills it in.
        doc = seed_baseline(
            project_root,
            rationale_ref="TODO",
            statement="TODO",
        )
        print(json.dumps(doc, indent=2))
        print(
            "\n# The TODO placeholders above are INVALID on purpose — `check` "
            "rejects\n# both of them. Replace rationale_ref with a real "
            "recorded decision\n# (ADR-NNN, an iterate-YYYY-MM-DD-slug run id, "
            "or #NNN) and write a\n# rule-specific statement before "
            "committing.",
            file=sys.stderr,
        )
        return 0

    result = scan(project_root)
    print(f"mode: {result['mode']}")
    for rule, sites in result["sites"].items():
        print(f"{len(sites):4d}  {rule}")
        for site in sites:
            print(f"        {site}")
    for item in result["unreadable"]:
        print(f"  UNREADABLE  {item}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check inline nosemgrep suppressions against the baseline.")
    parser.add_argument(
        "command", choices=("check", "scan"),
        help="check the ratchet / print discovered suppressions")
    parser.add_argument("--project-root", default=".", help="repo root")
    parser.add_argument(
        "--as-baseline", action="store_true",
        help="scan only: emit a baseline skeleton pinning the current counts")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        # Fails CLOSED on a typo'd path. Otherwise git errors out, the walk
        # finds nothing, no baseline exists, and the gate prints "no drift."
        # and exits 0 — a clean bill of health for a directory that is not
        # there (Stage-2 code review).
        print(
            f"inline-suppressions: --project-root {project_root} is not a "
            "directory; refusing to report a result for a tree that was "
            "never read.",
            file=sys.stderr,
        )
        return 2
    try:
        if args.command == "check":
            return cmd_check(project_root)
        return cmd_scan(project_root, as_baseline=args.as_baseline)
    except BaselineError as exc:
        # Fail closed: an unreadable baseline is never "nothing accepted".
        print(
            f"inline-suppressions: {baseline_path(project_root).name} is "
            f"invalid - {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
