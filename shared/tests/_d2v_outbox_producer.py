"""Standalone outbox producer for the D2V SUBPROCESS concurrency proof.

Not a test (leading underscore → pytest does not collect it). Invoked as a REAL
separate OS process by ``test_d2v_empirical_gate.py`` so the canonical triage
``_FileLock`` is contended cross-PROCESS (OS-level ``msvcrt.locking`` / ``fcntl``),
not merely cross-thread under one interpreter's GIL (external-review openai-H2 /
gemini concurrency finding). Each invocation appends N uniquely-tagged ids to the
gitignored outbox via the REAL ``triage.append_triage_item(..., to_outbox=True)``.

Usage: ``python _d2v_outbox_producer.py <work_root> <id1> <id2> ...``
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import triage  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: _d2v_outbox_producer.py <work_root> <id> [<id> ...]", file=sys.stderr)
        return 2
    work = Path(argv[0])
    ids = argv[1:]
    for iid in ids:
        # Sub-ms jitter so the inter-append window (where the sweep can acquire
        # the lock) varies; the parent process seeds nothing here — true wall-clock
        # interleaving across the two OS processes is the point.
        time.sleep(random.uniform(0.0, 0.002))
        triage.append_triage_item(
            work, source="plugin-sync", severity="low", kind="maintenance",
            title=iid, detail="d", to_outbox=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
