#!/usr/bin/env python3
"""Regenerate ``.shipwright/planning/adr/INDEX.md``. Nothing else.

This is the command named by the drift guard, by the generated header, and by
F3 when a best-effort refresh fails. It exists so that answer is never
"run ``aggregate_decisions.py``" — that would fold every pending decision-drop
into ``decision_log.md`` and delete the drop files, which is a release action,
not an index refresh.

A repo with no ADR folder is a no-op, not an error: the folder is never created.

CLI:
    uv run shared/scripts/tools/rebuild_adr_index.py --project-root .
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.adr_index import ADR_SPEC_FOLDER, rebuild_adr_index  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the ADR spec folder's INDEX.md.",
    )
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)

    try:
        path = rebuild_adr_index(Path(args.project_root))
    except (OSError, LockTimeout) as exc:
        print(f"ERROR: could not write INDEX.md: {exc}", file=sys.stderr)
        return 1

    # ASCII-only on stdout: on Windows Python encodes stdout with the console
    # codec (cp1252), so an em-dash here goes out as 0x97 and any caller reading
    # the pipe as UTF-8 raises UnicodeDecodeError.
    if path is None:
        print(f"no ADR spec folder at {ADR_SPEC_FOLDER} - nothing to do")
        return 0
    print(f"regenerated {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
