# Iterate Spec: timing-scope-mark-gap

- **Run ID:** iterate-2026-08-11-timing-scope-mark-gap
- **Type:** bug
- **Complexity:** medium (Stage 2 diff-driven detector: `cross_component=True`
  via `plugins/shipwright-iterate/hooks/hooks.json` +
  `shared/scripts/hooks/mark_implementation_span.py`; `touches_io_boundary=True`
  via `hooks.json`. Stage 1 message-only estimate was `small`.)
- **Status:** implemented
- **Trigger:** `trg-e6d1cc5e`, follow-up to TC5.1 (PR #617, "fix(iterate): make
  timing coverage trustworthy")

## Goal
TC5.1 shipped correct throughput-report READING logic (interval union,
`coverage_reason`, `degraded`), but the underlying WRITE side is nearly empty:
9 of the last 10 recorded runs report `missing_scope_mark` / `degraded`, and
the `implementation` top-level span has been present in only 1 of 32 runs
since 2026-08-07 (the TC5.1 build itself). Root-cause both gaps and fix the
writer, without touching the reporting logic TC5.1 already got right.

## Acceptance Criteria
- [x] Root-cause why the durable `scope` phase-timing mark is absent from
  nearly every run.
- [x] Root-cause why the `implementation` iterate-timing span is absent.
- [x] Fix the `scope` mark so it no longer depends on the agent remembering a
  separate CLI call.
- [x] Fix (or reliably backstop) the `implementation` span capture.
- [x] Do not modify `iterate_throughput_stats.py` / `iterate_throughput_render.py`
  (the reporting logic is explicitly out of scope and correct).
- [x] Do not attempt to capture `finalization`/`delivery` durations (structurally
  uncapturable before F5b folds — separate card, per CONTENTION brief).

## Spec Impact
- **Classification:** none
- **NONE justification:** this restores instrumentation behavior the M-Pre-1 /
  TC5.1 design already specifies (a `scope` mark denominator, a captured
  `implementation` span) — no FR describes agent-prose reliability as the
  intended mechanism, so there is nothing to correct in the FR spec itself.

## Out of Scope
- Reworking `build`/`review`/`test`/`finalize` phase-group marks (not reported
  broken by the evidence; `run_stat`'s coverage/degraded computation reads only
  `scope`).
- Capturing `finalization`/`delivery` durations (explicitly deferred).
- Making the interval-union / coverage reporting logic itself more lenient.

## Root Cause

**Defect 1 — `scope` mark.** `iterate_throughput_stats._scope_started_at`
reads `event["phase_timings"]` for a `{"phase": "scope", ...}` entry — the
run's sole durable wall-clock denominator. That entry is written only by
`iterate_phase_timing.py mark scope`, invoked from a single line in SKILL.md
§C ("→ **Phase Timing:** emit `mark scope` here …") — pure agent-prose, no
code-enforced writer, `finalize_iterate`'s fold (`iterate_phase_groups.
fold_into_event`) only *reads* whatever the sidecar already has. Plugin-cache
sync was checked and ruled out (`check_plugin_cache_sync.py --strict` — both
the SKILL.md text and `iterate_phase_timing.py` are present in the runtime
cache). The one run that has the mark is TC5.1's own build, where the
developer was manually exercising this exact instrumentation.

**Defect 2 — `implementation` span.** Same class of defect: `iterate_timing.py
start/end` calls at the Step 6 / Step 7 boundary are agent-prose annotations
with no code-enforced writer and no F11 verifier checking they fired. Unlike
`scope`, there is no single deterministic process boundary at "Step 6 begins"
to relocate the call into — Build is agent reasoning, not a tool call.

## Fix

1. **`scope`** — relocated into `shared/scripts/tools/setup_iterate_worktree.py`
   (§B1a), the one call every run unconditionally makes with `run_id` already
   in hand, on both the `created` and the already-in-worktree `noop` path
   (`lib.iterate_phase_groups.append_mark`, first-wins).
2. **`implementation`** — backstopped (not relocated, since no equivalent
   single call site exists) by a new PostToolUse hook,
   `shared/scripts/hooks/mark_implementation_span.py`, registered in
   `plugins/shipwright-iterate/hooks/hooks.json` under `Write|Edit|Bash`:
   - `start implementation` on the first `Write`/`Edit` this run that lands
     outside `.shipwright/` (pre-Build artifacts all live under it).
   - `end implementation` + `start review` + `start self_review` on the first
     Bash call matching `record_review_pass.py record --review-type self
     --status completed` (self-review is unconditionally mandatory, so this
     call always happens).
   Both edges resolve the active run via the same per-session pointer B1a
   writes (`lib.phase_quality._run_id.pointer_run_id`/`pointer_worktree_root`)
   and are first-wins against the sidecar, so an agent that does call
   `iterate_timing.py` itself is never double-recorded.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `setup_iterate_worktree.py` (`_mark_scope_started`) | `iterate_phase_groups.read_marks` → `finalize_iterate` F5b fold → `iterate_throughput_stats._scope_started_at` | JSONL sidecar (`<run_id>.phase_timings.jsonl`) |
| `mark_implementation_span.py` (`record_start`/`record_end`) | `iterate_timings_normalize.read_raw_events`/`normalize_iterate_timings` → `finalize_iterate` F5b fold → `iterate_throughput_stats.run_stat` | JSONL sidecar (`<run_id>.iterate_timings.jsonl`) |
| `plugins/shipwright-iterate/hooks/hooks.json` (new `PostToolUse` entry) | Claude Code harness (loads + dispatches on every `Write`/`Edit`/`Bash`) | JSON |

## Confidence Calibration

- **Boundaries touched:** both rows above (phase-timing sidecar,
  iterate-timings sidecar) plus the hooks.json → harness dispatch boundary
  (`touches_io_boundary` fired on `hooks.json` itself).
- **Empirical probes run:**
  - Read the live plugin cache (`~/.claude/plugins/cache/shipwright/...`) to
    rule out a sync gap as Defect 1's cause — confirmed the SKILL.md text and
    `iterate_phase_timing.py` were already present there, so the cause is
    agent-prose non-compliance, not a distribution gap.
  - Ran the diff-driven risk detectors (`risk_detectors.is_cross_component_change`
    etc.) directly against this run's changed-file list — confirmed
    `cross_component=True`, escalating the Stage-1 `small` estimate to
    `medium` per the classification floor.
  - Ran the real `setup_iterate_worktree.py` `setup()` twice per test (create,
    then noop-resume) against a real git worktree and read back the
    `.phase_timings.jsonl` sidecar — round-trip, not a mock.
  - Ran the real hook against a real worktree + pointer file, simulating
    `Write`/`Edit`/`Bash` PostToolUse payloads on stdin, and read back the
    `.iterate_timings.jsonl` sidecar — round-trip, not a mock.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `setup_iterate_worktree.py` create path stamps `scope` | tested | `test_setup_iterate_worktree.py::test_scope_mark_written_on_create` PASSED |
  | 2 | `setup_iterate_worktree.py` noop/resume path stamps `scope` | tested | `test_setup_iterate_worktree.py::test_scope_mark_written_on_noop_resume` PASSED |
  | 3 | existing `setup_iterate_worktree.py` behavior unbroken by the trim/edit | tested | `test_setup_iterate_worktree.py` full suite (13/13) PASSED |
  | 4 | first `Write`/`Edit` outside `.shipwright/` starts `implementation` | tested | `test_mark_implementation_span.py::test_write_outside_shipwright_starts_implementation` PASSED |
  | 5 | `Write`/`Edit` inside `.shipwright/` is ignored | tested | `test_mark_implementation_span.py::test_write_inside_shipwright_is_ignored` PASSED |
  | 6 | a second `Write`/`Edit` does not duplicate the `start` | tested | `test_mark_implementation_span.py::test_second_write_does_not_duplicate_start` PASSED |
  | 7 | self-review completion Bash call ends `implementation`, starts `review`/`self_review` | tested | `test_mark_implementation_span.py::test_self_review_bash_call_ends_implementation_and_starts_review` PASSED |
  | 8 | the same Bash call without a prior `start` does not fabricate an `end` | tested | `test_mark_implementation_span.py::test_self_review_bash_call_without_prior_start_does_not_emit_end` PASSED |
  | 9 | an unrelated Bash command is a no-op | tested | `test_mark_implementation_span.py::test_unrelated_bash_command_is_ignored` PASSED |
  | 10 | outside an active iterate, the hook is a no-op (never raises) | tested | `test_mark_implementation_span.py::test_outside_active_iterate_is_a_noop` PASSED |
  | 11 | malformed stdin never raises (best-effort contract) | tested | `test_mark_implementation_span.py::test_malformed_stdin_never_raises` PASSED |
  | 12 | the new hook is correctly registered + schema-compliant | tested | `test_hook_output_schema_compliance.py::test_hook_stdout_matches_event_schema[shipwright-iterate::PostToolUse::mark_implementation_span.py]` PASSED |
  | 13 (integration) | worktree setup → run pointer → hook resolution → sidecar write compose end-to-end across real git state | tested | `test_mark_implementation_span.py` (uses `siw.setup()` against a real `git_origin_repo` fixture, not mocks) + `test_phase_plugin_hooks_consistency.py` (49/49 PASSED, hooks.json wiring integrity) |
  | 14 | a repeated self-review-completion Bash call does not duplicate `start review`/`start self_review` (code-review finding: guard was end-only) | tested | `test_mark_implementation_span.py::test_repeated_self_review_bash_call_does_not_duplicate_review_start` PASSED |
  | 15 | a Bash command whose `--disposition`/other value merely contains the words "self"/"completed" is NOT matched (code-review finding: prior substring match false-positived) | tested | `test_mark_implementation_span.py::test_bash_command_with_self_and_completed_as_substrings_is_not_matched` PASSED |
  | 16 | `--flag=value` form is matched, not only `--flag value` (code-review round 3) | tested | `test_mark_implementation_span.py::test_equals_form_flag_value_is_matched` PASSED |
  | 17 | a `LockTimeout` on the guard-critical write leaves the "done" sentinel unset, so a retry stays possible (code-review round 3) | tested | `test_mark_implementation_span.py::test_lock_timeout_on_review_write_leaves_done_marker_unset` PASSED |
  | 18 | a second call in the same worktree/session reuses the cached pointer resolution instead of re-invoking the git-backed resolvers (code-review round 3) | tested | `test_mark_implementation_span.py::test_resolved_pointer_is_cached_across_calls` PASSED |
  | 19 | an asymmetric `LockTimeout` (review succeeds, self_review alone fails) is retried on the next matching call rather than permanently stranded (doubt-review round 3) | tested | `test_mark_implementation_span.py::test_self_review_only_lock_timeout_is_retried_on_next_call` PASSED |
  | 20 | an ordinary checkout with no active-iterate pointer for any session skips git-backed pointer resolution entirely (doubt-review round 3) | tested | `test_mark_implementation_span.py::test_no_active_iterate_skips_pointer_resolution` PASSED |
  | 21 | `mark_implementation_span.py` stayed under the 300-line bloat cap by splitting state helpers into `_mark_implementation_span_state.py` (doubt-review round 3 fixes pushed it to 315 lines) | tested | `wc -l` = 248 (hook) + 144 (state module); full suite re-run green post-split |

  0 untested-testable.

  **Verification against the user's own protocol (before F6 commit).** Per the
  triggering instruction's "VERIFY LIKE THIS": simulated a fresh POST-FIX
  iterate run end-to-end (`setup_iterate_worktree.setup()` against a throwaway
  git repo, the real `record_start`/`record_end` writers, `finalize_iterate.py`)
  and regenerated the throughput report against that scratch copy — never the
  live main tree. Result: `coverage: 5/5 applicable fold-time groups`,
  `Wall clock: 0.1 s (measured)`, run-history status `complete`. **This
  iterate's OWN row in the live report still reads `degraded`** —
  `setup_iterate_worktree.py`'s B1a step for THIS run's own worktree executed
  from `origin/main` BEFORE this session's fix to that file existed, so the
  fixed writer never ran for this run's own scope mark (a bootstrap-ordering
  artifact, not a defect: the iterate that fixes the writer cannot benefit from
  its own fix, the same way a compiler bug-fix doesn't recompile the compiler
  that built it). The NEXT iterate run, whose worktree is cut from a `main`
  that already has this fix merged, is the first to self-verify in the live
  report.

  **Code-review remediation (round 2, before F6 commit):** the code-reviewer
  found 4 issues in the first hook draft — (1) the duplicate-emission guard
  covered only the `end implementation` edge, not `start review`/`start
  self_review`, so a repeated matching Bash call re-opened them; (2) command
  matching used loose independent substrings (`"self" in command`) instead of
  parsing actual flag values; (3) `record_start`/`record_end` inherited
  `FileLock`'s 600s default with no override, contradicting the hook's own
  "never blocks the tool call" docstring; (4) `pointer_run_id`/
  `pointer_worktree_root` resolved via git shellouts on every matching call,
  including calls long after both edges were already captured. All four are
  fixed: (1)/(2) in `mark_implementation_span.py` (rows 14/15 above), (3) via
  a new optional `timeout_seconds` parameter threaded through
  `_append_line`/`record_start`/`record_end` in `iterate_timings.py`
  (backward-compatible default `None`), used by the hook with a 2s timeout and
  `LockTimeout` caught as a best-effort skip, (4) via a per-run "done" sentinel
  file checked before any git resolution. A 5th, low-severity finding
  (unlocked read-then-locked-write TOCTOU on the sidecar) was explicitly
  marked "no action required" by the reviewer given downstream tolerance.

  **Code-review remediation (round 3, before F6 commit):** a fresh review
  pass against the round-2 state (not a re-hash) found: (1) the round-2 done
  sentinel was written UNCONDITIONALLY even when the writes it certifies had
  themselves failed with `LockTimeout` — a single transient lock contention
  at the self-review call would permanently suppress the retry the event-
  based guard would otherwise allow; (2) `pointer_run_id`/
  `pointer_worktree_root` still cost two git shellouts on EVERY Write/Edit/
  Bash call for the whole Build/Review span before the done sentinel exists
  (`fast_main_root` never short-circuits from a worktree cwd), not merely an
  occasional call as the round-2 docstring implied; (3) `_value_after` missed
  the `--flag=value` form. Fixed: (1) `_start`/`_end` now return success, and
  `_mark_done` fires only once the guard-critical `review`/`self_review`
  writes both succeed (row 17); (2) a session-keyed resolved-pointer cache,
  re-validated on every read (session_id equality + worktree liveness) rather
  than trusted blindly, so it narrows *when* the authoritative resolvers run
  without narrowing *what* they check (row 18); (3) `_value_after` now
  recognizes both forms (row 16).

  **Doubt-review remediation (round 3, before F6 commit):** the doubt-reviewer,
  briefed to disprove rather than confirm, found 4 doubts against the round-3
  code-review state — 2 high, 2 medium:
  1. **(HIGH, fixed)** the round-3 "retry stays possible" fix gated the retry
     guard on `review` alone; an asymmetric failure (`review` succeeds,
     `self_review` alone hits `LockTimeout`) left `self_review` permanently
     unwritten because the guard saw `review` present and returned before
     ever retrying it. Fixed: the guard now tracks both edges independently
     and retries whichever is still missing (row 19).
  2. **(HIGH, fixed)** the resolved-pointer cache only covers the "an iterate
     IS active" case — a *failed* resolution (no active iterate at all) was
     never memoized, so every Write/Edit/Bash call in every session with no
     active iterate paid `pointer_run_id`'s unconditional `git rev-parse`
     cost, forever (this hook's matcher fires for the plugin's whole session
     lifetime, not merely during an iterate). Fixed: a git-free negative fast
     path (`no_active_iterate_fast_check`) skips the resolvers entirely when
     cwd is an ordinary checkout with no active-iterate pointer for any
     session (row 20).
  3. **(MEDIUM, fixed)** the cache/done-marker paths were keyed on raw
     `Path.cwd()`, so a cwd drift within one checkout (e.g. `cd
     plugins/shipwright-build` mid-session, per this repo's own documented
     test-running convention) missed the cache and wrote a stray duplicate —
     confirmed non-data-corrupting (the authoritative write path always uses
     the git-resolved `worktree_root`, never raw cwd) but wasteful. Fixed: a
     git-free `repo_root_hint` walk-up (looks for a directory owning both
     `.git` and `.shipwright`) normalizes the cache key.
  4. **(MEDIUM, low-confidence reachability, not fixed — reasoned rebuttal)**
     the "done" pre-resolution check globs for ANY run_id's marker in a
     worktree, resting on "one worktree hosts one run at a time." The
     reviewer could not find a reachable code path in this diff that
     re-purposes an existing worktree directory under a *different* run_id —
     `setup_iterate_worktree.py`'s create path refuses a slug/branch
     collision, and its noop/resume path keeps the same run_id — so the
     scenario is asserted-but-unproven-reachable, not confirmed. Addressed by
     tightening the ONE check that costs nothing extra to make precise: once
     run_id is known (from cache or fresh resolution), the second done-check
     is now run_id-scoped (`has_done_marker`) rather than reusing the broad
     pre-resolution glob (`has_any_done_marker`), which is documented as
     staying broad by design (the entire reason it can skip resolution
     cheaply). If the "one worktree, one run" invariant is ever broken
     elsewhere, the residual risk is the SAME pre-resolution glob only,
     documented explicitly in `has_any_done_marker`'s docstring.
  All fixes verified via re-run (`shared/tests/test_mark_implementation_span.py`
  15/15, plus the full affected-suite re-run below, 196/196).

- **Confidence-pattern check:** asymptote — no prior "are you confident?"
  moment in this run to re-probe (this is the first pass). Coverage — every
  ledger row is `tested`, 0 `untestable`, count (21) exceeds the AC count (6).
  Integration composition (row 13, `cross_component` fired): a real worktree +
  real pointer file + real hook dispatch + real sidecar round-trip, not a
  unit-level mock of any of the four.
