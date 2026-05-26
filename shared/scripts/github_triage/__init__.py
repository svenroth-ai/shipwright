"""GitHub findings -> triage inbox importer.

**Action-unit model** (iterate-2026-05-20-triage-launch-surface, supersedes
the per-finding mapping shipped in iterate-2026-05-19): GitHub findings
collapse into a tiny number of operator-actionable items rather than one
triage item per upstream finding. GitHub itself is the per-finding store —
this importer's job is to emit "there is work here, here is how to start
it", not to mirror that database.

- code-scanning + Dependabot  -> ``gh-security:{owner}/{repo}`` (one unit
  per repo; ``launchPayload`` starts with ``/shipwright-security``).
- secret-scanning             -> ``gh-secrets:{owner}/{repo}`` (one unit
  per repo; ``launchPayload`` is a whitelist-only rotation checklist —
  no slash command, no alert content, secret rotation is manual).
- failed default-branch CI    -> ``gh-ci:{workflow_id}`` (one unit per
  failing workflow; dedup key drops the ``head_sha`` so the payload is
  stable across reruns and links to the workflow PAGE URL, not a single
  run).

Dedup keys remain stable and namespaced; ``match_commit=False`` +
``window_seconds=None`` so a finding stays exactly one open inbox item
until it clears.

Auto-resolve mirrors ADR-052: a stale open item whose key left the current
finding set is dismissed with ``reason="githubResolved"`` — scoped strictly
to the three owned key prefixes, and ONLY for sources whose fetch actually
succeeded.

**Legacy migration** (one-shot): if a project's ``triage.jsonl`` predates
the action-unit iterate it carries per-finding items with prefixes
``github:code-scanning:`` / ``github:dependabot:`` /
``github:secret-scanning:`` / ``github-ci:{wf}:{sha}``. The first
successful per-source fetch dismisses the corresponding open legacy items
with ``reason="schemaMigration"`` — gated PER ORIGINAL SOURCE.

**Package layout** (sub-iterate B6, 2026-05-26):

- ``state.py``    — throttle state read/write (`is_due`, `read/write_last_import`,
                    `throttle_hours`, `DEFAULT_THROTTLE_HOURS`).
- ``severity.py`` — severity vocab + per-feed extractors (`triage_severity`).
- ``producer.py`` — security action-unit mappers + owned prefix constants.
- ``mappers.py``  — secrets + CI action-unit mappers + `latest_failed_ci_runs`.
- ``resolve.py``  — auto-resolve + legacy-migration sweeps.
- ``consumer.py`` — `import_findings` orchestrator (the side-effectful entry).

See sibling ``github_api`` for the `gh` client and the throttled
SessionStart entry point ``hooks/import_github_findings.py``.
"""

from __future__ import annotations

# Public surface — preserved exactly across the B6 split. Every name here
# was reachable as ``github_triage.<name>`` before the split and remains so.

from .consumer import import_findings
from .mappers import ci_action_unit, latest_failed_ci_runs, secrets_action_unit
from .producer import (
    PREFIX_CI,
    PREFIX_SECRETS,
    PREFIX_SECURITY,
    security_action_unit,
    security_action_unit_from_artifact,
)
from .resolve import SOURCE
from .severity import triage_severity
from .state import (
    DEFAULT_THROTTLE_HOURS,
    is_due,
    read_last_import,
    throttle_hours,
    write_last_import,
)

__all__ = [
    "DEFAULT_THROTTLE_HOURS",
    "PREFIX_CI",
    "PREFIX_SECRETS",
    "PREFIX_SECURITY",
    "SOURCE",
    "ci_action_unit",
    "import_findings",
    "is_due",
    "latest_failed_ci_runs",
    "read_last_import",
    "secrets_action_unit",
    "security_action_unit",
    "security_action_unit_from_artifact",
    "throttle_hours",
    "triage_severity",
    "write_last_import",
]
