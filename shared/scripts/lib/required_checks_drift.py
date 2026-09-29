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

import json
import re
from pathlib import Path
from typing import Iterable

# Contexts that are never expected in the configured set: they are reported by
# a third party or are informational, and requiring them is a deliberate choice
# rather than drift. Keeping this explicit stops the producer from nagging about
# checks the operator has decided not to gate on.
ADVISORY_CONTEXTS: frozenset[str] = frozenset()

# Where a consumer repo records its own "deliberately not required" decision:
# a top-level list of check names in the run config every Shipwright project has.
ADVISORY_CONFIG_FILE = "shipwright_run_config.json"
ADVISORY_CONFIG_KEY = "required_checks_advisory"


def load_advisory_checks(project_root: Path | str) -> list[str]:
    """Check names the repo's operator declared advisory (run-config key).

    Missing file, missing key, or a malformed value yields ``[]``: an unreadable
    declaration must never suppress a finding, so the producer keeps reporting.
    """
    try:
        data = json.loads((Path(project_root) / ADVISORY_CONFIG_FILE).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    value = data.get(ADVISORY_CONFIG_KEY) if isinstance(data, dict) else None
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


_PR_DEFAULT_TYPES = {"opened", "synchronize", "reopened"}
_GLOB_CHARS = set("*?[]!+")


def _job_runs_on_pr(condition: str) -> bool:
    """True only for a job `if:` provably true on a pull_request run.

    Deliberately tiny: `github.event_name ==/!= '<literal>'` and literal
    true. Anything else is unknown and stays possible-only.
    """
    expr = condition.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2].strip()
    if expr == "true":
        return True
    match = re.fullmatch(r"github\.event_name\s*(==|!=)\s*(['\"])([\w-]+)\2", expr)
    if not match:
        return False
    is_pr = match.group(3).casefold() == "pull_request"
    return is_pr if match.group(1) == "==" else not is_pr


def _pr_trigger_unfiltered(trigger: object, branch: str | None) -> bool:
    """True when the `pull_request` trigger provably fires for every PR into
    ``branch``. No glob matching: a glob, path filter or partial `types` list
    is not proved, so the workflow stays possible-only.
    """
    if trigger is None:
        return True
    if not isinstance(trigger, dict) or "paths" in trigger or "paths-ignore" in trigger:
        return False
    types = trigger.get("types")
    if types is not None and not (
        isinstance(types, list) and _PR_DEFAULT_TYPES <= {str(t).casefold() for t in types}
    ):
        return False
    include, ignore = trigger.get("branches"), trigger.get("branches-ignore")
    if include is None and ignore is None:
        return True
    patterns = include if ignore is None else ignore if include is None else None
    if branch is None or not isinstance(patterns, list) or not all(
        isinstance(p, str) and not (_GLOB_CHARS & set(p)) for p in patterns
    ):
        return False
    return (branch in patterns) if include is not None else (branch not in patterns)


def workflow_check_sets(
    project_root: Path | str, *, branch: str | None = None
) -> tuple[list[str], list[str]]:
    """Return ``(possible, candidates)`` check names for pull requests.

    ``possible`` — every check a non-dormant workflow can report, including
    job-`if:`-gated ones (GitHub reports a skipped job as Success): it
    disproves a phantom. ``candidates`` — checks that run on every PR into
    ``branch``: the only ones that can be called unenforced. Posted statuses
    (`POSTED_STATUS_CONTEXTS`) are candidates unproved: whether the stage-2
    script really posts the status is not analysed.
    """
    from lib.automerge_readiness import workflow_report  # local: avoids a cycle

    root = Path(project_root)
    possible: list[str] = []
    candidates: list[str] = []
    wf_dir = root / ".github" / "workflows"
    for path in sorted(wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []:
        report = workflow_report(root, path.name)
        # A workflow that cannot fire on a pull request never reports a check, so
        # it can be neither "unenforced" nor a reason to call a name real.
        if not report or report.get("parse_error") or report.get("dormant"):
            continue
        possible.extend(report["checks"])
        possible.extend(name for name, _cond in report["conditional"])
        if "pr_trigger" in report and not _pr_trigger_unfiltered(report["pr_trigger"], branch):
            continue
        candidates.extend(report["checks"])
        candidates.extend(name for name, cond in report["conditional"] if _job_runs_on_pr(cond))
    return possible, candidates


def all_workflow_check_names(project_root: Path | str) -> list[str]:
    """Every check name this repo can produce on PRs (the ``possible`` set)."""
    return workflow_check_sets(project_root)[0]


def compare_required_checks(
    derived: Iterable[str],
    configured: Iterable[str],
    *,
    advisory: Iterable[str] = (),
    unenforced_candidates: Iterable[str] | None = None,
) -> dict:
    """Compare possible PR checks with the host's must-pass contexts.

    ``derived`` includes conditional jobs even when skipped (their check reports
    Success); ``unenforced_candidates`` limits the opposite direction to
    checks provably run on every PR (defaults to ``derived`` for
    one-set callers). Job names are matrix-expanded; posted statuses use their
    actual context names.
    """
    d = {str(x).strip() for x in derived if str(x).strip()}
    c = {str(x).strip() for x in configured if str(x).strip()}
    # A declared-advisory name only silences "unenforced". It must NOT silence a
    # phantom: an in-repo list can go stale, and a name that is both declared
    # advisory and configured-but-never-produced blocks every PR.
    declared = {str(x).strip() for x in advisory if str(x).strip()}
    candidates = d if unenforced_candidates is None else {
        str(x).strip() for x in unenforced_candidates if str(x).strip()
    }

    unenforced = sorted(candidates - c - declared - ADVISORY_CONTEXTS)
    phantom = sorted(c - d - ADVISORY_CONTEXTS)
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
            "are advisory (list them under `required_checks_advisory` in "
            "shipwright_run_config.json)."
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
