# Mini-Plan — iterate-2026-08-07-triage-dedup-recursion-guard

**run_id:** `iterate-2026-08-07-triage-dedup-recursion-guard`
**Full spec:** `.shipwright/planning/iterate/2026-08-07-triage-dedup-recursion-guard.md`

## 1. Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/lib/triage_dedup.py` | Edit — widen `_parsed_append`'s except tuple to include `RecursionError` |
| `shared/scripts/lib/churn_merge.py` | Edit — widen `dedup_event_lines`'s except tuple to include `ValueError, RecursionError` |
| `shared/tests/test_triage_dedup.py` (or a new file if none exists) | New/edit — unit test pinning the fix, property test (AC-2) |
| `shared/tests/test_sweep_gc_canonical.py` | Edit — correct the now-stale docstring at `test_unparseably_deep_object_degrades_instead_of_raising` (lines 182-188), extend to assert survival |
| `shared/tests/` — a churn_merge dedup test file | New/edit — unit test pinning the `dedup_event_lines` fix |
| `shared/tests/` — end-to-end / integration test | New — AC-3 (`sweep_outbox_to_branch` survives + verdict), AC-5 (`resolve_churn_conflicts` events-log integration) |
| `shared/tests/test_triage_validate.py` or similar | Edit/new — AC-4 pin test for `classify_triage_text`'s already-shipped RecursionError handling |

## 2. Work breakdown (sequential)

1. Write failing tests first (TDD): unit test for `_parsed_append` RecursionError
   (AC-1), unit test for `dedup_event_lines` RecursionError (sibling of AC-1),
   property test (AC-2), AC-4 pin test (already-passing — this one is not
   red/green, it is a drift pin). Confirm each new test fails against
   pre-fix code except the AC-4 pin (which should already pass, proving
   `classify_triage_text` really is already fixed).
2. Apply fix 1: `triage_dedup.py` except-tuple widening. Re-run unit test 1 → green.
3. Apply fix 2: `churn_merge.py` except-tuple widening. Re-run unit test 2 → green.
4. Write + run AC-3 (sweep-level E2E, both outbox-origin and tracked-origin
   deeply-nested-line cases, asserting the specific verdict each yields).
5. Write + run AC-5 (integration: `resolve_churn_conflicts` events-log path
   survives a deeply-nested line) — this is the `category:"integration"`
   behavior `cross_component` owes.
6. Correct `test_sweep_gc_canonical.py`'s stale docstring + extend its assertion.
7. Run the full `shared/tests` suite (touches_shared_infra safety-enforcement).
8. Self-review (Step 7), Test Completeness Ledger (Step 7.5), review cascade
   (Step 8, model=opus per operator instruction).

## 3. Component hierarchy

N/A — no UI.

## 4. Data model changes

None — no schema, no migration. Pure exception-handling widening in two pure
functions (no I/O change, no new fields, no persisted-format change).

## 5. Test strategy

Unit (both fixed functions, both pre/post-fix behavior), one property test
bounded per the internal-review constraint (no `sys.setrecursionlimit`, reuse
the proven `'{"a":' * 20000` idiom), one E2E test through the real canonical
lock (`sweep_outbox_to_branch`), one integration test through the real churn
resolver (`resolve_churn_conflicts`). No E2E/browser layer — this is a pure
backend/library fix with no UI or API surface; F0.5 is not applicable in the
web sense (no `dev_url`), so its skip-rule applies. No Lighthouse/bundle gate
(no JS/frontend touched).

## 6. Alternative approach (medium requires one) — and why rejected

**Catch broadly with a bare `except Exception` at each site instead of naming
`RecursionError` specifically.** Rejected: too broad — it would also swallow
genuine programming errors (e.g. a future refactor that introduces a real
`TypeError` or `KeyError` bug in this function), turning a loud crash into a
silent `None`/skip for defects that should fail fast in CI/tests. Naming
`RecursionError` explicitly (matching the existing `jsonl_records.py`
precedent) fixes exactly the documented, measured failure mode without hiding
unrelated future bugs.
