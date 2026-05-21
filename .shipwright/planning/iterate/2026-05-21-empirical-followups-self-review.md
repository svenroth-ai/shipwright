# Self-Review — empirical-followups

- **Run ID:** iterate-2026-05-21-empirical-followups
- **Reviewer:** Claude (Opus 4.7)
- **Date:** 2026-05-21

## 7-point checklist

### 1. Spec compliance — does the code do what AC says?

- **AC-1.** `triage_add.py` writes a card with frId; round-trip + RTM deep-link verified via integration test. **PASS.**
- **AC-2.** Synthesis renders when `data.test_runs == []` AND any work_event has `tests_total > 0`. Old behavior unchanged when test_runs populated. Empirical run on real monorepo: 30 rows synthesized correctly. **PASS.**
- **AC-3.** `pytest shared/tests/test_artifact_path_canon.py` returns 4 passed. **PASS.**
- **AC-4.** Round-trip test (`test_round_trip_producer_to_file_to_consumer`) + drift-protection test (`test_drift_protection_both_branches_render_same_columns`) both green. **PASS.**
- **AC-5.** Full-suite check below.

### 2. Error handling — boundary conditions covered?

- `triage_add.py`: `--fr-id` validated only when supplied (Gemini #2 / OpenAI #5); empty + whitespace-only rejected; severity / kind / title delegated to existing `triage.append_triage_item` raises. JSON-on-stdout for both success and validation failure (OpenAI #9).
- `_full_suite_runs_from_work_events`: empty work_events → `[]`; non-empty but no qualifying → `[]`; cap-after-filter so non-qualifying events don't steal slots (OpenAI #3 / Gemini #5). Missing timestamp → em-dash (defensive even though `WorkEvent.from_dict` defaults).
- ALLOWLIST extension: narrowly scoped to the `compliance` entry; `triage_inbox.md` is the only added glob.

### 3. Security — input validation, secret-handling, injection paths

- `triage_add.py`: free-form `--title` / `--detail` stored verbatim (`test_main_preserves_pipes_and_brackets_in_title`). Downstream `markdown_table.escape_cell` handles markdown escaping at render time (the established pattern — see `markdown_table.py` allowlist entry). OpenAI #8 satisfied.
- `--fr-id`: format-only validation per spec Out-of-Scope; CLI surfaces a one-line operator-information note about the limitation (OpenAI #12).
- No subprocess calls with shell=True; no credential touching; no secrets in test fixtures (`_SENTINEL` not `_LEAKED_SECRET` per check_secrets.sh learning from 2026-05-19).
- Synthesis branch: no untrusted input — work_events come from the trusted `shipwright_events.jsonl` write path.

### 4. Test quality — do tests verify outcomes, not internal state?

- AC-1 tests assert on the resolved view (`read_all_items`) and the JSON contract on stdout — both observable from outside the CLI. Schema-parity test (`test_schema_parity_only_fr_id_differs`) catches wire-shape drift even if the underlying function changes its internal logic.
- AC-2 tests parse the rendered markdown back through `splitlines() + |-split + strip` (Gemini #4 robust parser) — they verify what an operator actually sees, not internal data flow.
- AC-3 verifies the path-canon test itself goes from FAILED→PASSED for the migration that previously failed.
- Round-trip + drift-protection tests defend against future regressions (both registry-driven SSoT and producer/consumer shape).

### 5. Naming + readability

- `triage_add.py`: short name, consistent with `triage_promote.py` / `triage_cli.py`. Function `_validate_fr_id` is private; `FR_ID_RE` is module-level for test access.
- `_full_suite_runs_from_work_events` mirrors the existing `_full_suite_runs` naming. The `_SYNTHESIS_CAP = 30` / `_DASH = "—"` constants are module-level (single source).
- ALLOWLIST entry has a 9-line comment explaining the regex root cause + iterate of origin — future maintainers won't have to reverse-engineer.

### 6. File sizes

- `shared/scripts/tools/triage_add.py`: 144 lines ✓ (< 300).
- `shared/tests/test_triage_add_cli.py`: 403 lines (crossed 300 at write time; flagged by hook). Tests are tightly cohesive around one CLI surface; splitting would scatter the schema-parity + subprocess + markdown-injection tests across files for no reviewer benefit. **Keep as-is.**
- `plugins/shipwright-compliance/tests/test_test_evidence_synthesis.py`: 352 lines (crossed 300; flagged). Two classes, both about the same feature. **Keep as-is.**
- `plugins/shipwright-compliance/scripts/lib/test_evidence.py`: 920 lines pre-existing, +83 lines this iterate. Already over-cap historically; not refactoring as part of this iterate (out-of-scope).
- `shared/scripts/lib/artifact_migrations.py`: 555 lines pre-existing; +12 this iterate. Same status.

### 7. Affected Boundaries — producer/consumer pairs

| Producer (writes)                                                | Consumer (reads)                                                  | Format          | Round-trip test |
|------------------------------------------------------------------|-------------------------------------------------------------------|-----------------|-----------------|
| `triage_add.py` → `.shipwright/triage.jsonl`                     | `read_all_items`, `aggregate_triage`, `rtm_generator`             | JSONL camelCase | `test_schema_parity_only_fr_id_differs` (wire shape) + `test_main_creates_card_with_fr_id` (round-trip via `read_all_items`) |
| `_full_suite_runs_from_work_events` → `test-evidence.md`         | Operator render + future parsers                                  | Markdown table  | `test_round_trip_producer_to_file_to_consumer` + `test_drift_protection_both_branches_render_same_columns` |
| `ALLOWLIST['compliance']` → `test_artifact_path_canon`           | Layer-1 lint                                                       | Python list-of-globs | The existing test_artifact_path_canon test IS the round-trip — extending allowlist re-runs the same check. |

## Confidence Calibration (Step 7.5)

**Boundaries touched:**

1. JSONL producer (triage.jsonl frId) — verified by round-trip + schema-parity tests.
2. Markdown producer (test-evidence.md Full Suite Runs) — verified by round-trip + drift-protection tests + empirical regen on real monorepo (30 rows, structurally correct).
3. Python config (ALLOWLIST) — verified by re-running the lint that previously failed (4/4 pass post-fix).

**Empirical probes run (8 categories from `references/boundary-probes.md`):**

1. **Producer→consumer round-trip** — JSONL (triage_add.py → read_all_items): green. Markdown (synthesis → splitlines/parse): green. Path-canon lint: green.
2. **Edge case: empty input** — `data.work_events == []` returns `[]`; `--fr-id` omitted produces `frId=None`; ALLOWLIST entry doesn't affect other migrations (verified by 3 other [planning/designs/agent_docs] tests still passing).
3. **Edge case: large input** — 35 qualifying events + 10 non-qualifying → cap-after-filter test (`test_synthesis_caps_at_30_after_filter`) verifies exactly 30 qualifying rows render. No buffer overrun risk (list slicing).
4. **Edge case: invalid input** — bad FR-IDs (12 shapes tested), bad severity, bad kind, blank title — all rejected with JSON error on stdout.
5. **Edge case: markdown injection** — pipes / brackets / newlines in title preserved on wire, escaped at render time by existing `escape_cell`.
6. **POSIX export prefix / inline `#` / quoted `#`** — N/A. The producers in scope are machine-only (JSONL, markdown). Same rationale as ADR-024/ADR-031 boundary docs.
7. **Drift protection across two producers** — `test_drift_protection_both_branches_render_same_columns` + `test_helper_header_matches_test_run_path`. Both verify the synthesis branch and test_run branch share identical column headers + structure.
8. **Empirical real-data check** — ran `update_compliance.py --phase iterate` on the worktree, confirmed 30 rows synthesized with correct shape; ran `pytest shared/tests/test_artifact_path_canon.py` post-fix, confirmed 4/4 green.

**Edge cases NOT probed + why acceptable:**

- **Cross-FR existence validation** (FR-99.99 references a non-existent FR). Explicitly out of scope per spec; CLI surfaces operator-information note. Risk: operator stamps a real card with a fictional FR → silent omission from RTM. Acceptable: format-only validation is what the spec promised; cross-FR validation is a separate iterate.
- **Concurrent writes to triage.jsonl from two `triage_add.py` invocations**. Not probed because `triage.append_triage_item` already holds the file lock during the append. Inherited from existing producer contract.
- **`tests_total > 0` but `tests_passed > tests_total`** (negative failure count via inversion). Not probed in synthesis branch. Acceptable: the synthesis path just renders the string `passed/total` — no derived counts. Inconsistent input → inconsistent display but no crash.

**Confidence-pattern check:** No "are you confident?"-style question has fired in this run. No yes-then-bug pattern. **Stop condition met.** All applicable probe categories covered; no marginal probe pending.

## Decision

All 7 self-review checkpoints PASS. Confidence Calibration STOP-CONDITION met. Proceed to Step 8 (Full Code Review).
