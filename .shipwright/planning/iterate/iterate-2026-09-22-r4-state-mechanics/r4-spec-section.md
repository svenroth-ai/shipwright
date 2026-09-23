# Sub-Iterate: R4 — concurrent state mechanics (state machine, fencing, atomic claim, lease-based reconcile — restated for the wave model)

## Scope

**Depends on:** R1 (`depends_on`/`merged_commit`) and R2 (lease mechanism).
Deliberately does not touch review or merge.

**Full detail:** `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md` § "R4 — concurrent state mechanics" (the
longest, most detailed section of the plan — read it in full before
starting, this summary is necessarily incomplete).

Bloat-baseline extraction is load-bearing: `autonomous_loop.py` is pinned
at limit 300 / current 436 / `grandfathered` (zero headroom); mechanics go
into two new modules — `shared/scripts/lib/loop_state.py` (state machine,
`_load_units_from`, lease fields, `_reconcile_in_progress`) and
`shared/scripts/lib/loop_claim.py` (`cmd_next_batch`, atomic claim,
`cmd_release`, `cmd_mark`, `cmd_mark_running` — the `claimed -> running`
promotion R5a's runner calls at its own Step 1.0.5, built here since it
shares the same fencing-token validation as every other claim mutation —
and `cmd_mark_merged`, the `merging -> merged` write R5b's step 3g point 5
calls with a verified merge-commit SHA; neither `cmd_record` nor `cmd_mark`
can correctly express this transition) — `autonomous_loop.py` becomes a
thinner dispatcher and MUST SHRINK. New tests go into
`test_loop_state.py`/`test_loop_claim.py`, never the pinned
`test_autonomous_loop.py`. Import convention: `lib.`-qualified for
`campaign_graph`/`loop_state`/`loop_claim`, matching `campaign_status.py`
etc — never a bare sibling import.

**`kind == "section"` compatibility, covers semantics, not just
arguments:**
- `cmd_init`'s resume/reinit fix applies ONLY for `kind == "sub_iterate"`.
  For `kind == "section"`, today's literal fallthrough (reinit whenever
  nothing is `pending`/`in_progress`) is preserved exactly.
- `_reconcile_in_progress`'s lease-based-only reconciliation applies ONLY
  for `kind == "sub_iterate"`. For `kind == "section"` (which never
  acquires a lease), today's two salvage paths plus the reset-to-pending
  fallback are preserved exactly.
- R4's regression test (work breakdown step 12) is a full BEHAVIORAL
  sequence — init -> next -> record -> crash -> init-resume -> finalize —
  for `kind == "section"`, asserting every return value and unit status
  matches pre-change, not merely that no new argument/exit-code reaches it.

### The unit state machine
States: `pending`, `claimed`, `running`, `built`, `reviewed`, `merging`,
`merged`, `failed`, `held`. `blocked` is derived, never stored.

Edges — each `-> held` edge carries a `reason_code` (consumed at the
R5b/step-3h status-mapping boundary to distinguish a unit that never got to
run from one demoted mid-flight):
- `pending -> claimed` (atomic claim) | `-> held` (STRICT-STOP drain sweep,
  `reason_code: "swept_never_started"`)
- `claimed -> running` (runner's own Step 1.0.5 promotion) | `-> pending`
  (launch-failure release, no attempt re-bump) | `-> failed` (attempt
  budget out) | `-> held` (drain sweep for a unit claimed but never
  promoted before STRICT-STOP, `reason_code: "swept_never_started"`)
- `running -> built` (runner finished) | `-> failed` | `-> pending` (lease
  expired at a wave boundary/`cmd_init`, budget left — next claim
  increments `attempt`) | `-> held` (drain, `reason_code:
  "swept_after_build"`; or `max_drain_seconds` timeout maps instead to
  `running -> failed`, `reason_code: "drain_timeout"`, per R5b)
- `built -> reviewed` (3f-bis pin+review) | `-> merging` (review-skipped
  path) | `-> failed` (Stage-1 REJECT) | `-> held` (drain, `reason_code:
  "swept_after_build"`)
- `reviewed -> merging` (3g starts, only once branch is current and pin is
  fresh) | `-> built` (rebase demotion) | `-> held` (drain, `reason_code:
  "swept_after_build"`)
- `merging -> merged` (PR merged, via `cmd_mark_merged` with a verified
  `merged_commit` — R5b) | `-> held` (CI red / conflict / timeout /
  mid-merge staleness discovery, `reason_code` names which) | `-> failed`
- `held -> pending` (operator-initiated resume via `cmd_mark`, or the
  natural re-entry point after a `merging -> held` staleness demotion —
  re-claim mints a fresh attempt, counted against `max_rebase_reviews`).
- `merged` is the only terminal SUCCESS state. `TERMINAL = {merged, failed,
  held}` — `cmd_finalize` refuses only outside this set.
- `cmd_mark` may cross any edge, always audited.

### Fencing: single writer, hyphen-based, cross-session-only reclaim
Claim is the ONLY writer of `attempt`. First claim: `attempt = 0`, per-unit
sibling path (`.worktrees/campaign-{slug}--{unit_id}`, no `-a{n}`
suffix — every unit is isolated from its first attempt; scoping only
disambiguates retries). A reclaim (`running -> pending`, evaluated only at
a wave boundary or `cmd_init`) does not bump `attempt`; the NEXT claim of
that now-`pending` unit increments it and mints
`attempt_id = f"{loop_id}-{unit_id}-a{attempt}"` (HYPHEN-BASED — a
colon is NTFS alternate-data-stream syntax on Windows, this project's
primary dev platform) inside `loop.lock`. Used directly as the path
segment:
- worktree: `.worktrees/campaign-{slug}--{unit_id}` (attempt 0) or
  `-a{n}` (attempt >= 1)
- branch: `iterate/campaign-{slug}-{unit_id}-{desc}` (attempt 0) or
  `-a{n}-{desc}` (attempt >= 1)
- run dir: `runs/{loop_id}/{unit_id}/a{attempt}/result.json`

**No `DONE` marker for `kind == "sub_iterate"`.** The runner receives
`unit_id`/`attempt_id`/`worktree`/`branch` explicitly in its brief (not via
`SHIPWRIGHT_LOOP_UNIT_ID`, which is single-valued and session-scoped,
incompatible with N concurrent runners) and writes `result.json` to the
path above using those values directly. R5a reads every wave unit's
`result.json` once the whole wave's `Task` calls return — the return
itself is the completion signal. Build's `kind == "section"` path is
UNAFFECTED: `write_terminal_marker.py` and the `SHIPWRIGHT_LOOP_UNIT_ID`
export stay exactly as they are.

**Reclaim/cleanup split (unchanged):** reclaiming a lease is immediate and
purely logical; physical cleanup (`git worktree remove` / `git branch -D`,
always RECOMPUTED FROM VALIDATED `(slug, unit_id, attempt)`, never a stored
path) is best-effort and never blocks; a Windows file-lock failure is swept
by `git worktree prune` at the next claim.

**Fencing invariant:** every mutation of a claimed-or-later unit —
`cmd_record`, the runner's own `claimed -> running` promotion,
`cmd_release`, lease touch/reclaim, and every write/delete of
`review_pin.json` — validates `(unit_id, attempt_id)` against the current
`loop_state.json` row before writing, under `loop.lock` (or, for the pin
file, via its own token check). A mismatch is a stale-attempt rejection:
- `cmd_record` — new REQUIRED `--attempt-id` (gated `kind ==
  "sub_iterate"`); mismatch -> exit `5`, `stale_attempt`, state untouched,
  rejected payload to `runs/{loop_id}/{unit_id}/rejected/{attempt_id}.json`.
- The runner, immediately before its F6 commit / step-5 push, calls
  `check_unit_attempt.py --state ... --unit X --attempt-id T`; non-zero
  aborts with `status: "failed", reason_code: "stale_attempt"`, no push.
- 3f-bis's review-record commit and 3g's merge both re-check the token.

### `cmd_mark` — the one audited operator override
`mark --unit X --status <state> --reason "<text>" --operator <id>`. Legal
only from a quiescent unit; `running`/`merging` require `--force` plus the
existing "confirm no Task is running against this worktree"
acknowledgement. `--status merged` requires `--merged-commit <sha>`; the
check performs a FRESH `git fetch origin` (or reuses
`fresh_remote_default_ref()`) before verifying the sha as an ancestor of
current `origin/{default}` — a stale local ref must never falsely reject
or falsely accept. `--reason`/`--operator` are length-capped and reject
control characters (the real surface is a markdown-table or
shell-`export` rendering of this data downstream, not the JSON file
itself, which escapes safely). This is the only supported way to unblock a
permanently-`failed` dependency, besides editing `campaign.md` to drop the
edge (legal only while the dependent is still `pending`, per R1's
frozen-on-claim rule).

### `loop_state.json` schema and the v1->v2 boundary
Add `"version": 2`. v2 is an additive superset of v1's row shape — a v1
reader degrades to today's serial-FIFO selection, ignoring `depends_on` and
leases. This guarantee is scoped to `cmd_next`'s selection logic only; true
mixed-binary safety across every v1 code path is out of scope, accepted
given this project's one-plugin-cache-version-at-a-time model.

**Live-campaign upgrade procedure:** a campaign lacking `"version": 2`
finishes under the plugin version that started it. To move it: drain to
`TERMINAL`, SNAPSHOT `loop_state.json` (copy, not delete) for forensic
reference, delete the live file, re-run `init` (reconstructs from
`campaign.md` + `status.json`, mapping `complete -> merged` with a verified
`merged_commit`). The v1-stopped-campaign variant (`held` did not exist in
v1, so a v1 campaign interrupted mid-flight has no clean drain path):
snapshot, delete, re-init, then hand-`cmd_mark` each interrupted unit to
`merged` (with a fetched-and-verified `--merged-commit`) or `failed`, based
on manually inspecting that unit's actual PR state on GitHub. Same
procedure serves as rollback.

### `cmd_init` — resume/reinit fixed (gated `kind == "sub_iterate"` only)
Today's `cmd_init` reinitializes (mints a new `loop_id`, resets every unit
to `pending`) whenever no unit is `pending`/`in_progress` — under the new
vocabulary that's the normal mid-wave state (`built`/`reviewed`/`merging`
exist). Fixed, FOR `kind == "sub_iterate"` ONLY: `ACTIVE = {claimed,
running, merging}` (resume in place), `RESUMABLE = {pending, built,
reviewed, held}`, reinit only when the unit list is genuinely empty.
`kind == "section"` keeps today's exact fallthrough.

### `_reconcile_in_progress` — lease-based, gated `kind == "sub_iterate"` only
For `kind == "sub_iterate"`: replace "missing result file = crashed" and
the old salvage paths with lease-expiry-only reclaim, evaluated at wave
boundaries/`cmd_init`. If a `head_sha` diagnostic is still wanted, capture
it at claim time as `git -C <campaign-worktree> rev-parse
origin/{default}` (the unit's actual resolved base), never a bare call
against the shared worktree. For `kind == "section"`: today's two salvage
paths and reset-to-pending fallback are preserved exactly, unchanged.

### Ready-set claiming, lock timing, and `cmd_finalize`
- `cmd_next_batch` (`--max-parallel N`, VALIDATED: positive integer,
  framework hard cap, reject zero/negative/non-integer/above-cap): computes
  the full ready set by REUSING R1's `loop_state.py::is_unit_ready`/
  `describe_blocker` (`all(dep == "merged" and ancestry-verified)` is that
  function's own definition, restated here for readability — do not write
  a second implementation of it in `loop_claim.py`), claims
  `min(max_parallel, |ready_set|)` — `active_count` is always `0` at this
  point under the wave model (the prior wave has fully drained through the
  merge lane before the next is claimed); the field stays in the data
  model only as a hook for a possible future cross-wave-pipelining
  increment, not built here. Atomic under `loop.lock`; deterministic
  ordering when the ready set exceeds capacity.
- Resolve the base ref once per batch, OUTSIDE `loop.lock` (today's
  `resolve_base_branch` for `serial` calls a 60s-timeout fetch inside a
  30s-timeout lock — a real starvation hazard); only pure state mutation
  happens inside the lock.
- `LockTimeout` gets exit `6`, `lock_timeout` — GATED `kind ==
  "sub_iterate"` (a `kind == "section"` caller preserves today's
  unhandled-exception behavior exactly).
- `cmd_release` — launch-failure path: `claimed -> pending` (or `-> failed`
  once `max_attempts`, default 3, exhausted); immediate logical release,
  physical cleanup best-effort per the reclaim/cleanup split; no attempt
  re-bump.
- Dependency ancestry assert: before claiming a unit with non-empty
  `depends_on`, assert
  `git merge-base --is-ancestor <dep.merged_commit> <resolved-base>` for
  every dependency; if not present locally, fetch once and retry; if still
  absent, leave the unit `pending` for the next `cmd_next_batch` call
  rather than failing the whole batch.
- Canonical state root, not cwd-relative: every path under
  `.shipwright/runs/{loop_id}/{id}` — `cmd_record`,
  `_reconcile_in_progress`, lease checks, `check_unit_attempt.py`,
  review-pin reads/writes, rejected payloads — resolves against one
  explicit, passed-in state root (`state_path`/`campaign_worktree`, R2).
- Base-ref resolution is threaded the same way: `branch_base.py`'s `git
  symbolic-ref`/`git fetch origin` calls run with no `cwd`/`-C`, using the
  process's own cwd — ambiguous once a per-unit worktree exists, and this
  is the exact mechanism the dependency-ancestry assert above resolves
  `<resolved-base>` through. Either thread a repo root into
  `branch_base.py`, or state as an invariant that `cmd_next_batch` always
  executes with cwd == the campaign worktree; whichever is picked, it must
  be STATED, not left to whatever the process cwd happens to be.
- `cmd_finalize` — refuses while any unit is outside
  `TERMINAL = {merged, failed, held}`; summary counts derive from that
  set, for `kind == "sub_iterate"` only (build's 5-token counting is
  untouched).
- Status-vocabulary boundary: the 9-state machine is internal to
  `loop_state.json`. `status.json` keeps its existing 5-token vocabulary
  unchanged — `campaign_progress.py`'s argparse enum needs no code change.
  The one mapping point is `campaign-mode.md` step 3h (R5b's file list):
  `merged -> complete`; `failed -> failed`; `held` maps to `failed` ONLY
  for a mid-flight-demotion `reason_code`, and to `pending` for a
  `"swept_never_started"`/`"swept_after_build"` `reason_code` — a flat
  `held/failed -> failed` mapping would make a stopped-but-healthy
  campaign's never-run units read as failures. See R5b's spec for the
  full rationale.

### Work breakdown
1. State machine as data in `loop_state.py`: `is_legal_transition`,
   exhaustively unit-tested against the (nine-edge-rich) table.
2. `loop_state.py::_load_units_from` moved + fixed (from R1).
3. Ready-set computation with the ancestry assert, bounded by
   `min(max_parallel, |ready_set|)`.
4. `loop_claim.py::` atomic claim, single-writer fencing, `max_parallel`
   validation, `cmd_mark_running` (`claimed -> running`, fencing-token
   checked — the command R5a's runner Step 1.0.5 calls), `cmd_mark_merged`
   (`merging -> merged`, fencing-token checked, strict-hex-SHA validated —
   the command R5b's step 3g point 5 calls).
5. `cmd_release` / `cmd_mark` (merged-ancestry proof with fresh fetch;
   reason/operator sanitization) + tests.
6. `loop_state.json` v2-as-superset (scoped to `cmd_next` selection) +
   v1-degrades-safely test.
7. `cmd_init` resume/reinit fix, GATED `kind == "sub_iterate"` — test: a
   mid-wave state resumes in place for sub_iterate; `kind == "section"`
   behavioral-sequence regression test proves no change.
8. Lease-based `_reconcile_in_progress`, GATED `kind == "sub_iterate"` —
   same dual test structure as step 7.
9. Batch-claim lock-timing fix + `LockTimeout` -> exit `6`, gated.
10. `cmd_finalize` `TERMINAL`-based refusal/summary + the 3h status-mapping
    cross-reference (R5b).
11. Canonical state-root threading through every named call site,
    including `branch_base.py`'s base-ref resolution.
12. `kind == "section"` full behavioral regression: init -> next -> record
    -> crash -> init-resume -> finalize, asserting every return value and
    status matches pre-change.

### Test strategy
- Unit tests per step, in `test_loop_state.py`/`test_loop_claim.py`.
- `category:"integration"` behavior: N concurrent claims against a shared
  `loop_state.json` from separate processes (real file locking), asserting
  no double-claim, correct single-writer fencing, correct lease
  expiry/reclaim at a simulated wave boundary, and the dependency ancestry
  assert rejecting a claim when the local fetch is stale. Paired with
  in-process unit coverage over the same functions (module-object
  monkeypatch) for the diff-coverage gate.
- `cmd_mark_merged` rejects a malformed SHA (fencing-token mismatch and a
  non-hex/short string both rejected before any write); `held`'s
  `reason_code` correctly routes to `pending` vs. `failed` at the mapping
  point exercised in R5b's own tests.

### Alternative approach considered — rejected
A fixed `--max-parallel 2` cap enforced by always waiting for pairs to
finish. Rejected: same implementation cost as a real bounded ready-set,
strictly less throughput.

## Cross-Cutting Constraints (apply to the whole campaign, not just this unit)

This runner reads only this spec file, not `campaign.md` — so the
campaign-wide constraints are restated here in full:

- FR-gate / spec impact: `change_type: infra`, `spec_impact: none`.
- Test-coverage gate: every subprocess-level integration test this
  sub-iterate adds must be paired with in-process unit coverage over the
  same functions (module-object monkeypatching) — subprocess-executed
  lines are invisible to this repo's 80% diff-coverage gate. Any new test
  file declares its own pytest root (`shared/tests` for the
  `autonomous_loop`/`loop_state`/`loop_claim`/`campaign_graph`/
  `worktree_location`/`campaign_status` work) — one root per pytest
  process, per this repo's hard rule (root `conftest.py`, exit 4 on
  violation).
- Explicitly out of scope for the WHOLE campaign — do not build any of
  this even if it seems like a natural extension of this unit's own work:
  per-unit `mode`/guided-vs-autonomous merge policy; `campaign_init.py`/
  `campaign.md` markdown-injection hardening beyond id/duplicate/
  existence/charset validation; WebUI changes; true mixed-plugin-version
  safety; cross-wave pipelining; migrating existing `stacked`-strategy
  campaigns to `depends_on`.
- `shared/scripts/lib/autonomous_loop.py` is bloat-baseline pinned at
  limit 300 / current 436 / `grandfathered` — ZERO headroom, for every
  unit that touches it (not just R1/R4). Leave it at or below 436 lines;
  `shared/tests/test_autonomous_loop.py` is separately pinned at 442, same
  zero headroom — put new tests in new files.
- Plugin-cache sync: **do NOT run `bash scripts/update-marketplace.sh` or
  `check_plugin_cache_sync.py --strict` after this unit merges, even
  though this unit may edit `campaign-mode.md`/`campaign-worktree.md`/
  `sub-iterate-runner.md`.** All cache syncs for this campaign are
  deferred to a single pass after R6 (the last unit) merges — syncing
  mid-campaign would swap the runner's contract out from under the
  still-running orchestrator and break every remaining unit's
  `cmd_mark_running` call.
- Full design authority: read the corresponding section of
  `.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md`
  (Plan v6) for anything this spec doesn't spell out; nothing in this spec
  should contradict it.

## Acceptance Criteria

- [ ] `loop_state.py` + `loop_claim.py` created; `autonomous_loop.py` shrinks and stays at or below 436 lines (checked via `wc -l`, not just judged "thinner").
- [ ] `loop_claim.py` (holds `cmd_next_batch`, atomic claim, fencing, `cmd_release`/`cmd_mark`/`cmd_mark_running`/`cmd_mark_merged` — the module most likely to exceed a plain module budget) stays at or below 300 lines, or carries a `shipwright_bloat_baseline.json` exception entry + ADR in the same diff. Split into a second module first if the exception would otherwise be needed purely from feature count, not genuine cohesion.
- [ ] The 9-state machine + edge table implemented exactly as specified, with `reason_code` on every `-> held` edge.
- [ ] Fencing invariant enforced on every claimed-or-later mutation; hyphen-based `attempt_id`.
- [ ] `cmd_mark_running`, `cmd_mark_merged`, `cmd_release`, `cmd_mark` all implemented in `loop_claim.py`.
- [ ] `cmd_init` / `_reconcile_in_progress` fixes gated strictly to `kind=="sub_iterate"`; a full `kind=="section"` behavioral regression test proves zero change for shipwright-build.
- [ ] `cmd_next_batch` with validated `--max-parallel`, dependency-ancestry assert, lock-timing fix (base-ref resolved outside `loop.lock`), `LockTimeout` -> exit 6 gated.
- [ ] Canonical state root threaded everywhere, including `branch_base.py`'s base-ref resolution.
- [ ] `cmd_finalize` refuses outside `TERMINAL`; step-3h status-mapping honors `reason_code` (swept vs. mid-flight).
- [ ] Import convention: `lib.`-qualified for `campaign_graph`/`loop_state`/`loop_claim` — no bare sibling imports.
