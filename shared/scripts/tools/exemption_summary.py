"""Print one run's exemption count - the line F12 and the PR body carry.

    uv run exemption_summary.py --project-root . --run-id iterate-2026-10-08-x

Reads the F5c entry's ``exemptions`` block (``lib.exemption_record``) and prints
``0`` or ``N (reason-code: n, ...)`` - e.g. ``2 (fixture-or-helper: 2)``. An entry
that predates the block prints ``0``. Exit 0 on a readable entry, 1 when the run
has no entry or the block is malformed (the line then says ``INVALID - ...``),
so a PR body never silently claims "0" for a run whose record is broken.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.exemption_record import entry_exemptions_error, entry_summary_line  # noqa: E402
from lib.iterate_entry import find_entry_by_run_id  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    entry = find_entry_by_run_id(Path(args.project_root), args.run_id)
    if entry is None:
        print(f"INVALID - no iterate entry for {args.run_id} (F5c has not run)")
        return 1
    print(entry_summary_line(entry))
    return 1 if entry_exemptions_error(entry) else 0


if __name__ == "__main__":
    sys.exit(main())
