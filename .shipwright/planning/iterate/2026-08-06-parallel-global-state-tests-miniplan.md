# Mini-Plan — iterate-2026-08-06-parallel-global-state-tests

- **Run ID:** iterate-2026-08-06-parallel-global-state-tests
- **Spec:** `.shipwright/planning/iterate/2026-08-06-parallel-global-state-tests.md`
- **Complexity:** medium · **Risk flags:** `cross_component`

## Files to create / modify

| File | Change |
|---|---|
| `shared/templates/hooks/cache_repair_lock.py` | edit — `await_fanout_observers` becomes progress-based; add `_FANOUT_IDLE_SECONDS`, `_FANOUT_MAX_SECONDS` |
| `plugins/shipwright-{project,design,plan,build,test,security,deploy,changelog,compliance,iterate,adopt,run}/scripts/hooks/cache_repair_lock.py` | 12 vendored copies re-synced byte-identically |
| `shared/tests/test_ensure_shared_cache_fanout_join.py` | edit — unit coverage for the four exit paths (AC-2..AC-5) |
| `integration-tests/test_ensure_shared_cache_fanout.py` | edit — AC-6 integration behavior under real fan-out load |

## The constants, and where each number comes from

Measured over 6 rounds × 22 saturated cores (see spec → "Measured arrival
distribution"). Every value is the measured maximum with ~2.4× headroom, not a
value chosen to make a test pass.

| Constant | Old | New | Derived from |
|---|---|---|---|
| `_FANOUT_PROBE_SECONDS` | 0.1 s | **retained, 0.1 s — no longer a fan-out deadline** | it stops being the "is a fan-out running?" proxy in the wait loop, because `len(peers) >= 2` answers that exactly. Its one remaining use is the bounded settle sleep on the **un-enumerable** path (`peers is None or len(peers) < 2`), where there is no peer set to wait on. Deleting it there would be an unmeasured behaviour change, so it stays |
| `_FANOUT_ARRIVAL_GRACE_SECONDS` | — | **1.0 s** | max observed first-peer arrival ≈ 0.41 s |
| `_FANOUT_IDLE_SECONDS` | — | **1.0 s** | max observed inter-arrival gap 0.41 s |
| `_FANOUT_WAIT_SECONDS` (ceiling) | 2.0 s | **3.0 s** | max observed full fan-out 1.36 s; must stay < the guard's `_READY_WAIT_SECONDS = 10.0` |

## Work breakdown

1. **Write the failing test first (AC-4).** A unit test in which the first peer
   arrives at 0.5 s — after the 0.1 s probe — must fail against today's code,
   proving the test pins the *named root cause* (the probe) and not a side
   effect. *Expect: red before the fix.*
2. **Replace the existence-probe with a progress rule.** Keep the two correct
   fast paths (`len(peers) < 2` → return; all peers observed → return). Drop the
   `fanout_seen` / `probe_deadline` proxy. Exit on, evaluated **after** a fresh
   scan: all observed · nobody arrived by `_ARRIVAL_GRACE` · idle since the last
   arrival exceeds `_IDLE` · `now >= started + _WAIT` (anchored at entry, never
   reset by a late arrival). *Expect: step 1 green.*
3. **Cover the other exit paths** (AC-2, AC-3, AC-5, AC-5b) as unit tests,
   including the entry-anchored ceiling under continuous arrivals and the
   "duplicate / unexpected identity is not progress" case.
4. **Re-sync the 12 vendored copies** and run the drift guard
   (`test_ensure_shared_cache_vendored.py`). *Expect: byte-identical.*
5. **Add the integration behavior (AC-6)** — the real 12-process fan-out under
   load elects one scanner. Required by `cross_component`;
   `check_integration_coverage` recomputes the flag from the diff and STOPs
   without it.
6. **Re-run the AC-1 measurement** — 10 consecutive runs under 22-core
   saturation, recorded as evidence.
7. **Regression sweep** — the whole `ensure_shared_cache` family
   (`_error_paths`, `_partial_reap`, `_repair_isolation`, `_ssot_pins`,
   `_vendored`, `_walk`, `_fanout_join`, `_main_inprocess`, `_integration`)
   plus the 20 integration fan-out tests, notably
   `test_late_participant_cannot_trust_prior_identical_completion` and
   `test_guard_rejects_expired_done_until_successor_repairs`.

## Test strategy

- **Unit** (`shared/tests`) — every exit path of the wait loop, driven by an
  **injected clock and injected observation state**, never by real sleeping.
  Deterministic and host-load independent (external review, DeepSeek #2).
- **Integration** (`integration-tests`) — the real 12-process fan-out. Made
  deterministic by **delaying participant registration past the old 0.1 s
  probe** rather than by saturating cores, so it gates honestly on an
  under-provisioned CI runner (external review, DeepSeek #4 + GPT #3).
  `category:"integration"` in the ledger, satisfying `cross_component`.
- **Empirical** — AC-1's 10-run tally under 22-core saturation. Supplementary
  regression evidence, not the gate.
- **No E2E/browser** — no UI surface in this change.

## External plan review — dispositions

`reviews.json` → `plan`, 11 findings, verdicts `openai: revise`,
`deepseek: approve`. All accepted; the plan above already reflects them.

| # | Finding | Disposition |
|---|---|---|
| GPT-1 | ceiling must be anchored at entry, unresettable | **accepted** — step 2 + AC-5 |
| GPT-2 | "count increases" imprecise; track validated peer identities | **accepted** — set-membership + AC-5b. (`has_completion_observation` is already generation-scoped, so cross-generation markers could not leak; the set makes duplicates non-progress explicit) |
| GPT-3 | derive constants from the measured distribution | **accepted, and it changed the outcome** — measuring falsified the draft root cause (2.0 s bound) and found the real one (0.1 s probe) |
| GPT-4 | scan → update → evaluate ordering; final scan before expiry | **accepted** — step 2 |
| GPT-5 | confirm the full propagation mechanism, not just the 12 copies | **accepted** — step 4 verifies against `test_ensure_shared_cache_vendored.py`, which pins all 13 by content, plus `scripts/update-marketplace.sh` for the runtime cache |
| DS-1 | state the constants / their derivation | **accepted** — the table above |
| DS-2 | unit tests need a fake clock, else they are flaky | **accepted** — injected clock |
| DS-3 | confirm the drift guard exists and runs | **confirmed** — `shared/tests/test_ensure_shared_cache_vendored.py`, bidirectional |
| DS-4 | integration test must not need a saturated host | **accepted** — injected registration delay instead |

## Alternative considered — and why rejected

**Raise `_FANOUT_WAIT_SECONDS` from 2.0 s to ~8 s.** One-line change, no new
constants, and it would very likely make the measured 4/6 go green.

Rejected because it trades one fixed wall-clock for a larger fixed wall-clock.
It keeps the defect's shape — the bound is still unrelated to whether the
fan-out is actually still arriving — so it fails again on a busier host, which
is exactly how #543's 2.0 s bound came to fail one day after it shipped. It
also makes the *common* case worse: a genuinely absent peer would stall every
SessionStart for the full 8 s, where the progress-based rule returns as soon as
arrivals stop. Progress-based waiting costs two constants and pins all four
exit paths with tests.

**Second alternative — let a straggler adopt a fresh completion** instead of
rolling to `.next`. Rejected on evidence, not taste: it breaks
`test_late_participant_cannot_trust_prior_identical_completion`, because a
completion is not proof the cache is still healthy (it can be reaped between
generations). The rollover is a deliberate fence and stays.
