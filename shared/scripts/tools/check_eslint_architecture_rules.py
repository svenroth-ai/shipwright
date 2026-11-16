#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check (and optionally repair) the architecture-rule ESLint blocks of a project.

    check_eslint_architecture_rules.py --project-root R [--profile NAME] [--apply] [--replace-stale] [--json]

The profile is ``--profile``, else the ``profile`` of ``shipwright_run_config.json``. For every rule of
that profile that carries an ESLint fragment, the project's ``eslint.config.*`` must hold the marked
block (see ``shared/scripts/eslint_architecture_rules.py``). ``--apply`` appends the missing blocks as
the last elements of the exported array; it refuses a config it cannot edit without guessing, and
never changes package.json. ``--replace-stale`` also overwrites blocks that differ from the profile
(a block folded by hand with an existing option differs on purpose: replace it only knowingly).

Exit codes: 0 every block present (or the profile has no ESLint rule), 1 findings remain,
2 the profile cannot be resolved, 3 ``--apply`` refused (message says why; nothing was written).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ADDED = _SCRIPTS not in sys.path
if _ADDED:
    sys.path.append(_SCRIPTS)  # APPEND, never insert(0): plugins own a `lib` / `tools`
import eslint_architecture_rules as ear  # noqa: E402
if _ADDED:
    sys.path.remove(_SCRIPTS)


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="check_eslint_architecture_rules.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--profile")
    ap.add_argument("--apply", action="store_true", help="append the missing blocks to the project's config")
    ap.add_argument("--replace-stale", action="store_true", help="with --apply: overwrite blocks that differ from the profile")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        name, rules = ear.rules_for_project(args.project_root, args.profile)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"error: profile cannot be loaded: {type(exc).__name__}: {exc}\n")
        return 2
    refused = ""
    if args.apply and rules:
        done = ear.apply(args.project_root, rules, replace_stale=args.replace_stale)
        refused = done.message if done.status == "cannot" else ""
    report = ear.check(args.project_root, rules)
    bad = report.bad
    if args.json:
        sys.stdout.write(json.dumps({
            "profile": name, "applicable": bool(rules), "config": report.config, "legacy": report.legacy,
            "findings": [vars(f) for f in report.findings], "notes": report.notes, "refused": refused,
        }, indent=2) + "\n")
    elif not rules:
        sys.stdout.write(f"not applicable: profile {name} has no rule with an ESLint fragment\n")
    else:
        sys.stdout.write(f"profile {name}, config {report.config or 'none'}: "
                         + ("every architecture-rule block is present\n" if not bad else f"{len(bad)} finding(s)\n"))
        for f in bad:
            sys.stdout.write(f"  {f.status.upper()} {f.rule_id}: {f.detail}\n")
        for note in report.notes:
            sys.stdout.write(f"  note: {note}\n")
        if refused:
            sys.stdout.write(f"  REFUSED: {refused}\n")
    if refused:
        return 3
    return 1 if bad else 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(_main())
