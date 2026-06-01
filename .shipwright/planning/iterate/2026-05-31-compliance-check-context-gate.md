# Iterate Spec — compliance check context-gate (D5 fix + disabled_checks)

- **run_id:** `iterate-2026-05-31-compliance-check-context-gate`
- **Type:** change (fix a real check bug + add an applicability mechanism)
- **Complexity:** medium (`touches_io_boundary`: reads `audit_config.json`,
  affects the compliance audit contract + the triage bundle; rewrites/adds tests)
- **Base:** `main` @ 0c15e9a6 (all prior iterates + CI merges landed)
- **Follow-up to:** iterate-2026-05-31-compliance-triage-bundle (#129). The
  bundle collapsed 11→1; this empties the bundle of *context-noise* findings on
  the adopted framework monorepo, the operator-approved iterate-4.

## Problem

The compliance backlog bundle (`trg-1f38b5fe`) holds 6 findings. Assessed:

| Finding | Verdict |
|---|---|
| **D5** iterate events link an FR | **Real check bug** — exempts only `spec_impact=none`, but the `record_event` ADR-C.1 gate ALSO accepts `change_type∈{tooling,compliance,infra,docs}+none_reason`. Tooling/compliance iterates pass the gate but fail D5. |
| **B7** every commit since release has an event | Context-noise: a framework/library monorepo isn't every-commit-is-an-iterate (35 non-iterate commits). |
| **D1** spec FR coverage in events | Context-noise: adopted FRs aren't actively event-tracked; repo isn't FR-driven. |
| **G2** commit-scope matches alias-map | Context-noise: multi-component scopes (`canon`, `build,iterate`, `hooks`) not in the split alias-map. |
| **A5.6** dormant-trigger contract | Context-noise: the security CI workflow is *intentionally active* (pull_request/schedule) here, not dormant. |
| **G3** commit-body ADR refs in decision_log.md | NOT noise — ADR-092/093 are pending decision-drops; clears at next `/shipwright-changelog` release. Left alone. |

D5 is a real bug (fix in code). B7/D1/G2/A5.6 are **structurally not-applicable to
this project type** (adopted, multi-component, active-CI framework monorepo) — a
single FR-driven consumer app keeps them on.

## Goal

(1) Fix the D5 `change_type` exemption bug. (2) Add an explicit, per-project
`audit_config.disabled_checks` applicability mechanism (NOT auto-detection / NOT
a blanket) so a project can declare which detective checks don't apply to it.
(3) Configure the framework repo to disable the 4 context-noise checks.

## Acceptance Criteria

- [ ] **AC-1 (D5 change_type exemption).** `group_d._check_d5` exempts a
      feature/change iterate event when `change_type` (lower) ∈
      `{tooling, compliance, infra, docs}` — in addition to the existing
      `spec_impact=none` exemption. Matches `record_event`'s ADR-C.1 gate. An
      FR-bearing feature iterate with neither FR linkage nor an exemption still
      FAILs (D5 stays useful).
- [ ] **AC-2 (disabled_checks mechanism).** `audit_detector.run_all` reads
      `config["disabled_checks"]` (list of check-ids, default `[]`). Any
      produced finding whose `check_id` is listed is rewritten to
      `status="skip"`, `severity="LOW"`, `detail="disabled via
      audit_config.disabled_checks"` (preserving the original name). Uniform
      across all groups; applied once after collection, before return.
- [ ] **AC-3 (default = no-op).** With no `disabled_checks` key (the default),
      behavior is unchanged — every existing audit test stays green.
- [ ] **AC-4 (bundle interaction).** Disabled checks become `skip`, so they
      drop out of `report.any_fail` and the `compliance:backlog` bundle
      (iterate-3) naturally — no separate change needed.
- [ ] **AC-5 (framework config).** A repo-root `audit_config.json` sets
      `disabled_checks: ["A5.6","B7","D1","G2"]`, each with a one-line reason
      comment, documenting WHY each is N/A for this adopted framework monorepo.
- [ ] **AC-6 (LOC / no ratchet).** `audit_detector.py` stays under its
      grandfathered baseline (currently ~362). `group_d.py` change is small.
- [ ] **AC-7 (tests).** D5 change_type exemption (group_d test); disabled_checks
      → skip + default no-op (audit_detector test); the framework
      `audit_config.json` parses and disables exactly those 4.
- [ ] **AC-8 (docs).** `docs/hooks-and-pipeline.md` documents the
      `disabled_checks` config key.

## Out of scope

- G3 (self-resolves at `/shipwright-changelog` release — running that is a
  separate operator action).
- Re-architecting B7/G2 internals (multi-scope parsing, commit classification)
  — `disabled_checks` is the right tool for "this check doesn't apply here".
- The 11-way phase-quality Stop-hook fan-out (separate architecture iterate).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `run_all` skip-rewrites disabled findings | `AuditReport` → `mirror` bundle + dashboard | in-memory + triage.jsonl |
| `audit_config.json` `disabled_checks` | `run_all` | repo-root JSON |

## Confidence Calibration

- **Boundaries touched:** reads `audit_config.json`; rewrites finding status in
  `run_all`; `group_d` event-field read.
- **Empirical probes run:**
  - End-to-end on the REAL repo (`run_audit.py --fix`): before = 6 fails
    (A5.6,B7,D1,D5,G2,G3); after = A5.6/B7/D1/G2 → SKIP (disabled), D5 dropped
    4→1 (the 3 tooling/compliance events now exempted; 1 anomalous
    `change_type=fix` feature event correctly still flags), G3 unchanged
    (self-resolves at release). **6 → 2** (1 anomalous D5 + G3).
  - Self-caught regression: my `group_d.py` edit tripped the artifact-path-canon
    lint (bare `"compliance"` literal + a `compliance/` comment) — stash-verified
    it was MINE (clean base passed), fixed with the established
    `# artifact-path-canon: legacy` marker + comma-reword. Now green.
  - `architecture_md` failure stash-verified PRE-EXISTING (clean base fails too).
- **Test Completeness Ledger:**
  | Behavior | Status | Evidence |
  |---|---|---|
  | D5 exempts change_type∈{tooling,compliance,infra,docs} incl. casing (AC-1) | tested | test_audit_d5_change_type::test_d5_exempts_known_change_types (5 params) |
  | D5 still exempts spec_impact=none; still flags no-FR-no-exemption; rejects unknown change_type | tested | ::test_d5_still_exempts_spec_impact_none + ::_still_flags_… + ::_does_not_exempt_unknown_change_type |
  | disabled_checks → finding rewritten to skip + any_fail false (AC-2) | tested | test_audit_detector::test_disabled_check_rewritten_to_skip |
  | default (no key) = no-op (AC-3) | tested | ::test_disabled_checks_default_is_noop + ::_in_default_config_empty |
  | only listed ids affected | tested | ::test_disabled_checks_only_affects_listed_ids |
  | framework audit_config disables exactly A5.6/B7/D1/G2 (AC-5) | tested | ::test_framework_audit_config_disables_expected_checks |
  | bundle interaction: disabled → not in any_fail/bundle (AC-4) | tested | end-to-end probe (SKIP findings absent from fails) |
  | artifact-path-canon stays green after edits | tested | shared/tests/test_artifact_path_canon.py (4) |
  | docs note (AC-8) | untestable (`covered-by-existing-test`) | doc prose |
  - **0 untested-testable behaviors.**
- **Confidence-pattern check:** asymptote — exercised casing, unknown-type
  rejection, default no-op, only-listed-affected, AND the real-repo end-to-end
  (not just unit happy-paths); caught + fixed my own lint regression. Coverage —
  group_d + audit_detector unit + canon-lint + real-repo probe + full suites
  (579 plugin / 2712 shared). Residual: 1 anomalous D5 event + G3 remain (real-ish,
  not noise) — left for the operator (FR backfill / `/shipwright-changelog`).
