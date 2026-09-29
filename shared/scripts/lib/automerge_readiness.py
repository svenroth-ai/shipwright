"""Render the per-repo AUTOMERGE_SETUP.md doc /shipwright-adopt scaffolds.

A freshly adopted repo carries dormant `ci.yml` / `security.yml` / `codeql.yml`
workflows plus an active `claude-review.yml`. To turn on B4.5-style automerge,
the adopter must require the *exact* GitHub check names or branch protection
waits forever. This module derives them from **deployed** workflow files
(matrix-expanded), rather than guessing.

Self-contained on purpose: this module imports only stdlib + PyYAML and holds
its own ``KNOWN_WORKFLOWS`` list (relative paths under `.github/workflows/`),
so the adopt scaffolder can load it via ``spec_from_file_location`` without the
``lib`` package-name collision (ADR-045). ``KNOWN_WORKFLOWS`` is drift-pinned to
the per-workflow convention modules' path constants by
``shared/tests/test_automerge_readiness.py``.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path

import yaml

# Template + deployed-doc paths.
AUTOMERGE_SETUP_TEMPLATE_PATH = "shared/templates/AUTOMERGE_SETUP.md.template"
AUTOMERGE_SETUP_OUTPUT_PATH = "AUTOMERGE_SETUP.md"

# Workflow files (relative to `.github/workflows/`) the doc inspects, in display
# order. Drift-pinned to ci_workflow / security_workflow / codeql_workflow
# WORKFLOW_PATH constants by the convention test (kept literal here so this
# module stays loadable via spec_from_file_location without sibling imports).
KNOWN_WORKFLOWS: tuple[str, ...] = (
    "ci.yml",
    "security.yml",
    "codeql.yml",
    "claude-review.yml",
    "claude-review-run.yml",
)

# Workflows whose Required-Check is a commit status POSTED by a job, not a job
# check name (two-stage review, FR-01.17). Job names here would name a check
# branch protection can never match, and the `pull_request`-trigger test would
# call stage 2 dormant when it works as designed. Scopes: its drift test.
POSTED_STATUS_CONTEXTS: dict[str, str] = {
    "claude-review-run.yml": "Claude Code Review",   # adopted repos
    "pr-review-run.yml": "PR Review",                # this monorepo + the webui
}

# Placeholders the template carries.
PROFILE_PLACEHOLDER = "{PROFILE}"
TABLE_PLACEHOLDER = "{REQUIRED_CHECKS_TABLE}"

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib/scripts/shared/<root>


def _matrix_ref(key: str) -> re.Pattern[str]:
    """Regex matching a `${{ matrix.<key> }}` interpolation (whitespace-tolerant)."""
    return re.compile(r"\$\{\{\s*matrix\." + re.escape(key) + r"\s*\}\}")


def _matrix_dims(job: dict) -> dict[str, list]:
    """Return the list-valued matrix dimensions of a job.

    Skips GitHub's `include`/`exclude` matrix-extension keys (they are
    list-of-mappings, not expansion dimensions) and any non-list / empty entry
    — only list-valued dimension keys multiply into check instances.
    """
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    if not isinstance(matrix, dict):
        return {}
    return {
        k: v
        for k, v in matrix.items()
        if k not in ("include", "exclude") and isinstance(v, list) and v
    }


def _job_check_names(job_id: str, job: dict) -> list[str]:
    """Return the GitHub check names a single job produces.

    Mirrors GitHub's display rules:
    - No matrix: the check name is `name:` if set, else the job id.
    - Matrix + `name:` that references EVERY matrix dimension: the rendered
      name per combo (e.g. `Analyze (${{ matrix.language }})` -> `Analyze (python)`).
    - Matrix + a `name:` that references only some (or none) of the dimensions,
      or no `name:`: GitHub appends the full combo tuple, so we emit
      `<rendered-or-jobid> (<combo values joined by ", ">)` per combo. This both
      matches GitHub and keeps multi-dim names unique (no collisions).
    """
    name = job.get("name")
    name = name if isinstance(name, str) and name else None
    dims = _matrix_dims(job)
    if not dims:
        return [name or str(job_id)]
    keys = list(dims)
    out: list[str] = []
    for combo in itertools.product(*(dims[k] for k in keys)):
        mapping = dict(zip(keys, combo))
        combo_label = ", ".join(str(v) for v in combo)
        if name is None:
            out.append(f"{job_id} ({combo_label})")
            continue
        rendered = name
        referenced: set[str] = set()
        for key, val in mapping.items():
            new = _matrix_ref(key).sub(str(val), rendered)
            if new != rendered:
                referenced.add(key)
            rendered = new
        if referenced == set(keys):
            out.append(rendered)  # fully parametrized name — GitHub shows it as-is
        else:
            out.append(f"{rendered} ({combo_label})")
    return out


def _expand_jobs(parsed: dict) -> list[tuple[str, str | None]]:
    """Return matrix-expanded ``(check_name, if_condition)`` pairs.

    A skipped job reports Success but does not gate work; callers distinguish
    job-level conditions (including YAML booleans) from unconditional jobs.
    """
    jobs = parsed.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []
    out: list[tuple[str, str | None]] = []
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        cond = job.get("if")
        if cond is True:
            cond = None  # YAML `if: true` always runs
        elif cond is not None and not isinstance(cond, str):
            cond = str(cond).lower()
        cond = cond if isinstance(cond, str) and cond.strip() else None
        for check in _job_check_names(str(job_id), job):
            out.append((check, cond))
    return out


def expand_check_names(parsed: dict) -> list[str]:
    """Return every job check name, including `if:`-gated ones."""
    return [name for name, _cond in _expand_jobs(parsed)]


def _is_dormant(parsed: dict) -> bool:
    """True when no `pull_request` trigger can report checks on a PR."""
    # PyYAML quirk: bare `on:` parses as Python literal True (YAML 1.1 truthy).
    triggers = parsed.get("on") or parsed.get(True)
    if isinstance(triggers, (dict, list)):
        return "pull_request" not in triggers
    return triggers != "pull_request"


def workflow_report(project_root: Path, workflow_rel: str) -> dict | None:
    """Inspect a workflow; None if absent, parse_error on invalid YAML.

    ``checks`` are unconditional names; ``conditional`` holds name/if pairs.
    ``pr_trigger`` is the `pull_request` filter mapping (None when bare).
    """
    path = Path(project_root) / ".github" / "workflows" / workflow_rel
    if not path.exists():
        return None
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        parsed = None
    if not isinstance(parsed, dict):
        return {
            "workflow": workflow_rel,
            "checks": [],
            "conditional": [],
            "dormant": None,
            "parse_error": True,
        }
    triggers = parsed.get("on") or parsed.get(True)
    posted = POSTED_STATUS_CONTEXTS.get(workflow_rel)
    if posted is not None:
        # The gate is the posted status, not the jobs that post it.
        return {
            "workflow": workflow_rel,
            "checks": [posted],
            "conditional": [],
            "dormant": False,
            "parse_error": False,
        }
    expanded = _expand_jobs(parsed)
    pr_trigger = triggers.get("pull_request") if isinstance(triggers, dict) else None
    return {
        "workflow": workflow_rel,
        "checks": [name for name, cond in expanded if cond is None],
        "conditional": [(name, cond) for name, cond in expanded if cond is not None],
        "pr_trigger": pr_trigger,
        "dormant": _is_dormant(parsed),
        "parse_error": False,
    }


def gather_required_checks(project_root: Path) -> list[dict]:
    """Reports for every KNOWN_WORKFLOWS file present in the repo, in order."""
    reports: list[dict] = []
    for wf in KNOWN_WORKFLOWS:
        report = workflow_report(Path(project_root), wf)
        if report is not None:
            reports.append(report)
    return reports


def required_check_names(project_root: Path) -> list[str]:
    """Flat list of every UNCONDITIONAL Required-Check name across all present
    workflows (excludes `if:`-gated jobs — those are surfaced separately)."""
    names: list[str] = []
    for report in gather_required_checks(project_root):
        names.extend(report["checks"])
    return names


def render_checks_table(reports: list[dict]) -> str:
    """Render the reports as a markdown table (+ a conditional-jobs warning)."""
    header = (
        "| Workflow | Required-Check name(s) | Trigger | "
        "Before adding as a Required Check |\n"
        "|---|---|---|---|\n"
    )
    if not reports:
        return header + (
            "| _(no Shipwright workflows found in `.github/workflows/`)_ "
            "| — | — | — |\n"
        )
    rows: list[str] = []
    conditional_lines: list[str] = []
    for r in reports:
        wf = f"`.github/workflows/{r['workflow']}`"
        if r.get("parse_error"):
            rows.append(
                f"| {wf} | _(could not parse — open the file and read the job "
                f"names)_ | ? | Inspect manually |"
            )
            continue
        if r["checks"]:
            names = "<br>".join(f"`{c}`" for c in r["checks"])
            if r["dormant"]:
                trigger = "dormant"
                action = (
                    "Uncomment the `pull_request:` trigger **first** — a check "
                    "that never reports blocks every PR"
                )
            else:
                trigger = "active"
                action = "Already fires on PRs"
            rows.append(f"| {wf} | {names} | {trigger} | {action} |")
        for name, cond in r.get("conditional", []):
            conditional_lines.append(f"- `{name}` ({r['workflow']}) — `if: {cond}`")

    table = header + "\n".join(rows) + "\n"
    if conditional_lines:
        table += (
            "\n> **Conditional jobs — do NOT require unless they run on your "
            "PRs.** A skipped job reports a successful check, so requiring it "
            "does not gate any work. A job gated on "
            "`github.event_name == 'pull_request'` runs on PRs and is safe to "
            "require; a deploy job gated on `refs/heads/main` does **not** run "
            "on a feature-branch PR — never require it.\n>\n"
            + "\n".join(f"> {line}" for line in conditional_lines)
            + "\n"
        )
    return table


def render_automerge_setup(project_root: Path, profile: str | None) -> str:
    """Render the AUTOMERGE_SETUP.md content for an adopted repo.

    Reads the template, substitutes the profile name and the
    derived-from-deployed-workflows Required-Check table.
    """
    template = (_REPO_ROOT / AUTOMERGE_SETUP_TEMPLATE_PATH).read_text(
        encoding="utf-8"
    )
    table = render_checks_table(gather_required_checks(project_root))
    profile_label = (profile or "").strip() or "(unknown — detect from CLAUDE.md)"
    return template.replace(PROFILE_PLACEHOLDER, profile_label).replace(
        TABLE_PLACEHOLDER, table
    )
