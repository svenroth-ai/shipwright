# Iterate Spec: risk-recheck-recording-integrity

- **Run ID:** iterate-2026-08-05-risk-recheck-recording-integrity
- **Type:** change
- **Complexity:** medium (self-escalated from Stage-1 `small` — see Complexity Escalation below)
- **Status:** draft

## Complexity Escalation

Stage 1 (`classify_complexity.py`, message-only, no diff yet) returned
`small` (history prior, no scope keyword). Escalated to `medium` on positive
evidence per SKILL.md Step E: this change adds a new F11 finalization
verifier and registers it in `run_all_checks` — i.e. it "changes phase
validators" in exactly the sense CLAUDE.md's own project rule names as
requiring a `docs/hooks-and-pipeline.md` update in the same diff. A
message-only classifier cannot see that; the Repo Scout / project convention
can. Under-classifying a change to the F11 gate registry (which every future
campaign iterate finalizes through) would be reckless given the safety
margin this framework otherwise insists on for its own gates.

## Goal

Close the recording-integrity gap identified by the doubt-review of
`iterate-2026-08-01-campaign-diff-driven-risk-recheck` (triage `trg-da9320d8`,
retitled P4.01, superseding `trg-da9320d8`): the campaign sub-iterate-runner's
Step 3.4 (`diff_risk_recheck.py`) computes `effective_complexity` from the real
diff and the contract *tells* the runner to record that value at F5c, but
nothing *checks* that it did. A runner could silently write Step 2's stale,
message-only estimate into the F5c entry instead, and no gate would catch it.

This matters beyond the one gate the original finding named
(`check_integration_coverage`, whose complexity-based SKIP was already removed
by P1.04/#520): the F5c-recorded `complexity` is a durable, cross-run input —
`classify_complexity`'s history-prior fallback (`prior_source: history`) reads
the median of exactly these recorded values for every *other* no-keyword
iterate in the project. An unenforced under-record doesn't just make one run's
audit trail wrong; it quietly corrupts the classifier every future run falls
back on.

Persist Step 3.4's computed block to a durable per-run artifact (sibling to
`ci_supplychain_ack.json` and `reviews.json`), and add a new, non-dodgeable F11
verifier that fails when the F5c-recorded complexity is outranked by that
recorded `effective_complexity`.

## Acceptance Criteria

- [ ] `diff_risk_recheck.py`'s CLI persists its full `recheck()` result to
      `.shipwright/planning/iterate/<run_id>/risk_recheck.json` whenever
      `--run-id` is supplied (both the `exit 0` continue path and the `exit 3`
      CI-escalation path — the artifact records what was computed regardless
      of whether the run continues).
- [ ] The write validates `run_id` is a single safe path component (mirrors
      `is_safe_run_id` from the CI-ack precedent) and fails closed rather than
      writing outside the planning tree.
- [ ] A new F11 verifier, `check_risk_recheck_recorded` (registered in
      `run_all_checks`), reads that artifact for the run and the F5c entry's
      recorded `complexity`, and FAILS when the recorded complexity's rank is
      lower than `effective_complexity`'s rank (canonical order: trivial <
      small < medium < large).
- [ ] Absence of the artifact is a SKIP, not a failure — this mechanism is
      campaign-only (Step 3.4 never runs for a standalone iterate), so every
      standalone iterate and every pre-existing campaign run without the
      artifact must be unaffected.
- [ ] Presence of the artifact with a missing/malformed F5c entry is a FAILURE
      (an under-recording runner cannot dodge the gate by omitting F5c
      entirely).
- [ ] A malformed `risk_recheck.json` (bad JSON, wrong schema version, missing
      `effective_complexity`) is a FAILURE, not a silent pass.
- [ ] `sub-iterate-runner.md` Step 3.4 prose is updated: "F5c MUST record this
      value" becomes "F5c MUST record this value — F11's
      `check_risk_recheck_recorded` now enforces it."
- [ ] `F6.md`'s directory-level `git add` note for
      `.shipwright/planning/iterate/<run_id>/` names `risk_recheck.json`
      alongside `reviews.json` and `ci_supplychain_ack.json`.
- [ ] `docs/hooks-and-pipeline.md` documents the new F11 verifier (per
      CLAUDE.md's rule: changing phase validators requires updating it in the
      same diff).
- [ ] A `category:"integration"` test proves the real composition: the CLI
      writes the artifact, a deliberately under-recorded F5c entry is written,
      and `run_all_checks` (or the new check function against a real repo)
      reports the failure — not three units individually correct and
      collectively untested together.

## Spec Impact

- **Classification:** none
- **NONE justification:** this is an internal finalization-gate mechanism
  inside the Shipwright framework's own campaign-mode tooling — it has no
  user-visible FR in `.shipwright/planning/spec.md` (the Shipwright product
  spec describes SDLC phases and skills, not the internal verifier registry
  that backstops them). No FR row describes "F11 recomputes and enforces
  recorded complexity"; the closest is the general "iterate finalization
  gates" architecture, which is documented in `architecture.md` /
  `docs/hooks-and-pipeline.md`, not the FR catalogue.

## Out of Scope

- Re-deriving Stage 1's classification independently from the spec text at
  F11 time (would require re-running `classify_complexity.py` against the
  sub-iterate spec file and is a separate, larger "full independent
  re-verification" feature, not what P4.01 asked for).
- Generalizing the new gate to standalone (non-campaign) iterates. Step 3.4 is
  a campaign-only mechanism; a standalone iterate's Stage-2 Repo Scout already
  runs the diff-driven detectors directly (SKILL.md Step E), so there is no
  analogous "computed-but-unrecorded" artifact to check there.
- Touching `check_integration_coverage`'s existing `_floor_note` message logic
  — P1.04 already removed its complexity-based SKIP; this change adds a
  *different*, general recording-integrity gate, not a second copy of that
  one's cross_component-specific floor note.

## Design Notes

n/a — no UI/design surface; this is a Python CLI + verifier change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py` (`main()`) | `shared/scripts/tools/verifiers/<new module>.check_risk_recheck_recorded` | JSON (`.shipwright/planning/iterate/<run_id>/risk_recheck.json`) |
| `shared/scripts/tools/append_iterate_entry.py` (F5c, pre-existing) | same new verifier | JSON (`.shipwright/agent_docs/iterates/<run_id>.json`, `complexity` field) |

`touches_io_boundary` risk flag fires (new JSON producer/consumer pair) — a
real round-trip probe is required before commit (Confidence Calibration /
Boundary Probe).

## Confidence Calibration

- **Boundaries touched:** `diff_risk_recheck.py`/`risk_recheck_record.py`
  (producer of `risk_recheck.json`) → `risk_recheck_recording.py` (consumer),
  a machine-written/machine-read JSON artifact (never hand-edited in the
  normal flow — `run_id` and complexity values are regex-validated ASCII by
  construction, so the BOM/CRLF/non-ASCII/inline-comment probe set for
  human-edited formats does not apply the way it would to a `.env` file).

- **Empirical probes run:**
  1. Real producer→file→consumer round trip: `test_cli_persists_artifact_the_verifier_can_read`
     runs the actual `diff_risk_recheck.py` CLI as a subprocess against a real
     git repo and asserts the bytes it wrote are exactly what the verifier
     reads back. Finding: none on the first pass — the two sides already
     agreed because the schema was designed once and shared by both (no bug
     to iterate on here, unlike the env-file precedent this checklist exists
     for).
  2. Malformed-artifact probes (the actual edge-case space for a machine-only
     JSON format): not-JSON, non-object, wrong `schema_version`, mismatched
     envelope `run_id`, non-object `risk_recheck`, missing/unrecognized
     `effective_complexity` — 8 cases, all converted to named `CheckResult`
     failures rather than exceptions (external plan review findings #3/#8).
  3. Write-time probes: unsafe `run_id` (10 cases incl. `..`, absolute-ish,
     over-length, non-string), a non-regular-file already at the target path
     (external plan review finding #2, scoped down from full symlink-escape
     hardening — see mini-plan's External Plan Review Findings §2).
  4. CI-escalation (exit 3) persistence: `test_main_persists_on_ci_escalation_exit_3`
     and the integration-level `test_ci_escalation_path_also_persists_for_the_verifier`
     (external plan review findings #1/#6 — both providers flagged this path
     as untested in the original plan).
  5. Write-failure visibility: `test_main_reports_write_failure_without_changing_exit_code`
     proves a persistence failure surfaces in the JSON without turning a real
     CI-boundary escalation into a generic operational failure (external plan
     review finding #9).

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | CLI persists `recheck()` result to `risk_recheck.json` when `--run-id` given | tested | `test_write_recheck_record_writes_expected_shape` PASSED |
  | 2 | No `--run-id` → no artifact written | tested | `test_main_does_not_persist_when_no_run_id` PASSED |
  | 3 | Unsafe `run_id` rejected before any write | tested | `test_write_recheck_record_rejects_unsafe_run_id[*]` (10 cases) PASSED |
  | 4 | Non-regular-file at target path rejected (write + read sides) | tested | `test_write_recheck_record_rejects_non_regular_file_target`, `test_fail_when_artifact_exists_but_is_not_a_regular_file` PASSED |
  | 5 | Artifact persisted on exit-0 (continue) path | tested | `test_main_persists_artifact_when_run_id_given` PASSED |
  | 6 | Artifact persisted on exit-3 (CI escalation) path | tested | `test_main_persists_on_ci_escalation_exit_3` PASSED |
  | 7 | Write failure reported without changing exit code | tested | `test_main_reports_write_failure_without_changing_exit_code` PASSED |
  | 8 | `is_safe_run_id` plugin-lib copy matches the shared precedent | tested | `test_is_safe_run_id_sync_with_shared_precedent` PASSED |
  | 9 | Verifier SKIPs when artifact absent (campaign-only, standalone unaffected) | tested | `test_skip_when_artifact_absent` PASSED |
  | 10 | Verifier PASSes when F5c meets/exceeds `effective_complexity` | tested | `test_pass_when_f5c_matches_effective_complexity`, `test_pass_when_f5c_exceeds_effective_complexity` PASSED |
  | 11 | Verifier FAILs when F5c under-records | tested | `test_fail_when_f5c_underrecords` PASSED |
  | 12 | Verifier FAILs when F5c entry missing (no dodge-by-omission) | tested | `test_fail_when_f5c_entry_missing` PASSED |
  | 13 | Verifier FAILs on 8 classes of malformed artifact (JSON/schema/shape) | tested | `test_fail_when_artifact_is_not_json` + 7 siblings PASSED |
  | 14 | `_rank()` never raises on unrecognized input | tested | `test_rank_returns_none_never_raises[*]` (6 cases) PASSED |
  | 15 | `_COMPLEXITY_ORDER` stays in lock-step with the plugin's SSoT (ADR-044) | tested | `test_complexity_order_sync_with_plugin_vocabulary` PASSED |
  | 16 | New check registered exactly once in `run_all_checks` | tested | `test_registered_in_run_all_checks` PASSED |
  | 17 (integration) | Real CLI + real F5c under-record fails the REAL registry, not just the bare function | tested | `test_underrecorded_f5c_fails_the_real_registered_check` PASSED |
  | 18 (integration) | Real CLI + real correctly-recorded F5c passes the REAL registry | tested | `test_correctly_recorded_f5c_passes_the_real_registered_check` PASSED |
  | 19 (integration) | Standalone iterate (no artifact) unaffected by the real registry | tested | `test_standalone_iterate_without_artifact_is_unaffected` PASSED |
  | 20 | A write failure on the CONTINUE path exits non-zero (2), never 0 | tested | `test_main_fails_on_write_failure_on_the_continue_path` PASSED |
  | 21 | An unsafe `--run-id` at the CLI level exits non-zero (2), not a silent continue | tested | `test_main_fails_on_unsafe_run_id_on_the_continue_path` PASSED |
  | 22 | A write failure on the CI-escalation path still exits 3 (unchanged) | tested | `test_main_reports_write_failure_without_changing_exit_code` PASSED |
  | 23 | Writer rejects a `<run_id>` directory symlinked outside the planning tree | tested | `test_write_recheck_record_rejects_symlinked_run_directory` (skips gracefully where symlink creation is unavailable) |
  | 24 | Verifier FAILs (not SKIPs) on an unsafe `run_id` | tested | `test_fail_when_run_id_unsafe[*]` (5 cases) PASSED |
  | 25 | Verifier FAILs on a `<run_id>` directory symlinked outside the planning tree | tested | `test_fail_when_run_directory_is_a_symlink_escaping_the_planning_tree` (skips gracefully where unavailable) |
  | 26 | A dangling/symlinked artifact path is malformed, never genuine absence | tested | `test_fail_when_artifact_path_is_a_dangling_symlink` (skips gracefully where unavailable) |
  | 27 | Missing `effective_complexity` reports "lacks", not "unrecognized (None)" | tested | `test_fail_when_effective_complexity_field_missing_names_it_as_missing` PASSED |

- **Confidence-pattern check:** Asymptote (depth) — the external plan review's
  first pass found 9 actionable gaps; all 9 were addressed. The external CODE
  review then found 5 MORE gaps against the actual implementation (a
  continue-path write failure silently bypassing the whole gate, HIGH
  severity; two independently-flagged path-safety gaps; a message-clarity
  issue) — the fact that a second, independent review pass against real code
  still surfaced a HIGH-severity gap is itself evidence the asymptote was NOT
  reached after the first round. All 5 were addressed and re-verified (26/27
  ledger rows tested at that point); no further findings surfaced after the
  second round of fixes — asymptote reached now. Coverage (breadth) — 27/27
  ledger rows `tested`, 0 untested-testable; the one behavior this change
  deliberately does NOT prove (independent re-derivation of
  `effective_complexity` from the diff, vs. trusting the persisted
  self-report) is recorded as Out of Scope, not silently skipped.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run pytest plugins/shipwright-iterate/tests/ -v`
  (unit) + `uv run pytest integration-tests/ -v -k risk_recheck_recording`
  (the new integration behavior)
- **Evidence path:** pytest output captured in F5/F5c `test_completeness`
- **Justification:** no web/API surface exists for this change; it is a CLI +
  library-level finalization-gate mechanism, verified by its own test suite
  and by `verify_iterate_finalization.py` running against this run's own
  commit (F6-verify).
