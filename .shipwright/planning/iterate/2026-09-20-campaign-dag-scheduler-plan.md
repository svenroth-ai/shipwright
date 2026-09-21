# Plan v6: dependency-aware parallel campaign scheduler

**run_id:** iterate-2026-09-20-campaign-dag-scheduler · **Supersedes:** v5.
The sixth review round (internal Opus, reading live code; external GLM,
OpenAI) found that v5's own headline fix — "the wave model no longer
serializes the merge lane behind a wave's slowest build" — does not actually
hold: spawning wave N+1 is itself a blocking `Task` round-trip under the
adopted wave premise, so it cannot be made independent of processing wave
N's review/merge without either delaying wave N's merge (no better than
serializing) or leaving wave N's finished builds unreviewed for the whole of
wave N+1's build (worse than serializing). **Decision (operator, this
round): accept the honest throughput model — waves serialize on the merge
lane; the real, real speedup is concurrent building of independent units
*within* one wave, not overlapping a wave's merge lane with the next wave's
build.** Round 6 also found: a security control (`ci_supplychain_authorship_guard.py`)
would fail open once `SHIPWRIGHT_LOOP_UNIT_ID` is dropped; the
`campaign_status.py` bloat mitigation was illusory (the file is genuinely at
its 300-line cap with no baseline entry); and three of the five targeted
fixes applied just before this round's review (readiness-predicate ownership,
`cmd_mark_running`'s call contract, the merge-time `merged_commit` write, and
the R2 capability-only framing) had real remaining defects, caught against
live code rather than the plan's own claims about it. Every fix below is
traced to the finding that forced it.

## What changed from v5, and why

- **The merge-lane/next-wave "decoupling" is withdrawn.** It claimed
  processing wave N's results and spawning wave N+1 were both "ordinary
  orchestrator-turn work" that neither gated on the other. False: spawning a
  wave **is** the blocking `Task` round-trip under this plan's own adopted
  premise (the orchestrator regains control only once the whole spawned
  batch returns), so there is no ordering that achieves both goals at once —
  spawning wave N+1 before wave N's review/merge leaves wave N's finished
  builds unreviewed for the entire length of wave N+1's build (strictly
  worse than serializing); doing wave N's review/merge first is exactly the
  stall external review flagged in round 5. **Operator decision: waves
  serialize on the merge lane, stated plainly.** The actual, real speedup
  this plan delivers is concurrent building of independent units *within*
  one wave — replacing today's one-unit-at-a-time campaign loop — not
  overlap between a wave's merge lane and the next wave's build. R5a and R5b
  are rewritten to reflect strict wave-to-wave sequencing: a wave's units
  are all recorded/reviewed/merged (serial merge lane, unchanged) before the
  next wave's ready set is computed and spawned.
- **`SHIPWRIGHT_LOOP_UNIT_ID`'s removal is corrected to preserve a live
  security control.** Dropping the variable entirely (as v5 specified) fails
  `ci_supplychain_authorship_guard.py`'s `refuse_if_campaign_runner_context()`
  **open** — that check refuses a CI-trust-boundary acknowledgment purely on
  the variable's truthiness, with no override flag, built and hardened twice
  (trg-33d30377/#718, #732) specifically so a campaign runner cannot
  self-author the ack a human is supposed to reason through. R5a now keeps a
  **wave-scoped, non-identity-bearing** export —
  `SHIPWRIGHT_LOOP_UNIT_ID="__campaign_wave__"` — for the whole wave, so the
  guard's truthiness check still refuses; the variable's other,
  identity-bearing consumers (`_run_id.py`'s tier-3 derivation,
  `generate_handoff_on_stop.py`'s namespacing) migrate to the brief-provided
  `unit_id` explicitly, since a shared sentinel value cannot serve those. All
  five known consumers are enumerated and dispositioned in R5a's own section
  (was: only `write_terminal_marker.py`, the one v5 happened to fix).
- **`campaign_status.py`'s bloat mitigation is corrected — it was illusory.**
  v5 moved `id_charset_ok`/`validate_dependency_graph` into the new
  `campaign_graph.py` "instead of growing `campaign_status.py` past its
  limit," but those functions were never in `campaign_status.py` — R1's
  actual additions to that file (`safe_project_campaign_status`, the
  header-indexed parser rewrite, `depends_on`/`merged_commit` carry-through)
  were the real growth, and the file is verified at exactly 299/300 lines
  with **no baseline entry at all** — a first crossing the pre-commit hook
  cannot catch, landing as an unplanned post-merge finding. Fixed:
  `safe_project_campaign_status` moves into `campaign_graph.py` too (it
  wraps graph validation; it belongs there), leaving `campaign_status.py`'s
  own additions to only the parser rewrite and field carry-through.
- **The R1↔R4 readiness-ownership split (introduced this round, then
  re-reviewed) is converged across the document.** The design itself holds —
  `cmd_next` (today's single-unit command, used unchanged by
  `kind == "section"`) stays untouched at the interface level; R1 ships only
  the pure `is_unit_ready`/`describe_blocker` predicates; R4's new
  `cmd_next_batch` is the sole consumer and the sole place the new
  `--campaign-dir` argument and exit code `4` are wired in. What changed
  this round: (a) five stale references elsewhere in the document that still
  described `cmd_next` gaining these features are corrected; (b) **`cmd_next`
  itself gains one narrow, `kind == "sub_iterate"`-gated guard clause** —
  skip a not-`is_unit_ready` pending unit inside its existing FIFO selection
  loop, no new flag, no new exit code — closing the interim-window hazard
  round 6 found: without it, a campaign run between R1 landing and R4
  landing (separately merged sub-iterates) would have no `depends_on`
  awareness at all, exactly the ordering guarantee the original spec asked
  the schema to provide from day one.
- **`cmd_mark_running`'s call contract is completed.** Confirmed as the
  right module (`loop_claim.py`, sharing `loop.lock` + fencing-token
  validation with every other claim mutation), but R5a's brief never gave
  the runner a resolvable path to `loop_state.json` — after the flip,
  `{project_root}` is the *per-unit* worktree, not the campaign worktree
  where that file lives. Fixed by minting `campaign_worktree` and
  `state_path` as explicit brief parameters (see the R2 fix below — they're
  introduced there, not at R5a, so R5a's flip needs no further wiring).
- **The merge-time `merged_commit` write is corrected — the gap was real,
  the fix had three bugs.** (1) It read `gh pr view --json mergeCommit`
  *before* `campaign-mode.md`'s existing "poll until `state == MERGED`" loop
  — that poll exists precisely because the PR object lags the merge call, so
  the field could still read empty. Fixed: read after that poll, and extend
  the poll condition to also require a non-empty `mergeCommit.oid`. (2) The
  `git rev-parse origin/{default}` fallback is deleted outright — this repo
  has run three concurrent campaigns merging 15 PRs in one window (see
  memory), so an unrelated sibling merge landing in the gap would record an
  ancestrally-true but semantically-wrong SHA, a silently-passing false
  proof, worse than no proof. (3) Writing it via `cmd_record`/`cmd_mark` is
  wrong — `cmd_record`'s contract can't express `merging → merged` and
  `cmd_mark` is the **audited operator override**, not a place for the happy
  path. Fixed: a new fencing-validated `loop_claim.py::cmd_mark_merged`,
  requiring the SHA to match a strict hex-SHA pattern before it's accepted
  (the same guard `audit_compliance_lifecycle.py::_merge_sha` already
  applies, reused rather than reinvented, because this value flows unquoted
  into `git merge-base` argv next). Stated explicitly: `loop.lock` is never
  held across a `gh` call, and another wave's `cmd_next_batch` claim can
  legitimately interleave with the merge lane recording this — both are
  fine because every writer takes the lock for its own mutation.
- **R2's "capability-only" framing is corrected — it was not sound.** The
  claim that R5a's flip needs "no further wiring" was false in two
  code-verified ways: the campaign session lock file and `loop_state.json`
  both live under the *campaign* worktree's `.shipwright/`, but R2 wired the
  runner's touch calls off `{project_root}`, which R5a's flip repoints to
  the *per-unit* worktree — every touch would then raise
  `CampaignLockError`, exactly where R2 claims to be the sole liveness
  coverage. Fixed: R2 now introduces `campaign_worktree` and `state_path` as
  explicit brief parameters from the start (reused unchanged by R5a and
  `cmd_mark_running`/`cmd_mark_merged` above), specifies the lease-toucher as
  a field-creating **upsert** (R2 is independent of R1 in the DAG, so no
  `loop_state.json` row is guaranteed to exist yet, and no fencing-token
  validation applies until R4 adds it), and specifies the runner's response
  to a failed touch as **warn-and-continue** — the orchestrator's own
  step-boundary touches stay the authoritative lock-lost detector; a runner
  aborting a near-finished build over a heartbeat hiccup is strictly worse
  than the staleness risk being mitigated.
- **A never-started unit no longer reads as `failed`.** v5's STRICT-STOP
  sweep and exit-4 handling both moved every remaining `pending`/`claimed`
  unit to `held`, and `held` mapped to `status.json`'s `failed` token at step
  3h — so a campaign stopped after 2 of 6 units would show four units that
  never ran as failures, sticky against the WebUI's Campaigns board until a
  full re-run. Fixed: `held` reached via a sweep (never started) maps to
  `pending` at the status boundary; `held` reached via a mid-flight demotion
  (staleness cascade, operator `cmd_mark`) keeps mapping to `failed`,
  distinguished by the unit's `reason_code`.
- **Exit `4`'s sweep is scoped to the actually-blocked subgraph.** v5's
  loop-action table swept *every* `pending`/`claimed` unit to `held`
  whenever exit `4` fired; two independent reviewers read this as "one
  failure bricks unrelated DAG branches," which turns out to hold even
  though exit 4 by definition only fires once the ready set is already
  empty (no independent branch has schedulable work left) — the ambiguity
  itself was worth fixing. Reworded to say explicitly: the units swept are
  the ones `describe_blocker` names as transitively blocked, which — at the
  moment exit 4 fires — is definitionally the same set as "every remaining
  `pending`/`claimed` unit," but stating it this way makes the invariant
  auditable rather than merely true by construction.
- **One `shared/scripts/lib` import convention is declared.** `campaign_graph.py`,
  `loop_state.py`, and `loop_claim.py` are all imported as `lib.<module>`
  (matching `campaign_status.py`, `worktree_location.py`,
  `campaign_session_lock.py`), never as a bare sibling import the way
  `autonomous_loop.py` imports `branch_base`/`file_lock` today — two module
  objects for the same file is the ADR-045 lib-collision class, and it would
  silently break the module-object monkeypatching this plan's own test
  strategy relies on for the diff-coverage gate. `campaign_init.py` (which
  imports nothing from `shared/` today) gets the same `sys.path` bootstrap
  `campaign_progress.py` already uses.
- **The per-unit completion signal is redesigned, not patched.**
  `write_terminal_marker.py` keys off `SHIPWRIGHT_LOOP_UNIT_ID`, a
  single-valued, session-scoped variable exported once — it cannot carry N
  distinct values for N concurrent runners in a wave, and no sub-iterate
  touched this. Since the wave model already means "the whole wave's `Task`
  calls returning" *is* the completion signal, the `DONE`-marker rendezvous
  is simply **dropped for campaign waves** (kept, unchanged, for
  shipwright-build's single-Task `kind == "section"` loop). Each runner
  instead receives its own `unit_id`/`attempt_id`/`worktree`/`branch` as
  explicit brief parameters (not environment variables) and writes
  `result.json` directly to a path derived from them; R5a reads every
  spawned unit's `result.json` once the wave returns, no polling needed.
- **`cmd_mark_running` moves from the orchestrator to the runner.** R5a's own
  adopted premise — the orchestrator cannot act between spawning a wave and
  the whole wave returning — makes "the orchestrator calls it once `Task(...)`
  has been spawned" unreachable code. The runner now promotes its own
  `claimed → running` as its first action (Step 1.0.5, using the fencing
  token it received in its brief), matching the same "the occupying process
  is the one that reports on itself" pattern R2 already established for
  lease-touching. A unit still `claimed` when its wave returns is
  launch-failed by construction; the orchestrator calls `cmd_release` on it.
- **Lease reconciliation is restated as cross-session crash recovery**,
  evaluated only at wave boundaries and `cmd_init` — nothing can evaluate a
  lease mid-wave once the orchestrator has no control until the wave
  returns. `active_count` is always `0` at the point a new wave is claimed
  (the prior wave has, by construction, fully drained through the merge lane
  before the next is spawned), so `max_parallel - active_count` degenerates
  to `min(max_parallel, |ready_set|)` today; the field is kept in the data
  model only as a hook for a possible future cross-wave-pipelining increment,
  explicitly not built here.
- **The id/slug charset is widened and rescoped.** v4's "lowercase ASCII +
  hyphens" would reject this repo's own live conventions
  (`R0`, `15.0`, `14.2`, `p3.8`, all attested in existing code/docs) and,
  wired into the scheduler's degrade path, would strand every pre-existing
  campaign with no recovery. Widened to `[A-Za-z0-9._-]` (bounded length, no
  leading/trailing separator, no `..` segment, no literal `--`), enforcing
  case-*insensitive* uniqueness rather than lowercase normalization (Windows
  worktree directories case-fold). The **hard reject applies only at
  `campaign_init` write time** for newly-authored rows; on the scheduler's
  read path a charset violation is a `warnings` entry, never a degrade — a
  pre-existing campaign keeps running.
- **STRICT-STOP's drain no longer deadlocks `cmd_finalize`.** v4 had no path
  from `pending` to any `TERMINAL` state, so a stop with unclaimed units left
  the campaign undrainable and the session lock held indefinitely — a
  regression against today's unconditional step-4 release. Fixed: `pending →
  held` and `claimed → held` are added to the edge table, and STRICT-STOP
  immediately sweeps every `pending`/`claimed` unit to `held` before waiting
  out `{running, merging}`. A `max_drain_seconds` bound also force-resolves a
  runner that keeps heartbeating without finishing.
- **R2/R3/R4 are resequenced.** R2 becomes capability-only — it builds the
  per-unit guard mode, lease mechanism, and worktree wrapper, but does not
  yet wire `campaign-mode.md`'s live steps onto per-unit paths (that flip
  needs R4's claim-time field minting and canonical state root to exist
  first). R3's guard falls back to the shared campaign worktree when a
  unit's row carries no `worktree`/`attempt_id` yet, so it can ship and be
  fully tested (against directly-constructed per-unit fixtures) before the
  live flip happens. **The actual flip onto per-unit worktrees happens in
  R5a**, alongside the wave model and the brief-parameter redesign above.
- **R3 no longer opens an unpinned-merge window.** v4 replaced the legacy
  `$run_dir/reviewed_head` file with `review_pin.json` but didn't teach 3g to
  read the replacement until R5b — meaning every campaign PR would have
  merged with no `--match-head-commit` in between. R3 now keeps writing the
  legacy file alongside the new one (one extra line; removed once R5b
  rewrites 3g to read `review_pin.json` directly), with an explicit
  acceptance criterion: no campaign PR merges unpinned at any point during or
  after R3.
- **A dependent's readiness now includes an ancestry proof, not just a
  status string.** Every unit gains a `merged_commit` field, populated
  whenever it transitions to `merged` (normal merge, `cmd_mark --merged-commit`,
  or migration — all three now require and verify the SHA, never trust a
  bare status). Before claiming a dependent, the scheduler asserts
  `git merge-base --is-ancestor <dep.merged_commit> <resolved-base>` for
  every dependency; a stale local fetch triggers one retry-fetch, not a
  false "ready."
- **`branch_strategy` is reconciled with `depends_on`.** Once a unit has any
  `depends_on` entries, its base ref is derived from its dependencies'
  verified `merged_commit`s, not from `branch_strategy` — the two are no
  longer both in play for the same unit. A unit with empty `depends_on`
  keeps today's `branch_strategy` behavior unchanged. `stacked` is
  deprecated going forward (it was a workaround for expressing exactly what
  `depends_on` now expresses safely and explicitly) — `campaign_init.py`
  warns, does not reject, if a new campaign chooses it.
- **Several structural fixes to keep the plan buildable against real bloat
  and compatibility constraints**: the graph/charset validators move into a
  new `shared/scripts/lib/campaign_graph.py` rather than growing
  `campaign_status.py` past its own 300-line limit (unnoticed in v4); R1
  states its own bloat budget for `autonomous_loop.py` (must not grow it,
  the same constraint v4 only stated for R4); `cmd_init`'s and
  `_reconcile_in_progress`'s new logic is explicitly gated on `kind ==
  "sub_iterate"`, with build's `kind == "section"` path keeping its exact
  current behavior (v4 gated arguments/exit-codes but missed that these two
  functions' *semantics* changed too); and R6 gets the same four sections
  (files, work breakdown, test strategy, rejected alternative) every sibling
  sub-iterate has, instead of a paragraph of prose.
- **Security hardening** (from external review): destructive git operations
  recompute expected worktree/branch paths from validated `(slug, unit_id,
  attempt)` rather than trusting whatever is stored in `loop_state.json`;
  the review-record commit asserts `HEAD == reviewed_head` exactly and
  stages only `reviews.json` by explicit path, never `git add -A`; the pin
  record persists the PR's node ID and `headRefName`/`baseRefName`, not just
  a branch name, so a PR is never re-resolved by name alone; `max_parallel`
  has a validated, framework-wide hard cap.

Prior changelogs (v4→v5, v3→v4, v2→v3, v1→v2) are preserved in this file's
git history; dropped here to keep the current document readable.

## Campaign shape (revised DAG)

```
R1 (depends_on schema, campaign_graph.py) ─┐
                                             ├─▶ R4 (state mechanics) ─┐
R2 (per-unit worktree CAPABILITY only) ─────┼─▶ R3 (diff-fix, fallback-safe) ─┤
                                             └───────────────────────────────┼─▶ R5a (wave build, THE FLIP) ─▶ R5b (merge lane) ─▶ R6 (capstone)
```

- **R1** and **R2** are independent (disjoint files) — build in parallel.
- **R3** depends on **R2** (per-unit guard mode must exist, even though R3
  falls back to the shared worktree until the flip) and carries a
  file-ownership edge on **R1** (`campaign-mode.md`, `# file:
  campaign-mode.md`).
- **R4** depends on **R1** (`depends_on`/`merged_commit`) and **R2** (lease
  mechanism).
- **R5a** (the flip: per-unit worktrees go live, wave model, brief-parameter
  redesign) depends on **R3** (diff-fix merged) and **R4** (state mechanics,
  canonical state root).
- **R5b** (merge lane: pin/verify, staleness cascade, STRICT-STOP) depends
  on **R5a**.
- **R6** (capstone) depends on **R5b**.

---

## R1 — `depends_on` schema, `campaign_graph.py`, campaign-design conversation, resume-safe readiness

### New module: `shared/scripts/lib/campaign_graph.py`

**v5, new — closes a bloat-budget gap:** `campaign_status.py` is already 299
of its own 300-line limit with no baseline entry (a first crossing isn't
blocked by the pre-commit hook, but lands as an unplanned Group H detective
finding post-merge). The id/slug charset predicate and
`validate_dependency_graph` move into their own module instead:
- `id_charset_ok(value: str) -> bool` — `[A-Za-z0-9._-]`, bounded length
  (64), no leading/trailing separator, no `..` segment, no literal `--`
  (reserved as the campaign-slug/unit-id path separator — see R2).
- `validate_dependency_graph(rows: list[dict]) -> list[str]` — pure,
  structural: duplicate ids, every referenced id exists, no self-dependency,
  no cycle (any length), **plus** a charset check whose *severity* is
  caller-controlled (see below) — reject the whole write on any structural
  violation (duplicates/existence/self-loop/cycle are always hard errors,
  everywhere); a charset violation is returned as a distinct, separately-typed
  finding so callers can choose hard-reject vs. warn.
- `check_frozen_contracts(rows: list[dict], loop_state_units: list[dict]) ->
  list[str]` — a unit whose row status is anything other than `pending`
  cannot have its `depends_on` changed from what's recorded on its
  `loop_state.json` row; a violation names the unit and reverts to the
  frozen value for scheduling purposes rather than failing the whole
  campaign (see `cmd_next_batch`'s exit-4 handling below, R4).
- `safe_project_campaign_status(campaign_dir: Path, events_log: Path) ->
  tuple[dict, dict]` (v6, moved here from `campaign_status.py` — closes a
  round-6 finding that the original bloat mitigation was illusory, since
  these three validators were never what was growing that file;
  `safe_project_campaign_status`'s own body — parsing plus validation — was.
  Living beside the validators it wraps also fixes a second finding: its
  signature now genuinely mirrors `regenerate_campaign_status`'s
  `tuple[dict, dict]` return, `(status, summary)`, with `warnings` and
  `degraded_reason` living in `summary` exactly where
  `campaign_progress.py`'s existing caller already expects them, rather than
  inventing a new flat-`dict` shape that caller can't consume) — wraps
  `parse_campaign_skeleton` + `validate_dependency_graph` (structural: hard
  error; charset: warning) + `check_frozen_contracts`. On a structural
  violation, returns the **last successful** `status.json` projection
  verbatim plus a `warnings` entry and `degraded_reason` in `summary` —
  **never** a new top-level `status` token (that enum is also consumed by an
  out-of-scope WebUI repo). On a `check_frozen_contracts` violation for a
  specific unit, that unit's row reverts to its frozen `depends_on` for
  scheduling and a `warnings` entry names it — **the rest of the campaign
  schedules normally**; a single bad edit no longer bricks unrelated DAG
  branches (v5 fix — v4's exit-4 would degrade the whole projection for this
  case).

**Import convention (v6, new — closes an ADR-045 lib-collision risk):**
`campaign_graph.py`, and the sibling `loop_state.py`/`loop_claim.py` modules
R4 adds, are always imported as `lib.<module>` — matching
`campaign_status.py`, `worktree_location.py`, and `campaign_session_lock.py`
— **never** as a bare sibling import the way `autonomous_loop.py` imports
`branch_base`/`file_lock` today. Two module objects for one file would
silently break the module-object monkeypatching this plan's own test
strategy relies on for the diff-coverage gate. `campaign_init.py` (which
imports nothing from `shared/` today) gets the same `sys.path` bootstrap
`campaign_progress.py` already uses.

Imported by `campaign_status.py`, `campaign_init.py`, and `loop_claim.py`
(R4).

### Files to create/modify
- `shared/scripts/lib/campaign_graph.py` (new, above).
- `plugins/shipwright-iterate/scripts/tools/campaign_init.py` — accept
  `depends_on` per sub-iterate; call `validate_dependency_graph` at write
  time with charset treated as a **hard reject** (new rows only — this is
  where "canonical" is actually enforced; `stacked` `branch_strategy` gets a
  **warning**, not a rejection, suggesting `depends_on` instead — see the
  `branch_strategy` reconciliation below).
- `shared/scripts/lib/campaign_status.py::parse_campaign_skeleton` —
  **header-indexed** column lookup (with a legacy positional fallback for a
  table with no header row), so adding `depends_on` doesn't silently
  misalign existing columns. **Stays structural-only with respect to
  validation** — it does not call `validate_dependency_graph` — but it does
  **extract** the `depends_on` cell into each skeleton row regardless (the
  "structural-only" distinction is about validation, not what fields get
  read; `project_campaign_status` needs the field present on the row to
  carry it through). Cell grammar: comma-separated bare ids; empty cell =
  `[]`; markdown emphasis stripped per token, matching `_strip_md`'s existing
  treatment of id/slug cells.
- `shared/scripts/lib/campaign_status.py` — **no longer hosts
  `safe_project_campaign_status`** (v6, moved to `campaign_graph.py` above —
  this file stays at its own 300-line limit); its only R1 additions are the
  `parse_campaign_skeleton` rewrite and `project_campaign_status`'s carry-
  through, both below.
- `shared/scripts/lib/campaign_status.py::project_campaign_status` — carry
  `depends_on` and `merged_commit` (R4) into each `status.json` sub-iterate
  entry.
- `shared/scripts/lib/loop_state.py` (**new module — see R4's bloat note**;
  R1's share of it) — `_load_units_from` moves here with three fixes: add
  `depends_on` to its fixed key set (previously dropped silently); retain
  **every** unit for the life of the campaign (never drop a row); and map
  `status.json` terminal statuses onto unit statuses explicitly —
  `complete → merged` (with `merged_commit` populated from a fresh,
  fetch-then-verify ancestry check against `origin/{default}`, never trusted
  blindly — v5 fix, see R4), `failed`/`escalated → failed` (recoverable only
  via `cmd_mark`). An id that legitimately doesn't exist (typo, cross-campaign
  reference) is rejected at parse time above, not here.
- **Readiness reads the live `campaign.md` projection, refreshed per-pending-unit
  (v5, specified — was ambiguous in v4):** on every `cmd_next_batch` call
  (R4) — and on `cmd_next`'s own narrow guard clause below — `depends_on` is
  refreshed onto each `pending` unit's row from
  `safe_project_campaign_status`'s current projection; a refresh that would
  change a **non-**`pending` unit's row is rejected by `check_frozen_contracts`
  and that unit keeps its frozen value (above). This is what makes "a
  pending unit's dependencies remain freely editable" actually true.
- **Ownership split, stated explicitly (v5, closes a sequencing gap — R4's
  `cmd_next_batch` doesn't exist yet when R1 builds, so R1 cannot be
  modifying it):** R1 adds the pure readiness predicate —
  `loop_state.py::is_unit_ready(unit, all_units) -> bool` (all deps
  `merged` with verified `merged_commit` ancestry) and a
  `describe_blocker(unit, all_units) -> str` helper naming the specific
  blocking unit/edge — as standalone, independently-testable functions.
  `shared/scripts/lib/autonomous_loop.py::cmd_next` (the existing,
  single-unit command) is **left untouched at the interface level** — no new
  flag, no new exit code, `kind == "section"`'s exact contract preserved —
  **except for one narrow, `kind == "sub_iterate"`-gated guard clause added
  in this same sub-iterate (v6, new — closes an interim-window ordering
  hazard round 6 found):** inside `cmd_next`'s existing FIFO selection loop,
  a `pending` unit for which `is_unit_ready` returns false is skipped in
  favor of the next candidate, exactly as if it weren't there. Without this,
  a campaign run in the window between R1 merging and R4 merging (each is
  its own separately-merged sub-iterate) would have zero `depends_on`
  awareness — the very ordering guarantee the schema exists to provide from
  day one. R4's new `cmd_next_batch` (in `loop_claim.py`) is the only place
  the new **`--campaign-dir`** argument and exit code `4` are wired in,
  gated `kind == "sub_iterate"`. Exit `2` must mean the campaign actually
  finished.
- **v5, R1's own bloat budget (was only stated for R4):**
  `shared/scripts/lib/autonomous_loop.py` is pinned at limit 300 / current
  436 / `grandfathered` — zero headroom. R1 must leave it **at or below 436
  lines**; the `_load_units_from` extraction into `loop_state.py` pays for
  most of this, and `cmd_next`'s own guard clause above is a few lines,
  calling into `loop_state.py::is_unit_ready` rather than duplicating any
  logic locally. New tests
  go into new test files — `shared/tests/test_autonomous_loop.py` is
  separately pinned at 442, same zero headroom.
- `references/campaign-mode.md` — document the column, cell grammar,
  charset rule (hard at write, warning at read), frozen-on-claim rule and
  its per-unit (not whole-campaign) degradation, the new exit code, and the
  degraded side-channel. Add the campaign-design conversation (decompose →
  for each pair, ask "does X need Y first") to the campaign setup step,
  populating `depends_on` there. **Document the cost of a `depends_on` edge**:
  the dependent cannot start until the dependency has *merged* (a full CI +
  review + merge cycle) — an edge should reflect a genuine need.
- **`branch_strategy` reconciliation (v5, new — external review finding):**
  once a unit has any `depends_on` entries, its base ref is derived from its
  dependencies' `merged_commit`s (R4's ancestry-assert), and
  `branch_strategy` plays no role for that unit. A unit with empty
  `depends_on` keeps today's `branch_strategy` resolution unchanged.
  `stacked` is deprecated (superseded by explicit `depends_on`); a new
  campaign choosing it gets a warning suggesting `depends_on` instead, not a
  rejection (existing campaigns using `stacked` are unaffected — out of
  scope to migrate). `single-branch` strategy is orthogonal (one unit of
  work) and unaffected.
- **Exit-code loop-action table (v5, new — closes an unspecified-orchestrator-
  reaction gap; lives in `campaign-mode.md` step 3a, extended by R4/R5b):**
  `2` → Finalize. `4` → **fires only once the ready set is already empty
  while `pending` units remain** — by construction at that point every
  independent branch has already been scheduled in an earlier wave, so the
  remaining `pending`/`claimed` units are exactly `describe_blocker`'s
  transitively-blocked set, never an unrelated independent branch (v6,
  reworded — two separate reviewers read the original "sweep every
  pending/claimed unit" phrasing as bricking unrelated DAG branches; it
  can't, given when it fires, but the phrasing was genuinely ambiguous).
  Sweep that set to `held` (`reason_code: "swept_never_started"`, R4's new
  edges — R5b maps this back to `pending` at step 3h, not `failed`), name
  the blocker to the operator, then Finalize. `5` (at `cmd_record`) →
  discard that unit's payload, apply the reclaim rule to it, continue
  processing the rest of the wave — never a loop-level stop. `6` (R4) → one
  bounded retry, then a LOCK-LOST-style stop with no state write.

### Explicitly out of scope for R1
Per-unit `mode`/guided-vs-autonomous merge policy — descoped; not touched
here.

### Work breakdown
1. `campaign_graph.py`: `id_charset_ok`, `validate_dependency_graph`,
   `check_frozen_contracts` — pure functions, unit tests first (including a
   charset test against `R0`/`15.0`/`14.2`/`p3.8` all passing).
2. `campaign_init.py` calls `validate_dependency_graph` at write time
   (charset hard, structural hard); `stacked` warning.
3. `parse_campaign_skeleton` header-indexed rewrite + legacy fallback +
   `depends_on` extraction (no validation call) — regression test: an
   existing campaign.md with no `depends_on` column parses unchanged.
4. `safe_project_campaign_status` (charset warning / structural hard-error /
   per-unit frozen-contract revert) + `project_campaign_status` carrying
   `depends_on`/`merged_commit` through.
5. `loop_state.py::_load_units_from` (key set + retain-all + terminal
   mapping, incl. `merged_commit` population and the fresh-fetch ancestry
   verification for a migrated `complete` row — cross-referenced with R4).
6. `cmd_next`'s narrow guard clause (ancestry-verified `is_unit_ready` skip,
   no new flag/exit code) — test: dependent unit skipped when its
   dependency isn't `merged`, independent unit still claimed FIFO, and a
   `kind == "section"` regression test proving no new required
   argument/exit code reaches build's loop. (`cmd_next_batch`'s exit `4` +
   `--campaign-dir` are R4's work — see R4's own file list; not built here.)
7. Doc updates: cell grammar, charset scoping, `branch_strategy`
   reconciliation, exit-code table, campaign-design-conversation prose.

### Test strategy
- Unit tests for each numbered step above, in new test files (never
  `test_autonomous_loop.py`).
- `category:"integration"` behavior (required, `cross_component`): a
  three-unit campaign (`A`, `B` depends on `A`, `C` independent) run through
  `campaign_init` → `cmd_next`'s guard clause end to end across a simulated
  resume (v6, confirmed buildable against the guard clause added in step 6
  above — a round-6 finding flagged this test as routing through a command
  R1 no longer touches; it doesn't, once `cmd_next` carries its own
  `is_unit_ready` check), proving `B` waits for `A`'s verified
  `merged_commit` ancestry to survive the
  reload and `C` is never blocked by it; a second scenario edits `B`'s
  `depends_on` after `B` is claimed and asserts only `B` degrades, `A`/`C`
  unaffected.

### Alternative approach considered — rejected
Store `depends_on` only in `status.json` (skip the campaign.md column).
Rejected: `campaign.md` is what the operator and the design conversation
read and edit; the source of truth belongs there.

---

## R2 — per-unit worktree CAPABILITY + liveness (does not flip the live loop — see R5a)

**v5: rescoped to capability-only.** v4 flipped `campaign-mode.md`'s live
steps onto per-unit paths in this sub-iterate, but the fields those paths
need (`worktree`, `branch`, `attempt_id`) aren't minted until R4's claim,
and the canonical (non-cwd-relative) state root is also R4's — flipping
here would break `cmd_record`'s `result.json` fallback the moment
`{project_root}` becomes a per-unit worktree, before R4 exists to fix it.
R2 now builds the guard mode, the lease mechanism, and the worktree wrapper
as capabilities; **R5a performs the actual flip**, once R4 exists.

**"Capability-only" scopes specifically to the worktree/branch *checkout*
path — not to the lease-touch wiring below, and the claim that this wiring
needs "no further change at R5a" only holds once the following is fixed
(v6, correcting a round-6 finding that the original framing was factually
wrong on two counts, both code-verified):** the campaign session lock file
and `loop_state.json` both live under the **campaign** worktree's
`.shipwright/` (`campaign_session_lock.py`'s `_state_path`;
`campaign-worktree.md`), never the runner's own `{project_root}` — which is
already true today (the runner's `{project_root}` *is* the campaign
worktree, pre-flip) but becomes false the moment R5a repoints it to the
per-unit worktree. Resolving a lock/state path off `{project_root}` would
then raise `CampaignLockError` on every runner in every wave, exactly where
this section claims to be the **sole** liveness coverage. **Fixed: R2
introduces two explicit brief parameters, `campaign_worktree` and
`state_path`, from the start** — populated with the campaign worktree's own
path (identical value pre- and post-flip), reused unchanged by R5a's
`cmd_mark_running` call and `result.json` write and by R5b's
`cmd_mark_merged` call, so no further brief-parameter change is needed at
R5a. (The prior framing also misdescribed unit identity as coming from
`SHIPWRIGHT_LOOP_UNIT_ID` — the runner never reads that variable; it
receives `sub_iterate_id` in its brief today. That variable's actual
consumers, and what happens to them, are enumerated in R5a.) Because R2 is
independent of R1 in the DAG (no `loop_state.json` row is guaranteed to
carry lease fields yet, and `_load_units_from`'s fixed key set doesn't mint
them), the toucher is specified as a **field-creating upsert**, and **no
fencing-token validation applies to it until R4 adds fencing** (R4's own
invariant list covers every *other* claim mutation; the lease touch is
explicitly the one exception, stated here to avoid a builder over-applying
R4's check to a field nothing yet writes). A touch that still fails
(lock released early, reclaimed past `DEFAULT_STALE_AFTER_SECONDS`, or the
worktree recreated) is specified as **warn-and-continue, never fatal** — the
orchestrator's own step-3a/3g touches remain the authoritative lock-lost
detector; aborting a near-finished build over a heartbeat hiccup is strictly
worse than the staleness risk being mitigated.

The guard is a **mode**, not an "either form" OR (an OR would let a runner
legally sit in the shared campaign worktree — exactly the race per-unit
worktrees exist to remove): the orchestrator's own step-3c check validates
only the campaign path; the runner's own isolation check (its contract's
Step 1.0) validates only its own unit path. `worktree_location.py`'s
existing `expected_campaign_slug` parameter already supports a composite
value (`"{slug}--{unit_id}"`) with **zero code change** to the guard itself
— this is call-site wiring, not new guard logic.

### Files to create/modify
- `references/campaign-worktree.md` — document the per-unit path form
  (`.worktrees/campaign-{slug}--{unit_id}`, `-a{n}` suffix only for a retry
  attempt ≥ 1 — R4), correct the doc's description of the session lock
  (liveness heartbeat; `status.json`/`loop_state.json` guarded separately by
  `loop.lock`), and **name the lease toucher explicitly as the runner
  itself**: the `sub-iterate-runner` subagent calls both its own per-unit
  lease touch and the campaign-session-lock touch at its own step
  boundaries, using the `campaign_worktree`/`state_path` brief parameters
  (new, v6 — see above) and the `session_id` it already receives in its
  brief (v5 fix: the lock's `touch()` validates `existing["session_id"] ==
  session_id` against the *orchestrator's* `$SHIPWRIGHT_SESSION_ID` — the
  runner must use that value, not its own subagent identity, or every touch
  raises `CampaignLockError`). State `DEFAULT_STALE_AFTER_SECONDS = 7200`,
  that under the wave model (orchestrator blocked for the whole wave) the
  runner's touch is the **sole** coverage, not merely better coverage, and
  that a failed touch is **warn-and-continue** (v6, new — never aborts the
  runner's build).
  Also state explicitly that campaigns keep using this narrow location
  guard rather than the full `check_iterate_isolation.py` leak-guard even
  once per-unit worktrees carry their own run-pointer/main-tree snapshot —
  step 3h's main-tree `status.json` write (the thing that would trip the
  full guard) is unaffected and stays the campaign worktree's alone (v5,
  new: **single-writer invariant** — campaign-level `status.json`
  regeneration happens only in the campaign worktree, orchestrator or churn
  resolver; a per-unit worktree's runner writes only its own per-unit
  iterate artifacts, never the shared `status.json`, enforced by the same
  isolation guard).
- `shared/scripts/checks/check_campaign_session_lock.py` (naming precedent
  already in this directory) or a sibling module — per-unit lease fields
  (`attempt`, `attempt_id`, `lease_touched_at`, `lease_expires_at`,
  `worktree`, `branch`) live on the unit's own row in `loop_state.json`,
  guarded by the existing `loop.lock`/`file_lock` — not a second state file.
  The toucher is a **field-creating upsert** (v6, new — R2 is independent of
  R1, so a row may not yet carry these fields) and applies **no
  fencing-token validation** (R4 adds that for every other claim mutation;
  this touch is the explicit exception until then).
- **New brief parameters, `campaign_worktree` and `state_path` (v6, new —
  closes a round-6 finding that the runner had no resolvable path to either
  the lock file or `loop_state.json` once R5a repoints `{project_root}`)**:
  both resolve to the campaign worktree's own path, unchanged by the flip;
  introduced here rather than at R5a so R5a needs no further brief-parameter
  change, and reused as-is by `cmd_mark_running` (R4/R5a) and
  `cmd_mark_merged` (R5b).
- `shared/scripts/tools/setup_iterate_worktree.py` or a thin new wrapper —
  reuse its fresh-fetch/gitignore/cleanup behavior for a per-unit checkout
  at the sibling path (built here, wired live in R5a).
- **Security hardening (v5, new):** the guard and wrapper always recompute
  the expected worktree/branch path from validated `(slug, unit_id,
  attempt)` rather than trusting a stored path value for any destructive
  operation, and enforce that the resolved path stays under the approved
  worktree root — reused by R4's cleanup paths.
- **Total path-length bound (v6, new — closes a Windows finding):** id
  length is bounded (64, R1) but total path length isn't — a real ~35-char
  slug plus `campaign-` plus a 64-char id plus an `-a{n}` suffix, under this
  repo's own nested `.worktrees/` structure, can reach Windows' `MAX_PATH`
  (260) on the stated primary dev platform. The wrapper computes the full
  path length before calling `git worktree add` and fails loudly with a
  clear message (naming the campaign slug and unit id) rather than letting
  `git` fail mid-checkout with an opaque error.

### Work breakdown
1. Call-site wiring for the composite `expected_campaign_slug` (guard-mode,
   not OR) + unit tests (a directory merely starting with the same string
   is still rejected; recomputed-vs-stored path mismatch is rejected).
2. Per-unit lease/heartbeat mechanism + unit tests.
3. Runner-side step-boundary touches for both its lease and the campaign
   session lock, using the new `campaign_worktree`/`state_path` brief
   parameters and the orchestrator's `session_id`; a failed touch is
   warn-and-continue, never fatal to the build.
4. Worktree lifecycle wrapper for a per-unit checkout at the sibling path
   (built, not yet wired live).
5. Doc corrections in `campaign-worktree.md`.

### Test strategy
- Unit tests above.
- `category:"integration"` behavior: two per-unit worktrees created
  concurrently at sibling paths for the same campaign slug; a campaign-level
  `git clean -xfd`/`git add -A` does not touch either sibling; both leases
  held/touched independently; N concurrent runner touches against one lock
  file all succeed (serialize on `file_lock`); a runner using the wrong
  `session_id` is rejected by `CampaignLockError`; a lease-touch upsert
  against a row with no lease fields yet creates them without error; a
  simulated lock failure during a touch is confirmed non-fatal to the
  runner's own build.

### Alternative approach considered — rejected
A second lock tier layered on the existing session lock. Rejected: the
session lock does not guard the state files that would need a second tier.

---

## R3 — fix the review-diff corruption path (depends on R2; fallback-safe until R5a's flip; file-ownership edge on R1)

**Why this comes before scheduler concurrency:** shipping concurrency before
this fix means the pre-merge review gate can silently attribute a review to
the wrong unit's branch. **v5: this sub-iterate can ship and be fully
tested before R5a's live flip** — `check_review_attribution.py` falls back
to the shared campaign worktree when a unit's row carries no `worktree`
field yet, and defaults `attempt_id` to `a{unit['attempt']}` when absent, so
its own tests construct per-unit fixtures directly rather than depending on
the live flip having happened.

`R3 depends_on R1`, file-ownership edge only (`campaign-mode.md`, annotated
`# file: campaign-mode.md`).

### Files to create/modify
- `references/campaign-mode.md` step 3f-bis — name every call site that
  must become unit-scoped: the diff itself, `run_dir`, `reviewed_head`, the
  `git add`/`commit`/`push` of `reviews.json` (all as `git -C
  <unit-worktree>`, falling back to the campaign worktree per above),
  `record_review_pass.py --payload-file`'s root, and the `gh pr view` branch
  resolution. Same set for 3g. **v5, closes the unpinned-merge window:**
  keep writing the legacy `$run_dir/reviewed_head` file (one extra line)
  alongside the new `review_pin.json`, so 3g's existing `[ -f
  "$run_dir/reviewed_head" ] && head_pin=…` continues to work unchanged
  until R5b rewrites 3g to read the replacement directly. **Acceptance
  criterion, explicit:** no campaign PR merges without `--match-head-commit`
  at any point during or after this sub-iterate.
- `shared/scripts/checks/check_review_attribution.py` (new) — hashes
  content, not identity. Two modes:
  - `--mode pin`: resolves the unit's `worktree`/`branch`/`attempt_id` from
    `loop_state.json` (falling back to the campaign worktree / `a{attempt}`
    default per above); asserts the checked-out branch matches; records
    `HEAD` as **`reviewed_head`**; computes `base_sha = merge-base
    origin/{default} HEAD` **at pin time only, never recomputed at verify
    time**; writes `runs/{loop_id}/{unit_id}/a{n}/review_pin.json` =
    `{unit_id, attempt_id, branch, worktree, reviewed_head, base_sha,
    diff_sha256, shipped_head, pinned_at, review_skipped, pr_node_id,
    pr_head_ref, pr_base_ref}`. **v5: `shipped_head` is part of the schema
    from the start** (was missing in v4); for `review_skipped: true`, it is
    set equal to `reviewed_head` at pin time (uniform for R5b's point 4 —
    see below). **`diff_sha256` is an evidence field, not a gate** (v5,
    demoted — nothing actually checks it as specified; stated explicitly so
    a builder doesn't invent an unneeded check). `pr_node_id`/`pr_head_ref`/
    `pr_base_ref` (v5, new) persist the PR's identity so it is never
    re-resolved by branch name alone.
  - `--mode verify --expect-file review_pin.json --against
    {reviewed_head|shipped_head}`: asserts the named field is still the
    branch's actual tip (or, for `shipped_head`, that the review-record
    commit's parent is `reviewed_head`) — an ancestry check against a
    **pinned** value, never a fresh recompute of `base_sha` against a moving
    `origin/{default}` (staleness is triggered only by an actual rebase
    action — see R5b). **This is the single detection path** for every
    branch-change route (rebase, manual push, PR base change, a failed
    merge-time check) — there is no second implementation to keep in sync.
  - **`review_skipped: true`**: `--mode pin` runs unconditionally at
    3f-bis's top even for a below-threshold unit that skips the review
    cascade, so `built → merging` (R4) always has a pin to verify at merge
    time.

### Work breakdown
1. **Reproduce first, as a failing test**: two per-unit worktrees with
   different diffs; simulate today's 3f-bis logic and assert it computes
   the wrong one's diff.
2. Fix every named call site to be unit-scoped, with the shared-worktree
   fallback.
3. Add `check_review_attribution.py` (`--mode pin` / `--mode verify`,
   including `review_skipped` and the legacy-file dual-write).
4. Re-run step 1's test green; add the "no PR merges unpinned" acceptance
   test.

### Test strategy
- The reproduction test (red → green).
- Guard's own unit tests (pin/verify on an untouched branch passes; a
  commit added after pinning, or a rebase, is detected; review-skipped pin
  verifies correctly at merge time; fallback-to-shared-worktree behavior
  when `worktree` is absent from the row).

### Alternative approach considered — rejected
Serialize step 3f-bis itself instead of fixing the diff source. Rejected:
reintroduces a serial bottleneck and still requires knowing which unit's
diff is "current" — the same fix, done reactively.

---

## R4 — concurrent state mechanics (state machine, fencing, atomic claim, lease-based reconcile — restated for the wave model)

**Depends on:** R1, R2. Deliberately does not touch review or merge.

**v5: this sub-iterate's mechanics are restated against the wave model**,
not the continuous scheduler v3/v4 assumed. Bloat-baseline extraction is
still load-bearing: `autonomous_loop.py` is pinned at limit 300 / current
436 / `grandfathered` (zero headroom); mechanics go into two new modules —
`shared/scripts/lib/loop_state.py` (state machine, `_load_units_from`,
lease fields, `_reconcile_in_progress`) and `shared/scripts/lib/loop_claim.py`
(`cmd_next_batch`, atomic claim, `cmd_release`, `cmd_mark`, **`cmd_mark_running`**
— the `claimed → running` promotion R5a's runner calls at its own Step 1.0.5,
built here since it shares the same fencing-token validation as every other
claim mutation — and **`cmd_mark_merged`** (v6, new — the `merging → merged`
write R5b's step 3g point 5 calls with a verified merge-commit SHA; neither
`cmd_record` nor `cmd_mark` can correctly express this transition, see R5b
for why) —
`autonomous_loop.py` becomes a thinner dispatcher and must **shrink**. New
tests go into `test_loop_state.py`/`test_loop_claim.py`, never the
pinned `test_autonomous_loop.py`.

**`kind == "section"` compatibility, restated to cover semantics, not just
arguments (v5 fix — v4 gated arguments/exit codes but two of the riskiest
changes are behavioral):**
- `cmd_init`'s resume/reinit fix (below) applies **only** for `kind ==
  "sub_iterate"`. For `kind == "section"`, today's literal fallthrough
  (reinit whenever nothing is `pending`/`in_progress`) is preserved exactly.
- `_reconcile_in_progress`'s lease-based-only reconciliation (below) applies
  **only** for `kind == "sub_iterate"`. For `kind == "section"` (which never
  acquires a lease), today's two salvage paths plus the reset-to-pending
  fallback are preserved exactly.
- R4's regression test (work breakdown step 12) is a full **behavioral**
  sequence — init → next → record → crash → init-resume → finalize — for
  `kind == "section"`, asserting every return value and unit status matches
  pre-change, not merely that no new argument/exit-code reaches it.

### The unit state machine

**States:** `pending`, `claimed`, `running`, `built`, `reviewed`, `merging`,
`merged`, `failed`, `held`. `blocked` is derived, never stored.

**Edges:** each `→ held` edge below carries a `reason_code` (v6, new —
consumed at the R5b/step-3h status-mapping boundary to distinguish a unit
that never got to run from one demoted mid-flight, see R5b).
- `pending → claimed` (atomic claim) | **`→ held`** (v5, new — STRICT-STOP
  drain sweep, `reason_code: "swept_never_started"`)
- `claimed → running` (runner's own Step 1.0.5 promotion — v5, moved from
  the orchestrator) | `→ pending` (launch-failure release, no attempt
  re-bump) | `→ failed` (attempt budget out) | **`→ held`** (v5, new —
  drain sweep for a unit claimed but never promoted before STRICT-STOP,
  `reason_code: "swept_never_started"`)
- `running → built` (runner finished) | `→ failed` | `→ pending` (lease
  expired at a wave boundary/`cmd_init`, budget left — next claim
  increments `attempt`) | `→ held` (drain, `reason_code:
  "swept_after_build"`; or `max_drain_seconds` timeout maps instead to
  `running → failed`, `reason_code: "drain_timeout"`, per R5b)
- `built → reviewed` (3f-bis pin+review) | `→ merging` (review-skipped path)
  | `→ failed` (Stage-1 REJECT) | `→ held` (drain, `reason_code:
  "swept_after_build"`)
- `reviewed → merging` (3g starts, only once branch is current and pin is
  fresh — v5, states explicitly where the currency check sits) | `→ built`
  (rebase demotion) | `→ held` (drain, `reason_code: "swept_after_build"`)
- `merging → merged` (PR merged, via `cmd_mark_merged` with a verified
  `merged_commit` — v6, R5b) | `→ held` (CI red / conflict / timeout /
  mid-merge staleness discovery, `reason_code` names which) | `→ failed`
- **`held → pending`** (operator-initiated resume via `cmd_mark`, or the
  natural re-entry point after a `merging → held` staleness demotion —
  re-claim mints a fresh attempt, counted against `max_rebase_reviews`).
- `merged` is the only terminal *success* state. **`TERMINAL = {merged,
  failed, held}`** — `cmd_finalize` (below) refuses only outside this set.
- `cmd_mark` may cross any edge, always audited.

### Fencing: single writer, hyphen-based, cross-session-only reclaim

Claim is the **only** writer of `attempt`. First claim: `attempt = 0`, per-unit
sibling path (`.worktrees/campaign-{slug}--{unit_id}`, no `-a{n}` suffix —
every unit is isolated from its first attempt; scoping only disambiguates
retries). A reclaim (`running → pending`, evaluated only at a wave boundary
or `cmd_init`) does not bump `attempt`; the **next claim** of that
now-`pending` unit increments it and mints `attempt_id =
f"{loop_id}-{unit_id}-a{attempt}"` (hyphen-based — a colon is NTFS
alternate-data-stream syntax on Windows, this project's primary dev
platform) inside `loop.lock`. Used directly as the path segment:
- worktree: `.worktrees/campaign-{slug}--{unit_id}` (attempt 0) or `-a{n}`
  (attempt ≥ 1)
- branch: `iterate/campaign-{slug}-{unit_id}-{desc}` (attempt 0) or
  `-a{n}-{desc}` (attempt ≥ 1)
- run dir: `runs/{loop_id}/{unit_id}/a{attempt}/result.json`

**No `DONE` marker for `kind == "sub_iterate"` (v5, new — see the plan's top
changelog).** The runner receives `unit_id`/`attempt_id`/`worktree`/`branch`
explicitly in its brief (not via `SHIPWRIGHT_LOOP_UNIT_ID`, which is
single-valued and session-scoped, incompatible with N concurrent runners)
and writes `result.json` to the path above using those values directly.
R5a reads every wave unit's `result.json` once the whole wave's `Task`
calls return — the return itself is the completion signal. Build's `kind
== "section"` path is unaffected: `write_terminal_marker.py` and the
`SHIPWRIGHT_LOOP_UNIT_ID` export stay exactly as they are.

**Reclaim/cleanup split (unchanged from v4):** reclaiming a lease is
immediate and purely logical; physical cleanup (`git worktree remove` /
`git branch -D`, always **recomputed from validated `(slug, unit_id,
attempt)`**, never a stored path — v5 security hardening) is best-effort and
never blocks; a Windows file-lock failure is swept by `git worktree prune`
at the next claim.

**Fencing invariant:** every mutation of a claimed-or-later unit —
`cmd_record`, the runner's own `claimed → running` promotion, `cmd_release`,
lease touch/reclaim, and every write/delete of `review_pin.json` — validates
`(unit_id, attempt_id)` against the current `loop_state.json` row before
writing, under `loop.lock` (or, for the pin file, via its own token check).
A mismatch is a stale-attempt rejection:
- `cmd_record` — new **required** `--attempt-id` (gated `kind ==
  "sub_iterate"`); mismatch → exit `5`, `stale_attempt`, state untouched,
  rejected payload to `runs/{loop_id}/{unit_id}/rejected/{attempt_id}.json`.
- The runner, immediately before its F6 commit / step-5 push, calls
  `check_unit_attempt.py --state … --unit X --attempt-id T`; non-zero aborts
  with `status: "failed", reason_code: "stale_attempt"`, no push.
- 3f-bis's review-record commit and 3g's merge both re-check the token.

### `cmd_mark` — the one audited operator override

`mark --unit X --status <state> --reason "<text>" --operator <id>`. Legal
only from a quiescent unit; `running`/`merging` require `--force` plus the
existing "confirm no Task is running against this worktree" acknowledgement.
`--status merged` requires `--merged-commit <sha>`; the check performs a
**fresh `git fetch origin`** (or reuses `fresh_remote_default_ref()`) before
verifying the sha as an ancestor of current `origin/{default}` — a stale
local ref must never falsely reject or falsely accept. `--reason`/`--operator`
are length-capped and reject control characters (the real surface is a
markdown-table or shell-`export` rendering of this data downstream, not the
JSON file itself, which escapes safely — restated rationale, v5). This is the
only supported way to unblock a permanently-`failed` dependency, besides
editing `campaign.md` to drop the edge (legal only while the dependent is
still `pending`, per R1's frozen-on-claim rule).

### `loop_state.json` schema and the v1→v2 boundary

Add `"version": 2`. v2 is an additive superset of v1's row shape — a v1
reader degrades to today's serial-FIFO selection, ignoring `depends_on` and
leases. This guarantee is scoped to `cmd_next`'s selection logic only; true
mixed-binary safety across every v1 code path (e.g. v1's own
`_reconcile_in_progress`) is out of scope, accepted given this project's
one-plugin-cache-version-at-a-time model.

**Live-campaign upgrade procedure:** a campaign lacking `"version": 2`
finishes under the plugin version that started it. To move it: drain to
`TERMINAL`, **snapshot** `loop_state.json` (copy, not delete) for forensic
reference, delete the live file, re-run `init` (rebuilds from `campaign.md`
+ `status.json`, mapping `complete → merged` with a verified
`merged_commit` per R1's fix). **v5, the v1-stopped-campaign variant
(explicit — `held` did not exist in v1, so a v1 campaign interrupted
mid-flight has no clean drain path):** snapshot, delete, re-init, then
hand-`cmd_mark` each interrupted unit to `merged` (with a fetched-and-verified
`--merged-commit`) or `failed`, based on manually inspecting that unit's
actual PR state on GitHub. Same procedure serves as rollback.

### `cmd_init` — resume/reinit fixed (gated `kind == "sub_iterate"` only)

Today's `cmd_init` reinitializes (mints a new `loop_id`, resets every unit to
`pending`) whenever no unit is `pending`/`in_progress` — under the new
vocabulary that's the normal mid-wave state (`built`/`reviewed`/`merging`
exist). Fixed, **for `kind == "sub_iterate"` only**: `ACTIVE = {claimed,
running, merging}` (resume in place), `RESUMABLE = {pending, built,
reviewed, held}`, reinit only when the unit list is genuinely empty.
`kind == "section"` keeps today's exact fallthrough.

### `_reconcile_in_progress` — lease-based, gated `kind == "sub_iterate"` only

For `kind == "sub_iterate"`: replace "missing result file = crashed" and the
old salvage paths with lease-expiry-only reclaim, evaluated at wave
boundaries/`cmd_init`. If a `head_sha` diagnostic is still wanted, capture it
at claim time as `git -C <campaign-worktree> rev-parse origin/{default}`
(the unit's actual resolved base), never a bare call against the shared
worktree. For `kind == "section"`: today's two salvage paths and
reset-to-pending fallback are preserved exactly, unchanged.

### Ready-set claiming, lock timing, and `cmd_finalize`

- `cmd_next_batch` (`--max-parallel N`, **validated: positive integer,
  framework hard cap** — v5, new, reject zero/negative/non-integer/above-cap):
  computes the full ready set (`all(dep == "merged" and ancestry-verified)`),
  claims `min(max_parallel, |ready_set|)` — **`active_count` is always `0`
  at this point under the wave model** (the prior wave has fully drained
  through the merge lane before the next is claimed); the field stays in
  the data model only as a hook for a possible future cross-wave-pipelining
  increment, not built here. Atomic under `loop.lock`; deterministic
  ordering when the ready set exceeds capacity.
- Resolve the base ref once per batch, **outside** `loop.lock` (today's
  `resolve_base_branch` for `serial` calls a 60s-timeout fetch inside a
  30s-timeout lock — a real starvation hazard); only pure state mutation
  happens inside the lock.
- `LockTimeout` gets exit `6`, `lock_timeout` — **gated `kind ==
  "sub_iterate"`** (v5 fix — a `kind == "section"` caller preserves today's
  unhandled-exception behavior exactly, since build's loop has no branch for
  any new exit code).
- `cmd_release` — launch-failure path: `claimed → pending` (or `→ failed`
  once `max_attempts`, default 3, exhausted); immediate logical release,
  physical cleanup best-effort per the reclaim/cleanup split; no attempt
  re-bump.
- **Dependency ancestry assert (v5, new):** before claiming a unit with
  non-empty `depends_on`, assert `git merge-base --is-ancestor
  <dep.merged_commit> <resolved-base>` for every dependency; if not present
  locally, fetch once and retry; if still absent, leave the unit `pending`
  for the next `cmd_next_batch` call rather than failing the whole batch.
- Canonical state root, not cwd-relative: every path under
  `.shipwright/runs/{loop_id}/{id}` — `cmd_record`, `_reconcile_in_progress`,
  lease checks, `check_unit_attempt.py`, review-pin reads/writes, rejected
  payloads — resolves against one explicit, passed-in state root
  (`state_path`/`campaign_worktree`, R2).
- **Base-ref resolution is threaded the same way (v6, new — closes a gap:
  the canonical-state-root list above named everything except this).**
  `branch_base.py`'s `git symbolic-ref`/`git fetch origin` calls run with no
  `cwd`/`-C`, using the process's own cwd — ambiguous once a per-unit
  worktree exists, and this is the exact mechanism the dependency-ancestry
  assert above resolves `<resolved-base>` through. Either thread a repo root
  into `branch_base.py`, or state as an invariant that `cmd_next_batch`
  always executes with cwd == the campaign worktree; whichever a builder
  picks, it must be stated, not left to whatever the process cwd happens to
  be.
- `cmd_finalize` — refuses while any unit is outside `TERMINAL = {merged,
  failed, held}`; summary counts derive from that set, for `kind ==
  "sub_iterate"` only (build's 5-token counting is untouched).
- **Status-vocabulary boundary:** the 9-state machine is internal to
  `loop_state.json`. `status.json` keeps its existing 5-token vocabulary
  unchanged — `campaign_progress.py`'s argparse enum needs no code change.
  The one mapping point is `campaign-mode.md` step 3h (R5b's file list):
  `merged → complete`; `failed → failed`; `held` maps to `failed` only for a
  mid-flight-demotion `reason_code`, and to `pending` for a
  `"swept_never_started"`/`"swept_after_build"` `reason_code` (v6, corrected
  — see R5b's status-mapping bullet for the full rationale; a flat
  `held/failed → failed` mapping made a stopped-but-healthy campaign's
  never-run units read as failures).

### Work breakdown
1. State machine as data in `loop_state.py`: `is_legal_transition`,
   exhaustively unit-tested against the (now nine-edge-richer) table.
2. `loop_state.py::_load_units_from` moved + fixed (from R1).
3. Ready-set computation with the ancestry assert, bounded by
   `min(max_parallel, |ready_set|)`.
4. `loop_claim.py::` atomic claim, single-writer fencing, `max_parallel`
   validation, `cmd_mark_running` (`claimed → running`, fencing-token checked
   — the command R5a's runner Step 1.0.5 calls), `cmd_mark_merged`
   (`merging → merged`, fencing-token checked, strict-hex-SHA validated —
   the command R5b's step 3g point 5 calls).
5. `cmd_release` / `cmd_mark` (merged-ancestry proof with fresh fetch;
   reason/operator sanitization) + tests.
6. `loop_state.json` v2-as-superset (scoped to `cmd_next` selection) +
   v1-degrades-safely test.
7. `cmd_init` resume/reinit fix, **gated `kind == "sub_iterate"`** — test:
   a mid-wave state resumes in place for sub_iterate; `kind == "section"`
   behavioral-sequence regression test proves no change.
8. Lease-based `_reconcile_in_progress`, **gated `kind == "sub_iterate"`** —
   same dual test structure as step 7.
9. Batch-claim lock-timing fix + `LockTimeout` → exit `6`, gated.
10. `cmd_finalize` `TERMINAL`-based refusal/summary + the 3h status-mapping
    cross-reference (R5b).
11. Canonical state-root threading through every named call site, including
    `branch_base.py`'s base-ref resolution (v6, new — see above).
12. `kind == "section"` full behavioral regression: init → next → record →
    crash → init-resume → finalize, asserting every return value and status
    matches pre-change.

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

---

## R5a — the flip: wave-based concurrent build (depends on R3 + R4)

**This is where campaigns actually move onto per-unit worktrees and the
wave model goes live.** Must not merge before R3 has.

The orchestrator computes the bounded ready set (R4), spawns it as parallel
`Task` calls in one message — each carrying `unit_id`, `attempt_id`,
`worktree`, `branch`, `campaign_worktree`, `state_path` (R2), a
wave-scoped `SHIPWRIGHT_LOOP_UNIT_ID` value (see security note below), and
the orchestrator's `session_id` explicitly in its brief (replaces
per-runner *identity* use of the env-var mechanism for `kind ==
"sub_iterate"`) — and **regains control only once every spawned `Task` in
that message has returned** (the conservative assumption; nothing confirms
the alternative for the runtime a live orchestrator session actually runs
under). Each runner's own first action (Step 1.0.5) is its
`cmd_mark_running --state "{state_path}" --unit "{unit_id}" --attempt-id
"{attempt_id}"` promotion using its own fencing token; the orchestrator
treats any unit still `claimed` at wave-return as launch-failed and calls
`cmd_release`. A unit that returns `running` with no `result.json` written
(the `Task` errored out or exhausted its own turn/step budget rather than
launch-failing outright) is treated the same as a genuine build failure —
demoted to `failed` with whatever diagnostic is available, never silently
re-claimed — since nothing in this design can distinguish "will finish if
retried" from "wedged" once the wave has already returned. Once the wave
returns, results are read directly from each unit's `result.json` at the
canonical state root (no `DONE` marker) and handed to R5b's merge lane in a
fixed order (campaign.md row order).

**Waves serialize on the merge lane (v6, decision — withdraws v5's
"decoupling" claim, see the changelog):** wave N+1's ready set is computed,
and wave N+1 is spawned, only once wave N's units have all been
recorded/reviewed/merged (or held) through R5b's serial merge lane. This is
the honest cost of the wave model: the speedup this plan delivers is
concurrent *building* of independent units within one wave — replacing
today's fully serial, one-unit-at-a-time campaign loop — not overlap
between a wave's merge lane and the next wave's build. A campaign whose DAG
is mostly independent branches still gets most of its benefit (those
branches build together within each wave); a campaign that is a long
dependency chain gets little benefit beyond today's loop, which is the
correct, expected outcome for a chain and not a defect of this design.

**Explicit non-goal:** cross-wave pipelining (starting a newly-ready unit
before the current wave has fully cleared the merge lane) is not attempted —
that would require processing individual `Task` completions mid-turn, which
is unconfirmed and out of scope. A future increment may revisit this once
that capability is confirmed one way or the other.

**Security: `SHIPWRIGHT_LOOP_UNIT_ID`'s consumers, enumerated and
dispositioned (v6, new — closes a round-6 finding that dropping the
variable entirely fails a security control open):**
- `ci_supplychain_authorship_guard.py::refuse_if_campaign_runner_context()`
  refuses a CI-trust-boundary acknowledgment purely on this variable's
  **truthiness**, with no override flag. **Preserved:** the orchestrator
  keeps exporting it for the whole wave, set to a fixed,
  non-identity-bearing sentinel (`"__campaign_wave__"`), so the guard still
  refuses exactly as it does today.
- `_run_id.py`'s tier-3 run-id derivation and `generate_handoff_on_stop.py`'s
  handoff namespacing both need the actual per-unit identity, which a shared
  sentinel cannot provide. **Migrated:** both read the brief-provided
  `unit_id` directly instead.
- `diff_risk_recheck.py` only tests the same truthiness the authorship guard
  does. **Unaffected** by the sentinel value.
- `capture_session_id.py`'s propagation via `CLAUDE_ENV_FILE` is **why a
  per-runner self-export doesn't work** as a workaround — that file is
  rewritten per SessionStart and shared across a session's Bash calls, so N
  concurrent runners exporting their own value would race each other the
  same way N raw env-var values would. The single wave-scoped sentinel,
  exported once by the orchestrator before spawning, is what avoids this.

### Files to create/modify
- `references/campaign-mode.md` steps 3a–3f — the flip: per-unit worktree
  checkout (R2's wrapper), brief-parameter passing (no per-unit-identity env
  var), multi-spawn in one message, full-wave-return wait, fixed-order
  result processing, wave-scoped `SHIPWRIGHT_LOOP_UNIT_ID` sentinel export
  before spawning (security note above).
- `plugins/shipwright-iterate/agents/sub-iterate-runner.md` — Input block
  gains `unit_id`, `attempt_id`, `worktree`, `branch`, `campaign_worktree`,
  `state_path` (session_id already present); Step 1.0.5 (new):
  `cmd_mark_running --state "{state_path}" --unit "{unit_id}" --attempt-id
  "{attempt_id}"`, right after the isolation check, before `checkout -b`;
  Step 6's `result.json` write uses the brief-provided path (canonical state
  root, `runs/{loop_id}/{unit_id}/a{attempt}/`), not
  `SHIPWRIGHT_LOOP_UNIT_ID` (which the runner never read for this purpose).
- `restore_derived_to_head` under concurrency — verified explicitly, with a
  named test in this sub-iterate's own test strategy (not deferred to R6):
  each per-unit worktree has its own copy of the twelve derived paths, so
  file-level collisions should not occur across a concurrent wave, proven
  rather than assumed.

### Work breakdown
1. The flip: per-unit checkout wired live, brief parameters (including
   `campaign_worktree`/`state_path` from R2) replace the env var for
   identity purposes; `write_terminal_marker.py` untouched and used only by
   `kind == "section"`; wave-scoped `SHIPWRIGHT_LOOP_UNIT_ID` sentinel export
   preserved for the authorship guard.
2. Multi-spawn in one message + full-wave-return read of each unit's
   `result.json` (no polling, no marker); a `running`-with-no-`result.json`
   unit demoted to `failed`, not silently re-claimed.
3. Runner's Step 1.0.5 `cmd_mark_running`; orchestrator's `cmd_release` for
   any unit still `claimed` at wave-return.
4. Fixed-order result processing handoff to R5b's serial merge lane; wave
   N+1's ready-set computation and spawn wait for that merge lane to finish
   the whole of wave N (v6 — waves serialize on the merge lane).
5. `restore_derived_to_head` concurrency verification, with its own named
   test.

### Test strategy
- `category:"integration"` behavior: a real-git composition test with
  actual concurrent worktrees and processes — not a mocked stand-in. Mocks
  only the Agent-tool execution itself. Paired with in-process unit coverage.
- A dedicated test proving wave N+1 is **not** spawned until wave N's merge
  lane has fully cleared (v6 — replaces v5's now-withdrawn decoupling test).
- The `restore_derived_to_head` cross-contamination test, run unconditionally
  here (not R6).
- A launch-failure test: a unit stuck `claimed` at wave-return is released
  and re-claimed in the next wave without attempt double-bump.
- A `running`-with-no-`result.json` unit (simulated Task error/budget
  exhaustion) is demoted to `failed`, never silently re-claimed.
- A test asserting the authorship guard still refuses under the wave-scoped
  `SHIPWRIGHT_LOOP_UNIT_ID` sentinel, and that `_run_id.py`/handoff
  namespacing use the brief-provided `unit_id` instead.

### Alternative approach considered — rejected
A claimed individual-completion-order model. Rejected: nothing confirms the
runtime can process `Task` completions individually rather than as one
blocking batch, and the wave model achieves the same safety properties
without an unverifiable assumption.

---

## R5b — serial merge lane: review pinning, staleness cascade, STRICT-STOP (depends on R5a)

### Files to create/modify
- `references/campaign-mode.md` steps 3f-bis–3i — rewrite 3g to read
  `shipped_head` from `review_pin.json` directly (removing R3's legacy
  dual-write); `check_review_attribution.py --mode verify` at four points:
  1. **3f-bis, before spawning `spec-reviewer`** → `--mode pin` (also
     unconditional for a review-skipped unit).
  2. **3f-bis, immediately before the `reviews.json` commit** → assert
     `HEAD == reviewed_head` **exactly** (v5, sharpened — not just
     "unchanged"); stage **only** `reviews.json` by explicit path, never
     `git add -A`; after commit, assert the new commit's parent equals
     `reviewed_head`. Any deviation → do not commit; delete the pin, demote
     `reviewed → built`, re-enter 3f-bis.
  3. **After that push** — `shipped_head` was already written to the schema
     at pin time for the review-skipped path; for the reviewed path, record
     it here as the post-commit branch tip.
  4. **3g, after `gh pr checks --watch` returns green, before `gh pr merge`**
     → `--mode verify --against shipped_head` + assert `gh pr view --json
     headRefOid,id,headRefName,baseRefName` matches the pinned
     `shipped_head`/`pr_node_id`/`pr_head_ref`/`pr_base_ref` (v5: PR
     identity, not just branch name); `--match-head-commit $shipped_head`.
  5. **After the existing "poll until `gh pr view --json state -q .state`
     reports `MERGED`" loop (v6, corrected — v5's version read `mergeCommit`
     before this poll, which exists precisely because the PR object lags the
     merge call, and `mergeCommit` lags the same way):** extend that poll's
     condition to also require a non-empty `mergeCommit.oid`, then read it.
     **Bound the poll (v6, new — it was and remains unbounded in today's
     3g):** the same `max_drain_seconds`-style deadline pattern applies here
     — a bounded number of retries, after which the unit demotes to `held`
     with `reason_code: "merge_confirmation_timeout"` rather than hanging
     the merge lane indefinitely.
     Validate it against a strict hex-SHA pattern before accepting it (reuse
     `audit_compliance_lifecycle.py::_merge_sha`'s guard rather than
     reinventing it — this value flows unquoted into `git merge-base` argv
     next, the same threat that function already defends against). **Delete
     the `git rev-parse origin/{default}` fallback entirely** — it assumes
     this PR's merge is the current tip of the default branch, which a
     concurrent sibling merge (this repo has run three campaigns merging 15
     PRs in one window) can falsify, recording an ancestrally-true but
     semantically-wrong SHA: a silently-passing false proof, worse than no
     proof. Record the verified SHA via a new fencing-validated
     `loop_claim.py::cmd_mark_merged --state "{state_path}" --unit
     "{unit_id}" --attempt-id "{attempt_id}" --merged-commit <sha>` —
     **not** `cmd_record` (whose result-contract can't express `merging →
     merged`) or `cmd_mark` (the audited *operator override*, not a home
     for the happy path) — completing the `merging → merged` transition.
     This is what R4's dependency-ancestry assert (`git merge-base
     --is-ancestor <dep.merged_commit> <resolved-base>`) actually reads for
     every non-migrated unit. **Concurrency:** `loop.lock` is never held
     across a `gh` call, so another wave's `cmd_next_batch` claim can
     legitimately interleave with this write — both are safe because every
     writer takes the lock only for its own mutation.
  6. **First action of any rebase / `ensure_current` / `integrate_main` on a
     unit's branch** → unconditionally delete the pin, demote `reviewed →
     built`.
  **Staleness trigger, restated (v5 fix — closes a false-positive):**
  triggered *only* by an actual rebase/integrate action on the unit's own
  branch, never by `base_sha` drifting because `origin/{default}` advanced
  from an unrelated sibling's merge. `--mode verify` checks ancestry of the
  pinned values only.
- **Where the currency check sits (v5, specified — closes the missing
  `merging`-edge gap):** the "is this branch current, does it need a
  rebase" decision happens while the unit is still `reviewed`;
  `reviewed → merging` is taken only once the branch is current and the pin
  is fresh. A mid-`merging` discovery of staleness (e.g. a sibling merged
  during CI-watch) demotes `merging → held`; resume is via the existing
  `held → pending` edge, re-entering with a fresh attempt counted against
  `max_rebase_reviews`.
- **Merge lane stays strictly serial**; a rebase invalidates both the review
  pin and the prior CI verdict — order after any rebase: rebase → fresh
  3f-bis → fresh `gh pr checks --watch` → `gh pr merge
  --match-head-commit $shipped_head`. **`max_rebase_reviews = 2`** — a third
  forced cycle moves the unit to `held` (livelock signal).
- **STRICT-STOP / `draining`**: immediately stops spawning new waves;
  **sweeps every `pending`/`claimed` unit to `held`**, `reason_code:
  "swept_never_started"` (R4's new edges), before waiting out `{running,
  merging}`; a running unit finishes its current build but moves to `held`
  (`reason_code: "swept_after_build"`) rather than merging — PR stays open.
  An expired lease during draining is never reclaimed/relaunched: `running →
  failed`, `reason_code: "lease_expired_during_drain"`, PR left open,
  worktree left on disk. **`max_drain_seconds` (v5, new — closes an
  indefinite-drain hazard):** a runner that keeps heartbeating without
  finishing is force-transitioned `running → failed`,
  `reason_code: "drain_timeout"`, once this bound is exceeded, so draining
  is guaranteed to terminate even against a live-but-stuck runner; `cmd_mark
  --force` remains available as a manual escape hatch before that bound.
  Draining completes when no unit remains in `{claimed, running, merging}`
  (now guaranteed, given the pending/claimed sweep and the drain deadline).
  `cmd_finalize` refuses while any unit is outside `TERMINAL`; the session
  lock release moves to "only after `cmd_finalize` confirms drained" —
  **restated to still guarantee release on every path**, unlike v4's version
  which could deadlock.
- **Status-mapping point (v6, corrected — closes a false-failure finding):**
  step 3h maps `merged → complete`; `failed → failed`; `held` maps to
  `failed` **only** when its `reason_code` indicates a mid-flight demotion
  (`lease_expired_during_drain`, `drain_timeout`, a staleness-cascade
  exhaustion, or an operator `cmd_mark`) — a `held` reached via
  `"swept_never_started"` maps to **`pending`** instead, since that unit
  never ran and a `failed` token would sit sticky on the WebUI Campaigns
  board (per `campaign_status.merge_status`'s off-ladder-terminal handling)
  until a full re-run, misreporting a stopped-but-otherwise-healthy campaign
  as having failed units it never attempted. `"swept_after_build"` maps to
  `pending` as well — its build succeeded, only the merge was deferred, and
  it can resume from `held → pending` cleanly. No change to
  `campaign_progress.py update-status`'s own enum.

### Work breakdown
1. Pin/verify insertion at the four points, `HEAD == reviewed_head`
   exactness + explicit-path staging, PR-identity verification at merge.
2. Currency-check placement (in `reviewed`, not `merging`) + the
   `merging → held` demotion path.
3. Rebase-triggered (not base-sha-drift-triggered) staleness cascade,
   covering review and CI, with `max_rebase_reviews`.
4. STRICT-STOP sweep (`pending`/`claimed → held`) + `max_drain_seconds` +
   conditional lock release (guaranteed via R4's `TERMINAL`/`cmd_finalize`).
5. Step-3h status-vocabulary mapping.

### Test strategy
- `category:"integration"` behavior: a real-git composition test across two
  sequential merges, asserting `shipped_head`/PR-identity checks at merge
  time.
- A dedicated staleness-cascade test: two units merge in sequence; a
  negative test asserts the second unit's pin is **not** invalidated merely
  by the first unit's unrelated merge advancing `origin/{default}`; a
  positive test rebases the second unit and asserts invalidation, fresh
  review, fresh CI, and a third forced cycle moving it to `held`.
- A dedicated STRICT-STOP test: a stop with one unit `pending`, one
  `claimed` (never promoted), one `running` — assert the first two go
  `held` immediately, the third finishes its build then goes `held`, the
  lock releases only once `cmd_finalize` confirms drained. A second variant
  exercises `max_drain_seconds` forcing a stuck-but-heartbeating runner to
  `failed`.

### Alternative approach considered — rejected
A fixed-width wave/batch model instead of a live ready-set. The ready set
feeding each wave is still DAG-computed at wave-start, not pre-planned; the
rejection is specifically about pre-planning batches in advance.

---

## R6 — capstone integration proof (depends on R5b)

### Files to create/modify
- `shared/tests/test_campaign_dag_scheduler_integration.py` (new, mirroring
  the precedent `test_campaign_serial_composition_integration.py` named in
  the investigation doc) — a single end-to-end real-git composition test
  exercising: (1) two independent units building concurrently in one wave,
  (2) a dependent third unit correctly waiting for verified `merged_commit`
  ancestry and starting only in the next wave, (3) survival of a mid-run
  resume (state reloaded between waves), (4) the review cascade correctly
  attributing each diff to its own unit (R3's guard, exercised live), (5) a
  STRICT-STOP mid-flight draining correctly per R5b's policy including the
  session-lock release.

### Work breakdown
1. Fixture: a five-unit DAG (two independent, one dependent on both, two
   more independent) built against a local bare-origin repo with a mocked
   `gh` contract.
2. Assertion (1): both independent units' worktrees exist concurrently and
   both reach `built` before either merges.
3. Assertion (2)+(3): the dependent unit is not claimed until both its
   dependencies show a verified `merged_commit`; a simulated resume between
   waves does not lose or duplicate this readiness state.
4. Assertion (4): a deliberately-corrupted shared-worktree diff (today's bug)
   is proven absent — each unit's review record cites only its own diff.
5. Assertion (5): a STRICT-STOP fired mid-wave drains correctly and releases
   the lock.

### Test strategy
- The single integration test above, in `shared/tests` (one pytest root).
- **Diff-coverage gate note (v5, explicit — this sub-iterate is
  test-only):** R6 adds no production code, so the diff-coverage
  denominator is near-zero and the gate is trivially satisfied; stated here
  so it isn't questioned at build time.

### Alternative approach considered — rejected
Folding this into R5a/R5b's own integration tests instead of a standalone
capstone. Rejected (v5, decided — was left open in v4): each of R5a/R5b's
tests already exercises its own slice; a single sub-iterate whose only job
is the full composed claim keeps that proof obligation owned and reviewable
on its own, rather than implicit across two other sub-iterates' test suites.

---

## Explicitly out of scope

- **Per-unit `mode` / guided-vs-autonomous merge policy** — `gate_policy.py`
  reuse does not type-check for campaigns as designed; a future campaign can
  extend its catalog schema for a new campaign-merge phase.
- **`campaign_init.py`/`campaign.md` markdown-injection hardening beyond
  id/duplicate/existence/charset validation.**
- **WebUI** (per-sub-iterate launch controls, autonomous/guided toggle,
  DAG-state display) — out of scope until R1–R6 exist.
- **True mixed-plugin-version safety** (an old v1 binary executing mutating
  commands against v2 state) — accepted residual risk given this project's
  one-version-at-a-time plugin-cache-sync model.
- **Cross-wave pipelining** (starting a newly-ready unit before the current
  wave's builds fully drain) — would require an unconfirmed runtime
  capability.
- **Migrating existing `stacked`-strategy campaigns to `depends_on`** — new
  campaigns are steered away from `stacked` via a warning; existing ones are
  unaffected.

## Cross-cutting

- **FR-gate / spec impact:** `change_type: infra`, `spec_impact: none`.
- **Complexity:** R1–R5b each independently medium; R6 is its own medium
  sub-iterate (test-only, near-zero diff-coverage denominator).
- **Plugin-cache sync reminder:** R1, R2, R3, R5a, R5b edit
  `campaign-mode.md`/`campaign-worktree.md`/`sub-iterate-runner.md`; R4
  edits `shared/scripts/lib/`. Each needs `bash scripts/update-marketplace.sh`
  + `check_plugin_cache_sync.py --strict` after merge.
- **Test-coverage gate note:** every subprocess-level integration test in
  R4/R5a/R5b is paired with in-process unit coverage over the same functions
  (module-object monkeypatching), since subprocess-executed lines are
  invisible to this repo's 80% diff-coverage gate. Each new test file
  declares its pytest root (`shared/tests` for the
  `autonomous_loop`/`loop_state`/`loop_claim`/`campaign_graph`/
  `worktree_location`/`campaign_status` work) — one root per pytest process.
