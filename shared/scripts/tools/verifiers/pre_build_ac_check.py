"""F11 claim check: a feature/change iterate recorded its AC (or exemption, or restore) BEFORE the build (a warning, never a hold).

The decision, the table and the frozen-hash rule live in :mod:`lib.ac_decision`. This module finds the run's
``work_completed`` event and its plan stub, and reports.

* No event for the run, a non-iterate source, or an intent other than feature/change: SKIPPED (a bug fix is
  not asked for a new promise here).
* No plan stub, or a stub with no ``AC frozen:`` record: an advisory WARNING.
* A record whose text no longer matches its frozen hash, an item that is unreadable, an exemption whose reason is
  only a label, or a restore naming an AC that is not in the catalog: the same WARNING.

Advisory and strict-exempt, like the other iterate-local claims: the recorded event cannot be rewritten by the F5b
repair path, and nothing holds a PR on this check. Structure only: whether the sentence is true is for the reviewers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_decision import label_only, load_catalog_acs, parse_stub_ac  # noqa: E402
from lib.spec_chain import plan_rel_path, safe_plan_path  # noqa: E402

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402

CHECK_NAME = "pre-build AC recorded (feature/change iterate)"
_INTENTS = ("feature", "change")
_REPAIR = ("write the declaration with tools/ac_decision.py (the exact AC text, an exemption by outcome, or the AC id a "
           "restore restores), then tools/write_plan_stub.py --ac-decision")


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def check_pre_build_ac_recorded(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    event = _work_event(root, run_id)
    if event is None:
        return _skip(f"no work_completed event for {run_id}")
    intent = str(event.get("intent") or "").strip().lower()
    if event.get("source") != "iterate" or intent not in _INTENTS:
        return _skip(f"source={event.get('source') or 'unknown'}, intent={intent or 'unknown'}")
    recorded = event.get("plan_path")
    rel = recorded if isinstance(recorded, str) and recorded.strip() else plan_rel_path(run_id)
    target = root / rel
    if not safe_plan_path(rel) or not target.is_file():
        return _warn(f"no plan stub to hold the pre-build AC ({rel}) - {_REPAIR}")
    try:
        ac = parse_stub_ac(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _warn(f"{rel} is unreadable ({exc})")
    if not ac["frozen"] or not ac["items"]:
        return _warn(f"{rel} carries no 'AC frozen:' record - {_REPAIR}")
    if not ac["hash_ok"]:
        return _warn(f"the AC text in {rel} no longer matches its frozen hash (edited after the freeze, or unreadable) - re-run the decision and say why the text moved")
    if len(ac["decisions"]) != len(ac["items"]) or not all(isinstance(d, dict) and d.get("mode") in ("auto", "asked") and d.get("ac") for d in ac["decisions"]):
        return _warn(f"{rel} has no usable 'AC decisions:' line (one {{ac, mode: auto|asked, answer}} per item) - {_REPAIR}")
    catalog = load_catalog_acs(root)
    for item in ac["items"]:
        if item.get("kind") == "exempt" and label_only(item.get("exempt_reason")):
            return _warn(f"an exemption in {rel} gives a label, not an outcome - say what stays the same for users and operators")
        if item.get("kind") == "restore" and item.get("restores_ac") not in catalog:
            return _warn(f"{rel} restores {item.get('restores_ac')}, which is not in the catalog - that is a catalog gap, so add the AC")
    return CheckResult(CHECK_NAME, True, "recorded")
