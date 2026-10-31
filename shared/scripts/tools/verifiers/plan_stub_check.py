"""F11 claim check: a feature/change/bug iterate leaves a plan stub and names it as ``plan_path`` (a warning, never a hold).

The convention, the stub shapes and the lookups live in :mod:`lib.spec_chain`. This module finds the run's
``work_completed`` event and reports.

* No event for the run, a non-iterate source, or an intent outside feature/change/bug: SKIPPED.
* Every other iterate is asked, in any project and whatever paths it touched: the event carries no complexity,
  so "non-trivial" cannot be told apart and a tiny run writes the one-line stub.
* ``plan_path`` absent, the file missing, or no ``Goal:`` / ``Reason:`` line in it: an advisory WARNING
  (strict-exempt). The F5b repair path cannot rewrite a recorded event, so an error would be an unfixable block.
  Structure only: whether the sentences are true is for the reviewers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.affected_acs_gate import is_scoped_intent  # noqa: E402
from lib.spec_chain import parse_stub, plan_rel_path, safe_plan_path  # noqa: E402

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402

CHECK_NAME = "plan stub recorded (iterate)"


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def check_plan_stub_recorded(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    event = _work_event(root, run_id)
    if event is None:
        return _skip(f"no work_completed event for {run_id}")
    if event.get("source") != "iterate" or not is_scoped_intent(event):
        return _skip(f"source={event.get('source') or 'unknown'}, intent={event.get('intent') or 'unknown'}")
    repair = ("write the stub with tools/write_plan_stub.py (goal = WHAT, reason = WHY, reference; one line when tiny, "
              "full when an AC changes or a catalog gap is declared) and put its path on the event as plan_path")
    recorded = event.get("plan_path")
    if not isinstance(recorded, str) or not recorded.strip():
        return _warn(f"this iterate's event has no plan_path - {repair} (convention: {plan_rel_path(run_id)})")
    target = root / recorded
    if not safe_plan_path(recorded) or not target.is_file():
        return _warn(f"plan_path {recorded} names no file in the tree - {repair}")
    try:
        stub = parse_stub(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError: not UTF-8 (a UTF-16 file from a Windows shell); a crash would read RED
        return _warn(f"plan_path {recorded} is unreadable ({exc})")

    if not stub["goal"] or not stub["reason"]:
        return _warn(f"{recorded} lacks a 'Goal:' or 'Reason:' line - {repair}")
    return CheckResult(CHECK_NAME, True, "recorded")
