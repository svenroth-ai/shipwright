"""Phase-runner RESULT CONTRACT for the single-session pipeline (SS1 scaffold).

The contract (reconciled-target foundation #3): a phase-runner subagent that
runs ONE phase skill returns ONE compact structured result and writes its real
outputs to DISK — never into the result. The orchestrator reloads pipeline
state from ``shipwright_run_config.json`` + these compact summaries, NEVER from
full phase transcripts (context budget).

The result dict IS the ``result`` payload passed verbatim to
``phase_task_lifecycle.complete_phase_task``: exactly ONE result shape flows
through the ONE existing completion path. ``complete_phase_task`` reads ``ok``
to branch done/failed and stores the whole dict in ``phase_tasks[].result``
(the v2 schema already types ``result`` as "includes ok flag and artifacts
list").

Shape::

    {
      "ok": bool,            # required — completion branch (done | failed)
      "phase": str,          # required — one of VALID_PHASES (cross-check)
      "summary": str,        # required — compact, <= MAX_SUMMARY_CHARS
      "artifacts": [str],    # required — repo-relative paths persisted to disk
      "splitId": str | None, # optional — build/plan fan-out unit
      "reason": str,         # required WHEN ok is False (failure reason)
      "metrics": {...},      # optional — small structured extras
      "review_status": {...},# optional — review-cascade state (see below)
      "waiting": {...},      # optional — the phase waits for an outside event (below)
    }

``waiting`` (U5) says the phase is NOT done and NOT failed: it waits for something outside
the run — ``{"reason": "waiting_for_merge", "pr_url": "https://..."}``. Such a result is
``ok: false`` (so an applier that does not know ``waiting`` strict-stops instead of
completing the phase and running deploy) and carries the usual ``reason``. The loop holds
the task, answers ``waiting`` with the link, and dispatches the SAME task again on resume —
so a phase that reports waiting must check the outside state itself when re-run, and report
``waiting`` again or ``ok``, never repeat its outward work. Only ``WAITING_REASONS`` exist.

``review_status`` is backward-compatible (absent = phase prescribes no cascade,
or an older runner): ``{"state": <REVIEW_STATES>, "reason_code": str,
"passes": {name: str}}``. ``reason_code`` is required for ``partial`` /
``deferred`` / ``skipped`` so a skipped or deferred cascade is visible to the
master instead of vanishing. ``reason_code`` is free-form on purpose (the
run plugin does not import the shared review vocabulary).

This module VALIDATES the shape; it neither runs a phase nor touches
run_config. ``VALID_PHASES`` is a literal kept in lockstep with the schema
``Phase`` enum by ``test_single_session_result_contract`` (both-direction
drift guard).
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

# Compact-summary ceiling — the context-budget guard. A phase-runner that needs
# more than this to report is leaking transcript into the result; the real
# output belongs on disk (in ``artifacts``), summarised here.
MAX_SUMMARY_CHARS = 2000

REVIEW_STATES = ("completed", "partial", "deferred", "skipped", "not_applicable")
_REVIEW_STATES_NEEDING_REASON = ("partial", "deferred", "skipped")

REQUIRED_RESULT_KEYS = ("ok", "phase", "summary", "artifacts")

# The outside events a phase may wait for (closed set — not a general pause mechanism).
WAITING_REASONS = ("waiting_for_merge",)
# The phases allowed to report each reason: the release phase is the only producer (U6).
WAITING_PHASES = {"waiting_for_merge": ("changelog",)}
# A plain https link with a host name, at most 508 characters, URL characters only: no
# space, control or escape character reaches a terminal or a card. Mirrored literally in
# hooks/master_stop_check.py.
PR_URL_RE = re.compile(r"(?=.{9,508}$)https://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*(?::[0-9]{1,5})?"
                       r"(?:[/?#][A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?")

# Mirror of shared/schemas/run_config.v2.schema.json $defs.Phase.enum. Kept as a
# literal (no runtime import coupling); drift is caught by the contract test.
VALID_PHASES = (
    "project",
    "design",
    "plan",
    "build",
    "test",
    "security",
    "changelog",
    "deploy",
)


class ResultContractError(ValueError):
    """Raised by ``build_phase_runner_result`` on an invalid result."""


def _is_relative_repo_path(p: Any) -> bool:
    """True iff ``p`` is a non-empty, relative, non-traversing repo path.

    Artifacts are persisted repo-relative (reloadable from any surface), so an
    absolute path, a drive-qualified path, or a ``..`` escape is rejected.
    """
    if not isinstance(p, str) or not p.strip():
        return False
    if PurePosixPath(p).is_absolute() or PureWindowsPath(p).is_absolute():
        return False
    parts = p.replace("\\", "/").split("/")
    return ".." not in parts


def validate_phase_runner_result(result: Any) -> list[str]:
    """Return a list of human-readable errors; empty list means valid.

    Non-raising so the orchestrator can record the errors on a malformed
    subagent return without crashing the loop.
    """
    errors: list[str] = []
    if not isinstance(result, dict):
        return [f"result must be a dict, got {type(result).__name__}"]

    for key in REQUIRED_RESULT_KEYS:
        if key not in result:
            errors.append(f"missing required key: {key!r}")

    ok = result.get("ok")
    if "ok" in result and not isinstance(ok, bool):
        errors.append("'ok' must be a bool")

    phase = result.get("phase")
    if "phase" in result and phase not in VALID_PHASES:
        errors.append(f"'phase' must be one of {VALID_PHASES}, got {phase!r}")

    summary = result.get("summary")
    if "summary" in result:
        if not isinstance(summary, str) or not summary.strip():
            errors.append("'summary' must be a non-empty str")
        elif len(summary) > MAX_SUMMARY_CHARS:
            errors.append(
                f"'summary' exceeds MAX_SUMMARY_CHARS ({len(summary)} > "
                f"{MAX_SUMMARY_CHARS}); persist detail to an artifact, not the result"
            )

    artifacts = result.get("artifacts")
    if "artifacts" in result:
        if not isinstance(artifacts, list):
            errors.append("'artifacts' must be a list of repo-relative paths")
        else:
            for i, a in enumerate(artifacts):
                if not _is_relative_repo_path(a):
                    errors.append(
                        f"artifacts[{i}] must be a non-empty relative repo path "
                        f"(no absolute/drive/'..'), got {a!r}"
                    )

    # A failure result must carry a reason — complete_phase_task forwards it to
    # mark_phase_failed as the recorded error.
    if isinstance(ok, bool) and ok is False:
        reason = result.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append("a failure result (ok=False) must carry a non-empty 'reason'")

    if "splitId" in result and not (result["splitId"] is None or isinstance(result["splitId"], str)):
        errors.append("'splitId' must be a str or None")
    if "reason" in result and not isinstance(result["reason"], str):
        errors.append("'reason' must be a str")
    if "metrics" in result and not isinstance(result["metrics"], dict):
        errors.append("'metrics' must be a dict")

    if "review_status" in result:
        errors.extend(_validate_review_status(result["review_status"]))

    if "waiting" in result:
        errors.extend(_validate_waiting(result["waiting"], ok, phase))
    elif result.get("reason") in WAITING_REASONS:
        errors.append(f"reason {result['reason']!r} needs the 'waiting' block "
                      "(else the phase would be counted failed)")

    return errors


def _validate_waiting(waiting: Any, ok: Any, phase: Any) -> list[str]:
    if not isinstance(waiting, dict):
        return ["'waiting' must be a dict"]
    errors: list[str] = []
    if ok is not False:
        errors.append("a waiting result must be ok=False (the phase is not done)")
    if waiting.get("reason") not in WAITING_REASONS:
        errors.append(f"'waiting.reason' must be one of {WAITING_REASONS}, "
                      f"got {waiting.get('reason')!r}")
    elif phase not in WAITING_PHASES[waiting["reason"]]:
        errors.append(f"only the {WAITING_PHASES[waiting['reason']]} phase may report "
                      f"{waiting['reason']!r}, not {phase!r}")
    url = waiting.get("pr_url")
    if not (isinstance(url, str) and PR_URL_RE.fullmatch(url)):
        errors.append("'waiting.pr_url' must be a plain https:// link "
                      "with a host name (URL characters only, at most 508)")
    return errors


def _validate_review_status(rs: Any) -> list[str]:
    if not isinstance(rs, dict):
        return ["'review_status' must be a dict"]
    errors: list[str] = []
    state = rs.get("state")
    if state not in REVIEW_STATES:
        errors.append(f"'review_status.state' must be one of {REVIEW_STATES}, got {state!r}")
    reason = rs.get("reason_code")
    if "reason_code" in rs and (not isinstance(reason, str) or not reason.strip()):
        errors.append("'review_status.reason_code' must be a non-empty str")
    elif state in _REVIEW_STATES_NEEDING_REASON and "reason_code" not in rs:
        errors.append(f"'review_status' with state {state!r} must carry a 'reason_code'")
    passes = rs.get("passes")
    if "passes" in rs and not (
        isinstance(passes, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in passes.items())
    ):
        errors.append("'review_status.passes' must map pass name (str) to status (str)")
    return errors


def is_valid_result(result: Any) -> bool:
    """True iff ``result`` satisfies the phase-runner contract."""
    return not validate_phase_runner_result(result)


def build_phase_runner_result(
    *,
    ok: bool,
    phase: str,
    summary: str,
    artifacts: list[str],
    reason: str | None = None,
    split_id: str | None = None,
    metrics: dict[str, Any] | None = None,
    review_status: dict[str, Any] | None = None,
    waiting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a validated phase-runner result.

    Raises :class:`ResultContractError` if the assembled result is invalid —
    the summary is NEVER silently truncated (that would hide the very context
    loss the ceiling exists to prevent). Optional keys are omitted when None so
    the stored result stays compact.
    """
    result: dict[str, Any] = {
        "ok": ok,
        "phase": phase,
        "summary": summary,
        "artifacts": list(artifacts),
    }
    if split_id is not None:
        result["splitId"] = split_id
    if reason is not None:
        result["reason"] = reason
    if metrics is not None:
        result["metrics"] = metrics
    if review_status is not None:
        result["review_status"] = review_status
    if waiting is not None:
        result["waiting"] = waiting

    errors = validate_phase_runner_result(result)
    if errors:
        raise ResultContractError("; ".join(errors))
    return result
