"""F11 claim check: the independent gap check left a record for this iterate (a warning, never a hold).

The check itself (``tools/ai_gap_check.py``) writes ``ai-gap-check.json`` into the run's planning
directory: ``status: "ran"`` with the model's verdict, or ``status: "not_run"`` with the reason
(no key, provider down, unreadable reply). Either is a visible, honest record. This module only asks
that one of them exists; it never reads the verdict. Whether the check agreed is for the PR reader.

* No event for the run, or a source other than iterate: SKIPPED.
* No record, or an unreadable one: an advisory WARNING (strict-exempt). A missing check must never
  hold a PR, and the F5b repair path cannot rewrite a recorded event.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402

CHECK_NAME = "independent gap check recorded (iterate)"

_REPAIR = ("run shared/scripts/tools/ai_gap_check.py for this run (references/F5b.md, 'Independent gap check') "
           "and paste .shipwright/planning/iterate/<run_id>/ai-gap-check.md into the PR body; a check that cannot "
           "run records itself as not_run, which also satisfies this")


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def check_ai_gap_check_recorded(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    event = _work_event(root, run_id)
    if event is None:
        return CheckResult(CHECK_NAME, True, f"skipped (no work_completed event for {run_id})", severity=Severity.SKIPPED.value)
    if event.get("source") != "iterate":
        return CheckResult(CHECK_NAME, True, f"skipped (source={event.get('source') or 'unknown'}, not an iterate event)",
                           severity=Severity.SKIPPED.value)
    record = root / ".shipwright" / "planning" / "iterate" / run_id / "ai-gap-check.json"
    if not record.is_file():
        return _warn(f"no independent gap check record for this iterate - {_REPAIR}")
    try:
        status = json.loads(record.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError, AttributeError) as exc:
        return _warn(f"the independent gap check record is unreadable ({exc}) - {_REPAIR}")
    if status not in ("ran", "not_run"):
        return _warn(f"the independent gap check record has status {status!r}, expected ran or not_run - {_REPAIR}")
    return CheckResult(CHECK_NAME, True, "not run (recorded with its reason)" if status == "not_run" else "recorded")
