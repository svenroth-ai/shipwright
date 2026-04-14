"""Unified CLI entrypoint for the Shipwright phase verifier.

Iterate 12.0 shipped ``iterate`` + ``runtime``. Iterate 12.1 adds
``project``. Iterate 12.2-12.4 will add ``design``, ``plan``, ``build``,
``test``, ``changelog``, ``deploy``.

Usage:

    uv run shared/scripts/tools/verify_phase.py \\
        --phase iterate --project-root webui \\
        --run-id iterate-2026-04-14-foo --commit $(git rev-parse HEAD)

    uv run shared/scripts/tools/verify_phase.py \\
        --phase runtime --project-root webui

    uv run shared/scripts/tools/verify_phase.py \\
        --phase project --project-root webui --run-id project-2026-04-14-foo

    uv run shared/scripts/tools/verify_phase.py \\
        --phase all --project-root webui --run-id iterate-foo

Exit codes:

- 0 — all green (or warnings only)
- 1 — at least one ERROR-severity failure (or any WARNING with ``--strict``)

Iterate 12.0b replaced the ``runtime_checks`` stub with a real
zombie-task reconciliation driven by the webui event-store +
``pids.json``, so ``--phase all`` dispatches both ``iterate`` and
``runtime`` together. Iterate 12.1 adds ``project`` to the ``all`` set;
the ``--run-id`` arg is shared across all phases (project + iterate both
use it to verify ``phase_history`` / ``iterate_history`` membership).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap: make the verifier package importable when this file is run
# directly via `uv run`.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers import (  # noqa: E402
    iterate_checks,
    project_checks,
    runtime_checks,
)
from tools.verifiers.common import (  # noqa: E402
    CheckResult,
    format_report,
    summarise,
)


# The phases that ``--phase all`` dispatches today.
#
# Iterate 12.0 excluded ``runtime`` because it was a stub (SKIPPED
# severity would have looked like a pass). 12.0b shipped the real
# runtime check; 12.1 adds ``project`` after wiring the canon into the
# project plugin's Step 8.
ALL_PHASES = frozenset({"iterate", "runtime", "project"})

DISPATCHABLE_PHASES = frozenset({"iterate", "runtime", "project", "all"})


def dispatch_iterate(project_root: Path, run_id: str, commit: str) -> list[CheckResult]:
    if not run_id:
        return [CheckResult(
            name="iterate phase dispatch",
            ok=False,
            detail="--run-id is required for --phase iterate",
        )]
    return iterate_checks.run_all_checks(project_root, run_id, commit)


def dispatch_runtime(project_root: Path) -> list[CheckResult]:
    return runtime_checks.run_all_checks(project_root)


def dispatch_project(project_root: Path, run_id: str) -> list[CheckResult]:
    return project_checks.run_all_checks(project_root, run_id=run_id)


def dispatch_all(project_root: Path, run_id: str, commit: str) -> list[CheckResult]:
    out: list[CheckResult] = []
    if "iterate" in ALL_PHASES and run_id:
        # Skip iterate in --phase all when no run_id — it would be a
        # guaranteed failure (run_id is required for the iterate dispatch).
        out.extend(dispatch_iterate(project_root, run_id, commit))
    if "runtime" in ALL_PHASES:
        out.extend(dispatch_runtime(project_root))
    if "project" in ALL_PHASES:
        out.extend(dispatch_project(project_root, run_id))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--phase",
        required=True,
        choices=sorted(DISPATCHABLE_PHASES),
        help="Which phase's checks to run",
    )
    parser.add_argument("--project-root", default=".", help="Project directory")
    parser.add_argument(
        "--run-id",
        default="",
        help="Phase run id — required for iterate, optional for project "
        "(enables phase_history membership check).",
    )
    parser.add_argument("--commit", default="", help="Current HEAD commit hash (iterate phase)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit 1 if any WARN/FAIL)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    if args.phase == "iterate":
        results = dispatch_iterate(project_root, args.run_id, args.commit)
        title = "iterate finalization"
    elif args.phase == "runtime":
        results = dispatch_runtime(project_root)
        title = "runtime reconciliation"
    elif args.phase == "project":
        results = dispatch_project(project_root, args.run_id)
        title = "project finalization"
    else:  # all
        results = dispatch_all(project_root, args.run_id, args.commit)
        title = f"all phases ({', '.join(sorted(ALL_PHASES))})"

    print(format_report(title, results))

    summary = summarise(results)
    blocking = summary.errors > 0 or (args.strict and summary.warnings > 0)
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
