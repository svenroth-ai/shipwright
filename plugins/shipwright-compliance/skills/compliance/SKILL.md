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
  A — Artifact + path integrity (A2 dev-block npm/uv/make, A3 [project.scripts], A4 config path-fields, A5 CI security workflow integrity incl. A5.8 behavioral gate probe)
  B — Config ↔ Config ↔ Event-log coherence (splits, sections, events, reverse git scan)
  C — Planning internal coherence (preventive re-run of plan_checks)
  D — Event-log FR coverage (uncovered FRs, stale refs, promised-not-delivered, last-build state)
  E — Compliance-doc content staleness (regen + byte compare; --fix rewrites stale docs)
  F — ADR structural integrity (preventive re-run)
  G — Agent-docs freshness vs. git activity (G2 conventional-commit scope, G3 ADR-ID body refs)
  H — Bloat-policy detective audit (new crossings of the 300/400-line budgets + ratchets vs shipwright_bloat_baseline.json; Campaign A.review)

Reports written (both gitignored — transient):
  - .shipwright/compliance/audit-report.md    ← human-readable summary
  - .shipwright/compliance/audit-report.json  ← structured payload (also on stdout)
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
uv run "{plugin_root}/scripts/audit/run_audit.py" \
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
  .shipwright/compliance/audit-report.json
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

## Coverage notes & follow-up

All Plan-v7 groups (A, B, C, D, E, F, G) are wired. The CLI no longer
falls through to `groups_skipped=[(letter, "not-implemented")]` for any
group — individual checks may still self-skip when their preconditions
are absent (e.g. B7 / G2 / G3 skip on a non-git repo or before the first
release tag).

**Adopted-status note (B1 / B4):** Both checks scope themselves to
splits with `status="complete"`. Adopted projects (`status="adopted"`)
intentionally fall outside that scope: adopted code is treated as
retroactively complete *without* a planning artifact and *without* a
`split_completed` event — there's nothing for B1 (sections recorded) or
B4 (matching event) to compare against. Coverage for adopted projects
comes from B7 (commit-on-default-branch ↔ event match) and Group G
(commit-quality scans), which both run regardless of split status.

All nine detective groups (A–I) are wired — the seven Plan-v7 groups
(A–G), Group H (bloat-policy audit, Campaign A.review) and Group I
(requirement hygiene vs `shared/fr-authoring.md`; I1–I3 advisory, I4 fails). The
post-Plan-v7 A5 follow-up (CI security workflow integrity) is live. A5 ships in the Group A
rollup via a composite registry handler that merges A2/A3/A4 (group_a)
and A5 (group_a5) findings.

`audit_config.json` schema (extend in `audit_detector._DEFAULT_CONFIG`):

- `a4_path_fields` — dotted paths into `shipwright_*_config.json` whose
  string values must point to existing files. Grammar: `key` (descend),
  `key[]` (iterate list), `key{}` (iterate dict values). Defaults cover
  `plan_config.splits.{}.plan_file` (multi-split layout) and
  `plan_config.spec_file` (single-split layout).
- `g2_stoplist` — conventional-commit scopes G2 should silently accept
  (generic / cross-cutting scopes that don't map to a split).
- `g2_alias_map` — split-name → variant list. A scope passes G2 when it
  matches any alias-map value or a known `splits[].name`.
- `b7_exclusions.exclude_merge_commits`, `exclude_authors`,
  `exclude_path_prefixes` — rule data for B7.
- `b7_exclusions.last_release_tag_pattern` (default `v*`) — glob passed
  to `git describe --tags --match`.
- `retention.rule_a/rule_b/rule_c` — per-rule on/off switches for B7
  (lets users keep rule data while disabling individual rules for
  archaeology runs).
- `a5_workflow_path` / `a5_required_permissions` /
  `a5_critical_gate_step_id` / `a5_sarif_category` — escape hatches for
  projects that legitimately diverge from the convention-lock at
  `shared/scripts/lib/security_workflow.py`. `null` (default) means
  "consume the constant"; bad-type overrides fall back to the constant
  rather than crashing the audit.
