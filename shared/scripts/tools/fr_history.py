#!/usr/bin/env python3
"""Which recorded changes touched a requirement.

    uv run shared/scripts/tools/fr_history.py FR-01.11
    uv run shared/scripts/tools/fr_history.py FR-01.11 --json

Campaign ``2026-07-18-requirements-catalog``, S7. The requirements catalog says
change history is "answered by querying the append-only event log" — this is
the query. Without it that sentence points at a file and a hope.

Exit codes
----------
``0``  the requirement exists; its changes are listed, or it has none.
``2``  bad usage — argparse owns this code, so nothing else may claim it.
``3``  the id names no requirement in any spec (a typo, not an empty history).
``4``  the event log exists but could not be read — no answer was produced.

``3`` is the load-bearing one. If an unknown id exited 0 with an empty list, a
typo would read as "nothing ever touched this requirement" — the silent-green
shape the golden corpus froze as FV-1/FV-2 and this campaign keeps meeting. It
is deliberately NOT 2: argparse exits 2 on a malformed command line, and a
caller that could not tell "you typed the flag wrong" from "that requirement
does not exist" would be back to guessing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.fr_change_history import (  # noqa: E402
    STATUS_UNKNOWN_FR,
    change_history_for_fr,
)
from lib.fr_history_render import _ascii, _render_text  # noqa: E402
from lib._fr_history_events import EventLogUnreadable  # noqa: E402
from lib.tty_sanitize import strip_control_chars  # noqa: E402
# The neutral shared home for the Windows cp1252 stdout pin — reused rather
# than copied a sixth time (bloat-extraction recipe). Event summaries in this
# log genuinely carry non-ASCII (em dashes, arrows), so without it every
# non-trivial answer crashes on a default Windows console.
#
# stderr is deliberately NOT reconfigured, so every one of the three messages
# written there passes through `_ascii`. An earlier version of this comment
# claimed there was only one such message and that it was "kept ASCII-only" —
# both false: the unknown-id message interpolated the user's argv, which
# `strip_control_chars` leaves >= 0xA0 intact, so a non-ASCII id raised
# UnicodeEncodeError from the message explaining the rejection.
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402

EXIT_OK = 0
#: Matches argparse's own exit code for a malformed command line, so the two
#: usage paths (a blank id here, a bad flag there) report identically.
EXIT_USAGE = 2
EXIT_UNKNOWN_FR = 3
#: The log exists but could not be read or decoded. Distinct from every other
#: code because it is the one case where NO answer was produced.
EXIT_LOG_UNREADABLE = 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fr_history.py",
        description="Which recorded changes touched a requirement.",
    )
    parser.add_argument("fr_id", help="Requirement id, e.g. FR-01.11")
    parser.add_argument("--project-root", default=".", help="Repo root (default: .)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args(argv)
    ensure_utf8_stdout()  # before any write — reconfigure rejects a late change

    # Sanitise the ONE unsanitised value in the program, here at its entry
    # rather than at each of the three places it is echoed back (stdout
    # heading, stderr unknown-id message, --json payload). Folding at the
    # boundary is what makes "nothing is interpolated into output unsanitised"
    # a property of the program instead of a habit of its call sites.
    fr_id = " ".join(strip_control_chars(args.fr_id).split())
    if not fr_id:
        print("fr_id must not be empty (e.g. FR-01.11)", file=sys.stderr)
        return EXIT_USAGE

    root = Path(args.project_root).resolve()
    # ONE read of the log, not two. The log is appended to while it is read, so
    # fetching coverage separately could describe a different snapshot than the
    # changes printed above it — an answer no single state of the log supported.
    try:
        history = change_history_for_fr(root, fr_id)
    except EventLogUnreadable as exc:
        # Reported as a failure, never as "No recorded changes." An unreadable
        # log means the question could not be answered at all; rendering that as
        # an empty history would be the loudest possible instance of the exact
        # defect this tool exists to prevent.
        print(f"cannot answer: {_ascii(str(exc))}", file=sys.stderr)
        return EXIT_LOG_UNREADABLE
    coverage = history.coverage

    if args.json:
        print(json.dumps({
            "fr_id": history.fr_id,
            "status": history.status,
            "existence_verified": history.existence_verified,
            "in_catalog": history.in_catalog,
            "corrupt_fragments": history.corrupt_fragments,
            "changes": [
                {
                    "event_id": c.event_id,
                    "run_id": c.run_id,
                    "label": c.label,
                    "ts": c.ts,
                    "relation": c.relation,
                    "summary": c.summary,
                    "commit": c.commit,
                    "spec_impact": c.spec_impact,
                }
                for c in history.changes
            ],
            "coverage": {
                "work_events": coverage.work_events,
                "fr_linked_events": coverage.fr_linked_events,
            },
        }, indent=2))
    elif history.status == STATUS_UNKNOWN_FR:
        # ASCII-only, and now actually so. stderr is NOT reconfigured to UTF-8
        # (see the import note), and this message interpolates `fr_id` — which
        # `strip_control_chars` deliberately leaves >= 0xA0 intact. So
        # `fr_history.py 'FR-01.01→'` on a cp1252 console raised
        # UnicodeEncodeError from the very message explaining the failure. The
        # comment asserted a property the code did not have; `_ascii` gives it
        # the property instead of deleting the comment.
        print(
            f"{_ascii(fr_id)} names no requirement under .shipwright/planning/.\n"
            "This is NOT an empty history - the id itself is unknown. Check the "
            "id against\nthe catalog, or add the requirement row first.",
            file=sys.stderr,
        )
    else:
        print(_render_text(history, coverage))

    return EXIT_UNKNOWN_FR if history.status == STATUS_UNKNOWN_FR else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
