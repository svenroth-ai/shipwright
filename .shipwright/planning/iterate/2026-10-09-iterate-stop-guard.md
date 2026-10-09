# Iterate Spec: iterate-stop-guard

- **Run ID:** iterate-2026-10-09-iterate-stop-guard
- **Type:** change
- **Complexity:** medium (diff-driven `cross_component`: Stop hook + `hooks.json`)
- **Status:** draft

## Goal
An `--autonomous` iterate must run to a MERGED PR with green checks. Today nothing stops it from ending its turn after the build and asking the operator how to continue (5 of ~10 sessions on 2026-10-09 did exactly that). Add a code-level Stop-guard, a hard written rule and a visible phase checklist.

## Acceptance Criteria
- [ ] A Stop in a session that ran `/shipwright-iterate … --autonomous` (slash command or Skill call) with a live run pointer returns `{"decision":"block","reason":…}`; the reason names the run id and the first unfinished phase (self-review → review cascade → finalization → F6 commit → F11 push/PR → delivery).
- [ ] No block when the session is not an autonomous iterate, when the run pointer is gone (`deliver_pr.py` retired it at MERGED/CLOSED), when `SHIPWRIGHT_LOOP_ID` is set, or on any internal error.
- [ ] `record_hard_blocker.py --reason-code <closed list>` lifts the guard for that run; an unknown code is refused.
- [ ] Bounded: after 3 consecutive blocks with no tool call in between, and after 40 blocks per run, the Stop passes. Real work between blocks resets the consecutive counter.
- [ ] `SKILL.md` carries a short hard rule + link to `references/autonomous-contract.md` (checklist, hard-blocker command, enforcement); `docs/hooks-and-pipeline.md` documents the hook.

## Spec Impact
- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.11 — AC43 (autonomous run may not stop before delivered)
- **REMOVE:** none

## Out of Scope
- Slimming `SKILL.md`'s very long lines (separate follow-up iterate).
- Making the guard also cover the Codex CLI harness.
- Any `gh`/network call at Stop time.

## Design Notes
n/a (no UI).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Claude Code Stop event (stdin) | `iterate_stop_guard.py` | JSON `{session_id, transcript_path}` |
| `iterate_stop_guard.py` stdout | Claude Code | JSON `{"decision":"block","reason"}` |
| `setup_iterate_worktree.py` run pointer | guard (`read_run_pointer`) | JSON file |
| `record_hard_blocker.py` / guard | guard | `.shipwright/runtime/iterate-stop-guard/<run_id>.json` |
| Claude Code transcript | `scan_transcript` | JSONL |

## Confidence Calibration
- **Boundaries touched:** the five rows above.
- **Empirical probes run:** hook run as a real subprocess against a real git worktree + run pointer from BOTH the main checkout and the worktree cwd (block / interactive / retired pointer / loop unit / blocker / kill switch); blocker CLI run from the worktree is honoured by the hook run from main; transcript shape checked against a real recorded session on disk (`str` content, newline-separated tags) and list content; incremental scan resumes and survives a shrunk file; counter boundaries at 3 and 40 stepped exactly.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Open autonomous run is blocked, reason names run + next phase | tested | test_open_autonomous_run_is_blocked_with_next_phase PASSED |
  | 2 | Interactive run / retired pointer / loop unit never blocked | tested | test_interactive_run_and_retired_pointer_are_never_blocked, test_loop_unit_is_left_alone PASSED |
  | 3 | Recorded blocker lifts the guard; unknown code and unknown run refused; works across cwds | tested | test_recorded_blocker_lifts_the_guard, test_unknown_blocker_code_is_refused, test_blocker_cli_refuses_a_run_without_a_live_pointer, test_hook_and_cli_agree_from_main_checkout_and_from_worktree PASSED |
  | 4 | Counters bounded (3 consecutive / 40 total), real work resets, kill switch | tested | test_prose_only_answers_run_out_but_real_work_resets, test_total_cap_releases_the_guard, test_operator_kill_switch_and_counter_boundaries PASSED |
  | 5 | Autonomy: latest invocation wins, flags only, campaign excluded, Skill call, real shape, list content, pasted text | tested | test_the_latest_iterate_invocation_decides, test_flag_inside_a_description_and_campaign_parents_are_not_autonomous, test_skill_tool_invocation_counts_as_autonomous, test_real_transcript_shape_and_list_content_are_read, test_a_pasted_command_line_without_the_command_tags_is_not_an_invocation PASSED |
  | 6 | Incremental scan + next-phase hint | tested | test_incremental_scan_resumes_and_survives_a_shrunk_file, test_hint_walks_the_phases_in_order PASSED |
  | 7 | hooks.json registration (guard in Stop, no `if:`) | tested | test_the_guard_is_registered_in_the_stop_hooks_of_the_iterate_plugin PASSED |
  | 8 | SKILL.md rule + reference present | tested | existing SKILL drift tests + wc/line budget |

- **Confidence-pattern check:** asymptote: the plan review's first "high" (tag order) was probed against a real transcript instead of argued; coverage: every ledger row tested, 0 untested-testable. Integration composition (`cross_component`): the hook-as-subprocess tests against a real worktree pointer are the composition test.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run --directory plugins/shipwright-iterate --extra dev pytest tests/test_iterate_stop_guard.py -q`
- **Evidence path:** `.shipwright/runs/iterate-2026-10-09-iterate-stop-guard/`

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Build option A (local Stop hook keyed on the run pointer) with B's written rule and checklist as part of it; C (gh at Stop time) adds nothing.
- **Findings:** necessity low (build it; A includes B) — fixed/accepted; smallest-option low (separate hook, not a blocking finalize hook) — accepted; complexity-cost medium (phase hint ties hook to phase layout) — disclosed (hint is best-effort, falls back to a generic line); security medium (agent can self-release via the CLI) — fixed (detail mandatory, stderr line, F12 must name it); completeness low (operator way out, pasted-command false positive) — fixed (kill switch env, `abandoned-by-operator` code, latest-invocation rule, test for pasted line); completeness low (stale pointer, CI wait, gitignore, multi-hook) — fixed/documented (cap is the bound; `.shipwright/*` is ignored); security low (fail-open invisibility) — already stderr diagnostics.
- **Known limitations:** the phase hint reads local artifacts and can lag a renamed phase; it never gates.
- **Status:** 4 fixed, 1 disclosed

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-09-iterate-stop-guard/architecture_brief.md`
- **Verdicts:** glm=approve · openai=revise
- **Smallest thing that would do (per reviewers):** option A, but both reviewers prefer an explicit `autonomous` flag in the run pointer over transcript scanning.
- **Findings:** (1) transcript scanning is the fragile part, record autonomy in the pointer — **declined with reason, see below**; (2) tie autonomy to the latest invocation — accepted-and-fixed; (3) path resolution from main checkout and worktree must agree — accepted-and-fixed (subprocess test from both cwds, CLI from the worktree); (4) define "real work" — kept: monotonic tool_use count compared with the count stored at the previous block, boundaries tested at 3 and 40; (5) escape for abandoned runs / self-release visibility — accepted-and-fixed.
- **Reconciliation:** The pointer flag would rest on the agent passing `--autonomous` to `setup_iterate_worktree.py` — the exact agent-followed step whose omission is the failure being fixed — and `worktree_isolation.py` sits at its bloat ceiling with zero headroom. The transcript is code-visible and does not depend on agent compliance. The resume scenario raised by glm does not apply: the pointer is session-keyed, so a fresh session has no pointer and a resumed one re-invokes the command. Maintenance cost of the transcript regex is accepted and bounded by the latest-invocation rule plus tests for slash command, Skill call and pasted text.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Core idea sound and fail-open; autonomy detection from the transcript was the weak point (format, cross-run leak, campaign parent), plus operator escape, background waits, rescan cost.
- **Findings:** (1) regex may miss real transcripts, list content unread — fixed (verified the real shape on disk: `str` content, tags newline-separated; list content now joined; test with the real shape); (2) autonomy attached to the session, not the run; `--autonomous` inside a description — fixed (latest invocation wins; flag must be among the leading flags; tests); pointer-flag alternative declined, see Architecture Review reconciliation; (3) campaign parent trapped — fixed (`--campaign` invocations are never autonomous for the guard; test); (4) operator escape — fixed (block reason tells the agent that an explicit operator stop is a recordable blocker; kill switch env; `abandoned-by-operator` code); human-turn detection declined: a nudge like "finish it" would release the guard exactly when it is needed; (5) background waits — fixed (hint says wait, do not re-spawn; prose-only waiting ends via the consecutive counter, work resets it); (6) "first in Stop" claim — fixed (no ordering claim; siblings run in parallel, idempotency disclosed); (7) full rescan per Stop — fixed (incremental offset scan stored in state); (8) off-by-one — fixed (`>=`, boundary test); (9) state-file concurrency — fixed (unique tmp name; stale-write window disclosed); (10) blocker unaudited — partly fixed (CLI validates the run id against a live pointer, stderr line, F12 must name it); event-log entry declined (extra producer for a gitignored runtime facility); (11) hint gaps — fixed (empty branch skips the push check, 5 s git timeouts); (12) reason injection — fixed (run id and pending keys sanitized, length-capped).
- **Known limitations:** the sibling Stop hooks (finalize repair, audits, triage aggregation, bloat gate) also run on every blocked Stop; they are existing, idempotent-by-design hooks and were not changed. The hint can lag a renamed phase.
- **Status:** 10 fixed, 2 declined, 2 disclosed

## Code Review, External Code Review, Doubt Review — triage
- **Stage 1 spec-compliance:** PASS (doc inconsistency about deleted worktrees fixed).
- **Stage 2 code-reviewer (opus), 10 findings, none high:** trailing / quoted `--autonomous` and Skill-path disagreement — fixed (one flag parser with real arity for both paths, trailing flag accepted); scan persisted only on block path, rewrite detection, whole-file read — fixed (persist on every Stop with a live pointer, transcript path stored, line iteration, `reset` flag); blocker not clearable — fixed (`--clear`); F6 hint satisfied by any commit, hard-coded main — fixed (`--grep` run id against `origin/HEAD` base); pointer check by substring — fixed (json.loads); reason lacked the command — fixed; silent cap release — fixed (stderr line); test gaps — fixed (31 tests).
- **External code review (openai + glm, both revise, none high):** same flag-parsing/blocker/pointer points as above — fixed; invalid state JSON must fail open, not reset — fixed (`strict` read, test through the real hook); missing hooks.json test (ledger row 7 pointed at a test that did not cover the guard) — fixed with a real test; glm self-release note — accepted, disclosed.
- **Stage 3 doubt-reviewer (opus), 6 doubts, none high:** session-less run pointers on disk (guard would never fire) — fixed (`live_pointer` fallback matches the transcript's run id; test); stale pointer after an out-of-band merge steering a duplicate PR — fixed (48 h age bound, push hint says check `gh pr list` first); polling burns the cap — fixed in the block reason (end the turn without tool calls while a named background task runs); kill switch is launch-time only — documented, live escape named; blocker lost to a concurrent write / orphan tmp — fixed (re-read blocker before the final write, tmp unlinked in finally); any skill named `*iterate*` flips autonomy — fixed (exact names).
- **Known limitations (disclosed):** the 40-block cap can still be consumed by repeated waits and then releases with a stderr line; sibling Stop hooks rerun on each blocked Stop.

