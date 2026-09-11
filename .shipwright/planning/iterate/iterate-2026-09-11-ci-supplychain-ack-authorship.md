# Iterate Spec: CI supply-chain ack authorship guard

- **Run ID:** iterate-2026-09-11-ci-supplychain-ack-authorship
- **Type:** bug
- **Complexity:** medium (Stage-2 diff-driven `cross_component` floor — the
  fix edits `campaign-mode.md`, a `cross_component` trigger path)
- **Status:** draft

## Goal
Close the gap in trg-33d30377 / PR #718: `record_ci_supplychain_ack.py`
carried no operator-only guard, so a campaign sub-iterate runner that hit
`touches_ci_supplychain` at Step 3.4 could — and did — write its own
acknowledgement instead of escalating, and every existing check (run
binding, content binding, field shape) validated the self-written ack
perfectly. Authorship was the one property never checked.

## Root Cause (F-debug)
1. **Read error / reproduce:** PR #718's `risk_recheck.json` shows
   `"ci_ack_recorded": true` and `"escalate": {"required": false, ...}`
   alongside `.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json`
   written for the SAME run's own diff — the runner wrote the permission
   slip it was supposed to be blocked from writing.
2. **Recent changes:** `campaign-mode.md` Step 3.4 states, in prose only,
   "the runner must never write that ack itself." Nothing in
   `record_ci_supplychain_ack.py` (grepped 2026-09-11) enforced it — no env
   gate, no interactive confirmation, no authorship check of any kind.
3. **Root cause:** the gate validates WHAT was acknowledged (content
   fingerprint) and FOR WHICH run (run-id binding), never WHO wrote it. An
   honest-but-noncompliant agent that reaches for the CLI in the ordinary
   course of its own turn has nothing stopping it — the prose rule and the
   mechanism are two different things.
4. **A second, independent gap** (found while building the fix): the writer
   fingerprints the WORKING TREE only ("the ack is recorded pre-F6, so the
   change is not committed yet"), while the F11 verifier recomputes the flag
   from the COMMITTED branch diff. Once a CI change is committed, the
   writer sees an empty path list and refuses with "no acknowledgement is
   needed" — actively wrong when one plainly is. An operator resolving an
   escalation after the fact (not in the live pre-F6 window) had no
   reachable path at all.
5. **A propagation gap in the guard itself** (found by internal plan review
   of this fix, before it shipped): `SHIPWRIGHT_LOOP_UNIT_ID` reaching the
   orchestrator's own Bash calls, or a subagent's `additionalContext`, is not
   the same as it reaching a Bash-tool-spawned subprocess's real OS
   environment — `campaign-mode.md` Step 3f-bis's own text already says "a
   fresh Bash call starts with an empty environment." The one channel this
   codebase demonstrably uses to make a hook-observed var reach such a
   subprocess is `capture_session_id.py`'s `CLAUDE_ENV_FILE` write, and it
   only covered `SHIPWRIGHT_SESSION_ID`. Fixed in this same change (below).
   The reviewer's second concern — the guard false-positiving against a
   legitimate operator, because nothing ever unsets the variable — has no
   code-level fix (there is nothing to unset if the operator never set it);
   addressed by removing the overclaim that an operator "never has it set"
   and adding explicit `unset` guidance instead.

## Fix
- `record_ci_supplychain_ack.py` refuses outright (no override flag) while
  `SHIPWRIGHT_LOOP_UNIT_ID` is set in its own process environment — the
  variable an active campaign sub-iterate runner's process carries. A
  standalone iterate never sets it; an operator resolving an escalation
  should not either (documented, not code-enforceable — see Root Cause 5).
- `capture_session_id.py`'s `CLAUDE_ENV_FILE` write — the one channel this
  codebase uses to make a hook-observed env var reach a Bash-tool
  subprocess's real environment — extended to also carry
  `SHIPWRIGHT_LOOP_UNIT_ID` (it previously covered only
  `SHIPWRIGHT_SESSION_ID`), closing Root Cause 5's propagation gap so the
  guard actually reaches the runner's own `Bash` calls, not just its
  `additionalContext`.
- The CLI accepts `--commit <ref>` to fingerprint that commit's branch diff
  (`_iterate_changed_paths`, the exact view the F11 verifier itself
  recomputes) instead of the working tree — the reachable path for an
  already-committed CI change.
- Every ack now stamps `provenance` (`"worktree"` | `"commit"`) naming which
  content it fingerprinted. `check_ci_supplychain_ack` rejects a per-run-
  location ack lacking it; the legacy `iterate_latest` leg is exempt (every
  legacy ack predates the field and cannot be rebased to add it). Kept as a
  required field over the architecture-review call's later suggestion to
  drop it (see `## External LLM Review`) — it is cheap to write, and even
  though no authorization decision reads it today, it is the one signal
  distinguishing this CLI's own output from a hand-assembled file, which is
  exactly what `check_ci_supplychain_ack` needs to reject a forged ack that
  gets run-id and content binding right by copying a real one.
- `campaign-mode.md`, `record_ci_supplychain_ack.py`'s own docstring/refusal
  message, and `docs/hooks-and-pipeline.md` updated to (a) describe the
  guard as a process-identity heuristic, not a cryptographic guarantee, (b)
  name the `CLAUDE_ENV_FILE` propagation path explicitly, and (c) tell an
  operator resolving an escalation not to `export
  SHIPWRIGHT_LOOP_UNIT_ID` themselves, and to `unset` it if in doubt — the
  "enforced, not just stated" framing from the first draft of this fix
  overclaimed the guard's reach before the propagation gap was closed.
- A squash-merge/rebase caveat: rewriting the committed SHA after a
  `"commit"`-provenance ack is recorded invalidates its `provenance_ref`;
  documented as "re-record post-rewrite," matching the existing
  content-fingerprint-change behavior.

**Honesty note carried into the ADR:** the `SHIPWRIGHT_LOOP_UNIT_ID` check is
a mitigation, not a cryptographic guarantee — an agent willing to `unset` its
own inherited environment before invoking the CLI can still defeat it. It
closes the failure actually observed (a runner reaching for the CLI while
still carrying the context that names it as the runner), matching this
repo's existing posture on agent-followed-prose gates (a mitigation,
code-backstopped where possible — see the SubagentStop salvage hook for
Step 8's review cascade).

## Acceptance Criteria
- [x] `record_ci_supplychain_ack.py` refuses to write an ack (in both
  worktree and `--commit` modes) while `SHIPWRIGHT_LOOP_UNIT_ID` is set, with
  no override.
- [x] The CLI accepts `--commit <ref>` and fingerprints that commit's branch
  diff via the same `_iterate_changed_paths` view the F11 verifier uses.
- [x] Every ack the CLI writes carries a `provenance` field (`"worktree"` or
  `"commit"`) plus a `provenance_ref`.
- [x] `check_ci_supplychain_ack` rejects a per-run-location ack missing
  `provenance`; a legacy-location ack missing it still passes (grandfathered).
- [x] `campaign-mode.md` Step 3.4 documents the guard and `--commit` as
  checked, not merely stated, without overclaiming what "checked" covers.
- [x] `SHIPWRIGHT_LOOP_UNIT_ID` reaches a runner's `Bash`-tool subprocesses
  via `CLAUDE_ENV_FILE`, not only the runner's own `additionalContext`
  (`test_claude_env_file_receives_loop_unit_id` et al.).
- [x] Docs/docstrings tell an operator resolving an escalation not to export
  the variable themselves, and how to recover (`unset`) if it is already set.

## Spec Impact
- **Classification:** none
- **NONE justification:** restores the behavior the contract already
  describes (`campaign-mode.md` Step 3.4: "the runner must never write that
  ack itself") by making it enforced instead of prose-only. No FR describes
  this gate's mechanics at a level this change contradicts.

## Out of Scope
- Retrofitting an ack onto PR #718 itself — already merged, and
  `check_ci_supplychain_ack` runs in no GitHub workflow (grepped
  `.github/workflows/*.yml`, 2026-09-11), so it was never a Required Check
  for that PR. Retrofitting by calling the writer's internals past its own
  refusal would be the original violation in a tidier shape.
- A cryptographic / unspoofable operator-identity proof. Not buildable with
  what this repo has (no human-in-the-loop signing infrastructure); see the
  honesty note above.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `record_ci_supplychain_ack.py` | `verifiers/ci_supplychain.py::check_ci_supplychain_ack` (F11) | JSON (`ci_supplychain_ack.json`) |

`touches_io_boundary` does not fire here (no `.env*`/`hooks.json`/`*_config.json`
touched) — this is a `ci_paths`/`provenance` field addition to an existing
JSON contract, not a new boundary.

## Confidence Calibration
- **Boundaries touched:** the ack JSON contract above (writer → F11 reader).
- **Empirical probes run:**
  - Real round-trip: write (worktree mode) → commit → F11 verifier read →
    accept (`test_written_ack_satisfies_the_gate`, pre-existing, still green).
  - Real round-trip: write (`--commit` mode, post-commit) → F11 verifier read
    → accept (`test_commit_mode_acknowledges_already_committed_content`, new).
  - Guard fires in both content modes, with no leak of a partially-written
    file (`test_refuses_inside_an_active_campaign_runner_context`,
    `test_refuses_in_commit_mode_too` — assert the ack file was never
    created).
  - Guard is a no-op absent the env var (`test_allows_when_loop_unit_id_is_unset`).
  - Legacy-location acks (pre-dating `provenance`) still pass; per-run acks
    lacking it are rejected (`test_legacy_ack_without_provenance_is_still_accepted`,
    `test_per_run_ack_without_provenance_is_rejected`).
  - Full `shared/tests/` root re-run after the change: 10594 passed, 33
    skipped, 0 failed — no regression elsewhere in the tree.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | Refuses to write while `SHIPWRIGHT_LOOP_UNIT_ID` is set (worktree mode), no file left behind | tested | `test_refuses_inside_an_active_campaign_runner_context` PASSED |
  | 2 | Refuses in `--commit` mode too | tested | `test_refuses_in_commit_mode_too` PASSED |
  | 3 | No-op when the var is unset (standalone iterate path) | tested | `test_allows_when_loop_unit_id_is_unset` PASSED |
  | 4 | `--commit` mode fingerprints the branch diff and the F11 verifier accepts it | tested | `test_commit_mode_acknowledges_already_committed_content` PASSED |
  | 5 | Worktree mode still stamps `provenance: "worktree"`, `provenance_ref: null` | tested | `test_worktree_mode_stamps_provenance_worktree` PASSED |
  | 6 | Commit mode stamps `provenance: "commit"`, `provenance_ref: <sha>` | tested | `test_commit_mode_acknowledges_already_committed_content` PASSED |
  | 7 | Per-run ack missing `provenance` is rejected by the F11 verifier | tested | `test_verifier_rejects_an_ack_missing_the_provenance_stamp`, `test_per_run_ack_without_provenance_is_rejected` PASSED |
  | 8 | Legacy-location ack missing `provenance` still passes (grandfathered) | tested | `test_legacy_ack_without_provenance_is_still_accepted` PASSED |
  | 9 | Already-committed CI change: working-tree mode now names `--commit` in its refusal instead of falsely claiming "no acknowledgement is needed" | tested | `test_refuses_with_a_pointer_to_commit_once_the_ci_change_is_committed` PASSED |
  | 10 | `cross_component` integration composition: writer CLI + F11 verifier + real git fixtures compose end to end under the new guard and the new content mode (not each tested in isolation) | tested (`category: "integration"`) | `test_commit_mode_acknowledges_already_committed_content`, `test_round_trip_cli_write_commit_verifier_read` (pre-existing) PASSED |
  | 11 | No regression in the ~40 pre-existing ack/deadlock/per-run-home tests, or the sub-iterate-runner Step 3.4 contract tests | tested | full `shared/tests/` (10594 passed) + `plugins/shipwright-iterate/tests/test_sub_iterate_runner_step_3_4.py` + `test_sub_iterate_runner_contract.py` (58 passed) |
  | 12 | `SHIPWRIGHT_LOOP_UNIT_ID` (not only `SHIPWRIGHT_SESSION_ID`) is appended to `CLAUDE_ENV_FILE`, is idempotent across repeated hook runs, and is omitted when unset | tested | `test_claude_env_file_receives_loop_unit_id`, `test_claude_env_file_loop_unit_id_idempotent`, `test_claude_env_file_omits_loop_unit_id_when_unset` (moved to `test_capture_session_id_env_file.py` when the original file crossed the bloat gate) PASSED |
  | 13 | A value with shell metacharacters is shell-quoted before being written into `CLAUDE_ENV_FILE`, not written raw (code-review finding, security) | tested | `test_claude_env_file_quotes_shell_metacharacters` PASSED |

- **Confidence-pattern check:** asymptote — no prior "are you confident?"
  self-report exists yet for this run to contradict. Coverage — every row
  above is `tested`; 0 untested-testable. `cross_component` integration
  composition is covered by row 10 (real writer+verifier+git-fixture
  round-trip, not two units asserted independently).

## Verification (medium+)
- **Surface:** none
- **Justification:** this is an internal iterate-tooling CLI + F11 verifier
  change with no web/API/CLI-product surface of its own — it is exercised
  entirely through its own test suite (the round-trip tests above ARE the
  runner). No `dev_url`, no deployed component, nothing a browser or an HTTP
  client would drive.

## Internal Plan Review
`opus-plan-reviewer` reviewed the mini-plan + architecture brief before build.
Two HIGH findings, both addressed before this spec was finalized:
1. **Propagation unverified.** The `SHIPWRIGHT_LOOP_UNIT_ID` guard's real-world
   efficacy depended on the variable reaching the runner's `Bash`-tool
   subprocess environment, which nothing in the original design actually
   established — `additionalContext` reaches the model, not a subprocess.
   **Fix:** extended `capture_session_id.py`'s `CLAUDE_ENV_FILE` write to
   also carry `SHIPWRIGHT_LOOP_UNIT_ID` (Root Cause 5, Fix, ledger row 12).
2. **False-positive risk against a legitimate operator**, because nothing
   ever unsets the variable. **Triaged as: disclose, not fix in code** —
   there is no variable to unset if the operator never exported it in the
   first place; `campaign-mode.md` Step 3b's `export` line is the
   orchestrator's own shorthand for what the harness sets on the *spawned
   runner's* process, not an instruction aimed at a human terminal. Fixed by
   removing the "an operator never has it set" overclaim and adding explicit
   `unset SHIPWRIGHT_LOOP_UNIT_ID` guidance at the one place a human would
   plausibly copy the export (campaign-mode.md's operator note,
   `record_ci_supplychain_ack.py`'s refusal message and docstring).

## External LLM Review
Branch A, two calls per `--mode iterate` / `--mode architecture` (external_review.py):
- **`--mode iterate`** (over the mini-plan): flagged that `provenance`/
  `provenance_ref` validation was too loose (a `"worktree"` ack with a
  non-null `provenance_ref`, or a `"commit"` ack with a missing one, would
  pass). **Triaged: fix** — added the consistency checks now in
  `_validate_fields` (`ci_supplychain.py`).
- **`--mode architecture`** (over `architecture_brief.md`): approved Option A
  (env-var guard + `--commit` mode), but separately questioned whether
  `provenance` needed to be a *required* field at all, since no described
  authorization decision reads its value. **Triaged: decline** — kept it
  required. Rationale in `## Fix` above: it is the one signal that
  distinguishes this CLI's own output from a hand-assembled forgery that
  otherwise gets run-id and content binding right by copying a real ack;
  "no authorization decision reads it" is true today but is exactly the kind
  of property a forger would exploit if the gate ever stopped checking it.
  The two calls' verdicts do not actually conflict — they answer different
  questions (validation tightness vs. whether the field should exist), and
  the second doesn't dispute anything the first fixed.

## Code Review Cascade (Step 8)
`spec-reviewer` → `code-reviewer` → `doubt-reviewer`, recorded via
`record_review_pass.py` against `reviews.json`.
- **spec-reviewer:** PASS — all 7 ACs verified against concrete code/tests,
  no divergence.
- **code-reviewer:** 3 findings, all fixed —
  1. (medium) `docs/hooks-and-pipeline.md`'s own `capture_session_id.py`
     section didn't mention the new `SHIPWRIGHT_LOOP_UNIT_ID` export →
     updated.
  2. (medium, security) `CLAUDE_ENV_FILE` values were written unescaped —
     a value with shell metacharacters could inject shell content on
     source → both exported values now pass through `shlex.quote`;
     regression test `test_claude_env_file_quotes_shell_metacharacters`.
  3. (low) commit-mode error messages showed the unresolved `--commit` ref
     instead of the resolved SHA → fixed ordering in `build_ack`.
- **doubt-reviewer:** 3 findings (2 HIGH), all fixed —
  1. (HIGH) `write_ack()` itself carried no authorship guard — reachable
     independently of `build_ack()` with a hand-built ack dict → guard
     added to `write_ack()` too; test
     `test_write_ack_refuses_a_hand_built_dict_bypassing_build_ack`.
  2. (HIGH) `CLAUDE_ENV_FILE`'s `SHIPWRIGHT_LOOP_UNIT_ID` write was
     append-only-if-different-value, so a stale export from a finished
     unit could linger indefinitely and block the guard's own documented
     operator-recovery path within the same session → the hook now
     *syncs* tracked export lines to its own current ambient environment
     every `SessionStart` (removes the line when the var is absent,
     replaces it when the value changed) instead of only appending; tests
     `test_claude_env_file_clears_stale_loop_unit_id_when_next_absent`,
     `test_claude_env_file_replaces_loop_unit_id_value_not_accumulates`.
  3. (MEDIUM) `SHIPWRIGHT_LOOP_UNIT_ID` is also set by
     `shipwright-build`'s unrelated `--autonomous` loop (its own
     `section-builder` spawn), so "campaign sub-iterate runner" was a
     narrower description than the guard's actual trigger surface →
     broadened the guard's docstring/refusal message and the mirroring
     prose in `record_ci_supplychain_ack.py` / `campaign-mode.md` to "any
     active autonomous-loop unit"; no behavior change (refusing either
     context is correct).

Two files crossed the 300-line bloat gate during this cascade and were
split rather than exempted: `record_ci_supplychain_ack.py` (guard logic →
`ci_supplychain_authorship_guard.py`) and `capture_session_id.py`
(Phase-Quality injection → `session_start_phase_quality.py`); two test
files followed the same split for the same reason
(`test_capture_session_id_env_file.py`,
`test_record_ci_supplychain_ack_authorship_guard.py`).

## Review Record
All review types answered (`record_review_pass.py show`): `spec` completed
(PASS), `code` completed (3 findings, fixed), `doubt` completed (3
findings, fixed), `plan_internal` completed (`opus-plan-reviewer`, 2 HIGH
findings, both addressed pre-build), `plan` **not_run** (the external
Branch A calls above did run earlier in this session, but the raw
provider JSON needed to replay them through `record_review_pass.py`'s
structured parser was not preserved across a mid-session context
compaction — recorded honestly as `not_run` with the verdicts/triage
pointed at `## External LLM Review` rather than fabricating a payload),
`self` completed, `external_code` not_applicable (advisory; substituted
by the internal cascade above).
