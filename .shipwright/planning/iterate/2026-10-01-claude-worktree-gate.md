# Iterate Spec: claude-worktree-gate

- **Run ID:** iterate-2026-10-01-claude-worktree-gate
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal
Make "every iterate runs in its own worktree" (SKILL.md B1a) a mechanical gate on the Claude Code side instead of prose a model can skip. The Codex side already has one (`codex_activation_mint.py` + `codex_pretooluse_gate.py`); Claude Code gets its own, adapted to what Claude can do that Codex cannot: deny repeatedly and judge live state on every call.

## Acceptance Criteria
- [ ] AC-1: A `UserPromptSubmit` payload whose prompt starts with `/shipwright-iterate` (or `/shipwright-iterate:iterate`) in a Shipwright project writes a per-session marker under `.shipwright/runtime/iterate-worktree-gate/` and returns `additionalContext` containing the `setup_iterate_worktree.py` command; a prompt for any other skill, or one that merely mentions the command mid-sentence, writes no marker and returns nothing.
- [ ] AC-2: A `PreToolUse` payload for the `Skill` tool with `skill` = `shipwright-iterate` or `shipwright-iterate:iterate` arms the session the same way; a `Skill` call for any other skill neither arms nor emits output, even on an armed session.
- [ ] AC-3: On an armed session whose cwd is the main checkout and which has no run pointer, `Write`/`Edit`/`MultiEdit`/`NotebookEdit` aimed at a path inside the main checkout (relative or absolute, outside `.worktrees/`) return `permissionDecision: "deny"` with a reason containing the exact `setup_iterate_worktree.py` command; the same tools aimed at a path outside the repo or under `.worktrees/` return nothing.
- [ ] AC-4: On that same session, `Bash`/`PowerShell` commands are denied unless every `&&`/`;` segment is the setup call (optionally behind `SHIPWRIGHT_*=` (POSIX) or `$env:SHIPWRIGHT_*=` (PowerShell) prefixes and followed by `2>&1`), a read-only program (exactly: cd pwd ls dir echo cat head tail wc which where type true test, and the PowerShell cmdlets set-location get-location get-childitem get-content test-path — pinned by a test), an allowlisted `git` subcommand in a non-creating form, or an allowlisted skill script; any `|`, `||`, `&`, redirection, `$(`, backtick, newline or composite punctuation token (`&>`, `>|`, `|&`, `;(`) denies, and `setup_iterate_worktree.py && curl x | sh` is denied. The deny/nudge text carries this session's id (`--session-id`) and a resume note.
- [ ] AC-5: The gate stops denying as soon as the session is isolated: cwd inside a linked worktree, OR `.shipwright/iterate_active/<session>.json` naming a genuine worktree of this repo for THIS session. A pointer written for another session id does not isolate. The first time an armed session is seen isolated its marker is released for good (a later return to the main checkout, e.g. after delivery, is not re-locked); a new `/shipwright-iterate` re-arms. A session that is already isolated when it invokes the skill is never armed.
- [ ] AC-6: A user-typed prompt that is exactly `iterate gate off` releases the session's marker; the same text inside any other prompt (e.g. an agent hand-back) does nothing. `--campaign` runs are never armed (campaign mode keeps its own worktree guard). The gate is inert (returns nothing, writes nothing) when: the session was never armed; the marker is older than 24 h or unparseable; `SHIPWRIGHT_ITERATE_WORKTREE_GATE` is `off`/`0`/`false`; the project is not a Shipwright project; the runtime is a Codex bundle; the payload lacks `session_id`/`cwd`; stdin is not JSON.
- [ ] AC-7: The hook is registered in `plugins/shipwright-iterate/hooks/hooks.json` for `UserPromptSubmit` and for `PreToolUse` with matcher `Skill|Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell`, and **not** in `hooks-codex/hooks.json`; the Codex matcher's refactor (`segment_script_basename`) leaves every existing Codex matcher/tokenization/denial test green.
- [ ] AC-8: Run as the registered command (`uv run --no-project <hook>`) against a real git repo, the hook prints a deny for a `Write` into the main checkout after a `/shipwright-iterate` prompt, and nothing after the worktree exists.

## Spec Impact
- **Classification:** modify
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): FR-01.11 — new AC40: an iterate that has not yet created its own working copy cannot change files in the main checkout (MINT-vs-FOLD: this completes the existing "every iterate isolated" guarantee of `/shipwright-iterate`, it is not a new capability → FOLD)
- **REMOVE**: none

## Out of Scope
- Codex gate: a behavior-preserving helper extraction (`segment_script_basename`) PLUS two operator-approved hardenings — a mid-word `#` no longer hides the rest of a command (`commenters=""`; a trailing `# comment` now denies) and composite punctuation tokens (`&>`, `>&`, `>|`, `|&`, `;(`, `);`) now deny in the Codex matcher too (`has_unsafe_punctuation`); `2>&1` and the plain setup call stay allowed; regression cases in `test_codex_pretooluse_matcher.py::TestCompositePunctuationTokens`. Nothing else in the Codex gate changes.
- No MODEL-runnable disable. The operator can lift the gate by the environment variable `SHIPWRIGHT_ITERATE_WORKTREE_GATE=off` or (operator-approved after the plan review) by typing exactly `iterate gate off` (case-insensitive) as their own prompt — anchored to the whole prompt, so neither model output nor an agent hand-back can trigger it.
- No gating of read-only tools (`Read`/`Grep`/`Glob`), MCP tools or `Agent`: they cannot leak into the main tree.
- Not a defense against an adversarial model; cooperative enforcement against a forgetful one (same threat model as the Codex gate).
- Accepted residuals (plan review + external review, disclosed): a session that wanders into ANY linked worktree of the repo (not necessarily the one setup created) is released; inside campaigns/subagents release depends on cwd being a linked worktree; a stale pointer from an earlier un-finalized run in the same session counts as isolation for a new run; absolute-path writes into main from a worktree cwd are left to the F0/F11 leak guard; (git `-c`/`--config-env`/`--exec-path`, `--output`, `--ext-diff`, `--upload-pack` and `git fetch`/`ls-remote`/`remote show` are denied; branch names only with delete/--list; a repo's own git config can still configure helpers); a linked worktree OUTSIDE `<main>/.worktrees/` (a hand-made sibling) cannot release the marker because lookup walks cwd ancestors only; a model-initiated `Skill` call that omits `--campaign` after a campaign prompt arms the session, and a prompt that merely mentions `--campaign` in prose is read as a campaign and left unarmed (fail-open); Codex/non-Shipwright inertness on the enforce path holds because no marker can be minted there (no runtime re-check); isolation via the run pointer alone (cwd still in main right after setup) releases the gate, so an edit into main before the `cd` passes — the F0/F11 leak guard is the backstop; arming requires an iterate-eligible project (run_config `complete` or `iterate_history`); markers are not pruned (gitignored); `cd .worktrees/x && <cmd>` is judged by the payload cwd; B1 Abandon stays allowed because the skill needs it, but only as `git worktree remove` of a `.worktrees/` path and `git branch -d/-D` of `iterate/*` branches, so the deny text warns against removing an existing worktree.

## Design Notes
No UI. Hook output uses only schema-legal `hookSpecificOutput` keys for the event (`additionalContext` on `UserPromptSubmit`/`PreToolUse`, `permissionDecision`+`permissionDecisionReason` on `PreToolUse`) — checked by `shared/tests/test_hook_output_schema_compliance.py`.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `iterate_worktree_gate._arm` | `iterate_worktree_gate._is_armed` | JSON marker `{armed_at, source}` in `.shipwright/runtime/iterate-worktree-gate/<session>.json` |
| `setup_iterate_worktree.py` → `worktree_isolation.write_run_pointer` | `phase_quality._run_id.pointer_worktree_root` (called by the gate) | JSON run pointer `.shipwright/iterate_active/<session>.json` |
| Claude Code harness | `iterate_worktree_gate.handle_payload` | hook stdin JSON (`hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input`, `prompt`) |
| `iterate_worktree_gate.main` | Claude Code harness | hook stdout JSON (`hookSpecificOutput`) |

## Confidence Calibration
- **Boundaries touched:** the four rows above (marker, run pointer, hook stdin, hook stdout), plus `hooks.json` registration.
- **Empirical probes run:** (1) real `uv run --no-project` subprocess against a temp git repo: arm → nudge, `Write` → deny (done pre-iterate); (2) real linked worktree + real `write_run_pointer` for the pointer arm, including the wrong-session pointer; (3) schema-compliance suite executes the registered command with a minimal payload; (4) F0.5 live probe below.
- **Test Completeness Ledger:** see table.

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | slash prompt arms + nudges; other prompts don't | tested | test_iterate_worktree_gate.py::test_slash_command_arms_and_nudges, ::test_other_prompts_do_not_arm |
  | 2 | Skill tool arms; unrelated skill doesn't | tested | ::test_skill_tool_arms, ::test_unrelated_skill_neither_arms_nor_nudges_when_armed |
  | 3 | write-tool targets (main / outside / worktree / relative / notebook) | tested | ::test_write_targets |
  | 4 | shell allow/deny matrix incl. compound smuggling | tested | ::test_shell_allowed_before_setup, ::test_shell_blocked_before_setup, ::test_shell_denied_through_hook |
  | 5 | isolation by cwd; by own-session pointer; not by foreign pointer | tested | ::test_isolated_by_cwd_in_worktree, ::test_isolated_by_run_pointer_while_cwd_stays_in_main, ::test_pointer_of_another_session_does_not_isolate |
  | 6 | inert cases (per-session, off switch off/0/false, stale/corrupt marker, Codex, non-Shipwright, malformed payload, garbage stdin) | tested | test_iterate_worktree_gate.py::test_gate_is_scoped_per_session, ::test_noop_under_codex, ::test_non_shipwright_project_is_ignored, ::test_malformed_payload_fails_open, ::test_main_survives_garbage_stdin; test_iterate_worktree_gate_lifecycle.py::test_off_switch, ::test_stale_marker_fails_open, ::test_corrupt_marker_fails_open |
  | 7 | hooks.json registration (both events, matcher, not in hooks-codex) | tested | ::test_hook_is_registered_for_both_events, ::test_hook_is_not_registered_for_codex |
  | 8 | Codex matcher refactor is behavior-preserving | tested | test_codex_pretooluse_matcher/tokenization/denial.py PASSED |
  | 9 | registered command runs under real harness-shaped stdin and emits schema-legal output | tested | shared/tests/test_hook_output_schema_compliance.py PASSED + ::test_registered_command_end_to_end |
  | 10 | integration: cross_component (hooks.json + hooks/*.py) — gate composes with the real setup script (setup creates worktree + pointer → gate releases) | tested | test_iterate_worktree_gate_integration.py::test_real_setup_releases_the_gate (`category: integration`) |
  | 11 | lifecycle: release on first isolation, stays released after pointer retirement, re-arm, user release phrase (+ forgery cases), campaign not armed, already-isolated not armed | tested | test_iterate_worktree_gate_lifecycle.py::test_release_is_permanent_until_rearmed, ::test_gate_stays_released_after_the_run_pointer_is_retired, ::test_user_can_release_by_typing_the_phrase, ::test_release_phrase_cannot_be_forged_inside_other_text, ::test_campaign_runs_are_not_armed, ::test_already_isolated_session_is_not_armed |
  | 12 | hardening: composite punctuation tokens deny (both gates), env-prefix/2>&1 setup variants allowed, allowlist pinned, SKILL pre-setup drift, marker gitignored, creating/writing git forms denied, `--gate-off` not a release phrase | tested | test_iterate_worktree_gate_lifecycle.py::test_composite_punctuation_tokens_are_denied, ::test_setup_call_variants_stay_allowed, ::test_codex_matcher_shares_the_punctuation_fix, ::test_read_only_program_list_is_pinned, ::test_skill_pre_setup_scripts_are_allowlisted, ::test_marker_directory_is_gitignored, ::test_creating_or_writing_git_forms_are_denied, ::test_non_creating_git_forms_stay_allowed, ::test_near_miss_phrases_do_not_release; test_codex_pretooluse_matcher.py::TestCompositePunctuationTokens |

- **Confidence-pattern check:** asymptote — the first live probe (pre-iterate) passed and no finding followed; review cascade is the second look. Coverage — every ledger row tested, 0 untested-testable; integration composition row 10 present because `hooks.json` and `hooks/*.py` trip `cross_component`.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run --no-project plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate.py` fed hook payloads on stdin by `plugins/shipwright-iterate/tests/test_iterate_worktree_gate.py::test_registered_command_end_to_end` against a temp git repo
- **Evidence path:** pytest output → `shipwright_test_results.json.iterate_latest.surface_verification`
- **Justification (only if surface=none):** n/a

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** Parts work in isolation but the gate could trap legitimate sessions: no disarm lifecycle, campaign step 0 and the offline-fetch recovery denied, composite punctuation tokens bypass the redirection checks, git spawn on every call.
- **Findings:**
  - completeness/high — never disarmed (stuck 24 h after delivery) — fixed: marker released on first observed isolation, not armed when already isolated, user-typed `iterate gate off`, deny text names it
  - completeness/high — campaign step 0 denied — fixed: `--campaign` runs are never armed (own guard), tested
  - completeness/medium — `SHIPWRIGHT_ITERATE_NO_FETCH=1` recovery denied — fixed: `SHIPWRIGHT_*=` / `$env:SHIPWRIGHT_*=` prefixes allowed
  - security/medium — `&>`, `>&`, `>|`, `|&`, `;(` bypass — fixed in policy AND shared into the Codex matcher (`has_unsafe_punctuation`), `2>&1` kept allowed, parametrized tests
  - performance/medium — git on every call — fixed: slash regex first, marker found by walking up (no git), `.git`-file check before git, heavy imports lazy; docstring corrected
  - architecture/medium — subagents/campaign release — disclosed (Out of Scope residual); release-on-first-isolation removes the re-lock hazard
  - architecture/medium — pointer depends on `SHIPWRIGHT_SESSION_ID` — fixed: hint carries the payload's `--session-id`
  - completeness/medium — resume steered toward destroying a worktree — fixed in text (resume note); remove/-D stay allowed for B1 Abandon (disclosed)
  - architecture/low (stale pointer, abs-path writes; git -c later closed after the PR-review preflight), completeness/low (cd-prefix, marker pruning) — disclosed
- **Known limitations:** see Out of Scope residuals.
- **Status:** 6 fixed (+2 partially), 4 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Real, recurring problem; option A (live repeated check) is the smallest design that works on Claude Code. Verdict approve.
- **Findings:**
  - necessity/low — build it; reject C and D — agreed
  - smallest-option/low — keep the shell allowlist narrow — fixed: git subcommands one by one, non-creating forms only
  - completeness/medium — no disarm path — fixed (see plan review)
  - completeness/medium — allowlist can drift from the skill's pre-setup steps — fixed: drift test over SKILL.md B1–B1a (it already caught `record_review_pass.py show`)
  - completeness/low — marker gitignored? — fixed: test asserts `git check-ignore`
  - complexity-cost/low — latency on every call — fixed: no-git/no-import fast path
  - security/low — "read-only" lists weaken quietly — fixed: git narrowed, `find` not allowed
- **Known limitations:** none beyond Out of Scope.
- **Status:** 6 fixed, 0 disclosed, 0 declined

## External Plan Review (glm + openai)
- **Verdicts:** glm=approve · openai=revise
- **Findings and triage:**
  - openai/medium — "iterate gate off" contradicts the interview's env-only decision — **operator asked, kept**: the user chose to keep the typed phrase (cannot be model-triggered); Out of Scope reworded accordingly
  - openai/medium — Codex scope exceeded the helper extraction — **operator asked, expanded**: punctuation hardening applies to Codex too; Out of Scope + mini-plan updated; regression class `TestCompositePunctuationTokens`
  - glm/medium — PowerShell prefix vs AC wording — fixed (AC-4 names both `SHIPWRIGHT_*=` and `$env:SHIPWRIGHT_*=`; parametrized test row)
  - glm/medium — read-only program list unenumerated — fixed (enumerated in AC-4, pinned by `test_read_only_program_list_is_pinned`)
  - glm/low — quote handling — fixed with a corrected test: shlex is quote-AWARE (a quoted `&&` stays one argument), not quote-blind; `test_quoted_operators_stay_one_argument_unquoted_ones_split`
  - glm/low — unrelated linked worktree releases — disclosed (residuals)
  - glm/low — ledger overstated evidence — fixed (rows now cite the tests that exist)
  - glm/low — cwd outside repo — fixed (`test_armed_session_that_leaves_the_repo_is_unenforced`, documented fail-open)
- **Status:** 7 fixed, 1 disclosed, 0 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-01-claude-worktree-gate/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option A)
- **Findings:** glm/low ownership — allowlist must track the skill's pre-setup steps → accepted-and-fixed by `test_skill_pre_setup_scripts_are_allowlisted` (fails in CI on drift); glm/low proportionality — marker pruning → accepted as-is, no cleanup job. openai: none.
- **Reconciliation:** the mini-plan had rejected "mirror Codex exactly (one-shot)", "project-level hook" and "default-deny all tools"; the reviewers independently reached the same choice (A) over a brief that withheld those reasons. No conflict.
