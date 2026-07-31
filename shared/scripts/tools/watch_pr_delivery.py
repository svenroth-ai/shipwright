#!/usr/bin/env python3
"""Watch a PR to DELIVERY — the F11 anti-"shoot-and-forget" gate
(iterate-2026-06-12-delivery-watch; memory `feedback_no_shoot_and_forget`).

"Delivered" = the PR is actually MERGED with all Required Checks GREEN. Arming
auto-merge is NOT delivery: a check can fail afterward and the PR sits BLOCKED.
This polls ``gh pr view --json state,mergeStateStatus,statusCheckRollup`` until a
terminal state and reports it, so F11 never declares "done" on an armed-but-red PR.

Pure core: :func:`classify_delivery` (testable, no gh) maps a payload to one of
``merged`` / ``checks_failed`` / ``closed`` / ``pending``. :func:`watch` is the thin
gh+sleep shell. Host-specific (gh) by nature — PR delivery IS a GitHub fact; the
iterate's host-agnostic *correctness* guarantees are unaffected.

Exit codes: 0 merged · 2 checks_failed · 3 closed · 4 pending-timeout · 5 gh-error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.pr_blockers import probe as _probe_blockers  # noqa: E402
from lib.pr_readiness import failing_checks as _failing_checks  # noqa: E402
from lib.pr_readiness import readiness as _readiness  # noqa: E402
from lib.pr_readiness import passing_checks as _passing_checks  # noqa: E402
from lib.pr_readiness import reported_names as _reported_names  # noqa: E402

#: ``headRefOid``/``headRefName`` are fetched for the delivery ladder's pinned
#: merge (iterate-2026-07-31-f11-delivery-truth): merging must be conditional on
#: the exact commit F11 verified, so the driver needs the head this poll observed.
_GH_FIELDS = "state,mergeStateStatus,statusCheckRollup,url,baseRefName,headRefOid,headRefName"

#: A host read must not outlive the operator's patience (matches lib/pr_blockers).
_GH_TIMEOUT_SECONDS = 60.0

#: owner / name / number out of the PR url the payload already carries — so
#: naming a blocker costs no extra call just to resolve which repo this is.
_PR_URL_RE = re.compile(r"github\.com/(?P<owner>[^/]+)/(?P<name>[^/]+)/pull/(?P<number>\d+)")


def classify_delivery(pr: dict, *, ready_is_terminal: bool = False,
                      seen_names=(), settled: bool = True) -> dict:
    """Map a ``gh pr view`` payload to a terminal-or-pending verdict.

    Returns ``{"status": "merged"|"closed"|"checks_failed"|"ready"|"pending", ...}``.
    ``checks_failed`` carries ``failed`` (a list of ``{name, url}``). A PR that is
    OPEN with no red checks is ``pending`` (still running, or merge blocked for a
    non-check reason like behind/required-review) — keep watching, never "done".

    ``ready_is_terminal`` is what the delivery ladder adds
    (iterate-2026-07-31-f11-delivery-truth). Where nothing on the host is going to
    merge this PR — auto-merge could not be armed at all — "open, all green,
    mergeable" is not something to keep waiting on, it is the moment to act. It
    stays OFF by default so every existing caller's verdicts, messages and exit
    codes are unchanged; ``test_watch_pr_delivery`` asserts that over a payload
    matrix rather than trusting the default. ``readiness`` lives in
    ``lib.pr_readiness`` beside ``failing_checks`` so the watcher and the driver
    cannot drift on one payload. ``refresh_needed`` is terminal for the same reason
    ``ready`` is — see the comment below.
    """
    state = (pr.get("state") or "").upper()
    if state == "MERGED":
        return {"status": "merged"}
    if state == "CLOSED":
        return {"status": "closed"}
    failed = _failing_checks(pr.get("statusCheckRollup") or [])
    if failed:
        return {"status": "checks_failed", "failed": failed}
    if ready_is_terminal:
        ready = _readiness(pr, seen_names=seen_names, settled=settled)
        # `refresh_needed` is terminal for the SAME reason `ready` is: nothing the
        # watcher can do will clear it. Returning `pending` here would poll a BEHIND
        # branch to the 1800s timeout — reintroducing, one state over, exactly the
        # "waiting for something that will never happen" defect this ladder removes.
        if ready["state"] in ("green", "refresh_needed"):
            status = "ready" if ready["state"] == "green" else "refresh_needed"
            return {"status": status, "readiness": ready}
        return {"status": "pending", "readiness": ready}
    return {"status": "pending"}


def _gh_pr_json(pr: str, repo: str | None) -> dict:
    """Fetch the PR payload via gh. Raises RuntimeError on ANY failure to read it.

    One exception type out: a missing `gh` is an OSError, a hang a TimeoutExpired, a zero
    exit with blank stdout a JSONDecodeError — all three escaped the ladder's handlers as
    a traceback instead of exit 5 (Stage 2). The timeout matters most: the poll loop
    consults its clock only AFTER fetch returns.
    """
    cmd = ["gh", "pr", "view", pr, "--json", _GH_FIELDS]
    if repo:
        cmd += ["--repo", repo]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              timeout=_GH_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not run gh: {type(exc).__name__}: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "gh pr view failed").strip()[:300])
    if not (proc.stdout or "").strip():
        raise RuntimeError("gh pr view returned no output")
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError(f"gh pr view returned unreadable JSON: {exc}") from exc


def _name_blockers(payload: dict, probe) -> dict:
    """The named reasons an OPEN, not-failing PR is not merging.

    Never raises: a diagnostic that can crash the watcher would cost the verdict
    it was meant to explain, so every failure becomes an explicit ``unknown``
    source rather than an exception or a clean-looking empty answer.
    """
    merge_state = str(payload.get("mergeStateStatus") or "")
    try:
        m = _PR_URL_RE.search(str(payload.get("url") or ""))
        if not m:
            raise ValueError("PR url not parseable")
        return probe(
            owner=m.group("owner"), name=m.group("name"), number=int(m.group("number")),
            branch=str(payload.get("baseRefName") or ""),
            merge_state=merge_state, rollup=payload.get("statusCheckRollup") or [],
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        return {
            "merge_state_status": merge_state,
            "blocking": merge_state.upper() == "BLOCKED",
            "causes": [],
            "unknown": [{"source": "probe", "reason": f"blocker probe failed: {type(exc).__name__}"}],
        }


def watch(
    pr: str,
    *,
    repo: str | None = None,
    timeout_seconds: float = 1800.0,
    poll_seconds: float = 30.0,
    once: bool = False,
    ready_is_terminal: bool = False,
    seen_names=(),
    fetch=_gh_pr_json,
    sleep=time.sleep,
    now=time.monotonic,
    probe_blockers=_probe_blockers,
) -> dict:
    """Poll until a terminal verdict (merged/closed/checks_failed) or timeout.

    Returns the classify_delivery result. A **pending** verdict — which used to say only
    how long it had waited — is augmented with ``blockers``: the named reasons the PR is
    not merging (unresolved review threads, required checks that never reported, the
    host's own BLOCKED verdict). Terminal verdicts are returned exactly as before; they
    already name their cause, so the probe is not run for them.

    The probe runs once, on the way out, rather than per poll: a 30-minute watch costs
    two extra API calls, not sixty. ``ready_is_terminal`` adds the delivery ladder's two
    act-now verdicts; ``seen_names`` seeds the "checks do not vanish" set — see below.

    ``fetch``/``sleep``/``now``/``probe_blockers`` are injectable for tests."""
    deadline = now() + timeout_seconds
    # The NAMES reported on this PR, accumulated across polls — the history lives in the
    # loop, the only place that has it. A count was not enough: three checks reporting
    # where three were seen before proves nothing if the base gained two workflows in
    # between, and a freshly pushed head's rollup starts empty (Stage 2, HIGH).
    seen: set[str] = set(seen_names)
    polls = 0
    while True:
        payload = fetch(pr, repo)
        # `settled` is False on the very first poll: an empty rollup because Actions has
        # not created the runs yet is indistinguishable from a host that runs none, and
        # mergeability flips to CLEAN faster than runs appear.
        verdict = classify_delivery(
            payload, ready_is_terminal=ready_is_terminal, seen_names=seen,
            settled=polls > 0,
        )
        seen |= _reported_names(payload.get("statusCheckRollup"))
        polls += 1
        if verdict["status"] != "pending":
            if ready_is_terminal:
                verdict["head_oid"] = payload.get("headRefOid") or ""
                verdict["seen_names"] = sorted(seen)
                verdict["checks_observed"] = len(seen)
                verdict["checks_passed"] = len(
                    _passing_checks(payload.get("statusCheckRollup")))
            return verdict
        timed_out = not once and now() >= deadline
        if once or timed_out:
            if timed_out:
                verdict["timed_out"] = True
            verdict["blockers"] = _name_blockers(payload, probe_blockers)
            if ready_is_terminal:
                # A wait that observed checks must not report zero just because it ended
                # pending (Stage 3).
                verdict["seen_names"] = sorted(seen)
                verdict["checks_observed"] = len(seen)
            return verdict
        sleep(poll_seconds)


def _exit_code(status: str) -> int:
    # `ready` / `refresh_needed` are explicitly NOT 0: the PR is mergeable, not
    # merged, and only `merged` is delivery. Mapped here rather than left to the
    # `.get` default so a future CLI exposure cannot quietly turn either into "done".
    return {"merged": 0, "checks_failed": 2, "closed": 3,
            "ready": 4, "refresh_needed": 4, "pending": 4}.get(status, 4)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Watch a PR to delivery (merged + green)")
    p.add_argument("--pr", required=True, help="PR number or URL")
    p.add_argument("--repo", default=None, help="owner/name (default: cwd's repo)")
    p.add_argument("--timeout-seconds", type=float, default=1800.0)
    p.add_argument("--poll-seconds", type=float, default=30.0)
    p.add_argument("--once", action="store_true", help="single poll, no loop")
    args = p.parse_args(argv)

    try:
        result = watch(
            args.pr, repo=args.repo,
            timeout_seconds=args.timeout_seconds, poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except RuntimeError as exc:
        print(json.dumps({"status": "gh_error", "error": str(exc)}, indent=2))
        return 5
    print(json.dumps(result, indent=2))
    if result["status"] == "checks_failed":
        print(
            "NOT DELIVERED — Required Check(s) failed: "
            + ", ".join(f"{f['name']} ({f['url']})" for f in result["failed"]),
            file=sys.stderr,
        )
    elif result["status"] == "pending":
        print(_render_pending(result), file=sys.stderr)
    return _exit_code(result["status"])


def _render_blocker(cause: dict) -> str:
    """One cause, in words.

    Matched on ``kind``, never on which keys happen to be present: an
    ``unresolved_review_threads`` cause carries BOTH ``count`` and ``detail``, so
    a `"detail" in cause` test rendered it as a raw Python list of untrusted
    GitHub file paths instead of its count (caught by external review).
    """
    kind = cause.get("kind", "?")
    if kind == "merge_state":  # our own wording, safe to print verbatim
        return f"{kind} ({cause.get('state', '?')}): {cause.get('detail', '')}"
    if "checks" in cause:
        return f"{kind}: {', '.join(cause['checks'])}"
    if "count" in cause:
        return f"{kind}: {cause['count']}"
    return kind


def _render_pending(result: dict) -> str:
    """Say WHY it is still pending, not just that it is.

    The whole point of the change: an operator reading this line should learn the
    cause. When a source could not be read we say so — an unreadable source is
    not the same answer as a clean one."""
    blockers = result.get("blockers") or {}
    head = "NOT DELIVERED (timed out) — " if result.get("timed_out") else "NOT MERGED YET — "
    causes = blockers.get("causes") or []
    unknown = blockers.get("unknown") or []
    parts: list[str] = []
    # Report the state OBSERVED, never a fixed phrase: `blocking` is true for
    # several states now (BLOCKED, DIRTY, DRAFT), and the old wording announced
    # "BLOCKED" for all of them — including a PR that merely had conflicts.
    if blockers.get("merge_state_status"):
        parts.append(f"merge state {blockers['merge_state_status']}")
    if causes:
        lead = "blocked by " if blockers.get("blocking") else "possible cause(s): "
        parts.append(lead + "; ".join(_render_blocker(c) for c in causes))
    if unknown:
        parts.append(
            "could not check " + ", ".join(f"{u['source']} ({u['reason']})" for u in unknown)
        )
    if not causes and not unknown:
        # Keyed on causes, NOT on `parts`: the observed merge state is always
        # reported, so a `not parts` test would never fire and the operator would
        # lose the one line that says "nothing is wrong, it is just queued".
        parts.append(
            "no blocker found — every required check reported and no review thread "
            "is unresolved; the PR is most likely still queued"
        )
    return head + "; ".join(parts)


if __name__ == "__main__":
    raise SystemExit(main())
