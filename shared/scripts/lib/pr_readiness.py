"""What state is this pull request in? (iterate-2026-07-31-f11-delivery-truth)

One reading of one ``gh pr view`` payload, shared by everything that asks a question
of it: the delivery watcher's terminal verdict, the ladder's decision to merge, and
the refresh trigger. Two views of one payload is exactly the drift PR #503 was about
— there, four gates each had their own answer to "what did this branch change" and
one of them was blind for eleven paths. ``failing_checks`` MOVED here out of
``tools/watch_pr_delivery.py`` for that reason; the watcher imports it.

The distinction that earns this module its existence: the watcher's ``pending``
conflated "checks still running" with "all green and nobody is ever going to merge
this", which is why an un-armable PR sat for the full 1800-second timeout. Readiness
names five states instead, and two of them — ``green`` and ``refresh_needed`` — are
things waiting will never resolve.

**Everything here fails towards "not ready".** Three deliberate choices, each of which
was the opposite way round in the first draft and each of which Stage 2 review caught
as a way to merge on no evidence:

* an **unrecognised** ``mergeStateStatus`` is ``pending``, never green. The clear
  states are whitelisted, because GitHub can add an enum member and a value we have
  never seen is not a value we have cleared.
* the "checks do not vanish" floor is a **name set**, not a count. Three checks
  reporting where three were seen before proves nothing if the base gained two
  workflows in between.
* a rollup that is empty because the host has not created its check runs yet is only
  accepted as "this host runs no checks" once a poll interval has actually passed.

Companions: ``lib/pr_delivery.py`` (what we may DO about the state),
``lib/pr_delivery_host.py`` (the outside world), ``lib/pr_self_merge.py`` (the
wait→refresh→verify→merge cycle).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

# --- check-rollup vocabulary --------------------------------------------------

#: CheckRun conclusions meaning "this will not go green on its own".
FAILING_CONCLUSIONS = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED"}
)
#: Legacy StatusContext states meaning failure.
FAILING_STATES = frozenset({"FAILURE", "ERROR"})
#: Legacy StatusContext states meaning "not finished".
PENDING_STATES = frozenset({"PENDING", "EXPECTED"})

# --- merge-state vocabulary ---------------------------------------------------

#: The ONLY states that mean "the host has nothing against merging this". A whitelist,
#: not a blacklist: ``readiness`` used to fall through to green for anything it did not
#: recognise, so a new or renamed ``MergeStateStatus`` member would have been read as
#: clear on no evidence — the one direction this module must never fail (Stage 2).
CLEAR_MERGE_STATES = frozenset({"CLEAN", "HAS_HOOKS", "UNSTABLE"})
#: States a refresh clears, and nothing else will. ``BEHIND`` is the obvious one;
#: ``DIRTY`` (conflicts) belongs here too, because the remedy is already wired into
#: this ladder — ``refresh_branch`` runs ``ensure_current``, i.e. the churn
#: regenerate-on-conflict resolver. Leaving DIRTY with the blocking states meant an
#: iterate that conflicted after another one merged spent 1800 seconds polling a state
#: one merge would have cleared (Stage 2).
REFRESHABLE_MERGE_STATES = frozenset({"BEHIND", "DIRTY"})
#: States where the host will not merge and waiting MIGHT still clear it — an
#: unresolved thread gets resolved, a required review arrives, a draft is marked ready.
BLOCKING_MERGE_STATES = frozenset({"BLOCKED", "DRAFT"})
#: Mergeability is computed asynchronously; until it lands the answer is "not yet".
UNCOMPUTED_MERGE_STATES = frozenset({"UNKNOWN", ""})


def _entries(rollup: Iterable | None) -> list[dict]:
    """The rollup's dict entries. A null or scalar entry is skipped rather than
    crashing the classifier — the sibling reader ``_pr_blocker_causes._reported``
    already guards this, and an ``AttributeError`` inside a verdict costs the verdict."""
    return [entry for entry in (rollup or []) if isinstance(entry, dict)]


def check_name(entry: Mapping) -> str:
    """One rollup entry's name, whichever kind it is."""
    if entry.get("__typename") == "StatusContext":
        return str(entry.get("context") or "?")
    return str(entry.get("name") or "?")


def failing_checks(rollup: list[dict] | None) -> list[dict]:
    """The red entries of ``statusCheckRollup`` as ``{name, url}``.

    SKIPPED / NEUTRAL / SUCCESS / still-running are NOT failures — a
    ``needs:``-skipped required job is a pass (B4.5).
    """
    failed: list[dict] = []
    for check in _entries(rollup):
        if check.get("__typename") == "StatusContext":
            if (check.get("state") or "").upper() in FAILING_STATES:
                failed.append({"name": check_name(check),
                               "url": check.get("targetUrl", "")})
        else:  # CheckRun, or an unknown typename treated as one
            if (check.get("conclusion") or "").upper() in FAILING_CONCLUSIONS:
                failed.append({"name": check_name(check),
                               "url": check.get("detailsUrl", "")})
    return failed


def pending_checks(rollup: list[dict] | None) -> list[str]:
    """Names of entries that have not reported a result yet."""
    waiting: list[str] = []
    for check in _entries(rollup):
        if check.get("__typename") == "StatusContext":
            if (check.get("state") or "").upper() in PENDING_STATES:
                waiting.append(check_name(check))
        else:
            if (check.get("status") or "").upper() != "COMPLETED":
                waiting.append(check_name(check))
    return waiting


def reported_names(rollup: list[dict] | None) -> set[str]:
    """Names present in this rollup at all, reported or not."""
    return {check_name(entry) for entry in _entries(rollup)}


def passing_checks(rollup: list[dict] | None) -> list[str]:
    """Names that actually SUCCEEDED — not merely "not red".

    SKIPPED and NEUTRAL are treated as passes for the merge decision (a ``needs:``-skipped
    required job is a pass, B4.5) but they are not EVIDENCE, and the delivery summary
    promises "how many checks the host actually ran". Counting rollup entries let an
    all-skipped rollup report "the host ran 3 check(s)" while the host had confirmed
    nothing — the exact sentence FR-01.11's criterion exists to make impossible (Stage 3).
    """
    passed: list[str] = []
    for check in _entries(rollup):
        if check.get("__typename") == "StatusContext":
            if (check.get("state") or "").upper() == "SUCCESS":
                passed.append(check_name(check))
        elif (check.get("conclusion") or "").upper() == "SUCCESS":
            passed.append(check_name(check))
    return passed


def readiness(pr: Mapping, *, seen_names: Iterable[str] = (),
              settled: bool = True) -> dict:
    """Is this PR ready to be merged **here**, right now?

    ``seen_names`` are the checks observed on EARLIER polls. Straight after a refresh
    push the new head's rollup can be empty — or partially registered — and either
    would read as "everything that exists has passed". Holding until every previously
    seen name reports again is what makes "checks do not vanish" true; the count-based
    version it replaces could be satisfied by three checks reporting where the base had
    meanwhile grown two more (Stage 2, HIGH).

    ``settled`` is ``False`` on the very first poll of a wait. A rollup that is empty
    because the host has not created its check runs yet is indistinguishable from a host
    that runs none, and mergeability flips to CLEAN faster than Actions creates runs — so
    "no checks at all" is only believed once a poll interval has passed.

    Returns ``{"state": "failed"|"blocked"|"pending"|"refresh_needed"|"green",
    "checks_observed": int, "reason": str}``. ``green`` and ``refresh_needed`` are the
    two states waiting cannot resolve, so callers must act on both.
    """
    rollup = _entries(pr.get("statusCheckRollup"))
    merge_state = (pr.get("mergeStateStatus") or "").upper()
    observed = len(rollup)

    passed = passing_checks(rollup)

    def answer(state: str, reason: str) -> dict:
        return {"state": state, "checks_observed": observed,
                "checks_passed": len(passed), "reason": reason}

    failed = failing_checks(rollup)
    if failed:
        return answer("failed", "red: " + ", ".join(f["name"] for f in failed))
    if merge_state in BLOCKING_MERGE_STATES:
        return answer("blocked", f"the host will not merge while the state is {merge_state}")
    if merge_state in UNCOMPUTED_MERGE_STATES:
        return answer("pending", "the host has not finished computing mergeability")
    if merge_state not in CLEAR_MERGE_STATES and merge_state not in REFRESHABLE_MERGE_STATES:
        # Never fall through to green on a state we do not recognise.
        return answer("pending", f"unrecognised merge state {merge_state} — not treating "
                                 "an unknown answer as a clear one")
    waiting = pending_checks(rollup)
    if waiting:
        return answer("pending", "still running: " + ", ".join(waiting))
    missing = sorted(set(seen_names) - reported_names(rollup))
    if missing:
        return answer("pending", "checks seen earlier have not reported on this head: "
                                 + ", ".join(missing) + " — checks do not vanish")
    if not observed and not settled:
        return answer("pending", "no checks have registered yet — waiting one interval "
                                 "before believing this host runs none")
    if merge_state in REFRESHABLE_MERGE_STATES:
        return answer("refresh_needed", f"the branch is {merge_state.lower()} "
                                        "and only a refresh clears that")
    return answer("green", f"every check that exists has passed "
                           f"({len(passed)} succeeded of {observed} observed)")


__all__ = [
    "BLOCKING_MERGE_STATES",
    "CLEAR_MERGE_STATES",
    "FAILING_CONCLUSIONS",
    "FAILING_STATES",
    "PENDING_STATES",
    "REFRESHABLE_MERGE_STATES",
    "UNCOMPUTED_MERGE_STATES",
    "check_name",
    "failing_checks",
    "passing_checks",
    "pending_checks",
    "readiness",
    "reported_names",
]
