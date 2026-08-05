#!/usr/bin/env python3
"""Console printing that survives an encoding the terminal cannot represent.

The runner's own prose is ASCII-only (test_operator_facing_strings_are_ascii_only
in `suite_units.py`), but a unit's captured pytest output - rendered into the
report by `suite_report.render_run_report` - is arbitrary third-party text that
discipline never reaches. On a Windows cp1252 console, a character that codepage
cannot encode used to raise UnicodeEncodeError AFTER the suite had already
decided pass/fail, truncating the report at the one moment - a red unit - the
console is the operator's primary read. The suite's own verdict is unaffected
either way; this only keeps the report on screen (the full tail still lands in
the diagnostics JSON under `.shipwright/runs/<hash>/f0-diagnostics/`).
"""

from __future__ import annotations

import sys


def print_console(line: str) -> None:
    """Print one report line, replacing what the console can't encode."""
    try:
        print(line)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(encoding, errors="replace").decode(encoding))
