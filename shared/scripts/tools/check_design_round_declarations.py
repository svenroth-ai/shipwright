#!/usr/bin/env python3
"""Refuse to finish the design phase while a feedback round is silent.

Part (1)'s completion gate. Design is where flows are rightly rethought, so a
round that changed *what a screen or flow does* must have corrected the
requirement it belongs to. Judging behaviour-versus-appearance is a human read —
but whether an answer was given at all is not, and that is what this checks.

Every processed round must have a requirement-impact declaration recorded under
**this** run id. Deciding a round was appearance-only is a perfectly good answer;
saying nothing is not.

Usage::

    # rounds discovered from the baselines the rounds themselves recorded
    uv run check_design_round_declarations.py --project-root . --run-id "$RUN"

    # or named explicitly
    uv run check_design_round_declarations.py --project-root . --run-id "$RUN" \\
      --round round-1 --round round-2

Exit codes: ``0`` every round declared, ``1`` a round is undeclared, ``2`` the
request itself was bad (damaged declaration files).

Origin: trg-e9e5188e (FR-01.04).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.requirement_impact import PHASE_VALUES  # noqa: E402
from lib.requirement_impact_baseline import discover_baseline_scopes  # noqa: E402
from lib.requirement_impact_store import (  # noqa: E402
    declaration_dir,
    find_declaration,
)

_DESIGN_PHASE = PHASE_VALUES[0]  # "design"


def discover_rounds(project_root, run_id) -> list[str]:
    """Round scopes derived from the baselines the rounds themselves recorded.

    **Not** from ``design-feedback-round*.md``. An earlier draft globbed those,
    and adversarial review broke it in one line: that file is gitignored review
    scratch the phase's own docs describe as transient, the standalone flow
    exports it through a browser download (so it may live anywhere, or arrive
    named ``...round2 (1).md``), and an empty glob resolved to PASS. Three
    processed rounds could therefore finalize clean.

    A baseline is written by the round itself, under this run's identity, in a
    tracked directory — so a round that ran cannot fail to be seen here.

    Scoped to ``run_id``, which also fixes the multi-session false failure: the
    design loop is explicitly resumable, so rounds accumulate across sessions,
    and requiring an earlier session's rounds to carry THIS session's id would
    have trained the agent to re-declare old rounds as appearance-only.
    """
    return discover_baseline_scopes(
        declaration_dir(project_root), run_id=run_id, phase=_DESIGN_PHASE)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify every design feedback round declared its requirement impact",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True,
                        help="this design run — a declaration from another run does NOT count")
    parser.add_argument("--round", action="append", dest="rounds", default=[],
                        metavar="SCOPE",
                        help="a round scope to require (repeatable); omit to "
                             "discover them from this run's recorded baselines")
    return parser


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()

    rounds = args.rounds or discover_rounds(project_root, args.run_id)
    directory = declaration_dir(project_root)

    declared: list[str] = []
    undeclared: list[str] = []
    all_problems: list[dict] = []
    for scope in rounds:
        record, problems = find_declaration(
            directory, run_id=args.run_id, phase=_DESIGN_PHASE, scope=scope)
        for problem in problems:
            if problem not in all_problems:
                all_problems.append(problem)
        (declared if record is not None else undeclared).append(scope)

    if all_problems:
        # Damage is not absence. Sending the operator to write declarations when
        # the real remedy is to repair a file wastes the one thing this gate is
        # meant to buy: an accurate picture of what each round decided.
        print(json.dumps({
            "success": False, "error": "declaration_damaged",
            "detail": "repair these declaration files before finalizing",
            "problems": all_problems,
        }, indent=2))
        return 2

    payload = {
        "success": not undeclared,
        "run_id": args.run_id,
        "rounds_checked": rounds,
        "declared": declared,
        "undeclared": undeclared,
        # Said out loud: no feedback rounds is a legitimately clean state (a
        # design approved on the first pass), NOT a check that silently found
        # nothing to look at.
        "note": ("no rounds recorded a baseline for this run — nothing to "
                 "declare (a design approved on the first pass is a legitimately "
                 "clean state)" if not rounds else None),
    }
    if undeclared:
        payload["detail"] = (
            f"{len(undeclared)} feedback round(s) have no requirement-impact "
            f"declaration for run {args.run_id!r}: {', '.join(undeclared)}. "
            "Run record_requirement_impact.py --phase design for each. Deciding a "
            "round was appearance-only is a fine answer (--impact none --reason "
            "'...'), but it has to be an answer — the design phase is not "
            "complete while a round is silent about what it did to the requirements."
        )
    print(json.dumps(payload, indent=2))
    return 1 if undeclared else 0


if __name__ == "__main__":
    sys.exit(main())
