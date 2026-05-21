# External Code Review — empirical-followups

- **Run ID:** iterate-2026-05-21-empirical-followups
- **Mode:** code (diff vs iterate spec)
- **Provider:** openrouter (Gemini returned null; OpenAI returned 3 findings)
- **Date:** 2026-05-21

## OpenAI findings (adopted)

### HIGH — test_evidence.py:39-43 — synthesis gate too permissive

**Finding.** "The synthesis branch is entered whenever `data.test_runs` is empty, regardless of whether any work event has `tests_total > 0`. AC-2 requires the old behavior to be preserved unless test_runs is empty **and at least one** work event qualifies."

**Disposition.** Adopted. Changed `else: synthesis` → `elif any(we.tests_total > 0 for we in data.work_events): synthesis`. Behavior was effectively the same (synthesis helper early-returns `[]` when no qualifying events), but the call site now makes the contract explicit — reading `generate()` immediately reveals the fallback condition.

### MEDIUM — triage_add.py:58-61 — `--detail` was required

**Finding.** "`--detail` is required by the new CLI, but AC-1 only requires `--title / --severity / --kind / --fr-id / --source manual`."

**Disposition.** Adopted. Made `--detail` optional (default `""`). Added new test `test_main_detail_is_optional` covering the minimal AC-1 surface (5 args: title/severity/kind/source/fr-id).

### MEDIUM — test_triage_add_cli.py:294-334 — schema-parity test under-asserted

**Finding.** "The schema parity test does not verify the CLI's stdout contract or the exact persisted wire shape promised by AC-1; it only compares a subset of fields between two items written through the same underlying helper. A broken implementation that omitted `frId` from stdout, wrote wrong JSON casing in stdout, or returned a wrong success payload could still pass this test."

**Disposition.** Adopted. Tightened `test_schema_parity_only_fr_id_differs` to:

- Parse the CLI stdout and assert `success / id / frId` keys + camelCase contract.
- Assert `fr_id` (snake_case) does NOT appear in stdout.
- Assert the persisted JSONL record carries the full camelCase wire-key set (19 keys including `frId`, `evidencePath`, `runId`, `dedupKey`, `launchPayload`, etc.).
- Assert `fr_id` snake_case does NOT leak into the persisted item.

## Gemini findings

Gemini returned `null` feedback (likely model-side issue at this temperature). OpenAI's review covered the diff; no fallback action needed.

## Carry-forward

None. All HIGH+MEDIUM findings adopted before commit.

## Tests after fixes

- `shared/tests/test_triage_add_cli.py`: 14 passed (was 13; +1 for `test_main_detail_is_optional`).
- `plugins/shipwright-compliance/tests/test_test_evidence_synthesis.py`: 11 passed.
- `plugins/shipwright-compliance/tests/test_test_evidence.py`: 37 passed (unchanged — synthesis branch is additive).
- `shared/tests/test_artifact_path_canon.py`: 4 passed.

Overall: 66 tests green across the three ACs.
