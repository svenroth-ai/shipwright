# Mini-Plan: fr-gate-test-evidence

- **Run ID:** iterate-2026-08-16-fr-gate-test-evidence

## Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/lib/fr_gates.py` | New `missing_test_evidence_error(event)` function; wire into `run_fr_gates` between the classification gate and the existence gate |
| `shared/scripts/lib/fr_classification.py` | Reuse `is_valid_none_reason`/`NONE_REASON_MAX_LEN` for `no_tests_reason` — no new predicate needed, same one-line shape |
| `shared/scripts/tools/record_event.py` | Add `--no-tests-reason` CLI arg; serialize `no_tests_reason` into the event dict (mirrors `none_reason`); import + call the new gate at the same point `_fr_or_change_type_gate_error`/`check_fr_existence` already run |
| `shared/tests/test_fr_gate_test_evidence.py` | New file — unit tests for the new gate function (mirrors `test_fr_gate_behavior_affecting.py`'s shape, kept out of the baseline-capped `test_record_event.py`) |
| `shared/tests/test_record_event.py` | Update `test_main_passes_with_affected_frs` (adds `--tests-passed`/`--tests-total` — it was silently demonstrating the hole this run closes); add a small `TestFrGateTestEvidenceCli` class for the CLI-level accept/reject/serialize cases |
| `shared/tests/test_finalize_iterate.py` | Update `test_finalize_allows_feature_event_with_affected_frs` (add `no_tests_reason` to `event_extras` — no test-results fixture in that project, so `_fold_tests_block` derives nothing); add 2 new tests for reject/accept parity on the F5b path |
| `plugins/shipwright-compliance/tests/test_reconciliation.py` | New test class asserting `compute_reconciliation` reconciles the 9 target FRs and still flags the 3 out-of-scope ones, given this run's own event shape |
| `docs/hooks-and-pipeline.md` | Check whether the FR-gate description there needs a one-line mention of the new discipline (SKILL.md rule: a hook/gate/validator change means checking this doc in the same diff) |
| This run's own `work_completed` event (via F5b) | `spec_impact: none`, `affected_frs` = the 9 reconciled FRs, real `tests.total` from F0's full-suite run — no code file, but the actual deliverable half of this card |

## Work breakdown (medium)

1. **Gate function.** Write `missing_test_evidence_error` in `fr_gates.py` mirroring
   `fr_or_change_type_gate_error`'s shape and docstring conventions. Rule:
   `type == work_completed`, `source == iterate`, `is_behavior_affecting(spec_impact)`,
   has non-empty `affected_frs`/`new_frs` → require `isinstance(event.get("tests"), dict)
   and event["tests"].get("total") is not None`, else require a valid
   `no_tests_reason` (reuse `is_valid_none_reason`). No FRs, not behaviour-affecting,
   non-iterate, non-work_completed, or malformed input → bypass (`None`).
   Test: unit tests for each branch (5 gate-behavior cases + 4 no_tests_reason
   validation cases already enumerated in the Test Completeness Ledger).
2. **Wire into `run_fr_gates`.** Insert between the classification gate and the
   existence gate — classification questions ("is this classified") come
   before evidence questions ("is the classification backed by proof") come
   before identity questions ("do the named ids exist"). Test: the ordering
   test already implicit in existing `run_fr_gates` tests — add one asserting
   a doubly-invalid event (unclassified AND no test evidence) surfaces the
   classification error first (existing precedent for gate-ordering tests).
3. **CLI wiring in `record_event.py`.** Add `--no-tests-reason` argparse
   entry next to `--none-reason` (same help-string style); in `build_event`,
   serialize `args.no_tests_reason` into `event["no_tests_reason"]` right
   after the existing `none_reason` line. Call the new gate at `main()`
   alongside the existing two gate calls (not via the `run_fr_gates` wrapper,
   matching the file's existing style of separate explicit calls — see
   Alternative approach below for why not switching to the wrapper).
   Test: CLI-integration tests (reject without evidence, accept with
   `--no-tests-reason`, event lands on disk with the field).
4. **`finalize_iterate.py` parity.** No code change needed — it already calls
   `run_fr_gates` as one call (line ~305), so the new gate applies for free.
   Test: 2 new tests exercising reject/accept through `fi.run()` directly
   (F5b path), confirming ADR-059 parity holds for the new rule too.
5. **Fix the two now-broken existing tests.** `test_main_passes_with_affected_frs`
   (record_event) and `test_finalize_allows_feature_event_with_affected_frs`
   (finalize_iterate) both construct exactly the silent case this card closes
   — spec_impact behaviour-affecting + FRs + no tests, expecting success.
   Update both to supply test evidence (the CLI one) or `no_tests_reason`
   (the finalize one, since there's no test-results fixture to derive from).
   Run the full `shared/tests` + `plugins/shipwright-compliance/tests` suites
   after steps 1-4 to find any other pre-existing test that silently relied
   on the hole; fix each the same way.
6. **Reconciliation test.** New test class in
   `plugins/shipwright-compliance/tests/test_reconciliation.py` asserting,
   given the current `shipwright_events.jsonl` PLUS a synthetic event shaped
   like this run's own (`spec_impact=none`, `affected_frs`=the 9,
   `tests_total>0`, timestamp after all 9's latest touches), that
   `compute_reconciliation` reports all 9 as `reconciled` and the 3
   out-of-scope FRs (`FR-01.16/18/19`) as still `needs_reverification` (or,
   for `01.16`/`01.19`, that they remain in `behavior_touched` with no
   change in status — they are untouched by this run and unaffected).
7. **This run's own event.** No manual `record_event.py` call — F5b
   (`finalize_iterate.py`) is the canonical write path for a worktree iterate.
   Pass `--event-extras-json` (or the equivalent `event_extras` kwarg) with
   `spec_impact: "none"`, `spec_impact_justification` (per the existing
   spec-impact gate, since `intent: change` needs one when `spec_impact` is
   `none`), and `affected_frs`: the 9. `tests.total` comes from
   `_fold_tests_block` reading this run's own F0/F5 ledger automatically —
   no manual `--tests-total` needed, and more honest than hand-typing a
   number, since it is the actual count F0 just produced.

## Test strategy
- Unit tests for the new gate function and `no_tests_reason` validation
  (pure, no filesystem).
- CLI-integration tests for `record_event.py` (subprocess-free, calling
  `main()` directly per the existing pattern in that file).
- `finalize_iterate.py` F5b-path tests via `fi.run()` (existing pattern in
  `test_finalize_iterate.py`).
- A read-side reconciliation test proving the mechanism this card exists to
  fix actually produces the claimed grade improvement.
- No E2E — no web/UI surface (Verification section: `surface: none`).

## Alternative approach (medium — one alternative + why rejected)

**Alternative: refactor `record_event.py`'s `main()` to call `run_fr_gates()`
as a single wrapper call (replacing its two separate `_fr_or_change_type_gate_error`
+ `check_fr_existence` calls), so the new gate is wired in exactly once and
CLI/F5b parity is structurally guaranteed rather than merely convention.**

Rejected for this run (initial decision): `run_fr_gates` is already imported
into `record_event.py` (re-exported, currently unused directly) specifically
so *other* callers (like `finalize_iterate.py`) get the combined gate without
duplicating the chain — but `record_event.py`'s own `main()` deliberately
calls the two constituent gates separately today, with distinct comments
explaining the ordering rationale inline at each call site. Swapping that to
the wrapper is a legitimate simplification but is a second, orthogonal
refactor (touching call-site structure, not adding a rule) that would widen
this diff's blast radius and complicate the "what changed" story for
reviewers without changing behavior. The three-call chain
(`fr_or_change_type_gate_error` → new `missing_test_evidence_error` →
`check_fr_existence`) was to be added explicitly at the same two call sites
instead, preserving today's structure.

**REVERSED after Internal Plan Review.** The reviewer's MEDIUM finding argued
the opposite: three separate calls at the CLI site is exactly the drift risk
`run_fr_gates` exists to prevent (a fourth gate added later could easily be
wired into one call site and missed at the other). The wrapper was adopted
instead — `record_event.py:main()` now calls `run_fr_gates(event,
project_root, "record_event")` once (step 3, as actually implemented),
matching `finalize_iterate.py`'s existing shape and giving CLI/F5b parity
structurally rather than by convention. This also happened to resolve the
step-5 bloat-budget pressure on `record_event.py` (net smaller after the
collapse than before the CLI wiring). The "why rejected" reasoning above is
kept for the record, not because it still holds — it doesn't.
