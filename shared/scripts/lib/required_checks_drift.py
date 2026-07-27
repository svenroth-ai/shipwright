"""Compare the must-pass check set configured at the host against reality.

Which checks must be green before merging is configured **outside** the
repository — in a GitHub ruleset or branch-protection rule. Nothing in the repo
can see that, so the two drift silently and in both directions:

- **unenforced** — a workflow declares a check, it runs on every PR, it reports
  a result, and it holds nothing up because nobody added it to the configured
  set. That is the card's whole complaint: *a check that runs, reports and gates
  nothing is worse than no check, because it reads as protection.*
- **phantom** — the configured set names a check the repo no longer produces
  (renamed job, deleted workflow). Nothing ever reports it, so the context stays
  `pending` and every PR blocks forever on a check that cannot exist.

Both are reported. `unenforced` is the quiet one and the reason this exists;
`phantom` is loud but arrives as a mystery, so naming it saves the debugging.

This module is pure — it compares two lists. Fetching the configured set needs
the host API (and admin scope), which is why the caller
(`tools/check_required_checks.py`) owns that and this does not.

FR-01.17 (E)6.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

# Contexts that are never expected in the configured set: they are reported by
# a third party or are informational, and requiring them is a deliberate choice
# rather than drift. Keeping this explicit stops the producer from nagging about
# checks the operator has decided not to gate on.
ADVISORY_CONTEXTS: frozenset[str] = frozenset()


def all_workflow_check_names(project_root: Path | str) -> list[str]:
    """Check names EVERY workflow in this repo produces, not just adopt's five.

    ``automerge_readiness.KNOWN_WORKFLOWS`` is deliberately the set
    ``/shipwright-adopt`` scaffolds into a target repo — it is the right scope
    for the AUTOMERGE_SETUP table and the wrong one here. Policing a repo's own
    configuration with it under-derives and reports honest checks as phantoms:
    run against this monorepo it missed `bloat-check.yml` and `pr-review-run.yml`
    and called both configured contexts non-existent. A wrong answer from a
    drift producer is worse than silence, so this enumerates the directory.
    """
    from lib.automerge_readiness import workflow_report  # local: avoids a cycle

    root = Path(project_root)
    names: list[str] = []
    wf_dir = root / ".github" / "workflows"
    for path in sorted(wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []:
        report = workflow_report(root, path.name)
        if not report or report.get("parse_error"):
            continue
        # A workflow that cannot fire on a pull request never reports a check, so
        # it cannot be "unenforced" — and REQUIRING it would block every PR
        # forever waiting on a result that never arrives (the dormant trap the
        # automerge guide warns about). `workflow_report` already decides this
        # and the first draft discarded it: run against this repo it called the
        # manual-only `grade-empirical.yml` drift. Over-derivation muted the
        # producer just as surely as the under-derivation it replaced.
        if report.get("dormant"):
            continue
        names.extend(report["checks"])
    return names


def compare_required_checks(
    derived: Iterable[str],
    configured: Iterable[str],
    *,
    advisory: Iterable[str] = (),
) -> dict:
    """Compare declared-in-repo check names against host-configured ones.

    ``derived`` — names the repo's workflows actually produce (from
    ``automerge_readiness.required_check_names``, which matrix-expands job names
    and knows that a `workflow_run` stage contributes a POSTED STATUS rather
    than a job name).

    ``configured`` — contexts the host will actually block on.

    Returns ``{in_sync, unenforced, phantom, derived, configured}`` with both
    lists sorted, so the output is stable enough to dedup a triage item on.
    """
    d = {str(x).strip() for x in derived if str(x).strip()}
    c = {str(x).strip() for x in configured if str(x).strip()}
    adv = {str(x).strip() for x in advisory if str(x).strip()} | ADVISORY_CONTEXTS

    unenforced = sorted(d - c - adv)
    phantom = sorted(c - d - adv)
    return {
        "in_sync": not unenforced and not phantom,
        "unenforced": unenforced,
        "phantom": phantom,
        "derived": sorted(d),
        "configured": sorted(c),
    }


def render_drift(result: dict, repo: str) -> str:
    """One human-readable paragraph per direction, for the triage detail."""
    parts: list[str] = []
    if result["unenforced"]:
        parts.append(
            "Runs but gates nothing on "
            + repo
            + " — these checks report a result on every pull request and hold "
            "nothing up, because they are not in the configured must-pass set: "
            + ", ".join(result["unenforced"])
            + ". Add them at Settings -> Rules, or decide deliberately that they "
            "are advisory."
        )
    if result["phantom"]:
        parts.append(
            "Configured but never reported on "
            + repo
            + " — the must-pass set names these, and no workflow produces them, "
            "so every pull request waits on a check that cannot arrive: "
            + ", ".join(result["phantom"])
            + ". Usually a renamed job or a deleted workflow."
        )
    return " ".join(parts) if parts else f"Required-check set on {repo} is in sync."


def dedup_key(result: dict, repo: str) -> str:
    """Stable key: the same divergence must not re-file every run."""
    return "|".join(
        [
            "required-checks-drift",
            repo,
            ",".join(result["unenforced"]),
            ",".join(result["phantom"]),
        ]
    )
