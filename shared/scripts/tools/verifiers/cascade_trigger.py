"""F11 gate: a small iterate with a risk flag or a diff > 100 lines answers for its code review.

The phase matrix says the code-review cascade runs at ``small`` when a risk
flag is set or the diff has more than 100 changed lines. Before this gate
nothing enforced that. ``code_review_floor`` starts at ``medium``, and the
review record only asked that every type be *answered*, so a free-text
``not_run`` passed.

When the trigger fires (inputs: :mod:`._cascade_trigger_inputs`) the ``code`` row
must be one of two things:

* ``completed`` with evidence, to the same bar as the medium+ floor
  (:func:`review_record_floor.carries_evidence`);
* ``not_run`` with a ``reason_code`` from :data:`ACCEPTED_CODES`, an allowlist
  inside the closed ``review_not_run`` vocabulary. Codes that say the trigger did
  not fire are refused because the measurement says otherwise; ``missing-keys``
  and ``config-disabled`` are refused because they describe the external leg,
  not the code-reviewer cascade. ``not_applicable`` is refused too: a fired
  trigger is exactly what makes the review applicable.

**Unknown is triggered, never quiet.** When the diff cannot be measured (no
trustworthy trunk base, a merge commit on the trunk) or a risk-flag source is
unreadable (corrupt plan, foreign ``risk_recheck.json``), the run is read as
triggered and the record decides. A reviewed run passes; an unanswered one fails
with a repair for the input as well as for the row.

The single exception is a git failure on the work tree itself (``git_error``):
it fails outright, because then even the risk detectors recomputed from the diff
cannot run, and "fix git" is the one repair that clears every input at once.

A campaign sub-iterate records ``delegated-to-orchestrator`` and passes. The
orchestrator's 3f-bis cascade later promotes the row.

Scope: everything the medium+ ``code_review_floor`` does not cover. The F5c
entry's complexity is raised to the session plan's when that plan is readable
and ranks higher. A missing or unrecognised complexity is IN scope, never a
skip. Trivial skips only when stated explicitly and not contradicted by the
plan. An entry that says medium+ skips, because the stricter floor already
requires a review that happened. A missing F5c entry or review record SKIPs
here, because ``check_review_record`` already fails it and one fault should give
one message.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402
from lib.reason_codes import reason_code_error  # noqa: E402
from lib.review_diff_threshold import DIFF_LOC_THRESHOLD, exceeds_diff_threshold  # noqa: E402
from lib.review_record import ReviewRecordError, entry_for, read_record  # noqa: E402

from ._cascade_trigger_inputs import measure_diff, read_plan, recorded_risk_flags  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git, git_context  # noqa: E402
from .review_record_floor import carries_evidence  # noqa: E402

CHECK_NAME = "code review at small (risk flag or diff > 100 lines)"

#: The only ``not_run`` codes a triggered ``code`` row may carry.
ACCEPTED_CODES = frozenset({"unavailable", "delegated-to-orchestrator", "user-opt-out"})

#: Why a vocabulary code outside :data:`ACCEPTED_CODES` does not answer a fired trigger.
_REFUSED_WHY = {
    "diff-below-threshold": "says the trigger did not fire, but it did",
    "complexity-below-threshold": "says the trigger did not fire, but it did",
    "trivial-auto": "says the trigger did not fire, but it did",
    "missing-keys": "describes the external review leg, not the code-reviewer cascade",
    "config-disabled": "describes the external review leg, not the code-reviewer cascade",
}

_TOOL = "shared/scripts/tools/record_review_pass.py"

_DIFF_REPAIR = ("To let F11 measure the diff instead, make the trunk branch resolvable: fetch the "
                "remote trunk (`git fetch origin <trunk>`), unshallow a shallow clone "
                "(`git fetch --unshallow`), or record the code review. ")
_FLAGS_UNRECORDED_REPAIR = ("Nothing is unreadable: the run never recorded its risk flags. Add `risk_flags: [...]` "
                            "(`[]` for none) to the F5c entry, or record the code review.")
_FLAGS_REPAIR = ("To clear the input instead, regenerate or remove the unreadable file named above "
                 "and re-run F11. ")

_RANK = {"trivial": 0, "small": 1, "medium": 2, "large": 3}


def _skip(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({detail})", severity=Severity.SKIPPED.value)


def _label(value: object) -> str:
    return str(value or "").strip().lower()


def _scope(project_root: Path, run_id: str, entry: dict) -> tuple[bool, str]:
    """``(in_scope, complexity label)`` from the F5c entry raised to the session plan's."""
    stated = _label(entry.get("complexity"))
    if stated in ("medium", "large"):
        return False, f"complexity={stated}; the medium+ code_review_floor enforces this"
    plan, err = read_plan(project_root, run_id)
    planned = _label(plan.get("complexity")) if plan else ""
    if stated == "trivial" and not err and (plan is None or planned == "trivial"):
        return False, "complexity=trivial; trivial runs no cascade"
    known = [c for c in (stated, planned) if c in _RANK]
    label = max(known, key=_RANK.__getitem__) if known else ""
    if not label or label == "trivial":
        label = "small"
    sources = f"entry {stated or 'missing'}, plan {planned or ('unreadable' if err else 'absent')}"
    return True, f"{label} ({sources})"


def _trigger(project_root: Path, run_id: str, commit_hash: str, entry: dict | None = None) -> tuple[str, str, str]:
    """``(state, detail, repair)``; state is ``fired``, ``quiet``, ``not_git`` or ``error``."""
    flags, err = recorded_risk_flags(project_root, run_id, entry)
    if err:
        repair = _FLAGS_UNRECORDED_REPAIR if "never recorded" in err else _FLAGS_REPAIR
        return "fired", f"risk flags unknown: {err}", repair
    flagged = f"risk flag(s) {', '.join(flags)}"
    ctx = git_context(project_root)
    if ctx == "not_git":
        return ("fired", flagged, "") if flags else ("not_git", "", "")
    if ctx != "work_tree":
        return "error", ("git could not answer whether this is a work tree, so the diff size is "
                         "unknown. Fix git first (a stale `.git/index.lock`, git missing from PATH, "
                         "a corrupt repository), then re-run F11"), ""
    commit = commit_hash
    if not commit:
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD", timeout=10.0)
        commit = out.strip() if rc == 0 else ""
    measure = measure_diff(project_root, commit, run_id) if commit else None
    if measure is None or measure.error:
        reason = measure.error if measure else "HEAD is unresolvable"
        reasons = [flagged] if flags else []
        return "fired", " and ".join(reasons + [f"diff size unknown: {reason}"]), _DIFF_REPAIR
    flags = sorted(set(flags) | set(measure.diff_flags()))
    reasons = [f"risk flag(s) {', '.join(flags)}"] if flags else []
    if exceeds_diff_threshold(measure.lines or 0):
        reasons.append(f"{measure.lines} changed lines > {DIFF_LOC_THRESHOLD}")
    if reasons:
        return "fired", " and ".join(reasons), ""
    return "quiet", f"no risk flag, {measure.lines} changed lines <= {DIFF_LOC_THRESHOLD}", ""


def _not_run_problem(status: str, code: object) -> str | None:
    """Why a ``not_run`` / ``not_applicable`` row does not answer a fired trigger, or ``None``."""
    if code is None:
        return "it has a free-text disposition and no `reason_code`"
    bad = reason_code_error("review_not_run", code)
    if bad is not None:
        return bad
    if status == "not_applicable":
        return "a fired trigger makes the review applicable; record it `not_run` with its code"
    if code in ACCEPTED_CODES:
        return None
    why = _REFUSED_WHY.get(str(code), "is not accepted for a triggered `code` row")
    return f"reason_code {code!r} {why} (accepted: {', '.join(sorted(ACCEPTED_CODES))})"


def check_cascade_trigger(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    project_root = Path(project_root)
    try:
        entry = find_entry_by_run_id(project_root, run_id)
    except (ValueError, OSError):
        entry = None
    if not isinstance(entry, dict):
        return _skip(f"no F5c entry for {run_id}; check_review_record reports that")
    in_scope, scope = _scope(project_root, run_id, entry)
    if not in_scope:
        return _skip(scope)

    state, why, repair = _trigger(project_root, run_id, commit_hash, entry)
    if state == "not_git":
        return _skip("not a git work tree and no risk flag recorded")
    if state == "quiet":
        return CheckResult(CHECK_NAME, True, f"not triggered: {why}")
    if state == "error":
        return CheckResult(CHECK_NAME, False, why)

    try:
        record = read_record(project_root, run_id)
    except ReviewRecordError:
        return _skip("the review record is unreadable; check_review_record reports that")
    if record is None:
        return _skip("no review record; check_review_record reports that")
    row = entry_for(record, "code")
    status = str(row.get("status", "")) or "unrecorded"
    if status == "completed":
        if carries_evidence(row):
            return CheckResult(CHECK_NAME, True, f"triggered ({why}); `code` completed")
        return CheckResult(
            CHECK_NAME, False,
            f"triggered ({why}); `code` is recorded completed but carries no evidence "
            f"(no findings, provider, excerpt or adapter). {repair}Re-record it: `{_TOOL} record "
            f"--run-id {run_id} --review-type code --status completed --from code-reviewer "
            "--payload-file <reply> --force`",
        )
    if status in ("not_run", "not_applicable"):
        code = row.get("reason_code")
        bad = _not_run_problem(status, code)
        if bad is None:
            return CheckResult(CHECK_NAME, True, f"triggered ({why}); `code` {status} ({code})")
        return CheckResult(
            CHECK_NAME, False,
            f"triggered ({why}); `code` is {status} but {bad}. {repair}Run the code-reviewer "
            f"cascade, or re-record the row with a closed code: `{_TOOL} record --run-id {run_id} "
            f"--review-type code --status not_run --reason-code <{'|'.join(sorted(ACCEPTED_CODES))}> "
            "--disposition \"<rule>\" --force`",
        )
    return CheckResult(CHECK_NAME, False,
                       f"triggered ({why}); `code` is {status}, so the code review is unanswered. "
                       f"{repair}Run the code-reviewer cascade and record it with `{_TOOL} record`")
