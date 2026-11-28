#!/usr/bin/env python3
"""Print where a Shipwright project file lives at a commit (or in the working tree), repo-relative.

For readers that are not Python - workflow YAML, the bash pre-commit hook - so they never spell a moving
file by its root name (campaign root-files-into-config R1d, BRIEF 4.1 "bloat gate fails OPEN"): ``git show
"$sha:$(uv run shared/scripts/tools/shipwright_rel_at.py bloat_baseline --commit "$sha")"``. The answer is
the new place when it exists AT THAT COMMIT, else the root (``shipwright_paths.rel_at``).

Exit 0 and one line on stdout; exit 2 for an unknown key; exit 3 when git cannot answer for ``--commit``
(an unresolvable commit, no git, a timeout) - never a silent root answer that CI would then read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import shipwright_paths as _sp  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("key", help="registry key, e.g. bloat_baseline")
    p.add_argument("--commit", default=None, help="a commit-ish; omitted: the working tree")
    p.add_argument("--project-root", default=".")
    a = p.parse_args(argv)
    if a.key not in _sp.SPECS:
        print(f"shipwright_rel_at: unknown key {a.key!r}", file=sys.stderr)
        return 2
    try:
        rel = _sp.rel_at(a.key, a.commit, a.project_root, strict=True)
        sys.stdout.buffer.write((rel + "\n").encode("utf-8"))   # LF even on Windows: bash $(...) keeps a CR
    except OSError as exc:   # GitReadError
        print(f"shipwright_rel_at: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
