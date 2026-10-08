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
* ``not_run`` with a ``reason_code`` from the closed ``review_not_run``
  vocabulary. A code that claims the trigger did not fire
  (``diff-below-threshold``, ``complexity-below-threshold``, ``trivial-auto``)
  is refused, because the measurement says otherwise. ``not_applicable`` is
  refused too: a fired trigger is exactly what makes the review applicable.

A campaign sub-iterate records ``delegated-to-orchestrator`` and passes. The
orchestrator's 3f-bis cascade later promotes the row.

Scope: ``small`` only. Trivial runs no cascade. At medium+ the stricter
``code_review_floor`` already requires a review that happened. A missing F5c
entry or review record SKIPs here, because ``check_review_record`` already
fails it and one fault should give one message.
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

from ._cascade_trigger_inputs import measure_diff, recorded_risk_flags  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git, git_context  # noqa: E402
from .review_record_floor import carries_evidence  # noqa: E402

CHECK_NAME = "code review at small (risk flag or diff > 100 lines)"

#: Codes that say the trigger did not fire. Contradicted by a fired trigger.
CONTRADICTED_CODES = frozenset({"diff-below-threshold", "complexity-below-threshold", "trivial-auto"})

_TOOL = "shared/scripts/tools/record_review_pass.py"


def _skip(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({detail})", severity=Severity.SKIPPED.value)


def _trigger(project_root: Path, run_id: str, commit_hash: str) -> tuple[str, str]:
    """``(state, detail)``: ``fired`` (detail says why), ``quiet``, ``not_git`` or ``error``."""
    flags, err = recorded_risk_flags(project_root, run_id)
    if err:
        return "error", err
    flagged = f"risk flag(s) {', '.join(flags)}"
    ctx = git_context(project_root)
    if ctx == "not_git":
        return ("fired", flagged) if flags else ("not_git", "")
    if ctx != "work_tree":
        return "error", "git could not answer whether this is a work tree; the diff size is unknown"
    commit = commit_hash
    if not commit:
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD", timeout=10.0)
        commit = out.strip() if rc == 0 else ""
    measure = measure_diff(project_root, commit) if commit else None
    if measure is None or measure.error:
        if flags:
            return "fired", flagged
        reason = measure.error if measure else "HEAD is unresolvable"
        return "error", (f"cannot measure the diff ({reason}); refusing to certify it as "
                         f"<= {DIFF_LOC_THRESHOLD} changed lines")
    flags = sorted(set(flags) | set(measure.diff_flags()))
    reasons = [f"risk flag(s) {', '.join(flags)}"] if flags else []
    if exceeds_diff_threshold(measure.lines or 0):
        reasons.append(f"{measure.lines} changed lines > {DIFF_LOC_THRESHOLD}")
    if reasons:
        return "fired", " and ".join(reasons)
    return "quiet", f"no risk flag, {measure.lines} changed lines <= {DIFF_LOC_THRESHOLD}"


def check_cascade_trigger(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    project_root = Path(project_root)
    try:
        entry = find_entry_by_run_id(project_root, run_id)
    except (ValueError, OSError):
        entry = None
    if not isinstance(entry, dict):
        return _skip(f"no F5c entry for {run_id}; check_review_record reports that")
    complexity = str(entry.get("complexity", "")).lower()
    if complexity != "small":
        return _skip(f"complexity={complexity or 'unknown'}; this gate applies at small only")

    state, why = _trigger(project_root, run_id, commit_hash)
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
            f"(no findings, provider, excerpt or adapter). Re-record it: `{_TOOL} record "
            f"--run-id {run_id} --review-type code --status completed --from code-reviewer "
            "--payload-file <reply> --force`",
        )
    if status in ("not_run", "not_applicable"):
        code = row.get("reason_code")
        bad = reason_code_error("review_not_run", code) if code is not None else (
            "it has a free-text disposition and no `reason_code`")
        if bad is None and status == "not_applicable":
            bad = "a fired trigger makes the review applicable; record it `not_run` with its code"
        if bad is None and code in CONTRADICTED_CODES:
            bad = f"reason_code {code!r} says the trigger did not fire, but it did"
        if bad is None:
            return CheckResult(CHECK_NAME, True, f"triggered ({why}); `code` {status} ({code})")
        return CheckResult(
            CHECK_NAME, False,
            f"triggered ({why}); `code` is {status} but {bad}. Run the code-reviewer cascade, "
            f"or re-record the row with a closed code: `{_TOOL} record --run-id {run_id} "
            f"--review-type code --status not_run --reason-code <unavailable|delegated-to-orchestrator|"
            "user-opt-out> --disposition \"<rule>\" --force`",
        )
    return CheckResult(CHECK_NAME, False,
                       f"triggered ({why}); `code` is {status}, so the code review is unanswered")
