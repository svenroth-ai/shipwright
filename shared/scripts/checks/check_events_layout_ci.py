#!/usr/bin/env python3
"""Consumer CI check (issue 978, S7): a PR must not write the legacy event log once the merge-base is on drops.

    check_events_layout_ci.py --project-root . --base-ref origin/main [--head-ref HEAD] [--allow-full-fold]

Judged at the merge-base of ``--base-ref`` and ``--head-ref`` (see ``lib/events_layout_ci.py``). Exit 0 = clean
(also: merge-base still legacy), 1 = violations (JSON on stdout), 2 = the refs could not be resolved. Wiring this
into a workflow is an operator decision (CI trust boundary); no workflow is changed by this script.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_layout_ci import GitError, check_layout_ci  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project-root", default=".")
    p.add_argument("--base-ref", required=True)
    p.add_argument("--head-ref", default="HEAD")
    p.add_argument("--allow-full-fold", action="store_true")
    a = p.parse_args(argv)
    ensure_utf8_stdout()
    try:
        violations = check_layout_ci(a.project_root, a.base_ref, a.head_ref, allow_full_fold=a.allow_full_fold)
    except (GitError, subprocess.SubprocessError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    print(json.dumps({"status": "violations" if violations else "ok",
                      "violations": [v.__dict__ for v in violations]}, indent=2, ensure_ascii=False))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
