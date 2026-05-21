# Iterate Spec: empirical-followups

- **Run ID:** iterate-2026-05-21-empirical-followups
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

Close three empirical-verification gaps from the artifact-polish campaign (PRs #57–#62) so the new compliance producers have visible, real-data effect on consumer repos (shipwright + webui). All three are internal tooling/compliance producer improvements that surface existing data — no new user-visible FR.

See `.shipwright/planning/campaigns/2026-05-21-artifact-polish-empirical-results.md` for the empirical-verification report that motivated this iterate.

## Acceptance Criteria

- [ ] **AC-1 (B.4 unlock).** A new CLI `shared/scripts/tools/triage_add.py --title ... --severity high --kind bug --fr-id FR-NN.NN --source manual` creates a triage card whose `frId` is preserved verbatim. After regenerating `update_compliance.py --phase iterate`, the RTM row for that FR shows `FAIL → [trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)` and the `### FRs with open triage items` Coverage Summary subsection lists the FR with the same deep-link. CLI rejects an `--fr-id` value that doesn't match `^FR-\d+\.\d+$`. Covered by unit tests against a tmp project root.

- [ ] **AC-2 (B.3 unlock).** When `shipwright_events.jsonl` carries zero `test_run` events but does carry `work_completed` events with flat-attr `tests_total > 0`, the regenerated `.shipwright/compliance/test-evidence.md` MUST render the `## Full Suite Runs` table populated from those `work_completed` events. Row shape: `Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date`. Trigger column = `iterate` or `build` (event source); Unit = `tests_passed/tests_total`; Integration / pgTAP / Smoke = `—` (unknown — not on the work_completed wire); E2E = `—` ALWAYS in the synthesis branch (`e2e_run` is a boolean signal without counts; honest rendering can't promote a boolean to a count — documented limitation, deferred until real `test_run` events become routine). Selection semantics (per external-review OpenAI #3 + Gemini #5): filter first on `we.tests_total > 0`, then cap at the **last 30** in `data.work_events` file order (matches collector append-order). When `data.test_runs` is non-empty, the old behavior is preserved unchanged — synthesis path is only entered when `data.test_runs` is empty AND at least one `work_event` has `tests_total > 0`. Round-trip producer→file→consumer test covers both branches.

- [ ] **AC-3 (path-canon ALLOWLIST).** `uv run --extra dev pytest shared/tests/test_artifact_path_canon.py` returns 4 passed, 0 failed. The fix extends `ALLOWLIST['compliance']` in `shared/scripts/lib/artifact_migrations.py` to permit `.shipwright/agent_docs/triage_inbox.md` (regenerated artifact containing SBOM card launchPayloads that legitimately reference `plugins/shipwright-compliance/scripts/...`). Other 3 migrations (`planning`, `designs`, `agent_docs`) restored to clean too (drift in any of them is in scope as it shares the same root cause class).

- [ ] **AC-4 (Boundary Probe).** Producer/consumer round-trip test for the new `_full_suite_runs_from_work_events` synthesis path: write a fixture work_event JSONL → run the renderer → parse the markdown table back → assert row count and column ordering match the source events. Drift-protection between the two synthesis paths (test_run-based vs work_event-based) via a parametrized test asserting both branches render the same column shape.

- [ ] **AC-5 (baselines restored).** Post-iterate: `uv run --extra dev pytest shared/tests/` returns 2162+ passed (no regressions from the baseline). `uv run --extra dev pytest plugins/shipwright-compliance/tests/` returns 434+ passed.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** All three fixes are internal compliance/triage producer improvements (tooling change_type). They surface data that already exists; they don't add or modify a user-visible capability. The shipwright monorepo's FR set covers SDLC pipeline phases — none of which gains or loses behavior here. C.1 FR-gate requires `--change-type tooling --none-reason "compliance/triage producer empirical-followups; surfaces existing data via deep-links and synthesized rows; no FR touched"`.

## Out of Scope

- B.3 explicit-test_run-event producer (i.e. wiring `/shipwright-test` or any phase to call `record_event.py --type test_run` with layer breakdowns). The synthesis-from-work_events path eliminates the producer gap for the immediate visibility need; a future iterate can promote to real test_run events when there's appetite for the full layer breakdown.
- Auto-stamping FRs onto triage cards based on diff/spec heuristics (handover Options 1 + 2). Manual `--fr-id` flag is the minimum viable path; auto-mapping is a separate iterate.
- Retroactive backfill of `frId` on existing open triage cards. Operators stamp going forward; old cards stay unstamped.
- Cross-FR validation (i.e. verifying `--fr-id FR-99.99` references a real FR in spec.md). Out of scope for this round; format-only regex check is sufficient.
- Rewriting any existing producer (test-evidence, sbom, github_triage) to emit `frId`. Manual stamping CLI is the only user-facing surface for FR attribution in this iterate.

## Design Notes

n/a — no UI. CLI surface only.

## Affected Boundaries

| Producer (writes)                                                          | Consumer (reads)                                                | Format          |
|----------------------------------------------------------------------------|-----------------------------------------------------------------|-----------------|
| `triage_add.py` → `.shipwright/triage.jsonl`                               | `compliance_report.py`, `rtm_generator.py`, `inbox_aggregator`  | JSONL (camelCase wire keys, `frId` field) |
| `test_evidence._full_suite_runs_from_work_events()` → `test-evidence.md`   | operator render (markdown), `data_collector.collect_all`        | Markdown table  |
| Path-canon ALLOWLIST → `artifact_migrations.ALLOWLIST['compliance']`        | `test_artifact_path_canon.py`                                   | Python list-of-globs |

## Confidence Calibration

- **Boundaries touched:** (1) triage JSONL via new `triage_add.py` producer (`frId` wire key); (2) markdown table via new `_full_suite_runs_from_work_events` render branch in test-evidence.md; (3) path-canon ALLOWLIST (Python config consumed by `test_artifact_path_canon`).
- **Empirical probes run:**
  - Producer→consumer round-trip on all 3 boundaries (JSONL via `read_all_items`, markdown via splitlines+`|`-split parser, path-canon via re-running the previously-failing test). All green.
  - Edge cases: empty work_events; missing fr_id; cap-after-filter with 35 qualifying + 10 non-qualifying events; 12 malformed FR-IDs; bad severity/kind/title; markdown injection via pipes/brackets/newlines. All assert correct behavior.
  - Drift protection across the two synthesis branches (test_run vs work_event) — header text + column count identical.
  - Empirical real-data run: `update_compliance.py --phase iterate` against the worktree produced 30 correctly-shaped Full Suite Runs rows.
- **Edge cases NOT probed + why acceptable:**
  - Cross-FR existence validation — explicitly out of scope (format-only validation per spec; CLI surfaces operator-info note).
  - Concurrent triage.jsonl writes — covered by existing `append_triage_item` file-lock contract.
  - `tests_passed > tests_total` inversion — synthesis only renders the string `passed/total`; no derived counts.
  - POSIX export / inline `#` / quoted `#` probe categories — N/A for machine-only formats (JSONL + markdown), per ADR-024/ADR-031 rationale.
- **Confidence-pattern check:** No "are you confident?"-style question has fired in this run; no yes-then-bug pattern. Stop condition met.

Detailed self-review: `.shipwright/planning/iterate/2026-05-21-empirical-followups-self-review.md`.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --color=no pytest plugins/shipwright-compliance/tests/test_test_evidence.py plugins/shipwright-compliance/tests/test_triage_add.py shared/tests/test_artifact_path_canon.py shared/tests/test_triage_add_cli.py -v`
- **Evidence path:** `.shipwright/runs/iterate-2026-05-21-empirical-followups/surface_verification.log`

## References

- `.shipwright/planning/campaigns/2026-05-21-artifact-polish-empirical-results.md` — empirical-verification report
- `.shipwright/planning/campaigns/2026-05-21-artifact-polish-empirical-verification.md` — handover that motivated the verification
- ADR-058 (B.4 RTM deep-link), ADR-057 (B.3 test-evidence Layer column)
- `shared/scripts/triage.py` (`append_triage_item` already accepts `fr_id`)
- `plugins/shipwright-compliance/scripts/lib/test_evidence.py:_full_suite_runs` (target for synthesis branch)
- `shared/scripts/lib/artifact_migrations.py` (target for ALLOWLIST extension)
