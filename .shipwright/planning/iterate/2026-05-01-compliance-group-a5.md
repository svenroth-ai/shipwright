# Iterate Spec: compliance-group-a5

- **Run ID:** iterate-20260501-compliance-group-a5
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal

Add detective-audit Group **A5** — *CI security workflow integrity* — that
compares each project's deployed `.github/workflows/security.yml` against the
convention-lock constants in `shared/scripts/lib/security_workflow.py` (laid
down by the `/shipwright-adopt` security-scaffolding iterate). This closes the
final post-Plan-v7 gap and brings the detective audit's seven-group coverage
(A..G) up to parity with the preventive Canon and reactive Phase-Quality
layers for the security-CI surface.

## Acceptance Criteria

- [ ] **A5.1 — File presence + skip-on-precondition.** When `WORKFLOW_PATH`
      is absent in the target repo, A5 emits a single `skip` Finding with
      `detail="no GitHub Actions workflow at <path>"`. Matches the B7 / G2 /
      G3 skip-on-precondition pattern. Default: skip cleanly, never fail.
- [ ] **A5.2 — YAML parseability.** When `WORKFLOW_PATH` exists but YAML
      parsing fails, A5 emits a single `fail` Finding (HIGH) with the
      parse error in `detail`. PyYAML is loaded via
      `audit_adapters.load_shared_lib` semantics — but PyYAML is a stdlib-
      level dep here; just `import yaml` directly inside the check (the
      compliance plugin's pyproject already declares `pyyaml>=6.0`).
- [ ] **A5.3 — Permissions block matches `REQUIRED_PERMISSIONS`.** Every
      key in `REQUIRED_PERMISSIONS` (security-events:write, contents:read,
      actions:read) must be present with the exact value. Missing or
      mismatched key → `fail` (HIGH); extra optional permissions (e.g.
      `pull-requests:write` from `OPTIONAL_PERMISSIONS`) do not fail.
      Missing entire `permissions:` block → `fail` (HIGH).
- [ ] **A5.4 — Critical-gate step id present.** A step with
      `id: <CRITICAL_GATE_STEP_ID>` ("shipwright-critical-gate") must
      exist in some job's `steps:`. Missing → `fail` (HIGH).
- [ ] **A5.5 — SARIF category matches `SARIF_CATEGORY`.** The
      upload-sarif step must declare `category: shipwright-security`.
      Different category → `fail` (MEDIUM). No upload-sarif step at all
      → `fail` (MEDIUM) — the workflow without SARIF upload is broken.
- [ ] **A5.6 — Dormant-trigger contract.** `workflow_dispatch:` must be
      present and active under `on:`. `pull_request:` and `schedule:` may
      be either commented-out (the dormant-default) or absent. Active
      (uncommented) `pull_request:` or `schedule:` → `fail` (LOW) — Phase
      B activation is a deliberate user choice, not a default. Missing
      `workflow_dispatch:` → `fail` (HIGH).
- [ ] **A5.7 — Fork-PR guard wired.** SARIF upload step must carry an
      `if:` condition gating on
      `github.event.pull_request.head.repo.full_name == github.repository`
      (or be unconditional, i.e. `if: always()`-style with the same
      embedded check). Missing fork guard → `fail` (MEDIUM). Skipped if
      A5.5 already failed (no upload step to inspect).
- [ ] **A5.8 — All findings carry `source=detective-only` and the
      group letter `"A"`.** Suggested-iterate command points at
      `.shipwright/compliance/audit-report.md` for fail findings.
- [ ] **A5.9 — Crash isolation.** A bug inside any single A5 sub-check
      must not prevent A2/A3/A4 from running, nor mask other A5 sub-
      checks. Top-level `run()` wraps each A5 check in try/except and
      emits one `fail` Finding (`detail="check raised <ExcType>: <msg>"`)
      per crashed check.

## Affected FRs

This iterate touches the shipwright-compliance plugin internals (no
end-user-visible FR), so no FR rows are added to a project spec. The
compliance plugin's "follow-up: Group A5" backlog item in
`SKILL.md` is the documentation surface that gets retired.

## Out of Scope

- Editing the security workflow template at `shared/templates/github-actions/security.yml.template`.
- Auto-fix (`--fix`) for A5 — workflow YAML edits are too high-risk
  for an automated rewriter; failing findings emit a suggested-iterate
  command and the user fixes by hand.
- Drift-checking the deployed workflow byte-for-byte against the
  template. Adopted repos may legitimately customize their workflow as
  long as the convention-lock constants (gate id, permissions, SARIF
  category, dormant-trigger contract) are preserved.
- Wiring A5 into the SessionStart-time preventive Canon or the Stop-
  hook Phase-Quality layer. A5 is a detective-only audit per the plan.
- Upgrading the shipwright monorepo's own `.github/workflows/security.yml`
  to carry the canonical step id. The smoke-run will surface this drift
  as a real A5 finding; reconciling it is a follow-up iterate (see
  `Open follow-ups` below).

## Open follow-ups

- **shipwright-monorepo `security.yml` drift (CONFIRMED).** Smoke-run
  surfaced the predicted A5.4 fail: the deployed `.github/workflows/
  security.yml` Critical-Findings step (line 140) lacks `id:
  shipwright-critical-gate`. Pre-dates the convention-lock. Track as a
  separate iterate `iterate/security-yml-canonical-id` (Cap on scope:
  add the canonical id to the existing step; do not rewrite the
  workflow).
- **shipwright-webui security scaffolding not yet present.** Smoke-run
  showed A5.1 skip — the webui has only `ci.yml`, no `security.yml`. The
  adopt-iterate's security-scaffolding feature (commits `d7a413c` /
  `3eff53b` / `d3fb84a`) hasn't been re-applied to the webui repo since
  it landed. Either re-run `/shipwright-adopt` on the webui or open a
  manual scaffolding iterate. Not blocking: A5.1 skip is the correct
  audit response when no security workflow is present.

## Smoke-run results (2026-05-01)

| Project | A5 outcome | Notes |
| --- | --- | --- |
| shipwright monorepo | A5.4 fail (HIGH) | Missing canonical `id:` on Critical-Findings step. Real drift. |
| shipwright-webui | A5.1 skip | No `security.yml` (only `ci.yml`). Adopt scaffolding pending. |
| aiportal | A5.1 skip | No `.github/workflows/` directory. Cleanest skip. |

## Design Notes

- New module: `plugins/shipwright-compliance/scripts/audit/group_a5.py`
  (separate from `group_a.py` because the YAML parsing + check layout
  is >100 LOC and lifecycle-different from A2/A3/A4 — a4-config-paths
  is data-driven, A5 is YAML-shape-driven).
- Registry entry: `_registry.py` registers `group_a5.run` on letter
  `"A"` AFTER `group_a.run` is registered. Findings from both modules
  merge under the same group rollup in audit-report.md.
- Default-config keys (`audit_detector._DEFAULT_CONFIG`):
  - `a5_workflow_path` — override `WORKFLOW_PATH` for unusual layouts;
    default `None` (consume the constant).
  - `a5_required_permissions` — override `REQUIRED_PERMISSIONS`;
    default `None` (consume the constant).
  - `a5_critical_gate_step_id` — override `CRITICAL_GATE_STEP_ID`;
    default `None`.
  - `a5_sarif_category` — override `SARIF_CATEGORY`; default `None`.
  Strict-by-default: all overrides are escape hatches for bespoke
  projects; the audit consumes the convention-lock constants directly
  unless a project explicitly opts out.
- SKILL.md banner: replace the current "A — Artifact + path integrity
  (dev-block npm/uv/make, [project.scripts], config path-fields)" line
  with one that adds A5 to the bullet list, and drop the "Group A5
  (later iterate)" follow-up paragraph at the bottom.
- Pollution-free shared-lib loading: use
  `audit_adapters.load_shared_lib("security_workflow")` to import the
  constants, mirroring Sub-Iterate A's pattern.
