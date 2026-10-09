"""Throwaway smoke check (PR #860 campaign): docs/_smoke/unit-2.md exists and is non-empty.

Exit 0 when the file exists and holds non-whitespace text, 1 otherwise.
Standard library only; never imported by any gate.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

_TARGET = Path("docs") / "_smoke" / "unit-2.md"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def check(project_root: Path) -> tuple[bool, str]:
    target = project_root / _TARGET
    if not target.exists():
        return False, f"missing: {target}"
    if not target.is_file():
        return False, f"not a file: {target}"
    try:
        text = target.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"unreadable: {target}: {exc}"
    # Drop Unicode format characters (category Cf: zero-width spaces/joiners, BOM,
    # direction marks, soft hyphen) that str.strip() keeps but nothing renders.
    visible = "".join(c for c in text if unicodedata.category(c) != "Cf")
    if not visible.strip():
        return False, f"empty: {target}"
    return True, f"ok: {target}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args(argv)
    ok, message = check(args.project_root)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
