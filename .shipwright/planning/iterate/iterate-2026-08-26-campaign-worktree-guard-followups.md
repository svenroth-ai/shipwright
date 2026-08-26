# Iterate Spec: campaign-worktree-guard-followups

- **Run ID:** iterate-2026-08-26-campaign-worktree-guard-followups
- **Type:** change
- **Complexity:** medium (cross_component: this diff edits `campaign-mode.md`,
  named in SKILL.md's `cross_component` file-pattern set — "campaign drain
  (`autonomous_loop`, `campaign_*`, `campaign-mode.md`)". Mid-flight
  escalation from the `classify_complexity.py` message-only estimate
  (`small`) — that call sees no diff, so `cross_component` is structurally
  invisible until this Repo Scout step, per SKILL.md §E.)
- **Status:** implemented
- **Trigger:** two known-limitations bullets left open by the doubt-review of
  `iterate-2026-08-26-campaign-worktree-guard` (PR #653), triaged as
  `trg-16bec646` (P2) and `trg-50bd22a1` (P3), merged into one run per the
  operator's own reasoning: both edit the same doc block
  (`campaign-worktree.md:88`, "Known limitations (doubt-review round, not
  fixed here)"), and (2) alone (an assertion + a test) would not justify its
  own worktree/review-cascade/PR/six-Required-Checks overhead.

## Goal

Close both known limitations from `campaign-worktree.md`'s "Known
limitations" section without touching the incident #653 already closed
(a sub-iterate landing on `main`): (1) two orchestrator sessions on the same
campaign slug can both drive the shared campaign worktree at once, racing
`git checkout -b`; (2) `check_worktree_location.py` proves a `project_root`
is *a* campaign worktree, not that it is *this* campaign's.

## Acceptance Criteria

- [x] A second session cannot acquire the campaign session lock while the
  first is live (fresh heartbeat); it CAN once the first has gone stale
  (crashed session must not block the campaign forever).
- [x] The lock is keyed to `SHIPWRIGHT_SESSION_ID`, not PID — a resumed
  session (same session id, new OS process) always renews cleanly.
- [x] `worktree_location_error` / `check_worktree_location.py` gained an
  optional identity check: a `project_root` that IS an isolated worktree but
  belongs to a DIFFERENT, still-valid campaign is now rejected.
- [x] Both known-limitations bullets removed from `campaign-worktree.md` now
  that they're closed (the section said "not fixed here"; leaving it would
  read as still-open to the next run).
- [x] `docs/hooks-and-pipeline.md` documents both mechanisms (CLAUDE.md rule:
  a between-phase-action change requires the same-diff update).
- [x] `campaign-mode.md` stays within its 400-LOC runtime-prompt budget
  (`test_every_new_reference_under_loc_budget`).

## Spec Impact

- **Classification:** none
- **NONE justification:** hardens existing campaign-mode machinery inside
  the Shipwright framework's own orchestration (a multi-session safety
  invariant campaign mode already implicitly claims); adds no new
  user-facing capability and there is no FR describing campaign
  worktree/session isolation for the framework's own behavior — same
  classification as the predecessor fix (PR #653) this one follows up on.

## Out of Scope

- The incident #653 already closed (a sub-iterate-runner landing on `main`)
  — fully closed by the location check; not reopened here.
- General session-liveness infrastructure for a standalone (non-campaign)
  iterate's own resume path. The card is explicit: this covers the campaign
  path only, deliberately not a broader primitive.
- General-purpose lock-file schema validation and clock-skew clamping for
  `campaign_session_lock.py` — corrupted state is treated as "no lock held"
  and a future-dated `last_touch` is not clamped, both documented in the
  module rather than engineered around; more machinery than a heartbeat lock
  over an already git-ignored, per-campaign directory warrants (external
  review, see below).
- Merging + syncing (`update-marketplace.sh`) while an autonomous campaign is
  mid-drain, and landing this before the next campaign (REQ3.04c,
  `trg-3be88962`) — both timing constraints for delivery/ops, not for this
  diff; noted for the operator, not encoded as a test.

## Root Cause

Two independent, pre-existing gaps named (not invented) by the #653
doubt-review, both scoped to the shared campaign worktree PR #653 introduced:

1. **No cross-session lock.** `campaign-worktree.md` Setup keys the worktree
   to the campaign SLUG so a resumed session re-enters the same directory —
   correct for the intended single-session case, but nothing stops a SECOND
   session (a second operator, or one resuming a session it believed had
   died) from reaching the same directory and racing the first's
   `git checkout -b`. `autonomous_loop.py`'s `file_lock` only serializes
   `loop_state.json` writes.
2. **Location, not identity.** `worktree_location_error` answers "is
   `{project_root}` a worktree under `.worktrees/`", never "is it THIS
   campaign's" — a mis-threaded `project_root` pointing at a stale prior or
   sibling campaign's still-valid worktree passes unchanged.

## Fix

1. **`lib/campaign_session_lock.py` (new) + `checks/check_campaign_session_lock.py`
   (new CLI, `acquire`/`touch`)** — a heartbeat lock, not an OS-level one:
   the campaign loop is a series of independent `uv run` subprocess calls
   across a Claude Code session's tool calls, not one long-lived process, so
   there is no single OS process to attach a held file-lock to (unlike
   `lib.host_resource_lease`, which brackets exactly one resource-holding
   subprocess). The lock records `session_id` + `last_touch`; a DIFFERENT
   session may only reclaim it once `last_touch` is older than
   `DEFAULT_STALE_AFTER_SECONDS` (2h — sized above one sub-iterate's worst
   case build+review+CI+merge cycle, so an active campaign never goes stale
   between touches, while a genuinely dead session's block is still bounded).
   The SAME `session_id` always renews (the resume path).
2. **`campaign-worktree.md`** — `acquire` wired into Setup (step 0,
   immediately after the worktree resolves; non-zero aborts campaign
   startup, nothing has run yet so there's nothing to STRICT-STOP into).
   **`campaign-mode.md`** — `touch` at the top of every loop iteration
   (step 3a) AND again immediately before the one genuinely UNBOUNDED wait
   in the loop, `gh pr checks --watch` (step 3g) — added after external
   review named the single-touch-per-iteration design as a real gap for a
   long-running iteration (see External Review below). Non-zero =
   STRICT-STOP at both, matching every other check in the loop.
3. **`lib/worktree_location.py`** — `worktree_location_error` gained an
   optional `expected_campaign_slug` kwarg: when given, also requires the
   worktree DIRECTORY to be named `campaign-{slug}` EXACTLY.
   **`checks/check_worktree_location.py`** gained `--campaign-slug`,
   threaded through. Call sites: `campaign-worktree.md` step 3c (the
   orchestrator already has `{slug}` in scope) and `sub-iterate-runner.md`
   Step 1.0, via a new `campaign_slug` brief parameter the orchestrator
   passes explicitly (also now used for the F5b event-stamp's `campaign`
   field) — code review flagged the original `$(basename "{campaign_path}")`
   re-derivation as a second, independent computation of the same value that
   a path-separator quirk could make disagree with the orchestrator's own
   `{slug}`; one derivation, passed once, closes that. A branch-prefix
   design (checked-out branch starts with `iterate/campaign-{slug}`) was
   built first, then replaced after external review: the directory
   basename is fixed at creation and never changes for the campaign's whole
   lifetime, while the branch checked out inside it DOES change per
   sub-iterate — so the directory check is both EXACT (no adjacent-slug
   ambiguity) and cheaper (no `git` call needed).
4. **`campaign-worktree.md`** — both "Known limitations" bullets removed now
   that they're closed.
5. **`docs/hooks-and-pipeline.md`** — the existing "Campaign Worktree
   (2026-08-26)" paragraph (from #653) gained a follow-up paragraph
   documenting both mechanisms, per CLAUDE.md's same-diff rule.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `check_campaign_session_lock.py acquire`/`touch` (new) | `campaign-worktree.md` step 0 (orchestrator, once) AND `campaign-mode.md` step 3a (orchestrator, every loop iteration) | exit code + `--json` payload; state file `{campaign_wt}/.shipwright/campaign_session.lock.json` |
| `worktree_location_error(..., expected_campaign_slug=...)` / `check_worktree_location.py --campaign-slug` (extended, backward compatible; checks the worktree directory basename) | `campaign-mode.md` step 3c (orchestrator, before every spawn) AND `sub-iterate-runner.md` Step 1.0 (runner, on itself) | exit code + `--json` payload |

## Confidence Calibration

- **Boundaries touched:** both rows above.
- **Empirical probes run:**
  - Ran the session lock against real timestamps (monkeypatched clock, not a
    mock of the lock itself): same-session renew keeps `acquired_at`,
    different-session-while-fresh raises, different-session-past-threshold
    reclaims with a fresh `acquired_at`.
  - Ran `worktree_location_error(expected_campaign_slug=...)` against a REAL
    linked git worktree named `campaign-{slug}`, the SAME worktree with a
    sub-iterate branch checked out inside it (proving the check is
    branch-independent), and a DIFFERENT real campaign worktree
    (`git_origin_repo` fixture, real `git worktree add`) — not synthetic
    strings.
  - Ran a genuine multi-process race: 8 real `check_campaign_session_lock.py
    acquire` subprocesses launched concurrently (`ThreadPoolExecutor`)
    against the same lock, different session ids — exactly one won, proving
    the `file_lock`-guarded critical section actually serializes decisions
    rather than relying on each unit test's sequential-call assumption.
  - Ran both CLIs as real subprocesses (matching how the docs actually
    invoke them) composed around the REAL `setup_iterate_worktree.py`
    producer's own output, in
    `test_campaign_worktree_guard_integration.py` — see ledger row 12.
  - Verified the `campaign-mode.md` edit stays at exactly 400 LOC
    (`test_every_new_reference_under_loc_budget`), and the bloat
    anti-ratchet gate (`shared/scripts/hooks/anti_ratchet_check.py`) is
    clean on the staged diff.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | first `acquire` succeeds | tested | `test_campaign_session_lock.py::test_first_acquire_succeeds` PASSED |
  | 2 | same-session re-acquire renews without a new `acquired_at` | tested | `test_campaign_session_lock.py::test_same_session_reacquire_renews_without_new_acquired_at` PASSED |
  | 3 | a different session is rejected while the lock is fresh | tested | `test_campaign_session_lock.py::test_different_session_rejected_while_lock_is_fresh` PASSED |
  | 4 | a different session reclaims a stale lock | tested | `test_campaign_session_lock.py::test_different_session_reclaims_a_stale_lock` PASSED |
  | 5 | `touch` refreshes `last_touch` for the owner | tested | `test_campaign_session_lock.py::test_touch_refreshes_last_touch_for_the_owner` PASSED |
  | 6 | `touch` by a non-owner (or a missing lock) raises | tested | `test_campaign_session_lock.py::test_touch_by_a_non_owner_raises` + `test_touch_with_no_lock_at_all_raises` PASSED |
  | 7 | CLI `acquire`/`touch` exit codes + JSON `decision` field | tested | `test_campaign_session_lock.py::test_cli_acquire_then_reject_then_stale_reclaim` + `test_cli_touch_exit_codes` PASSED |
  | 8 | `expected_campaign_slug` passes when the worktree directory name matches, independent of which branch is checked out inside it | tested | `test_worktree_location_error.py::test_expected_slug_passes_when_the_directory_name_matches` + `test_expected_slug_is_unaffected_by_which_branch_is_checked_out` PASSED |
  | 9 | `expected_campaign_slug` rejects a different, still-valid campaign worktree | tested | `test_worktree_location_error.py::test_expected_slug_rejects_a_different_valid_campaign_worktree` PASSED |
  | 10 | an adjacent hyphenated slug (`req3-04` vs `req3`) is a different directory and is rejected exactly, not by a fuzzy prefix heuristic | tested | `test_worktree_location_error.py::test_expected_slug_rejects_an_adjacent_hyphenated_slug` PASSED |
  | 11 | omitting `expected_campaign_slug` is unaffected (backward compatible) | tested | `test_worktree_location_error.py::test_expected_slug_none_keeps_prior_behavior` + full pre-existing suite (5/5) PASSED |
  | 12 (integration) | the REAL `setup_iterate_worktree.py` output composes correctly with BOTH new guards, including the card's own two acceptance tests (second-live-session rejected / dead-session reclaims; misdirected `project_root` at a foreign campaign rejected) | tested | `test_campaign_worktree_guard_integration.py` (3/3) PASSED — real subprocess invocations against a real git worktree, not mocked imports |
  | 13 | CLI wrapper for `check_worktree_location.py --campaign-slug` (allow matching, block foreign) | tested | `test_check_worktree_location.py::test_campaign_slug_allows_the_matching_campaign` + `test_campaign_slug_blocks_a_different_valid_campaign_worktree` PASSED |
  | 14 | an empty `session_id` is rejected by `acquire`/`touch` (lib) and both CLI subcommands | tested | `test_campaign_session_lock.py::test_acquire_requires_a_session_id` + `test_touch_requires_a_session_id` + `test_cli_rejects_an_empty_session_id` PASSED |
  | 15 (integration) | a multi-process race between different sessions has exactly one winner | tested | superseded by row 25 (same test function, rewritten with a genuine rendezvous barrier + 5-round repetition after the doubt-reviewer showed this original version proved ordering, not serialization) |
  | 16 | no regression in the pre-existing `worktree_location`/`check_worktree_location` behavior this diff extends | tested | `test_worktree_location_error.py` (10/10) + `test_check_worktree_location.py` (7/7) PASSED |
  | 17 | no regression across the shipwright-iterate plugin or shared scripts this diff touches | tested | `plugins/shipwright-iterate/tests/` (948 passed, 1 skipped) + `shared/tests/` full suite (9407 passed, 32 skipped) PASSED |
  | 18 | a state file corrupted to carry `session_id`/`last_touch` but not a valid `acquired_at` is treated as no lock held, not a `KeyError`, for BOTH `acquire` and `touch` | tested | `test_campaign_session_lock.py::test_state_file_missing_acquired_at_is_treated_as_no_lock_held` + `test_state_file_missing_acquired_at_touch_is_treated_as_no_lock_held` PASSED |
  | 19 | a non-finite or negative `stale_after_seconds` (NaN, -inf, negative, wrong type, `bool`) is rejected rather than silently disabling the staleness guard | tested | `test_campaign_session_lock.py::test_acquire_rejects_a_non_finite_or_negative_stale_after_seconds` (5 params) + `test_cli_rejects_a_nan_stale_after_seconds` PASSED |
  | 20 | `touch` on "no lock at all" and `touch` on "a different session holds it" raise distinct, non-conflated error messages | tested | `test_campaign_session_lock.py::test_touch_with_no_lock_at_all_raises` + `test_touch_by_a_non_owner_still_says_reclaimed_as_stale` PASSED |
  | 21 | `release` removes the owner's own lock (freeing it for a brand-new session_id); is a no-op for a non-owner, for no-lock-at-all, and requires a `session_id` | tested | `test_campaign_session_lock.py::test_release_removes_the_lock_the_session_holds` + `test_release_by_a_non_owner_is_a_no_op` + `test_release_with_no_lock_at_all_is_a_no_op` + `test_release_requires_a_session_id` PASSED |
  | 22 | CLI `release` command (exit 0, then a new session_id can acquire); CLI `reason` field discriminates `refused` (CampaignLockError) from `io_error` (LockTimeout/OSError); the plain (no `--json`) invocation shape both docs prescribe | tested | `test_campaign_session_lock.py::test_cli_release_then_a_new_session_id_can_acquire` + `test_cli_reason_field_discriminates_refused_from_io_error` + `test_cli_plain_invocation_without_json_prints_a_verdict_line` PASSED |
  | 23 | `expected_campaign_slug` rejects a nested lookalike directory (`<main>/.worktrees/other/campaign-foo`) that a basename-only compare would have passed | tested | `test_worktree_location_error.py::test_expected_slug_rejects_a_nested_directory_sharing_the_right_basename` PASSED |
  | 24 | `check_worktree_location.py`'s JSON payload carries `identity_checked` reflecting whether `--campaign-slug` was passed, so an omission is distinguishable from a pass | tested | `test_check_worktree_location.py::test_identity_checked_field_reflects_whether_the_slug_flag_was_passed` PASSED |
  | 25 (integration) | a genuine rendezvous-synchronized 8-way race across 5 independent rounds still has exactly one winner per round — replaces the prior best-effort-concurrent version the doubt-reviewer showed could pass identically whether or not `file_lock` serialized anything | tested | `test_campaign_session_lock.py::test_concurrent_acquire_by_different_sessions_has_exactly_one_winner` (rewritten) PASSED |

  0 untested-testable.

- **Confidence-pattern check:** asymptote — TWO rounds. The first pass
  believed a branch-prefix identity check was airtight (a test comment
  claimed "requires the '-' separator, not a bare startswith"); re-deriving
  the actual naming convention from a REAL branch already in this repo
  (`iterate/campaign-req3-04-ac-identity-mono-R0-spec-reader-shipped-shape`)
  surfaced the adjacent-hyphenated-slug ambiguity myself, and external
  review (below) then found the same gap independently plus a second,
  unrelated one (single-touch-per-iteration staleness) — both fixed, not
  just documented, in the second pass. That convergence (self-review and
  external review landing on the same design flaw from different angles) is
  itself the asymptote signal that a third probe was not needed. Coverage —
  every ledger row is `tested`, 0 `untestable`, count (17) exceeds the AC
  count (6). Integration composition (rows 12 and 15, `cross_component`
  fired): a real subprocess composition of the actual worktree-creation
  producer with both new guards, and a real concurrent-process race.

## External Review

**Record-keeping note:** this review genuinely ran and gated the build (the
findings below are real, specific, and independently reproduced in the
Doubt Review section's own citation trail) — but its raw provider payload
was not preserved to disk before a later context compaction, so
`record_review_pass.py record --review-type plan` cannot be completed
retroactively (it requires `--from external-review-json` with the actual
payload file, correctly refusing an unverifiable claim). `reviews.json`
therefore leaves `plan` `pending` rather than asserting a status the tool
can't verify; every other cascade type (self, spec, code, doubt,
plan_internal, external_code) is recorded. No F6/F11 gate reads `plan`'s
status from this ledger (grepped clean), so this does not block delivery —
flagged here for whoever next resumes this run_id.

`external_review.py --mode iterate` (openai + deepseek via OpenRouter), run
against the mini-plan and this spec after the FIRST implementation pass.
Both verdicts: `revise`. Six findings; two acted on (both independently
raised by both reviewers, or high-severity and directly actionable), the
rest documented as accepted residual limitations rather than engineered
around — proportionate to a cheap heartbeat lock over an already-isolated,
git-ignored directory:

- **[deepseek, high] Branch-prefix identity check fails the exact case the
  spec names (`req3` vs `req3-04`).** ACTED ON — replaced the check with an
  exact worktree-directory-basename match (see Fix §3). This was the
  correct call: the directory name is fixed at creation and cheaper to check
  than the branch (no `git` call), and it fully closes the ambiguity rather
  than narrowing it.
- **[openai, high] + [deepseek, medium] The lock is renewed once per loop
  iteration; a long iteration (unbounded CI wait) can exceed the staleness
  threshold and be reclaimed while still logically alive.** ACTED ON — added
  a second `touch` before step 3g's `gh pr checks --watch`, the one
  genuinely unbounded wait (see Fix §2).
- **[deepseek, high] `acquire` is wired in AFTER the worktree already
  resolves, so two sessions' FIRST-EVER `setup_iterate_worktree.py` calls on
  an absent worktree could still race.** NOT acted on — that race is at the
  git-ref level inside `setup_iterate_worktree.py` itself (its own existing
  slug-collision guard, exit code 2, shared with every standalone iterate),
  not inside this fix's scope; the incident this campaign lock actually
  closes (two runners' `git checkout -b` colliding INSIDE an
  already-shared, already-existing directory) is fully prevented regardless
  of exactly where cold-start ordering lands. Building general first-creation
  arbitration for `setup_iterate_worktree.py` is explicitly out of scope
  (the card: no general session-liveness infrastructure beyond the campaign
  path).
- **[openai, medium] + [deepseek, low] `SHIPWRIGHT_SESSION_ID` should be
  validated non-empty.** Already true when this review ran (`if not
  session_id: raise` in both `acquire`/`touch`) — reviewers evaluated the
  plan text, not the code; confirmed already covered, added explicit tests
  (ledger row 14) since none existed yet.
- **[openai, medium] + [deepseek, low] Corrupted lock-state JSON / future-dated
  `last_touch` (clock skew).** Documented as accepted residual limitations
  in `lib/campaign_session_lock.py`'s module docstring rather than solved —
  schema validation and a bounded-skew policy are more machinery than this
  gate's blast radius (a shared, already git-ignored per-campaign directory)
  warrants.
- **[deepseek, low] `expected_campaign_slug` behavior under detached HEAD.**
  Moot after the directory-basename redesign — the check no longer reads the
  branch at all, so a detached HEAD cannot affect it.

**Internal spec-reviewer (Stage 1, run against this same diff before commit):
REJECT, three findings, all ACTED ON:**

- `docs/hooks-and-pipeline.md`'s new paragraph was headed "... + branch
  identity" — naming the rejected design (see deepseek-high above) in its own
  title, four lines above the body's own "not the checked-out branch" text.
  Fixed: retitled "... + worktree identity".
- The `campaign-mode.md` step 3g `touch` (the fix for the openai-high /
  deepseek-medium finding above) was encoded only as a trailing `#` comment on
  the `gh pr checks --watch` line, never an executable command; the 3a
  fragment it pointed back to was itself missing `uv run` and the
  `{shared_root}/scripts/` prefix every other call in these references
  carries. Fixed: both 3a and 3g now carry the full runnable
  `uv run "{shared_root}/scripts/checks/check_campaign_session_lock.py" ...`
  invocation; 3g's touch is its own line, non-zero = STRICT-STOP, immediately
  before `--watch`. LOC-neutral: the two comment lines trailing `gh pr checks`
  were folded into one to hold `campaign-mode.md` at exactly 400 lines.
- `_load()` validated `session_id` and `last_touch` but not `acquired_at`, so
  a state file corrupted (external tampering only — this module's own writes
  go through `durable_atomic_write`) to carry the first two but not the third
  raised an uncaught `KeyError` in `acquire`/`touch` instead of the
  module docstring's documented "treated as no lock held". Fixed: `_load` now
  validates all three fields; test added
  (`test_state_file_missing_acquired_at_is_treated_as_no_lock_held`).

## Code Review

Stage-2 `code-reviewer`, run against the fully spec-reviewer-passed diff. 12
findings (5 medium, 7 low). Dispositions:

**ACTED ON:**

- **[medium] `_load` mapped ANY `OSError` to "no lock held"** — fails the
  guard OPEN on a transient read failure (a Windows sharing-violation
  `PermissionError`, per `lib/atomic_write.py`'s own documented rationale for
  `durable_read_text`), not just on genuinely corrupt content. Fixed: reads
  now go through `durable_read_text` (mirroring the writer), and the swallow
  is narrowed to `(UnicodeError, json.JSONDecodeError)` — a persistent
  `OSError` now propagates and the CLI converts it to a `block` decision
  (see next finding) rather than a silent reclaim.
- **[low] CLI caught only `CampaignLockError`** — a `file_lock` timeout or an
  `OSError` (from the fix above, or a write failure) would escape as an
  uncaught traceback: still a non-zero exit, but empty stdout, breaking the
  documented `--json` contract the diff's own concurrency test depends on.
  Fixed: `except (CampaignLockError, LockTimeout, OSError)`, all routed
  through the same structured `block` payload.
- **[medium] No `stale_after_seconds` validation** — `nan` or a negative
  value would make every `age <= stale_after_seconds` comparison `False`,
  silently disabling the staleness guard (every acquire reclaims,
  split-brain, no diagnostic) — the exact bug class
  `lib.file_lock._validated_timeout` already guards against one call away.
  Fixed: `_validated_stale_after_seconds` mirrors that helper; tests added
  (lib + CLI, ledger row 19).
- **[medium] No release path, no named remedy for a crashed session** — the
  most common real failure (session dies mid-campaign) blocks even a
  same-operator restart for up to 2h, and the error text named no recovery.
  Cheapest fix taken (proportionate to this gate's blast radius, same
  reasoning as the accepted corrupted-state/clock-skew limitations): the
  error now names the exact state-file path to delete for an immediate
  reclaim. A `release` subcommand was considered and rejected as more
  machinery than warranted here.
- **[medium] Docs overclaimed full heartbeat coverage** — "3a AND 3g ensure
  it never goes stale mid-loop" ignored that the `sub-iterate-runner` Task
  itself (3c spawn through 3d's DONE wait: build + reviews + F0–F6 + push) is
  the loop's LONGEST unbounded block and is touched by neither. Fixed: the
  docs now name the gap explicitly (`campaign-worktree.md`,
  `docs/hooks-and-pipeline.md`) instead of overclaiming coverage; step 0 also
  now runs the identity check BEFORE `acquire` (a related medium finding —
  the lock was previously claimable against an unverified `project_root`).
  Closing the gap itself (the runner heartbeating its own occupancy) is
  named as follow-up, not solved here — it is cross-cutting runner-contract
  work, not a doc or guard-ordering fix, and this iterate's scope is the two
  named known-limitations, not a new primitive.
- **[medium] Campaign slug double-derivation** — the orchestrator's
  `--campaign-slug "{slug}"` and the runner's `$(basename "{campaign_path}")`
  computed the same value two different ways; a path-separator quirk could
  make them silently disagree. Fixed: the orchestrator now passes
  `campaign_slug` as an explicit brief parameter (also used for the F5b
  `campaign` stamp), and the runner's Step 1.0 uses it directly — one
  derivation, not two.
- **[low] `pid` field written, never read, actively misleading** given the
  module's own thesis that no OS process persists across the loop's
  subprocess calls. Fixed: dropped, along with the now-unused `os` import.
- **[low] argparse subparser-registry indirection** (`sub.choices["acquire"]
  .add_argument(...)`) for a flag the loop already had `p` in hand for.
  Fixed: moved inside the loop.
- **[low] Concurrency test placed above its own CLI section, local
  `import concurrent.futures`.** Fixed: moved below the `_cli` helper it
  calls, import hoisted to module level.
- **[low] `_setup_campaign_worktree` in the integration test duplicated
  `test_check_worktree_location.py`'s `_setup` line-for-line.** Fixed —
  extracted, but NOT into `conftest.py` as first tried: `conftest.py` (320
  LOC) is a pre-existing bloat-baseline EXCEPTION pinned at exactly that
  `current` watermark against a 300-LOC source limit, and the Stop-hook
  anti-ratchet gate blocks ANY growth past `current` — zero headroom, not a
  soft target. The extraction landed instead in a NEW module,
  `shared/tests/_worktree_setup_helper.py` (`run_setup_iterate_worktree`),
  imported by both test files via the same `sys.path.insert(0, <test dir>)`
  + deferred-import pattern this file already uses for `_d2v_helpers` — a
  new file starts at zero baseline, so extraction-to-a-new-module is the
  sanctioned way to de-duplicate when the landing file has no room left.
  The same watermark constraint also forced the `campaign_slug` brief-param
  addition (medium finding #4) into a terser single-line form in
  `sub-iterate-runner.md` (already a 497/497 exception).
- **[low] Error prose for an empty `SHIPWRIGHT_SESSION_ID` implied a named
  holder + age**, which only the different-session-collision branch
  actually has. Fixed: `campaign-worktree.md` now covers the empty-id branch
  and its remedy explicitly.

**NOT acted on:** none — every finding from this round was either fixed or
(the runner-heartbeat gap) explicitly documented as a scoped-out follow-up
rather than silently dropped.

**Fix-verification pass (code-reviewer, re-run against the fixed tree):
PASS, all 12 confirmed, plus 3 new low findings the fixes themselves
introduced — all fixed:** a dangling self-reference in `campaign-worktree.md`
("same remedy as the empty-id case below" pointed at nothing); "tracked, not
solved here" for the runner-heartbeat gap asserted a tracking artifact
(triage card) that didn't exist — reworded to "documented", matching
`docs/hooks-and-pipeline.md`'s own phrasing; and `campaign-mode.md`'s "STAMPS
both" became ambiguous once the brief grew a third item (`campaign_slug`) —
reworded to name the two stamped fields explicitly, and `campaign_slug` was
added to the enumerated `prompt=<brief with ...>` list it had been left out
of. The reviewer also flagged that the diff handed to it was stale for the
conftest-vs-new-module redesign above; verified against the tree instead,
consistent, no dangling references.

## Doubt Review (Stage 3, adversarial, advisory-must-address)

Fresh-context `doubt-reviewer`, biased to disprove, run once code-review
passed — this diff is fundamentally about concurrency (session locking,
race conditions), the exact trigger for Stage 3. Result: 13 doubts (3 high,
7 medium, 3 low) across concurrency-ordering, reversibility,
boundary-contract, and hidden-coupling lenses. The two named known-limitations
survived every disproof attempt at the LIBRARY level (no slug-sanitization
bypass, no symlink/case/trailing-slash hole, correct `.gitignore` coverage) —
every doubt was concentrated where the fix meets the runtime prompt and the
operator. All 13 acted on; none dismissed.

**High (3, all fixed):**
- **Step-0 snippet didn't enforce its own ordering.** `campaign-worktree.md`
  emitted `check_worktree_location.py` and the lock `acquire` as two bare
  lines — the acquire ran even after an identity failure, acquiring a lock
  against a mis-substituted `project_root` before the failure was ever seen.
  Fixed: joined with `&&`; step 3g's own `|| STRICT-STOP` was already correct
  and is what exposed the inconsistency was inside this same change.
- **A failed `touch` STRICT-STOPped into Finalize, which writes the
  contested state.** The only cause of a touch failure is that a second
  session now owns the worktree and may be driving the same
  `loop_state.json` — routing the response through a write to that same
  file is exactly backwards. Fixed: a touch failure is now LOCK-LOST, a
  distinct terminal outcome from STRICT-STOP — no step 4, no write, report
  to the operator and stop (`campaign-mode.md` steps 3a/3g).
- **`touch` conflated "no lock at all" with "a different session holds
  it."** Both raised the same "the lock was reclaimed as stale" message —
  false for the first case, and reachable both by the acquire error's own
  documented delete-remedy (delete the state file, next touch says
  "reclaimed" when nothing was ever reclaimed) and by mid-campaign adoption
  (a `touch` before any `acquire` on this session). Fixed: split into two
  branches with distinct wording (`lib/campaign_session_lock.py::touch`).

**Medium (7, all fixed):**
- **3g's touch documented as covering the wait it precedes.** A touch only
  resets the deadline at the instant it runs; `--watch` plus the merge-poll
  after it is a SECOND unbounded, untouched window beside the runner Task,
  not covered by "touches it again immediately before." Fixed: reworded to
  name both windows honestly (`campaign-worktree.md` "touch coverage gap",
  mirrored in `docs/hooks-and-pipeline.md`).
- **`DEFAULT_STALE_AFTER_SECONDS`'s docstring contradicted the diff's own
  documented gap** ("an active campaign keeps renewing well inside this
  window" vs. "a sub-iterate that runs past it can go stale") with no
  measured p95 behind either claim. Fixed: docstring rewritten to state
  plainly that the constant is an unmeasured, generous guess and does not
  rule out the documented gap.
- **The delete-remedy is an unverifiable manual override whose failure mode
  is the exact split-brain the lock exists to prevent**, and carried no
  caution. Fixed: the error message and doc text now require confirming no
  `sub-iterate-runner` Task is still live before deleting, and print the
  `last_touch` as a wall-clock time (not just an age) so an operator can
  reason about it.
- **No release path** — nothing ever removed the lock, so a campaign that
  finished cleanly blocked its own operator's next, brand-new
  `SHIPWRIGHT_SESSION_ID` (the routine session-restart case) for up to the
  staleness window. Fixed: added `release()` / CLI `release` command, called
  as step 4's first action.
- **A worktree recreate (`git worktree remove` + re-create, the prescribed
  repair for `reason_code: "not_isolated"`) silently deletes the lock**
  since the state file lives inside the worktree it protects. Documented
  (not solved — the same class as the runner-heartbeat gap): re-`acquire`
  after any recreate.
- **The concurrency test proved ordering, not serialization** — no
  rendezvous barrier, no repetition, so it could pass identically whether or
  not `file_lock` actually serialized the critical section. Fixed: rewrote
  with a genuine rendezvous (each of 8 racers signals ready, then all
  release from a shared "go" file at once) across 5 independent rounds.
- **AC-2 (same-session-id resume renews cleanly) rested on two unproven
  premises**: that `SHIPWRIGHT_SESSION_ID` stays stable across a Claude Code
  resume, and that it is reliably present in the orchestrator's Bash
  environment (this diff also newly hard-fails campaign startup on an empty
  one). Documented: the module docstring now names this as an explicit,
  inherited assumption (`capture_session_id.py` already makes it elsewhere)
  rather than an asserted fact — no in-repo evidence either way was found,
  and manufacturing it is outside this iterate's scope.

**Low (3, all fixed):**
- **The identity check was exact on the basename only** — a nested lookalike
  directory (`<main>/.worktrees/other/campaign-foo`) would pass, and the
  compare was case-sensitive on a case-insensitive filesystem (Windows).
  Fixed: compares the FULL resolved path against
  `main_root/.worktrees/campaign-{slug}`, which also resolves the
  case-sensitivity question correctly per-platform for free (`Path.resolve()`
  consults the real filesystem).
- **The CLI's exit-code contract couldn't distinguish contention from
  infrastructure failure**, every CLI test passed `--json` (the
  no-`--json` shape both docs prescribe was untested), and
  `--stale-after-seconds` wasn't mentioned in the docstring's usage block.
  Fixed: added a `reason` discriminator (`refused` vs `io_error`) to the
  JSON payload, a plain-invocation test, and the missing usage-block line.
- **An omitted `--campaign-slug` degrades silently** to a location-only
  pass with no signal anywhere, and the bloat-cap-forced compression buried
  the new `campaign_slug` parameter inside another bullet in
  `sub-iterate-runner.md`. Fixed: added an `identity_checked` boolean to
  `check_worktree_location.py`'s JSON payload, and gave `campaign_slug` its
  own bullet (offset by merging two OTHER bullets elsewhere in the same
  497/497 exception file, not by growing it).

**NOT acted on:** none.

**Fix-verification:** full targeted suites re-run after every fix in this
section — `shared/tests/test_campaign_session_lock.py` (29/29),
`test_worktree_location_error.py` + `test_check_worktree_location.py` +
`test_campaign_worktree_guard_integration.py` (51/51 combined with the lock
suite), `plugins/shipwright-iterate/tests/` (948 passed, 1 skipped), ruff
clean, anti-ratchet gate clean (`sub-iterate-runner.md` back at exactly
497/497), `test_every_new_reference_under_loc_budget` clean
(`campaign-mode.md` back at exactly 400/400). Full `shared/tests/` re-run in
progress at write time; recorded once complete.

## Verification (medium+)

- **Surface:** none
- **Justification:** pure internal CLI/lib tooling for campaign
  orchestration guards (no runnable web/dev-server surface; this run's own
  automated test suites — unit + the real-subprocess integration test above
  — are the verification, per F0.5's `surface=none` path with the required
  justification).
