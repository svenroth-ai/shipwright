"""Deterministic post-commit verifier for iterate finalization.

Iterate 12.0 turned this file into a thin wrapper. The actual check
functions now live in ``tools/verifiers/iterate_checks.py`` (migrated
1:1 — same behaviour, same severity, same tests) and the shared
``CheckResult`` type lives in ``tools/verifiers/common.py``.

This file keeps its old import path (``tools.verify_iterate_finalization``)
so existing callers — the iterate skill's F11 gate check, the 18
regression tests in ``shared/tests/test_verify_iterate_finalization.py``,
and any out-of-tree scripts — keep working without edits.

CLI usage:
    uv run verify_iterate_finalization.py \\
        --run-id iterate-2026-04-13-foo \\
        --project-root webui \\
        --commit $(git rev-parse HEAD)

Exit code 0 = all green (or warnings only).
Exit code 1 = one or more hard-failures (missing required artifact).

The WARN level is used for soft drift (e.g. session_handoff.md stale by
hours) — visible to the user, not blocking. Callers that want strict
behavior can pass ``--strict`` to promote warnings to failures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap: add this file's parent (`shared/scripts`) to sys.path so that
# `tools.verifiers.*` resolves when the file is invoked as a script via
# `uv run shared/scripts/tools/verify_iterate_finalization.py`.
_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

# Re-export the legacy symbol surface expected by existing callers and
# by shared/tests/test_verify_iterate_finalization.py. DO NOT remove any
# of these without migrating every importer and updating the tests.
from tools.verifiers.common import CheckResult, Severity, format_report  # noqa: E402,F401
from tools.verifiers.iterate_checks import (  # noqa: E402,F401
    check_adr_in_iterate_history,
    check_changelog_unreleased,
    check_events_has_commit,
    check_iterate_history_has_run_id,
    check_session_handoff_fresh,
    run_all_checks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-id", required=True, help="Iterate run id to verify")
    parser.add_argument("--project-root", default=".", help="Project directory")
    parser.add_argument("--commit", default="", help="Current HEAD commit hash")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit 1 if any WARN/FAIL)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    results = run_all_checks(project_root, args.run_id, args.commit)
    print(format_report("iterate finalization", results))

    errors = sum(1 for r in results if r.is_failure and r.severity == Severity.ERROR.value)
    warnings = sum(1 for r in results if r.is_failure and r.severity == Severity.WARNING.value)

    if errors > 0 or (args.strict and warnings > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
