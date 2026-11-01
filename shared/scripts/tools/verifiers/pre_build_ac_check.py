"""F11 claim check: an iterate that changed observable behaviour recorded the AC it promises (a warning, never a hold).

Whether anything observable changed is COMPUTED from the branch diff (:mod:`lib.ac_surface`) - never read from a
label or an agent's say-so - and applies to every intent, bug fixes included. The decision table, the wording rule
and the freeze compare live in :mod:`lib.ac_decision` / :mod:`lib.ac_record`; this module finds the run's event and
the diff and reports.

* No event for the run, a non-iterate source, or a branch that cannot be seen: SKIPPED.
* The diff changes nothing observable and edits no catalog AC: passes, no record needed.
* Observable and no record, only an exemption, a restore naming an AC that is not in the base catalog or that
  no test in the diff mentions, a frozen text that differs from the catalog text in the diff, wording that no
  longer reads as an outcome against the committed diff, a catalog AC edited or removed that no item names, a
  superseded record, an asked decision not answered through the signed operator channel (``answered_via`` is
  self-reported), a record that is not append-only or was committed after the first code, or an ``unchanged``
  item whose files do not match the diff or whose AC no test names: WARNING.
* A catalog with text but no FR heading the parser can read: SKIPPED. A stacked unit uses its own fork point
  (the event's ``stack_base_ref``), not the trunk's.
  The pre-build exemption is only a claim (the diff was empty then); this check is where it is tested.
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

from lib.ac_catalog import load_catalog  # noqa: E402
from lib.ac_record import verify  # noqa: E402
from lib.ac_surface import merge_base  # noqa: E402

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _branch_base_commit  # noqa: E402

CHECK_NAME = "pre-build AC recorded (observable change)"


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


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
        fork = event.get("stack_base_ref")  # a stacked campaign unit: its own fork point, so it does not inherit earlier units' edits
        if isinstance(fork, str) and fork.strip():
            try:
                base = merge_base(root, fork.strip(), commit_hash)
            except RuntimeError:
                pass  # the stack base is not visible here: the trunk fork point stays
        catalog = load_catalog(root, base)
        if catalog["unparsed"]:
            return _skip("the requirement catalog has text but no FR heading this check can read")
        problems = verify(root, run_id, base, commit_hash, catalog)
    except Exception as exc:  # noqa: BLE001 - malformed record data must never turn F11 red
        return _warn(f"the AC record could not be checked ({type(exc).__name__}: {exc})")
    return _warn("; ".join(problems)) if problems else CheckResult(CHECK_NAME, True, "recorded, or no observable change and no catalog edit (computed from the diff)")
