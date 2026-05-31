# Iterate Spec — phase-quality dashboard consistency (SKIP unengaged phases)

- **run_id:** `iterate-2026-05-31-phasequality-dashboard-skip`
- **Type:** change (MODIFY audit finding semantics)
- **Complexity:** medium (`touches_io_boundary`: reads run_config/events, writes
  finding JSON; changes dashboard semantics + touches test_audit_phase_quality)
- **Stacked on:** `iterate/phasequality-triage-bundle` (PR #126) — reuses
  `phase_is_engaged` / `load_engagement_inputs` from that iterate.
- **Follow-up to:** the documented "known limitation" of iterate 1 — the
  producer-side gate cleaned the inbox but the skill-compliance **dashboard**
  still rendered unengaged-phase FAILs (design/build/deploy/adopt C1 etc.) as
  red, because it reads raw finding JSONs without the engagement filter.

## Goal

Make the dashboard consistent with the inbox: a phase the project never
actively engaged renders its Tier-1 FAILs as **SKIP (not applicable)**, not
FAIL — so the framework monorepo's dashboard stops showing red for phases it
never runs.

## Approach

In `audit_phase_quality_on_stop.py::main()`, after the per-phase `findings`
dict is built and BEFORE `write_finding_json`, convert `FAIL → SKIP` for the
audited phase when `phase_is_engaged(phase, cfg, events)` is False. The
conversion is a single post-process pass over the in-memory findings; the
persisted finding JSON then records SKIP, so `regenerate_all_aggregates`
renders SKIP on the dashboard. Engagement inputs come from iterate 1's
`pq.load_engagement_inputs` (FAIL-OPEN: unreadable state → engaged → no
conversion).

## Acceptance Criteria

- [ ] **AC-1.** When `phase_is_engaged` is False for the audited phase, every
      `status=FAIL` finding across all categories in the persisted finding
      JSON is rewritten to `STATUS_SKIP` with `provenance="not-engaged"` and an
      evidence note naming the phase. WARN/PASS/existing-SKIP untouched.
- [ ] **AC-2 (engaged untouched).** When the phase IS engaged, findings are
      written verbatim (FAILs stay FAIL) — no behavior change.
- [ ] **AC-3 (FAIL-OPEN).** Unreadable/absent run_config (`cfg is None`) →
      engaged → no conversion. Fresh/in-progress projects are unaffected (this
      is why the existing runner-direct tests stay green).
- [ ] **AC-4 (runners unchanged).** `run_canon_checks` / `run_*_checks` still
      return FAIL for missing evidence — the conversion is hook-level only, so
      tests calling the runners directly are unaffected.
- [ ] **AC-5 (consistency with iterate 1).** After conversion the persisted
      JSON has no FAIL for the unengaged phase, so iterate 1's
      `collect_in_scope_fails` naturally excludes it too (defense in depth;
      backlog + dashboard now agree).
- [ ] **AC-6 (non-blocking).** Best-effort; any error in the conversion path
      is swallowed and the hook still exits 0.
- [ ] **AC-7 (tests).** New tests assert the conversion (unengaged → SKIP,
      engaged → FAIL preserved, fail-open). `test_audit_phase_quality` /
      `test_phase_quality_rollout` updated only where a complete-unengaged
      setup now yields SKIP.
- [ ] **AC-8 (docs).** `docs/hooks-and-pipeline.md` notes the dashboard now
      renders unengaged phases as SKIP (closes the iterate-1 known limitation).
- [ ] **AC-9 (LOC).** Hook stays ≤300 LOC (currently 238).

## Out of scope

- Re-deriving engagement independently — reuse iterate 1's helper.
- Changing the runners or the C4/C5 not-applicable SKIPs they already emit.

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| hook converts FAIL→SKIP for unengaged phase | finding JSON → dashboard aggregate | `.shipwright/compliance/skill-compliance/*.json` |

## Confidence Calibration

- **Boundaries touched:** reads `shipwright_run_config.json` + events (via
  `pq.load_engagement_inputs`); writes the per-run finding JSON.
- **Empirical probes run:**
  - End-to-end probe (framework-repo conditions): design (unengaged) C1+D1
    `FAIL → SKIP (provenance=not-engaged)`; iterate (engaged) W2 stays `FAIL`;
    `collect_in_scope_fails` → `['iterate:W2']` (design excluded — backlog +
    dashboard agree, AC-5).
  - Blast-radius probe: full shared suite 2666 passed; `test_audit_phase_quality`
    + `test_phase_quality_rollout` unaffected (they call runners directly / use
    fail-open tmp projects). Hook 238 → 271 LOC (≤300, AC-9).
- **Test Completeness Ledger:**
  | Behavior | Status | Evidence |
  |---|---|---|
  | unengaged phase FAIL→SKIP + provenance (AC-1) | tested | test_phase_quality_dashboard_skip::test_unengaged_phase_fails_become_skip |
  | engaged phase FAIL preserved (AC-2) | tested | ::test_engaged_phase_preserves_fail + ::test_iterate_engaged_when_complete_preserves_fail + ::test_in_progress_current_step_engaged_preserves_fail |
  | FAIL-OPEN on missing run_config (AC-3) | tested | ::test_fail_open_without_run_config |
  | PASS/WARN/SKIP untouched | tested | ::test_pass_warn_skip_untouched |
  | runners unchanged (AC-4) | tested | test_audit_phase_quality (runner-direct tests still FAIL as before) |
  | dashboard+backlog consistency (AC-5) | tested | end-to-end probe above |
  | non-blocking best-effort (AC-6) | tested | helper wrapped in try/except; hook always exits 0 (test_hook_output_schema_compliance) |
  | docs note (AC-8) | untestable (`covered-by-existing-test`) | doc prose; behavior covered above |
  - **0 untested-testable behaviors.**
- **Confidence-pattern check:** asymptote — exercised fail-open, the
  in-progress-cursor branch, and PASS/WARN preservation, not just the happy
  unengaged path. Coverage — helper unit tests + end-to-end probe + full-suite
  regression. Residual: none beyond the documented pre-existing suite failures.
