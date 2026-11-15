#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Resolve, list and validate Shipwright stack profiles.

Lookup order: ``<project>/.shipwright/profiles`` -> ``~/.shipwright/profiles``
(or ``SHIPWRIGHT_USER_PROFILES_DIR``) -> bundled ``shared/profiles``.

    resolve_profile.py resolve  --name N [--project-root R] [--json | --path-only]
    resolve_profile.py list     [--project-root R] [--json]
    resolve_profile.py validate (--name N | --file F) [--project-root R]

Exit codes: 0 ok, 2 not found, 3 invalid / schema drift, 4 usage.
``validate`` also reports architecture-rule problems (stderr, and ``rule_errors`` /
``rule_warnings`` in ``--json``). They never change the exit code: a profile with a
malformed rule is still a valid profile (exit 0); read ``rule_errors`` / ``rules_valid`` to gate on them. Mechanism paths of a non-bundled
profile are checked against ``--project-root`` (default ``.``): run from the project.
stdout carries ONLY the requested output; provenance (source, shadows,
shadow warning) goes to stderr. ``resolve --path-only`` for ``generic`` /
``detecting`` prints nothing and exits 0 (empty path = built-in defaults).
``list`` and ``validate`` are strictly read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ADDED = _SCRIPTS not in sys.path
if _ADDED:
    sys.path.append(_SCRIPTS)  # APPEND, never insert(0): plugins own a `lib`
from profile_architecture_rules import check_paths, load_rules  # noqa: E402
from profile_resolver import (  # noqa: E402
    list_profiles, load_profile_file, provenance_lines, resolve_profile,
)
if _ADDED:  # in-process main(argv) must not leave shared/scripts (a `tools` package) on sys.path
    sys.path.remove(_SCRIPTS)

EXIT_USAGE = 4


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse's own exit 2 would collide
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        raise SystemExit(EXIT_USAGE)


def _parser() -> argparse.ArgumentParser:
    p = _Parser(prog="resolve_profile.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    for name in ("resolve", "list", "validate"):
        s = sub.add_parser(name)
        s.add_argument("--project-root", default=".")
        s.add_argument("--json", action="store_true")
        if name != "list":
            s.add_argument("--name")
        if name == "resolve":
            s.add_argument("--path-only", action="store_true")
        if name == "validate":
            s.add_argument("--file")
    return p


def _plain(text) -> str:
    """Control characters in a profile-controlled string must not drive the terminal."""
    return re.sub(r"[\x00-\x1f\x7f]", lambda m: repr(m.group())[1:-1], str(text))


def _emit(obj) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _list(args) -> int:
    out = list_profiles(args.project_root)
    for w in out["warnings"]:
        sys.stderr.write(f"warning: {_plain(w)}\n")
    if args.json:
        _emit(out)
        return 0
    for row in out["profiles"]:
        flag = "" if row["valid"] else f"  INVALID: {_plain(row['error'])}"
        sys.stdout.write(f"{_plain(row['name'])}\t{row['source']}\t{_plain(row['path'])}{flag}\n")
    return 0


def _run(args, parser) -> int:
    if args.cmd == "list":
        return _list(args)
    if args.cmd == "validate":
        if bool(args.name) == bool(args.file):
            parser.error("validate needs exactly one of --name or --file")
        res = (resolve_profile(args.name, args.project_root) if args.name
               else load_profile_file(args.file, project_root=args.project_root))
    else:
        if not args.name:
            parser.error("resolve needs --name")
        if args.json and args.path_only:
            parser.error("--json and --path-only are mutually exclusive")
        res = resolve_profile(args.name, args.project_root)
    for line in provenance_lines(res):
        sys.stderr.write(line + "\n")
    if args.cmd == "validate":
        rs = load_rules(res.data.get("architecture_rules"))
        errors = [f"architecture_rules: {e}" for e in rs.errors]
        if res.custom:  # a bundled profile's paths are checked by a repo test (cache layout differs)
            errors += [f"architecture_rules: rule {rid}: {m} (project root {args.project_root})" for rid, m in check_paths(rs.rules, args.project_root)]
        warnings = [f"architecture_rules: {w}" for w in rs.warnings]
        for kind, lines in ("error", errors), ("warning", warnings):
            for line in lines:
                sys.stderr.write(f"{kind}: {_plain(line)}\n")
        if args.json:
            _emit({"valid": True, **res.to_dict(), "rules_valid": not errors, "rule_errors": errors, "rule_warnings": warnings})
        else:
            sys.stdout.write(f"ok: {res.name} ({res.source})\n")
    elif args.path_only:
        sys.stdout.write((res.path + "\n") if res.path else "")
    elif args.json:
        _emit(res.to_dict())
    else:
        sys.stdout.write(f"{res.name}\t{res.source}\t{res.path or ''}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # captured / replaced stream
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        return _run(args, parser)
    except SystemExit as exc:  # usage error (4) or --help (0): return, never raise
        return exc.code if isinstance(exc.code, int) else 0
    except ValueError as exc:  # ProfileError and friends: branch on .exit_code
        sys.stderr.write(f"error: {exc}\n")
        return getattr(exc, "exit_code", 1)


if __name__ == "__main__":
    sys.exit(main())
