"""F11 claim check: a runtime-touching iterate declares ``affected_acs`` (presence only).

The rule, the field shape and the "presence, never content" stance live in
:mod:`lib.affected_acs_gate`. This module only finds the run's ``work_completed``
event and the paths its branch changed, and reports.

* No event for the run, or an intent outside feature/change/bug: SKIPPED.
* The branch cannot be seen (``None`` from the git view) and the event lists no
  ``changed_files``: SKIPPED as blind, never read as clean.
* Runtime paths touched and the declaration absent: FAIL, naming both repairs.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.affected_acs_gate import declaration_present, requires_declaration  # noqa: E402
from lib.events_log import resolve_events_path  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402
from lib.spec_impact_gate import SPEC_IMPACT_INTENTS  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _iterate_changed_paths, git_context  # noqa: E402

CHECK_NAME = "affected_acs declared (runtime-touching iterate)"

_REPAIR = (
    "add affected_acs (AC ids changed, implemented, or checked-and-unchanged, each with one line why "
    "the promise holds) to the F5b event extras, or catalog_gap: true with catalog_gap_fr (the nearest FR)"
)


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def _work_event(project_root: Path, run_id: str) -> dict | None:
    path = resolve_events_path(project_root)
    if not run_id or not path.exists():
        return None
    try:
        records = read_jsonl_records(path).records
    except OSError:
        return None
    found = None
    for evt in records:
        if evt.get("type") == "work_completed" and evt.get("adr_id") == run_id:
            found = evt  # append-only log: the last match is the live one
    return found


def check_affected_acs_declared(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    event = _work_event(root, run_id)
    if event is None:
        return _skip(f"no work_completed event for {run_id}")
    if event.get("source") != "iterate":
        return _skip(f"source={event.get('source') or 'unknown'}, not an iterate event")
    if str(event.get("intent") or "").strip().lower() not in SPEC_IMPACT_INTENTS:
        return _skip(f"intent={event.get('intent') or 'unknown'}")
    if declaration_present(event):
        return CheckResult(CHECK_NAME, True, "declared")

    # Two views of "what changed": the branch (git) and the paths the event lists. Either one showing a
    # runtime path is enough; an EMPTY git view is not proof of "clean" while the event lists paths.
    views: list[list] = []
    if git_context(root) == "work_tree":
        git_paths = _iterate_changed_paths(root, str(event.get("commit") or "") or commit_hash)
        if git_paths is not None:
            views.append(git_paths)
    if isinstance(event.get("changed_files"), list):
        views.append(event["changed_files"])
    if not views:
        return _skip("BLIND: no readable branch view and no changed_files on the event")
    if not any(requires_declaration(event, view) for view in views):
        return _skip("no runtime path touched; nothing to declare")
    return CheckResult(CHECK_NAME, False, f"this iterate touched runtime paths but its event has no affected_acs - {_REPAIR}")
