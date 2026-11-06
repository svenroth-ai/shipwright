#!/usr/bin/env python3
"""CI / F11 integrity check of the event folders (issue 978, S6, kill criterion 6).

    check_events_integrity.py --project-root . --base-ref origin/main [--head-ref HEAD]
                              [--run-id <id> ...] [--allow-full-fold]

A change may only ADD files under shipwright_events.d / .archive / .quarantine, judged against the merge-base
of ``--base-ref`` and ``--head-ref``; fold and quarantine are the recognised exceptions (see
``lib/events_integrity.py``). Exit 0 = clean (also: no event folders at all), 1 = violations (JSON on stdout),
2 = the refs could not be resolved. Wiring this into a workflow is an operator decision (CI trust boundary).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_integrity import GitError, check_integrity  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--base-ref", required=True)
    p.add_argument("--head-ref", default="HEAD")
    p.add_argument("--run-id", action="append", default=[], help="a run id this change owns (repeatable)")
    p.add_argument("--allow-full-fold", action="store_true")
    a = p.parse_args(argv)
    ensure_utf8_stdout()
    try:
        violations = check_integrity(a.project_root, a.base_ref, a.head_ref, own_keys=tuple(a.run_id),
                                     allow_full_fold=a.allow_full_fold)
    except GitError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    print(json.dumps({"status": "violations" if violations else "ok",
                      "violations": [v.__dict__ for v in violations]}, indent=2, ensure_ascii=False))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
