# Iterate — F0 failures under parallel iterates: one real defect, five true positives

- **Run ID:** iterate-2026-08-06-parallel-global-state-tests
- **Date:** 2026-08-06
- **Type:** bug
- **Complexity:** medium
- **Status:** draft
- **Spec Impact:** NONE
- **Affected FRs:** none (no sync-config mapping covers `**/hooks/*.py`)
- **Risk flags:** `cross_component`

---

## Summary

Eleven F0 diagnostics over ten days named eight tests across four test units.
The filed card grouped them under one cause — *"correct tests pointed at a
moving target, moved by sibling worktrees"* — and proposed re-pointing them at
fixtures, pinning snapshots, or declaring exclusivity.

The card asked for that grouping to be **measured before being acted on**,
because it was "a hypothesis grouped by inspection, not a measurement". It was
measured. **The hypothesis is false for seven of the eight tests, and the one
remaining failure has a different cause than the card states.**

Acting on the card as written would have suppressed five tests that were
telling the truth.

---

## Phase 1 — Read Error (verbatim, from the 11 on-disk diagnostics)

| Test | What the assertion actually said |
|---|---|
| `test_committed_index_is_not_stale` (×4) | `1 ADR file(s) unlisted in INDEX.md: ['125-iterate-timings-derived-parent-synthesis.md']` |
| `test_every_adr_file_in_this_repo_is_listed` (×4) | same file, count check |
| `test_no_inline_suppression_has_outgrown_its_baseline` (×2) | sites under `.shipwright/planning/iterate/iterate-2026-08-05-inline-suppression-ratchet/reviews.json` |
| `test_target_behaviour_matches_the_frozen_baseline[disc.review_runner.run_review]` (×2) | `source_lines: 119 → 120` in `review_runner.run_review` |
| `test_golden_file_is_byte_current` (×2) | the same sha, whole-file |
| `test_healthy_cache_fanout_elects_one_scanner_and_copies_nothing` (×2) | `assert 2 == 1` / `assert 3 == 1` — distinct scanner PIDs |
| `test_wait_output_names_queue_owner_run_id_and_heartbeats` (×1) | `"heartbeat:" not in err` |
| `test_three_process_writers_no_truncation_no_lost_update` (×1) | `PermissionError [Errno 13]` from `durable_read_text` on a `tmp_path` file |

**The decisive detail the sighting cards never carried:** every artifact failure
names **the failing run's own artifact**.
`iterate-…-iterate-timings-derived-parent` failed on ADR
`125-iterate-timings-derived-parent-synthesis.md`;
`iterate-…-f5b-dashboard-webui-unit-shape` failed on ADR
`124-bloat-webui-string-shape-tolerance.md`;
`iterate-…-inline-suppression-ratchet` failed on its own `reviews.json`;
`iterate-…-llm-review-gateway-route` failed on `review_runner.run_review`, the
function that run was changing.

## Phase 2 — Reproduce

All eight pass alone on a clean worktree. Two measurements, each 6 rounds, all
units fired concurrently under 22 saturated cores (the card's "weight 22 of 22"
condition):

| Test | Failures under load |
|---|---|
| `test_healthy_cache_fanout_elects_one_scanner_and_copies_nothing` | **4 / 6** |
| `test_wait_output_names_queue_owner_run_id_and_heartbeats` | 0 / 6 |
| `test_three_process_writers_no_truncation_no_lost_update` | 0 / 6 |
| `test_committed_index_is_not_stale` | 0 / 6 |
| `test_every_adr_file_in_this_repo_is_listed` | 0 / 6 |
| `test_no_inline_suppression_has_outgrown_its_baseline` | 0 / 6 |
| `test_golden_file_is_byte_current` | 0 / 6 |
| `test_target_behaviour_matches_the_frozen_baseline[…]` | 0 / 6 |

**Why concurrent SUITE EXECUTION cannot race the five artifact tests.** Each
resolves its subject as `Path(__file__).resolve().parents[2]` — *its own
worktree*. Every iterate runs in its own `.worktrees/<slug>/` checkout by
mandate (`setup_iterate_worktree.py`). A sibling worktree is a physically
separate directory tree; it cannot add an ADR file to, or regenerate an
`INDEX.md` in, the tree this test is reading. The card's premise — "committed
ADR INDEX.md … live in the shared tree, and a concurrent run regenerating any
of them changes the subject mid-assertion" — describes a shared checkout the
framework does not have.

**That claim is bounded to suite execution, and deliberately not stronger.**
Stage-3 review found a channel by which a concurrent run's content *does* enter
this worktree — not by writing into it, but through **this run's own
integrate**. `.shipwright/planning/adr/INDEX.md` is in
`churn_merge.CHURN_ALLOWLIST` and resolves `--theirs (mainline), then
re-derive`, and that re-derive is fail-soft by design
(`adr_index.refresh_best_effort` warns rather than raises, and
`test_f3_refresh_is_best_effort_and_warns` pins that it must not fail the
drop). So a sibling merging to main, plus a failed re-derive, produces
`1 ADR file(s) unlisted in INDEX.md` — verbatim the observed text — in a tree
nobody else touched. The measurement here (0/6 under load) ran suites
concurrently; it never performed an integrate against a moved main, so it does
not speak to that path. **The disposition is unchanged** — the test is a true
positive either way and must not be modified — but the mechanism is not proven
to be unique, and saying otherwise would be the same over-claiming the card is
being corrected for.

**They are true positives.** Each fired because the run under F0 had genuinely
written an artifact without regenerating what derives from it. `INDEX.md` names
its regeneration command in the failure text; the corpus test says in its own
docstring *"That may be correct — but it is a BEHAVIOUR CHANGE and must be
declared, not regenerated away."* Nine of eleven were dismissed as parallel-run
noise.

## Phase 3 — Recent Changes

Not "no regression". `await_fanout_observers` and `_FANOUT_WAIT_SECONDS = 2.0`
entered in **1cbe2dc5 — `fix(hooks): join active cache repair fanout` (#543,
2026-08-04)**. The cache fan-out failures are dated 2026-08-05, after it.

Two of the eight are already resolved and need no work here:
`test_wait_output_names_queue_owner_run_id_and_heartbeats` was fixed by
**fbe41e66 (#549)**, which replaced its fixed sleep with a release-file
handshake and a polling loop — its single diagnostic was captured *during* that
very run. `test_no_inline_suppression_has_outgrown_its_baseline` was authored by
**a9d60100 (#573)**; its two diagnostics are from that feature's own
development.

## Phase 4 — Component-Boundary Instrumentation

The fan-out was instrumented at three boundaries (`_claim_session` verdict,
`session_repair_state` reading, and the origin of each `_delivered` walk),
invoked through the real entry point `run_if_cache_ready.py`:

```
round 1: walks=78  claim verdicts: {OWNER: 3, peer-done(False): 8}
round 2: walks=26  claim verdicts: {OWNER: 1, peer-done(False): 7}
round 4: walks=78  claim verdicts: {OWNER: 3, peer-done(False): 8}
```

No fail-open (`None`) verdict occurred at all — the first hypothesis (a Windows
sharing violation in `read_claim_token` degrading to "unreadable") was tested
and **falsified**. `_claim_session` genuinely elects **multiple owners**, and
the walk count scales at 26 walks per owner.

A second hypothesis — *the owner gives up at the 2.0 s `_FANOUT_WAIT_SECONDS`
bound* — was written into the first draft of this spec and then **also
falsified**, by instrumenting which exit path `await_fanout_observers` actually
takes (5 rounds, 22 cores saturated):

```
round 1: exit=ALL           elapsed=0.773s  observed=12/12   <- correct
round 2: exit=PROBE(0.1s)   elapsed=0.106s  observed= 1/12   <- publishes early
         exit=FANOUT(2.0s)  elapsed=2.010s  observed=11/12   <- 2nd generation
round 3: exit=ALL           elapsed=0.908s  observed=12/12
round 4: exit=PROBE(0.1s)   elapsed=0.106s  observed= 1/12
         exit=FANOUT(2.0s)  elapsed=2.005s  observed=11/12
round 5: exit=ALL           elapsed=1.361s  observed=12/12
```

The successful rounds complete the whole 12-way fan-out in **0.77–1.36 s**, well
inside 2.0 s. The 2.0 s bound is not what fires. What fires is the
*other* early return:

```python
fanout_seen = fanout_seen or observed > 1
if (not fanout_seen and now >= probe_deadline) or now >= fanout_deadline:
    return
```

with `probe_deadline = started + _FANOUT_PROBE_SECONDS` (**0.1 s**).

### Root cause (one sentence)

`await_fanout_observers` decides "there is no fan-out to wait for" if no *second*
observer has appeared within 0.1 s — but under host CPU saturation the first peer
process needs ~0.2–0.4 s merely to spawn, so the owner publishes `.done` at
0.106 s with 1/12 observed, and each of the eleven stragglers then finds a
completion it never observed and rolls to a `<prefix>-<token>.next` claim, wins
it, and repeats the entire cache scan.

The second generation is then *structurally* unable to reach 12/12 — the peers
that already completed never observe it — so it always burns the full 2.0 s
before publishing (`observed=11/12` above). The 0.1 s probe is a proxy for "is a
fan-out configured?", a question `peers` already answers exactly.

### Measured arrival distribution (what the constants must cover)

6 rounds × 22 saturated cores:

| Quantity | max | p50 |
|---|---|---|
| whole 12-way fan-out, first→last observation | 1.36 s | ~1.0 s |
| inter-arrival gap between consecutive peers | 0.41 s | 0.05 s |

The new constants are derived from these, not from what makes a test pass.

**Why the obvious fix is wrong.** Making a straggler adopt a fresh completion
instead of rolling over would break
`test_late_participant_cannot_trust_prior_identical_completion`: a completion is
*not* evidence the cache is still healthy, because the cache can be reaped
between generations. The rollover is a deliberate fence. The defect is on the
**arrival** side, not the adoption side.

---

## Acceptance Criteria

- **AC-1** — With 22 host cores saturated, `test_healthy_cache_fanout_elects_one_scanner_and_copies_nothing`
  passes 10/10 consecutive runs (measured baseline: 4/6 **failed**).
- **AC-2** — `await_fanout_observers` returns as soon as every expected peer has
  an observation marker for this generation (fast path preserved): with all
  peers pre-marked it returns without consuming the arrival grace.
- **AC-3** — Two distinct "nothing to wait for" paths, both bounded:
  - *un-enumerable* (`peers is None`, or fewer than 2) — returns after the
    unchanged bounded settle sleep of `_FANOUT_PROBE_SECONDS`, never entering
    the wait loop. Covered by the pre-existing
    `test_non_object_install_manifest_uses_bounded_fallback`.
  - *configured but nobody arrives* — returns at
    `_FANOUT_ARRIVAL_GRACE_SECONDS`, not at the hard ceiling.
- **AC-4** — A peer arriving *after* 0.1 s no longer loses the generation: with
  the first peer landing at 0.5 s and the rest trailing at 0.3 s intervals, the
  call waits for all of them. This is the assertion that fails against today's
  0.1 s probe and is the pinned root cause.
- **AC-5** — Progress extends the wait but the ceiling does not move: with peers
  arriving continuously, the call still returns by `_FANOUT_WAIT_SECONDS`
  measured **from entry** (a late arrival cannot reset it), and that ceiling
  stays strictly below **`_CLAIM_WAIT_SECONDS = 5.0`** — the binding neighbour
  — as well as below `_READY_WAIT_SECONDS = 10.0`. Both are asserted against
  the imported constants, not against literals.
- **AC-5b** — Only a newly observed member of the *expected* peer set counts as
  progress: a duplicate observation, or a marker for an identity outside
  `peers`, does not extend the idle deadline.
- **AC-6 (integration, `cross_component`)** — the real 12-process
  `run_if_cache_ready.py` fan-out elects exactly one scanner and copies
  nothing. The behavior is carried by the **pre-existing**
  `test_healthy_cache_fanout_elects_one_scanner_and_copies_nothing`, which is
  already the honest composition proof: it was **4/6 failing** before this
  change and is **10/10 under 22-core saturation** after it (AC-1).

  A purpose-built staggered variant was written, reviewed, and then **deleted
  on measurement** — see "The integration test that was removed" below. The
  late-arrival property it was meant to add is held deterministically by AC-4
  at the unit level, so removing it cost no coverage.
- **AC-7** — Every previously declared property still holds: stale completion →
  new generation; late participant after a reap → re-verifies; all 13 vendored
  copies byte-identical.
- **AC-8** — The record is corrected: the five artifact tests are documented as
  true positives and are **not** modified by this change.

## The integration test that was removed, and why that is the finding

Stage-3 adversarial review raised, as its only high objection, that the new
staggered integration test would be **flaky-red on a 2-vCPU CI runner**: the
`_HEALER_WRAPPER` runs every process under `sys.settrace`, so eleven
line-traced interpreters can miss the arrival grace for reasons unrelated to
the property. That objection was **measured, not argued about**: the test
failed **2 of 8 runs** under 22-core saturation.

It was deleted. Shipping a known-flaky test into the very suite whose flakiness
this run exists to remove would have been the run reproducing its own subject.

The stagger is also not a production shape. Claude Code fires all twelve
SessionStart hooks together, which is what `test_healthy_cache_fanout_…`
already does and what AC-1 measured at 10/10. The artificial 0.3 s head start
put the fan-out outside the window the constants were derived for; the
constants are deliberately **not** re-tuned to accommodate a scenario that does
not occur.

Two earlier variants of the same test are recorded here because each failed a
different way and the sequence is the useful part: a fixed 0.35 s sleep
(discriminated, but its margin was interpreter-startup jitter — Stage 2), and a
pure claim-file handshake (robust, but it **passed against the pre-fix code**,
so it proved nothing — caught only by running it against the reverted
implementation). A test that cannot fail is not evidence.

## Timing composition — what is proven and what is not

Stage-2 code review pushed back on the first draft, which pinned the ceiling
against `run_if_cache_ready._READY_WAIT_SECONDS = 10.0`. That inequality is true
but not the one that binds, and a green test standing where a proof was not made
is exactly the false assurance this run exists to remove. Stated plainly:

**What is proven and asserted.** `_FANOUT_WAIT_SECONDS (3.0) <
_CLAIM_WAIT_SECONDS (5.0)`. A peer queued inside `_claim_session` gives up after
`_CLAIM_WAIT_SECONDS` and elects *itself* a recovering owner — the same
duplicate scan this change removes, reached by a second path. So the barrier
alone must never consume the peers' patience, and it does not.

**What is NOT proven.** The full owner budget before it publishes is
`barrier (≤3.0) + acquire_cache_lock (≤5.0) + scan`, which can exceed a peer's
5.0 s. That overrun **pre-dates this change** (it was 2.0 + 5.0 = 7.0), and this
change spends one more second of the margin. It is not proven here because the
argument that carries it is situational rather than arithmetic: in the fan-out
case `acquire_cache_lock` is uncontended — a peer that reads a fresh completion
short-circuits at `ensure_shared_cache.py:256` and never reaches the lock — so
the 5.0 s lock wait is only paid against a *different session's* healer, and the
barrier only runs long when peers *are* arriving (when none arrive there is no
peer left to time out).

That "never reaches the lock" holds for the `False` verdict, **not** for the
fail-open `None` one, which falls through to `acquire_cache_lock` unguarded.
What closes it is measurement rather than structure: this run's Phase-4
instrumentation recorded **zero** `None` verdicts across 4 rounds of the real
12-process fan-out under saturation.

Measured, and labelled precisely: the **barrier leg** elapsed 0.77–1.36 s
against a 5.0 s peer budget. The lock and scan legs were not separately
measured, so total publish latency is bounded by argument, not by a number.

This is recorded rather than closed. Making the two budgets compose by
construction — deriving `_FANOUT_WAIT_SECONDS` from `_CLAIM_WAIT_SECONDS` minus
the lock budget — is a real follow-up, and it is not this bug's fix.

**What the inequality actually buys — corrected.** An earlier draft of this
section, of the constant's comment and of the test's own failure message all
said a peer exhausting `_CLAIM_WAIT_SECONDS` "elects itself a recovering owner,
the very duplicate scan this barrier prevents". Stage-3 review traced it and
that is **wrong**: the recovering peer takes the writer lock, finds
`session_repair_state(...) is True` at `ensure_shared_cache.py:271-273` and
returns **without scanning**. It scans only when the owner genuinely failed to
publish, which is the designed recovery, not a defect. So the inequality buys
**SessionStart latency and lock contention** — a 5 s stall plus a spurious
"owner timed out" line — not a duplicate scan. Corrected in all three places.
Worth recording as its own lesson: this is the second time in this run that a
true assertion was pinned with a false mechanism.

## Residuals — where the fixed defect can still reach

Named rather than left for a twelfth sighting to re-diagnose:

1. **Unreadable manifest.** When `_installed_fanout_participants` returns
   `None` — a partially written `installed_plugins.json` during a plugin
   install gives a `JSONDecodeError` — the function still takes the
   `time.sleep(_FANOUT_PROBE_SECONDS); return` path, i.e. #543's behaviour
   verbatim, while a full 12-way fan-out may be in flight. `None` means "I
   could not read the manifest", not "there is no fan-out". Left unchanged
   deliberately: it is the pre-existing fail-open, changing it is an unmeasured
   behaviour change, and `test_non_object_install_manifest_uses_bounded_fallback`
   pins the current contract.
2. **Bloat-baseline provenance.** 12 `cache_repair_lock.py` paths were added to
   `shipwright_bloat_baseline.json` at `current: 457`, state `grandfathered`,
   written through the Producer (`bloat_baseline.write_baseline`) rather than
   by hand. Stated so the number is not read as wholly inherited: the
   pre-existing crossing was **389** (`git show HEAD:…`), so **+68 lines came
   from this diff** — most of them comment prose recording measurements and
   rejected alternatives. 457 is nevertheless the only mechanically possible
   single-commit value: had the entry existed at 389 the anti-ratchet would
   have blocked this very commit. Recording beats not recording — unbaselined,
   every copy had *no* ratchet protection and the next diff could grow them
   freely. This is a freeze at today's size, not a licence. (The gated set is
   12 paths, which includes the `shared/templates/` canonical copy and excludes
   `shipwright-build`, per the scanner's own candidate rule — not the 13 the
   vendoring drift-guard counts.)
3. **Phantom peers.** `peers` is derived from *installed* plugins, and
   `installed_plugins.json` carries no enabled/disabled field, so a user who
   disables some Shipwright plugins keeps them in `peers` where they never
   arrive. Old cost: the flat 2.0 s cap. New cost: up to the 3.0 s ceiling —
   so **+0.4 s to +1.0 s per SessionStart** in a partially-disabled install.
   A configuration this change makes slightly worse, stated rather than hidden.

The transient-unreadable-marker residual was **fixed**, not recorded: a single
`OSError` on one marker used to abandon the barrier outright
(`if state is None: return`), which reproduced the exact defect. It is now
treated as "cannot tell yet" and the ceiling bounds it.

## Non-goals (deliberate, per the measurement)

- Re-pointing the ADR/corpus/suppression guards at fixtures, pinning snapshots,
  or marking them exclusive. They are correct and already worktree-local;
  changing them would suppress real staleness detection — the card's own
  "WHAT IS NOT ACCEPTABLE" clause, arrived at from the other direction.
- Touching `test_wait_output_names_queue_owner_run_id_and_heartbeats` (fixed by
  #549) or the inline-suppression guard (its diagnostics predate its merge).
- `test_three_process_writers_no_truncation_no_lost_update`: one historical
  sighting, 0/6 under load here. Its `PermissionError` escaping
  `durable_read_text`'s retry ladder is real but unreproduced by this run — and
  it is **already carried by an open card**, `trg-db1de213` (source
  `iterate-2026-08-06-write-lock-primitives`), which measured the same defect
  from the other direction: on Windows a read inside a byte-range-locked region
  raises `PermissionError` with `winerror is None`, so the retry predicate —
  which matches on error numbers — never fires. That is this sighting's
  mechanism, verified through `Path.read_text`, the very call
  `durable_read_text` makes. Left to that card rather than duplicated here.

  **The cross-reference is deliberately written in both directions.**
  `trg-db1de213` is filed from the write-lock-primitives run's perspective and
  never names a test, so a future triager searching for
  `test_three_process_writers_no_truncation_no_lost_update` would find nothing
  and file sighting number twelve — the exact loop this run exists to break.
  The binding is therefore recorded here, with the node id spelled out in full,
  so the search hits this spec:
  `plugins/shipwright-run/tests/test_runconfig_concurrency.py::test_three_process_writers_no_truncation_no_lost_update`
  → `trg-db1de213`.

---

## Verification (medium+)

- **Surface:** `cli` — the SessionStart hook fan-out is a process-level surface;
  there is no web surface in this change.
- **Runner:** the real 12-process fan-out driven through
  `run_if_cache_ready.py` under 22-core saturation.
- **Evidence:** `.shipwright/compliance/evidence/` junit + the AC-1 10-run
  tally recorded in the ledger.

## Confidence Calibration

- **Boundaries touched:** the SessionStart cache-repair election
  (`await_fanout_observers` in `cache_repair_lock.py`) and its 12 vendored
  copies. No serialized-format boundary, no CI trust boundary.
- **Empirical probes run:**
  1. 11 on-disk F0 diagnostics parsed → every artifact failure names the
     failing run's *own* artifact (falsifies the sibling-race premise).
  2. 6 rounds × 22-core saturation → cache fan-out 4/6, all others 0/6.
  3. Boundary instrumentation of `_claim_session` → 3 owners elected, zero
     fail-open verdicts (falsifies the sharing-violation hypothesis).
  4. `git log -S` → the mechanism entered in #543, one day before the failures.
- **Test Completeness Ledger:** see F5 — every behavior below is `tested`.
- **Confidence-pattern check:** *asymptote* — the root cause is pinned to one
  expression (a wall-clock deadline) and reproduced 4/6, not inferred from
  code reading; the two competing hypotheses were each tested and killed.
  *breadth* — unit coverage of all four exit paths of the wait loop, plus the
  real 12-process integration composition (AC-6) required by `cross_component`.
