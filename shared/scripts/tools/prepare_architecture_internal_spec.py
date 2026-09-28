#!/usr/bin/env python3
"""Write a sanitized copy of a spec file for `architecture-internal-reviewer`.

That agent has ``tools: Read, Grep, Glob`` and is hand-fed a spec file PATH,
so a prose instruction to "ignore prior-review sections" is not a real
defense — it can simply re-read the original file. The external architecture
pass closed this same anchoring gap in code
(:func:`lib.external_review_modes.strip_prior_review_sections`, wired into
``external_review.py``'s ``--mode architecture``); this tool applies the
identical strip and hands the agent the SANITIZED COPY's path instead of the
original spec's, so there is nothing left to re-read even if it tried.

Output path: ``{project_root}/.shipwright/runs/{run_id}/architecture-internal-spec.md``
(same ephemeral, gitignored location `surface_verification.py` uses for
per-run scratch evidence — this file carries no information the committed
spec.md doesn't already have, so it is never committed itself).

Prints the output path on success (exit 0).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# parents[0]=tools, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from external_review_modes import strip_prior_review_sections  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--spec-file", required=True)
    args = parser.parse_args(argv)

    spec_path = Path(args.spec_file)
    spec_text = spec_path.read_text(encoding="utf-8")
    sanitized = strip_prior_review_sections(spec_text)

    runs_dir = Path(args.project_root) / ".shipwright" / "runs" / args.run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = runs_dir / "architecture-internal-spec.md"
    out_path.write_text(sanitized, encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
