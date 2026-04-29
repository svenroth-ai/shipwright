---
name: shipwright-compliance
description: "On-demand detective audit for cross-artifact consistency plus auto-background compliance documentation. Scans specs, plans, configs, event log, ADRs, and compliance reports for drift that the preventive Canon gate and reactive Phase-Quality Stop hook don't catch. Still produces the traceability matrix, test evidence, change history, SBOM, and dashboard when auto-background updates fire between phases.\nTRIGGER when: user wants a cross-artifact consistency audit, drift check, FR coherence verify, ADR integrity check, compliance report, audit documentation, traceability matrix, test evidence report, SBOM, or change history. Also when user asks about regulatory compliance, audit readiness, or documentation for auditors.\nDO NOT TRIGGER when: user asks to write code (/shipwright-build), run tests (/shipwright-test), fix a bug (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), plan implementation (/shipwright-plan), or design UI (/shipwright-design). If the user just wants to *add a feature*, route to /shipwright-iterate — do not accidentally consume 'add' / 'feature' prompts."
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required
---

# Shipwright Compliance Skill

Detective cross-artifact audit (`/shipwright-compliance`) plus the auto-background compliance-doc generation that fires after every phase completion. Plan v7 Option Z — plugin and command name unchanged; behavior expanded.

Positioning (3-layer):

| Layer | What | When |
|---|---|---|
| Preventive (Canon) | `phase_validators.py` at phase-complete | every phase |
| Reactive (Phase-Quality) | Stop-hook `audit_phase_quality_on_stop.py` | every session end |
| **Detective (this skill)** | `/shipwright-compliance` on-demand | explicit user invocation |

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-COMPLIANCE: Detective Audit
================================================================================
Cross-artifact consistency scan.

Usage:
  /shipwright-compliance                  # full audit, writes report
  /shipwright-compliance --fix            # also regenerate stale docs (Group E)
  /shipwright-compliance --only C,F       # restrict to specific groups
  /shipwright-compliance --format json    # JSON output only

Groups:
  A — Artifact presence + path integrity (npm/uv/make, markdown links, config paths)
  B — Config ↔ Config ↔ Event log coherence (splits, sections, commits, reverse scan)
  C — Planning internal coherence (preventive re-run of plan_checks)
  D — Implementation evidence (event-log FR coverage, section-test coverage)
  E — Compliance-doc content staleness (regen + byte compare)
  F — ADR structural integrity (preventive re-run)
  G — Agent-docs freshness vs. git activity (scope match, ADR refs)

Reports written:
  - .shipwright/compliance/audit-report.md  ← human-readable summary
  - shipwright_audit_report.json          ← structured payload
================================================================================
```

### B. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

---

## Step 1: Parse Arguments

Accept these flags (pass through to `run_audit.py`):

- `--fix` — enable Group E per-doc auto-regeneration (writes to working tree, does **not** commit).
- `--only <groups>` — comma-separated group letters (e.g. `C,F,E`). Defaults to all.
- `--format md|json|both` — output format. Default `both`.

## Step 2: Run the Audit

```bash
uv run {plugin_root}/scripts/audit/run_audit.py \
  --project-root "$(pwd)" \
  [--fix] [--only {groups}] [--format {format}]
```

Exit codes:
- `0` — all groups passed (or only skipped/WARN-level findings).
- `1` — at least one check failed. Report still written.
- `2` — `--project-root` missing.
- `3` — iterate-12 import-gate trip. See `audit-report.md → "Import Gate Error"` for the drift detail.

## Step 3: Present Results

Parse the JSON stdout (`report.any_fail`, `findings`, `fixes_applied`, `groups_run`, `groups_skipped`).

Render to the user:

```
================================================================================
DETECTIVE AUDIT: {PASS|FAIL}
================================================================================
Groups run:        {letters}
Groups skipped:    {letters + reasons}

Findings by group:
  A {fail}/{skip}/{pass}
  B {fail}/{skip}/{pass}
  ...

Top failures (detective-only):
  - B7 "commit on main without work_completed event" — {evidence}
  - E1 "RTM stale after FR-08.03 added" — diff at line 142

Top failures (preventive re-run):
  - C2 "plan.md references FR-05.02 not in spec.md"
  - F3 "ADR-041 superseded but no replacement linked"

Fixes applied:
  - .shipwright/compliance/traceability-matrix.md (regenerated)

Report:
  .shipwright/compliance/audit-report.md
  shipwright_audit_report.json
================================================================================
```

For each failing detective finding, the report contains a copy-pasteable `/shipwright-iterate` command. Do not auto-run it — surface the suggestion and let the user decide.

---

## Auto-Background Compliance Updates

Separately from `/shipwright-compliance`, `shipwright-run`'s orchestrator calls `scripts/tools/update_compliance.py --phase <name>` after every completed pipeline phase. That code path is unchanged by plan v7; it still regenerates the affected subset of compliance docs:

| Phase | Reports Updated |
|-------|----------------|
| project | RTM, Dashboard |
| plan | RTM, Dashboard |
| build | RTM, Test Evidence, Change History, Dashboard, SBOM |
| test | Test Evidence, Dashboard |
| deploy | Dashboard |
| changelog | RTM, Test Evidence, Change History, Dashboard, SBOM |
| iterate | RTM, Test Evidence, Change History, Dashboard, SBOM |

No user interaction needed for auto-background mode. When the compliance plugin is missing (e.g. a partial install), the orchestrator now loud-fails with a stderr warning and writes a `compliance_update_failed` event — so a broken install is visible rather than silently skipped (plan v7, Step 1).

---

## Follow-up (plan v7 roadmap)

Groups A, B, D, E, G (novel detective-only checks) are wired incrementally. Before every group lands, the CLI still reports its slot as `groups_skipped=[...,"not-implemented"]` — users see explicitly which coverage is missing.
