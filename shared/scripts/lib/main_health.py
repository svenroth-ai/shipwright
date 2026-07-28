"""Is `main` healthy, and if not — which commit broke it?

The pure core behind ``tools/main_health.py`` (iterate-2026-07-28-main-self-heal,
FR-01.19). Every input here is a payload and every "now" is a parameter: no
``gh``, no ``git``, no clock. The thin shell that calls those lives in the tool.

Three rules this module exists to keep:

1. **Only push-to-`main` runs speak for `main`.** One commit SHA carries both a
   pull-request run and a push run. Reading the newest run per SHA without the
   predicate lets a green PR run mask a red `main` run — and then "P green,
   C red ⇒ C is the first bad commit" is not merely unhelpful, it is confidently
   wrong.
2. **Unknown is never green.** A missing run, a cancelled run, an exhausted
   retrieval window: each is reported as itself. A health check that reads "I
   could not tell" as "healthy" is worse than none, because it is believed.
3. **Only the overlap class decides health.** A red security scan is a finding
   with its own machinery, not an overlap an agent should go and fix. It is
   reported — and it escalates — but it does not define whether `main` is red.
"""

from __future__ import annotations

from dataclasses import dataclass

# Attribution lives in its own module so both files stay inside the 300-LOC
# source budget; it is re-exported here so `lib.main_health` remains the one
# public surface callers and tests import. RELATIVE import on purpose — a bare
# `lib.` prefix resolves through whichever `lib` package won sys.path first
# (ADR-045), and this module is imported from tool code outside `lib/`.
from .main_health_attribution import (  # noqa: F401 — re-exported surface
    attribute,
    candidate_partners,
)

#: Conclusions that mean this run is satisfied. ``skipped``/``neutral`` count as
#: a pass for the same reason GitHub's required-checks do: a job that correctly
#: did not need to run has not failed.
PASS_CONCLUSIONS = frozenset({"success", "skipped", "neutral"})
#: Conclusions that mean this run will not go green on its own.
FAIL_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "startup_failure", "action_required"}
)
#: Statuses that mean the run has not finished yet.
RUNNING_STATUSES = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)


@dataclass(frozen=True)
class MonitoredWorkflow:
    """One workflow this repository watches on `main`.

    ``decides_health`` is the load-bearing field. Exactly the *overlap* class —
    lint and the test suites — answers "is `main` broken"; the rest are
    reported and escalate, so a slow CodeQL run or a long-standing scanner
    finding can never turn every iterate into a repair attempt for something it
    must not touch.
    """

    file: str
    name: str
    decides_health: bool


#: The policy, in code rather than inferred from a display name. A two-direction
#: invariant test (`shared/tests/test_main_attribution_workflows.py`) pins every
#: entry against the real `.github/workflows/*.yml`, because a policy that
#: drifts from the YAML would make ordinary commits look permanently incomplete.
MONITORED_WORKFLOWS: tuple[MonitoredWorkflow, ...] = (
    MonitoredWorkflow("ci.yml", "CI", True),
    MonitoredWorkflow("security.yml", "Security Scan", False),
    MonitoredWorkflow("codeql.yml", "CodeQL", False),
    MonitoredWorkflow("bloat-check.yml", "Bloat Check", False),
)

#: `unknown[]` reasons that make the whole answer untrustworthy rather than
#: merely annotating it. Anything listed here forces `status = "unknown"`, so a
#: caller keyed on the exit code cannot act on a result we already know is stale.
_LOAD_BEARING_UNKNOWNS = frozenset({"main_advanced_during_check"})

#: Commits walked backwards from the tip when attributing.
DEFAULT_COMMIT_WINDOW = 25
#: Attempts per (workflow, commit) the retrieval limit budgets for. Saturation
#: is still detected and reported — this only makes it rare.
_ATTEMPT_HEADROOM = 3


def run_limit_for(
    window: int, workflows: tuple[MonitoredWorkflow, ...] = MONITORED_WORKFLOWS
) -> int:
    """How many runs to retrieve for a commit window of ``window``.

    Derived, never fixed: a constant 100 against 25 commits x 4 workflows
    truncates silently, and the caller then attributes inside a partial set.
    """
    return max(1, window) * max(1, len(workflows)) * _ATTEMPT_HEADROOM


def _by_name(workflows: tuple[MonitoredWorkflow, ...]) -> dict[str, MonitoredWorkflow]:
    return {w.name: w for w in workflows}


def select_runs(
    runs: list[dict],
    *,
    default_branch: str = "main",
    workflows: tuple[MonitoredWorkflow, ...] = MONITORED_WORKFLOWS,
) -> dict[tuple[str, str], dict]:
    """The newest monitored push-to-`default_branch` run per (workflow, SHA).

    The four-part predicate is the whole point — see rule 1 in the module
    docstring. Ties on ``createdAt`` break towards the larger ``databaseId``,
    which is monotonic per repository.
    """
    known = _by_name(workflows)
    best: dict[tuple[str, str], dict] = {}
    for run in runs or []:
        name = run.get("workflowName")
        if name not in known:
            continue
        if (run.get("event") or "") != "push":
            continue
        if (run.get("headBranch") or "") != default_branch:
            continue
        sha = run.get("headSha") or ""
        if not sha:
            continue
        key = (name, sha)
        current = best.get(key)
        if current is None or _newer(run, current):
            best[key] = run
    return best


def _sort_key(run: dict) -> tuple[str, int]:
    """Recency of one run. `databaseId` is monotonic per repository, so it
    breaks a `createdAt` tie deterministically."""
    return (str(run.get("createdAt") or ""), int(run.get("databaseId") or 0))


def _newer(a: dict, b: dict) -> bool:
    return _sort_key(a) > _sort_key(b)


def run_state(run: dict) -> str:
    """``pass`` | ``fail`` | ``running`` | ``inconclusive`` for one run.

    ``cancelled`` is deliberately *inconclusive*: it is exactly the state the
    AC-1 concurrency fix stops producing on `main`, and reading it as a pass
    would resurrect the bug that fix removes.
    """
    status = (run.get("status") or "").lower()
    if status in RUNNING_STATUSES:
        return "running"
    conclusion = (run.get("conclusion") or "").lower()
    if conclusion in PASS_CONCLUSIONS:
        return "pass"
    if conclusion in FAIL_CONCLUSIONS:
        return "fail"
    return "inconclusive"


def commit_verdict(
    sha: str,
    selected: dict[tuple[str, str], dict],
    *,
    workflows: tuple[MonitoredWorkflow, ...] = MONITORED_WORKFLOWS,
) -> str:
    """``green`` | ``red`` | ``running`` | ``incomplete`` for one commit.

    Computed over the health-deciding workflows only. ``incomplete`` — no
    conclusive run — is never folded into ``green``.
    """
    states = []
    for wf in workflows:
        if not wf.decides_health:
            continue
        run = selected.get((wf.name, sha))
        states.append(run_state(run) if run else "missing")
    if not states:
        return "incomplete"
    if "fail" in states:
        return "red"
    if "running" in states:
        return "running"
    if all(s == "pass" for s in states):
        return "green"
    return "incomplete"


def classify(
    *,
    commits: list[dict],
    runs: list[dict],
    default_branch: str = "main",
    workflows: tuple[MonitoredWorkflow, ...] = MONITORED_WORKFLOWS,
    workflow_files_present: list[str] | None = None,
) -> dict:
    """Per-commit verdicts, the headline status, findings, and what we could
    not determine.

    ``commits`` is the first-parent series newest-first
    (``[{"sha", "subject"}, ...]``). ``workflow_files_present`` lets the caller
    hand in the repository's actual workflow filenames so a policy entry with no
    file behind it is *named* rather than silently producing permanent
    incompleteness.
    """
    selected = select_runs(runs, default_branch=default_branch, workflows=workflows)
    verdicts = {
        c["sha"]: commit_verdict(c["sha"], selected, workflows=workflows)
        for c in commits
    }
    unknown: list[dict] = []

    if not selected:
        unknown.append(
            {
                "source": "runs",
                "reason": "no monitored push-to-%s run was returned — cannot tell "
                "whether the branch is healthy" % default_branch,
            }
        )

    # "main advanced" means a run for a commit NEWER than the tip — not merely
    # one outside the walked window. `gh run list` reaches much further back
    # than `window` commits, so testing "sha not in the series" flagged every
    # ordinary older commit (caught by an empirical probe against the real
    # repository, where fixtures with two commits could not show it). Runs come
    # back newest-first, so it is the NEWEST selected run that answers the
    # question: if its commit is not in the series, a newer commit exists.
    known_shas = {c["sha"] for c in commits}
    newest = max(selected.values(), key=_sort_key, default=None)
    if newest is not None and (newest.get("headSha") or "") not in known_shas:
        unknown.append(
            {
                "source": "main_tip",
                "reason": "main_advanced_during_check",
                "detail": newest.get("headSha"),
            }
        )

    if workflow_files_present is not None:
        missing = [w.file for w in workflows if w.file not in workflow_files_present]
        if missing:
            unknown.append(
                {
                    "source": "workflow_policy",
                    "reason": "monitored workflow file(s) not present in the "
                    "repository: " + ", ".join(missing),
                }
            )

    tip_verdict = verdicts.get(commits[0]["sha"]) if commits else "incomplete"
    status = {"green": "green", "red": "red", "running": "running"}.get(
        tip_verdict or "", "unknown"
    )

    findings = []
    if commits:
        tip = commits[0]["sha"]
        for wf in workflows:
            if wf.decides_health:
                continue
            run = selected.get((wf.name, tip))
            findings.append(
                {
                    "workflow": wf.name,
                    "state": run_state(run) if run else "missing",
                    "url": (run or {}).get("url"),
                }
            )

    # A finding-class failure is NOT the ordinary green path. AC-6 requires a
    # card for it, and a caller that reads exit 0 will never look — so it gets
    # its own status rather than riding along in a field nobody is obliged to
    # read. Still distinct from `red`: it is a finding, never an overlap repair.
    if status == "green" and any(f["state"] == "fail" for f in findings):
        status = "escalate"

    # A DETECTED staleness must change the answer, not merely annotate it.
    # Reporting `main_advanced_during_check` and then returning green is the
    # exact "unknown read as healthy" failure this tool exists to prevent.
    if any(u["reason"] in _LOAD_BEARING_UNKNOWNS for u in unknown):
        status = "unknown"

    return {
        "status": status,
        "tip_sha": commits[0]["sha"] if commits else None,
        "verdicts": verdicts,
        "selected_runs": selected,
        "findings": findings,
        "unknown": unknown,
    }

