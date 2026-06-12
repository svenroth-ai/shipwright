# Iterate Spec — cross_component risk flag → forced integration coverage

- **Run ID:** iterate-2026-06-12-cross-component-gate
- **Intent:** CHANGE (add a risk flag + a verifier gate to the iterate test machinery)
- **Complexity:** medium (new risk flag + non-dodgeable F11 verifier gate + prose + tests)
- **Origin:** the gap analysis after the merge-cascade work. The empirical machinery
  (Confidence Calibration + Test Completeness Ledger) is BOUNDARY-centric
  (`touches_io_boundary` → round-trip probe) and E2E/F0.5 is APP-SURFACE-centric.
  NEITHER forces an INTEGRATION/COMPOSITION test for a framework CROSS-COMPONENT
  change (merge machinery, hooks, pipeline, campaign). So the cascade fixes were
  each unit-tested but the composition was never forced — I had to be TOLD to write
  `shared/tests/test_parallel_merge_cascade_integration.py`. This closes that hole so
  the next such iterate can't merge without the integration proof — the thing that
  makes auto-merge trustworthy for our (mostly framework) work.

## Decision

A new **`cross_component`** risk flag (covers merge/churn/event-log machinery,
Claude-Code hooks + hook fan-out, pipeline phase validators, and the campaign
drain — hooks included per the user). At **medium+**, it requires an **integration
coverage** behavior in the Test Completeness Ledger — a real-scenario integration
test proving the components compose (the cascade test is the reference pattern).

**Non-dodgeable:** the F11 verifier `check_integration_coverage` RECOMPUTES
`cross_component` from the actual diff (merge-base..HEAD) — not from an agent-reported
flag — and STOPs if cross-component machinery was touched but no behavior is
`category: "integration"`. This mirrors the leak-guard (verifier recomputes truth).

## Spec Impact

MODIFY — extends the risk taxonomy + the Test Completeness Ledger gate. No FR delta.

## Affected Boundaries

- `classify_complexity.{CROSS_COMPONENT_FILE_PATTERNS, is_cross_component_change}` —
  the diff-driven detector (SSoT); re-exported via `shared/contracts/iterate.py`.
- The Ledger schema: `iterate_latest.test_completeness.behaviors[].category` (new
  optional field; `"integration"` is the coverage marker the verifier requires).
- The verifier's self-contained pattern copy `_CROSS_COMPONENT_PATTERNS` (drift-pinned
  to the SSoT) — kept local so the load-bearing verifier never cross-plugin-imports.

## Approach

1. `classify_complexity.py`: `CROSS_COMPONENT_FILE_PATTERNS` + `is_cross_component_change`
   (mirrors `is_io_boundary_change`) + `RISK_TAXONOMY["cross_component"]` (min medium,
   enforces `integration_coverage` + `full_test_suite`; anchored message patterns for the
   Run-Summary hint, diff-driven detection is primary).
2. `shared/contracts/iterate.py`: re-export both.
3. `iterate_checks.py`: self-contained `_CROSS_COMPONENT_PATTERNS` + `_is_cross_component`
   + `_iterate_changed_paths` (merge-base..HEAD diff, fallback to the HEAD commit) +
   `check_integration_coverage(project_root, run_id, commit)` registered in `run_all_checks`.
4. Drift test: verifier patterns == `classify_complexity` patterns (cross_plugin).
5. Prose: SKILL risk-taxonomy row + Phase Matrix "Integration Coverage" row + Step 7.5;
   `confidence-anti-patterns.md` composition/integration dimension; `F5.md` `category`;
   `docs/hooks-and-pipeline.md`.

## Acceptance Criteria

- [ ] `is_cross_component_change` True on integrate_main/churn_merge/gitattributes_*/a
      hooks.json/a hooks/*.py/verify_phase; False on a route/component/doc (test).
- [ ] `check_integration_coverage`: medium+ cross-component diff WITHOUT a
      `category:integration` behavior → FAIL; WITH one → OK; non-cross-component → OK;
      small/trivial → SKIP (recomputes from the diff, not agent-reported).
- [ ] Verifier patterns drift-pinned to the SSoT (forward+reverse).
- [ ] SKILL risk taxonomy + phase matrix + Step 7.5 advertise it (drift tests).
- [ ] Full F0 (incl. iterate-plugin lints + agent-doc budget) green; no new bloat crossing.

## Confidence Calibration
- **Boundaries touched:** {filled before F0}
- **Empirical probes run:** {filled before F0}
- **Test Completeness Ledger:** {table below}
- **Confidence-pattern check:** {filled before F0}

### Test Completeness Ledger
| Behavior | Disposition | Evidence |
|---|---|---|
| is_cross_component_change positive (machinery/hooks/pipeline) | tested | classify detector test |
| is_cross_component_change negative (route/doc/component) | tested | classify detector test |
| verifier FAILs: medium+ cross-comp diff, no integration behavior | tested | verifier test (real-git diff) |
| verifier OK: same diff WITH category:integration behavior | tested | verifier test |
| verifier OK/skip: non-cross-component diff / small complexity | tested | verifier test |
| verifier recomputes from the diff, not the agent-reported flag | tested | verifier test seeds a clean ledger |
| verifier pattern copy == SSoT (no silent drift) | tested | drift test (cross_plugin) |
| SKILL taxonomy/phase-matrix/Step-7.5 advertise the flag | tested | prose drift tests |
