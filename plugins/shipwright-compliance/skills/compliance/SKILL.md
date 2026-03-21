---
name: shipwright-compliance
description: Generates audit-ready compliance documentation from Shipwright pipeline data. Produces traceability matrix, test evidence, change history, SBOM, and dashboard with Mermaid diagrams. Use at any point during or after the SDLC pipeline.
license: MIT
compatibility: Requires uv (Python 3.11+), git repository required
---

# Shipwright Compliance Skill

Generates audit-ready compliance reports from existing Shipwright pipeline data.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-COMPLIANCE: Audit-Ready Documentation
================================================================================
Aggregates pipeline data into compliance reports.

Usage: /shipwright-compliance
   or: Invoked automatically by /shipwright-run (orchestrator)

Reports:
  - Dashboard         (compliance/dashboard.md)
  - Traceability      (compliance/traceability-matrix.md)
  - Test Evidence     (compliance/test-evidence.md)
  - Change History    (compliance/change-history.md)
  - SBOM              (compliance/sbom.md)
================================================================================
```

### B. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

### C. Run Setup Script

```bash
uv run {plugin_root}/scripts/checks/setup_compliance.py \
  --project-root "$(pwd)" \
  --plugin-root "{plugin_root}" \
  --session-id "{session_id}"
```

Parse JSON output for:
- `available_data` — which config files and data sources exist
- `existing_reports` — which compliance reports already exist
- `mode` — `"new"` (first run) or `"update"` (reports exist)

---

## Step 1: Assess Available Data

**Goal:** Determine what compliance data is available.

The setup script reports which data sources exist. Show the user:

```
================================================================================
DATA SOURCES
================================================================================
Run Config:        {available / missing}
Project Config:    {available / missing}
Plan Config:       {available / missing}
Build Config:      {available / missing}
Decision Log:      {available / missing}
Git History:       {available / missing}
Dependencies:      {package.json / pyproject.toml / none}

Mode: {Generating new reports / Updating existing reports}
================================================================================
```

If no configs exist at all: print "No pipeline data found. Run /shipwright-run first." and stop.

---

## Step 2: Generate Reports

**Goal:** Generate all compliance artifacts.

```bash
uv run {plugin_root}/scripts/tools/generate_full_report.py \
  --project-root "$(pwd)"
```

This script:
1. Reads all available data via `data_collector.py`
2. Generates all reports (RTM, Test Evidence, Change History, Dashboard, SBOM)
3. Writes them to `compliance/` directory
4. Writes `shipwright_compliance_config.json`
5. Returns JSON summary

---

## Step 3: Present Results

**Goal:** Show the user what was generated.

```
================================================================================
SHIPWRIGHT-COMPLIANCE: COMPLETE
================================================================================
Reports generated:
  - compliance/dashboard.md              ← Start here
  - compliance/traceability-matrix.md
  - compliance/test-evidence.md
  - compliance/change-history.md
  - compliance/sbom.md

Summary:
  Splits:           {N}
  Sections:         {M} ({completed} complete)
  Tests:            {passed}/{total} passing
  Commits:          {count}
  Decisions:        {count}
  Packages:         {count} ({copyleft} copyleft)

Open compliance/dashboard.md for the full overview.
Tip: Use Ctrl+Shift+V in VS Code to preview Mermaid diagrams.
================================================================================
```

---

## Incremental Mode (Called by Orchestrator)

When called by `shipwright-run` between phases, the orchestrator runs:

```bash
uv run {compliance_plugin_root}/scripts/tools/update_compliance.py \
  --project-root "$(pwd)" --phase "{phase_name}"
```

This updates only the reports affected by the completed phase:

| Phase | Reports Updated |
|-------|----------------|
| project | RTM, Dashboard |
| plan | RTM, Dashboard |
| build | RTM, Test Evidence, Change History, Dashboard |
| test | Test Evidence, Dashboard |
| deploy | Dashboard |
| changelog | Change History, Dashboard |

No user interaction needed — runs silently in the background.
