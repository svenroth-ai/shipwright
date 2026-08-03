# Mini-Plan: serialize ensure_shared_cache SessionStart fan-out

- **Run ID:** iterate-2026-08-02-ensure-shared-cache-fanout
- **Complexity:** medium
- **Spec:** `.shipwright/planning/iterate/iterate-2026-08-02-ensure-shared-cache-fanout.md`

## Files to create or modify

- `shared/tests/test_ensure_shared_cache_fanout.py` — new deterministic unit tests for O_EXCL ownership, token fencing, atomic completion waiting, immutable successor election, safe timeout and fail-open branches.
- `integration-tests/test_ensure_shared_cache_fanout.py` — new real 12-process SessionStart scenario proving exactly-once repair, post-repair visibility, and safe consumer skipping for an over-budget live owner.
- `shared/templates/hooks/ensure_shared_cache.py` — add the stdlib-only session claim/barrier while keeping the bootstrap at or below 300 lines.
- `shared/templates/hooks/cache_repair_lock.py` — plugin-local stdlib reader/writer OS lease that serializes cache mutation across distinct session ids, keeps ready consumers concurrent, and releases on process death.
- `shared/templates/hooks/run_if_cache_ready.py` — plugin-local stdlib launcher that opens later SessionStart targets only after the completed claim tip is visible and the writer lease is clear.
- `plugins/*/scripts/hooks/ensure_shared_cache.py` — re-vendor the canonical hook to all 12 hook-bearing plugins.
- `plugins/*/scripts/hooks/{cache_repair_lock,run_if_cache_ready}.py` and `plugins/*/hooks/hooks.json` — re-vendor both helpers and guard every command after the first healer.
- `docs/hooks-and-pipeline.md` — move the healer into the guarded fan-out contract and document ownership, wait and failure semantics.
- Iterate finalization artifacts for this run (review record, decision/changelog drops, F5c evidence); no derived snapshots committed.

## Work breakdown

1. Add red unit tests that force simultaneous claims and assert one owner, token-fenced blocking waiters, completed-generation successor election and explicit failure behavior.
2. Add a red integration test that launches all 12 actual vendored hook scripts against one incomplete simulated cache, counts scanner processes, immediately drives a shared/mirror consumer, and covers a guard launched before its healer.
3. Implement a compact O_EXCL claim and token-specific atomic completion barrier in the canonical hook; hash `session_id` from each independently delivered stdin payload and coordinate outside the repaired trees.
4. Wrap every later SessionStart command with the ready guard, re-vendor byte-identically, update the hook/pipeline SSoT, and run targeted unit/integration/vendoring tests.
5. Run the review cascade, confidence probes, full F0/F0.5 gates and finalization/delivery.

## Test strategy

- Unit: deterministic barriers and injected time/file failures for every claim branch, including an old owner's late completion after an immutable successor election.
- Integration (`category: integration`): 12 separate Python healer/guard chains, independently supplied copies of one SessionStart payload, one shared cache, an immediate post-hook consumer per process, and an 11-second live writer proving the losing guard never opens its consumer early.
- Regression: existing partial-reap, repair-isolation, integration, SSoT and vendoring suites.
- Full suite: Shipwright F0 suite runner, ruff, `verify_local.py`, and F11 finalization verifier.

## Alternative considered

Use a pure first-wins claim and let eleven losers return immediately. Rejected:
it prevents concurrent copiers but allows each losing plugin's next SessionStart
hook to import from the destination while the winner is still copying, leaving
the card's most serious race open. A bounded wait-for-completion closes both
the duplicate-work and import-against-copy windows. Broken coordination remains
fail-open; a known running owner timeout safe-skips both the healer mutation and
the later cache-dependent commands instead of overlapping either side.
