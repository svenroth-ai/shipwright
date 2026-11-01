"""F11 claim check: an iterate that changed observable behaviour recorded the AC it promises (a warning, never a hold).

Whether anything observable changed is COMPUTED from the branch diff (:mod:`lib.ac_surface`) - never read from a
label or an agent's say-so - and applies to every intent, bug fixes included. The decision table, the wording rule
and the freeze compare live in :mod:`lib.ac_decision` / :mod:`lib.ac_record`; this module finds the run's event and
the diff and reports.

* No event for the run, a non-iterate source, or a branch that cannot be seen: SKIPPED.
* The diff changes nothing observable (docs, tests, comments, whitespace, renames): passes, no record needed.
* The diff is observable and there is no record, only an exemption, a restore naming an AC that is not in the
  catalog, a frozen text that differs from the catalog text in the diff, or a record that was superseded: WARNING.
* Malformed record, stub or decision data never crashes the check and never turns F11 red: it is a WARNING.

Advisory and strict-exempt, like the other iterate-local claims: the recorded event cannot be rewritten by the F5b
repair path, and nothing holds a PR on this check. Structure only: whether the sentence is true is for the reviewers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_decision import count_decisions, load_catalog  # noqa: E402
from lib.ac_record import changed_catalog, freeze_differences, read_records  # noqa: E402
from lib.ac_surface import git_changes, observable_files  # noqa: E402

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _branch_base_commit  # noqa: E402

CHECK_NAME = "pre-build AC recorded (observable change)"
_REPAIR = ("write the declaration with tools/ac_decision.py (the exact AC text, or the id of the AC a fix restores), "
           "then tools/write_plan_stub.py --ac-decision")


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def _problems(root: Path, run_id: str, files: list[str], base: str, commit: str) -> list[str]:
    records = read_records(root, run_id)
    if not records:
        return [f"the diff changes observable behaviour ({', '.join(files[:4])}) but no AC record exists - {_REPAIR}"]
    last = records[-1]
    items = last.get("items") if isinstance(last.get("items"), list) else []
    if not items or not all(isinstance(i, dict) for i in items):
        return ["the AC record carries no readable items"]
    out: list[str] = []
    if all(i.get("kind") == "exempt" for i in items):
        out.append(f"recorded as no observable change, but the diff changes observable behaviour ({', '.join(files[:4])}) - name the AC it restores, or add one")
    catalog = load_catalog(root)["acs"]
    out += [f"restores {i.get('restores_ac')}, which is not in the catalog - that is a catalog gap, so add the AC"
            for i in items if i.get("kind") == "restore" and i.get("restores_ac") not in catalog]
    specs = [f for f in git_changes(root, base, commit) if f.startswith(".shipwright/planning/") and f.endswith("/spec.md")]
    changed, removed = changed_catalog(root, base, commit, specs)
    out += [f"the frozen AC differs from the catalog - {d}" for d in freeze_differences(items, changed, removed)]
    if len(records) > 1:
        out.append(f"the AC record was superseded {len(records) - 1} time(s); first frozen: {records[0].get('items')!r}; now: {items!r}")
    decisions = last.get("decisions")
    if not isinstance(decisions, list) or count_decisions(decisions)["total"] != len(items):
        out.append("the AC record has no usable decisions (one {ac, mode, answer, kind} per item)")
    return out


def check_pre_build_ac_recorded(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    try:
        event = _work_event(root, run_id)
        if event is None:
            return _skip(f"no work_completed event for {run_id}")
        if event.get("source") != "iterate":
            return _skip(f"source={event.get('source') or 'unknown'}")
        base = _branch_base_commit(root, commit_hash) if commit_hash else None
        if not base:
            return _skip("branch not visible")
        surface = observable_files(git_changes(root, base, commit_hash))
        if not surface["observable"]:
            return CheckResult(CHECK_NAME, True, f"no observable change (computed from the diff; {surface['ignored']} file(s) ignored)")
        problems = _problems(root, run_id, surface["files"], base, commit_hash)
    except Exception as exc:  # noqa: BLE001 - malformed record data must never turn F11 red
        return _warn(f"the AC record could not be checked ({type(exc).__name__}: {exc})")
    return _warn("; ".join(problems)) if problems else CheckResult(CHECK_NAME, True, "recorded")
