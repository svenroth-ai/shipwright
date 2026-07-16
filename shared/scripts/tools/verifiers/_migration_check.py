"""``check_migration_quarantine_empty`` — extracted from ``iterate_checks.py``.

Split out (iterate-2026-07-15-removal-crosslayer-gates) to keep ``iterate_checks``
under its anti-ratchet bloat cap when the two enforcing traceability F11 gates
(``removal_coverage`` / ``cross_layer_coverage``) were registered. Behaviour is
unchanged — ``iterate_checks`` re-exports this symbol so every existing importer
(incl. ``test_verifiers_dual_mode``) keeps resolving it from its historical home.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import MIGRATION_QUARANTINED_COUNT_KEY  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402


def check_migration_quarantine_empty(project_root: Path) -> CheckResult:
    """Advisory warn — flag if iterate_history migration quarantined any entries.

    Loud signal on the operator's console so quarantined losses don't go
    unnoticed. Does not fail the check so follow-on work can proceed.
    """
    name = "iterate migration quarantine empty"
    cfg = project_root / "shipwright_run_config.json"
    if not cfg.exists():
        return CheckResult(name, None, "no run_config", severity=Severity.SKIPPED.value)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return CheckResult(name, None, "malformed run_config", severity=Severity.SKIPPED.value)

    count = data.get(MIGRATION_QUARANTINED_COUNT_KEY, 0)
    if not isinstance(count, int) or count == 0:
        return CheckResult(name, True, "no quarantined legacy entries")

    report = data.get("_iterate_migration_quarantine_report", "<no report path>")
    return CheckResult(
        name, False,
        f"{count} legacy iterate entries quarantined during migration — see {report}",
        severity=Severity.WARNING.value,
    )


__all__ = ["check_migration_quarantine_empty"]
