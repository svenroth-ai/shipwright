#!/usr/bin/env python3
"""Check or render the constitution enforcement register.

The register lives in ``shared/config/conventions.json`` (section ``constitution``); the rules in
``shared/constitution.md``. ``--check`` lists every drift between them; ``--write`` regenerates the document
kept beside the JSON as ``shared/config/constitution_register.md`` (UTF-8, LF; redirecting ``--render`` in Windows
PowerShell writes UTF-16 and is not safe).

    uv run shared/scripts/tools/constitution_register.py --check
    uv run shared/scripts/tools/constitution_register.py --write

Exit codes: 0 no drift; 1 drift; 2 a file is missing or unreadable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SHARED = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SHARED / "scripts"))

from lib import constitution_register as cr  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--render", action="store_true", help="print the document to stdout")
    mode.add_argument("--write", action="store_true", help="write shared/config/constitution_register.md")
    ap.add_argument("--repo-root", type=Path, default=SHARED.parent)
    args = ap.parse_args(argv)
    try:
        register = cr.load_register(args.repo_root / "shared" / "config" / "conventions.json")
        doc = (cr.render_markdown(register) + "\n").encode("utf-8")
        if args.render:
            sys.stdout.buffer.write(doc)
            return 0
        if args.write:
            (args.repo_root / "shared" / "config" / "constitution_register.md").write_bytes(doc)
            return 0
        rules, strays = cr.parse((args.repo_root / "shared" / "constitution.md").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        print(f"constitution_register: {exc}", file=sys.stderr)
        return 2
    problems = cr.check(rules, register, args.repo_root, strays)
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
