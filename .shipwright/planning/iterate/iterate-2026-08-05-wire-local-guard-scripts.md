# Iterate Spec — Wire the two local-only checkers to something that runs them

- **Run ID:** `iterate-2026-08-05-wire-local-guard-scripts`
- **Date:** 2026-08-05
- **Intent:** CHANGE
- **Complexity:** medium
- **Spec Impact:** NONE — neither checker's behaviour changes; only *when* they run.
- **Cards:** merges P2.27 (`trg-486cb11c`) and P3.03 (`trg-304c764b`, reduced
  successor of `trg-a089c9f7`); launched via the merged card that supersedes
  `trg-03cd5ab5`.
- **Risk flags:** `touches_io_boundary` (hooks.json), `cross_component`
  (`hooks.json` + `**/hooks/*.py`) → integration coverage is mandatory.

## Problem

Two checkers are built, tested, and invoked by nothing — no hook, no SKILL step,
no F-phase, no workflow. They run only when a human types them, so the failure
class each was built to catch is unchanged until someone remembers.

- `scripts/verify_local.py` — mirrors `ci.yml`'s three bespoke merge guards.
  Measured this run: **exit 0, 8.4 s**, all three gates green.
- `shared/scripts/tools/check_required_checks.py` — answers "does the host's
  must-pass check set match the checks that exist?". Measured this run:
  **exit 0, 1.5 s**, and it finds **one real divergence today**:
  `Prepare review request` runs on every PR and gates nothing.

## Decision — one rule, two homes (option D, with the why stated)

The two cards feared that answering separately "would leave the repo with two
conventions". It does not, because **the two scripts are different kinds of
object**:

| | `verify_local.py` | `check_required_checks.py` |
|---|---|---|
| Produces | a **verdict** about the change in front of you | a **finding** about the repository's configuration |
| Exit on a problem | non-zero — it is a gate | **zero** — it files a triage card |
| Answer changes | with every diff | only when a workflow is added/renamed/deleted, or Settings → Rules is edited |
| Portability | monorepo-only (`scripts/`, mirrors *this* `ci.yml` by hardcoded step name) | portable (`shared/`, takes `--project-root`/`--repo`, derives from whatever workflows exist) |
| Needs | nothing external | the operator's own `gh` auth (the Actions token cannot read protection config) |

**Three properties decide it, and they point opposite ways for the two scripts:
portability, whose credentials it needs, and whether its answer moves with the
diff.** Portable + operator-auth + diff-independent → the producer chain.
Monorepo-only + no credentials + diff-dependent → a phase gate. Neither
placement is an oversight; they differ because the subjects differ on all three.

*An earlier draft compressed this to "a check is wired where its answer is
needed, in the form its answer takes". The Stage-3 review was right that this
does no predictive work — it returns no answer for the next member of the same
class (`check_plugin_cache_sync.py --strict`, also built and also invoked by
nothing), and "the form its answer takes" is an exit code someone chose rather
than a property of the subject. The three properties above are what actually did
the deciding, and they are already the columns of the table.*

### Why F0 and not a pre-push hook, for `verify_local.py`

1. **F0 is the cheapest catch, and it narrows — but does not close — the gap the
   script documents about itself.** `describe_tree()` warns: *"These gates read
   the WORKING TREE; CI reads what you PUSH."*

   **An earlier draft of this spec claimed F0 was "the only home where that
   weakness disappears". That was false, and the Stage-3 review falsified it
   from this repo's own files.** Eight phases write tracked artifacts after F0
   (F0.5/F3/F3a/F4/F5/F5a/F5b/F5c — `SKILL.md` says so explicitly), and F11's
   `ensure_current.py` fetches and merges `origin/<default>` before the push. So
   the commit CI judges is F0's tree *plus* eight phases of artifacts *plus* a
   merge of main — and the divergence lands on the input that matters most, since
   `check_ci_gate_coverage.py` reads `.github/workflows` and the gate allowlist,
   both of which can arrive in that merge. A concurrent PR landing a gate step is
   exactly the case the guard exists for, and F0 cannot see it.

   What survives is still worth having and is what this run claims: F0 catches
   the common, boring reasons a push comes back red, at the moment they are
   cheapest to fix — before the commit exists, where a failure costs an edit
   rather than an amend plus a retracted push. The residual F0→push window is
   real, is stated in the docstring and the hooks doc rather than papered over,
   and its proper remedy is a second invocation at F11 after `ensure_current`
   and before the push. That is filed rather than smuggled in here.
2. **Failure is cheapest before the commit.** F0 already STOPs the run. Red at
   pre-push means a commit to amend with F11's delivery machinery
   (`ensure_current` → push → `gh pr create` → `deliver_pr`) already in flight.
3. **The repo answered this question once already.** `verify_local.py`'s own
   `CI_ONLY_GATES` says diff-coverage *"belongs in the F0 suite runner"*, and
   that landed as `iterate-2026-08-01-f0-diff-coverage-gate`. F0 is the
   established home for a CI-only gate.
4. **It reaches the stated population.** The card says the failures came from
   iterate runs and that *"agents execute STEPS rather than CLAUDE.md prose"*.
   F0 is a step agents execute.

**Not done: the gate as code inside `run_test_suite.py`.** An earlier draft
called this "closed on measurement" — that file is 518 LOC against a baseline
`current` of 518, so any addition ratchets and the pre-commit hook rejects it.
**The Stage-3 review showed that reasoning does not hold.** `anti_ratchet.py`
blocks only entries *present in the baseline*; `run_test_suite.py` is a thin
orchestrator over ~11 sibling modules, **none** of which is baselined, so a new
`suite_*.py` module ratchets nothing — and `iterate-2026-08-01-f0-diff-coverage-gate`
did exactly that, under the identical constraint, four days ago. The
Non-Goal's other justification ("would need a new recorded artifact") is also
false: F5 already writes `shipwright_test_results.json`, and a `mirrored_gates`
field there is JSON, not LOC.

So this is a **scope judgement, not a measurement**: mechanically enforcing the
step is possible and unblocked, and this run chose the documented step because
the operator's decision was about *placement*, and because the mechanical
version is a larger change than either card asked for. Recorded honestly so the
next reader does not inherit a foreclosure that was never real.

### Why the producer chain, and not a gate, for `check_required_checks.py`

1. **It is a producer.** It returns 0 on drift and files a card. Putting it
   behind a blocking hook would invent a verdict it does not have.
2. **Its cadence is per-session, not per-push.** Its answer does not depend on
   the diff.
3. **The precedent is exact.** `import_github_findings.py` is a *network*
   producer already in **shipwright-iterate's** SessionStart chain — and only
   there; the local-only producers (`check_drift`, `check_artifact_drift`) are
   in all three. That is the precise slot for a network producer.
4. **It needs no monorepo guard**, unlike `verify_local.py`: it is portable and
   earns its keep in a consumer project too.

### The P3.03 LANDMINE — verified, not deferred

*"A check that does NOT run on every PR blocks every PR forever once it is made
Required. Verify `grade-empirical.yml` before promoting anything to must-pass."*

**Verified 2026-08-05 and already neutralized in code.**
`required_checks_drift.all_workflow_check_names` skips workflows
`workflow_report` marks `dormant`, and its docstring names `grade-empirical.yml`
as the exact case that fix addressed. Confirmed empirically: that workflow is
`workflow_dispatch:`-only, and it is **absent** from the producer's `derived`
list in the live run above. The landmine's precondition is also not reached —
nothing here promotes any check to must-pass; that remains a separate decision.

## Acceptance Criteria

- **AC-1** — F0 runs `scripts/verify_local.py` when the project has it: a step
  in `F0.md` placed after the leak-guard and **before** the suite (8 s of
  fast-fail instead of 7 min), non-zero = STOP.
- **AC-2** — That step is guarded on the file existing, so it no-ops in a
  consumer project. `F0.md` already branches on project shape (`suite` block vs
  not), so the conditional is idiomatic rather than a leak.
- **AC-3** — `check_required_checks.py` runs on SessionStart via a thin hook
  wrapper registered in `plugins/shipwright-iterate/hooks/hooks.json`, after
  `import_github_findings.py`.
- **AC-4** — The wrapper is **fail-soft and silent**: `gh` missing, unauthed, or
  the repo unreachable (the producer's documented `exit 2`) must not make the
  session-start chain report failure, and it must write nothing to stdout.
  Required because `run_if_cache_ready.py` runs children with `check=False` but
  propagates the first non-zero code, and because
  `test_hook_output_schema_compliance.py` **executes every registered hook** and
  validates its stdout against the `SessionStart` schema — the producer's
  human-readable drift paragraph would fail that.
- **AC-5** — Every claim the repo makes about these scripts being unwired is
  corrected in the same diff: `verify_local.py`'s docstring (*"Nothing invokes
  this for you"*, citing `trg-486cb11c`), `CLAUDE.md` (*"Nothing runs it for
  you"*), the `SKILL.md` F0 one-liner, and the hooks registry in
  `docs/hooks-and-pipeline.md`.
- **AC-6** — Integration coverage for `cross_component`: a real-scenario test
  that drives the actual `run_if_cache_ready.py` chain with the new hook
  registered and proves the composition holds (chain completes, exit 0, no
  stdout pollution) when `gh` is unavailable.

## Affected Boundaries

- `plugins/shipwright-iterate/hooks/hooks.json` — hook manifest (io boundary,
  cross-component). Requires a plugin-cache re-sync to take effect at runtime.
- `shared/scripts/hooks/check_required_checks_hook.py` — new hook script.
- `plugins/shipwright-iterate/skills/iterate/references/F0.md` + `SKILL.md` —
  runtime prompts that ship to end users.
- `docs/hooks-and-pipeline.md`, `docs/guide.md`, `CLAUDE.md` — documentation.
- `scripts/verify_local.py` — docstring only, no behaviour change.

## Non-Goals

- **Promoting any check to must-pass.** That is the further decision the card
  explicitly excludes, and it is where the landmine actually lives.
- **A pre-push hook, blocking or advisory.** Superseded by the F0 placement for
  the reasons above.
- **Mechanically proving the F0 step ran.** The step is documented prose plus a
  command, exactly like F0's leak-guard, which works. A verifier would have to
  run post-commit and would need a new recorded artifact — scope beyond both
  cards, and the in-code alternative is bloat-blocked.
- **Acting on the live `Prepare review request` finding.** The producer files
  it; deciding it is the operator's, in triage.

## Confidence Calibration

- **Boundaries touched:** `plugins/shipwright-iterate/hooks/hooks.json` (io
  boundary + `cross_component`); new `shared/scripts/hooks/check_required_checks_hook.py`
  (`**/hooks/*.py`, `cross_component`); a new JSON state file
  `.shipwright/required_checks_state.json` (producer↔consumer round trip); two
  shipped runtime prompts (`SKILL.md`, `F0.md`); three docs; one docstring.

- **Empirical probes run:**
  - `check_required_checks.py` against the live repo → exit 0 in **1.5 s**, and
    it finds **one real divergence today**: `Prepare review request` runs on
    every PR and gates nothing. The producer works and has something to say.
  - `grade-empirical.yml` is `workflow_dispatch:`-only and is **absent** from the
    producer's `derived` list → the P3.03 landmine is already neutralized by
    `all_workflow_check_names`'s `dormant` skip. Verified, not deferred.
  - `verify_local.py` from this worktree → exit 0 in **8.4 s**, all three
    mirrored gates green.
  - Both F0 spellings executed by hand in **both** directions: file present →
    gates run and pass; file absent → no-op. The bash form via Git-Bash, the
    PowerShell form via PowerShell.
  - `run_test_suite.py`'s host file measured with the repo's own counter →
    **518 LOC against a baseline `current` of 518**, i.e. zero headroom. The
    in-code alternative is closed on measurement, not preference.
  - `anti_ratchet_check.py --staged` over the real staged tree → exit 0.
  - Full `shared/tests` root under Git-Bash → **7967 passed, 27 skipped, 0
    failed**. (A PowerShell run first showed 19 `test_hooks.py` failures; that
    shell has no `bash` on PATH — a property of the shell, not the repo or this
    change. Re-run under Git-Bash: 40/40.)

- **Test Completeness Ledger** — 31 behaviors, **0 testable-but-untested**:

| # | Behavior | Status | Evidence |
|---|---|---|---|
| 1 | F0 runs `verify_local.py` when present | tested | `test_f0_runs_verify_local` |
| 2 | The guard is inside the executable snippet | tested | `test_the_f0_step_guards_on_the_file_existing` (+ non-vacuity assert) |
| 3 | A PowerShell spelling exists at all | tested | `test_the_step_is_runnable_on_the_platform_this_repo_is_developed_on` |
| 4 | PowerShell handles a missing `uv` deterministically (`Get-Command` precondition) | tested | `test_the_powershell_spelling_can_actually_stop_the_run`. **Row corrected:** it previously described `$LASTEXITCODE` reset — an ABANDONED design. `CommandNotFoundException` is statement-terminating, so a comparison after the call never executes and no seeded value is read. |
| 5 | PowerShell pops the location in `finally` | tested | same |
| 6 | PowerShell `throw`s on non-zero | tested | same |
| 7 | bash keeps its subshell | tested | same |
| 7a | The guard is on IDENTITY, not a path — a foreign `scripts/verify_local.py` is declined | tested | `test_it_declines_a_foreign_script_at_the_same_path` (executes the snippet) |
| 7b | The snippet actually invokes the script (not merely names it) | tested | `test_both_snippets_actually_invoke_the_script` + `test_it_runs_a_passing_gate` |
| 7c | A passing gate lets F0 continue; a failing one stops it with the exact code | tested | `test_it_runs_a_passing_gate`, `test_it_propagates_a_failing_gate` (asserts `== 3`, not merely non-zero) |
| 8 | The step precedes the suite | tested | `test_the_step_precedes_the_suite` |
| 9 | `SKILL.md`'s summary does not contradict `F0.md` | tested | `test_skill_md_f0_summary_does_not_contradict_the_reference` |
| 10 | No file claims the script is unwired (3 homes) | tested | `test_no_file_still_claims_verify_local_is_unwired` |
| 11 | Producer `exit 2` is not a chain failure, and is silent | tested | `test_the_producers_documented_exit_2_is_not_a_failure` |
| 12 | A hang is bounded and fail-soft | tested | `test_a_hang_is_bounded_and_fail_soft` |
| 13 | The hook's own budget is bounded and declared to fit the chain's 30 s cap | tested | same (`0 < TIMEOUT_SECONDS <= 30`). **Scope corrected:** this pins the constant, not the chain's aggregate — that 30 s bounds all six hooks together, and no test exercises the sum. |
| 14 | An unexpected failure exits 0 but reaches the operator | tested | `test_an_unexpected_failure_still_exits_zero_but_reaches_the_operator` |
| 15 | An undocumented exit code is reported, not swallowed | tested | `test_a_producer_crash_is_reported_but_not_fatal` |
| 16 | `KeyboardInterrupt` is NOT swallowed | tested | `test_control_flow_exceptions_are_not_swallowed` |
| 17 | argv list, never a shell string | tested | `test_the_producer_is_driven_as_an_argv_list_never_a_shell_string` |
| 18 | Absolute producer path, explicit `--project-root`, pinned cwd | tested | `test_the_producer_path_is_absolute_and_the_root_is_explicit` |
| 19 | Child stdout+stderr captured, never forwarded | tested | `test_child_output_is_captured_not_forwarded` |
| 20 | No-op outside a Shipwright project | tested | `test_it_does_nothing_outside_a_shipwright_project` |
| 21 | A bare `.shipwright/` is not a project (fallback ⊆ canonical) | tested | `test_a_bare_shipwright_directory_is_not_a_shipwright_project` |
| 22 | `main()` survives an unresolvable project root | tested | `test_main_survives_a_project_root_that_cannot_be_resolved` |
| 23 | The hook is registered on SessionStart | tested | `test_the_hook_is_registered_on_session_start` |
| 24 | The first run in a window compares | tested | `test_the_first_run_in_a_window_compares` |
| 25 | A second session inside the window does not call out | tested | `test_a_second_session_inside_the_window_does_not_call_out` |
| 26 | The window expires | tested | `test_the_window_expires` |
| 27 | The interval is configurable | tested | `test_the_interval_is_configurable` |
| 28 | An unusable interval falls back to the default | tested | `test_an_unusable_interval_falls_back_to_the_default` (4 cases) |
| 29 | Unreadable state reads as due | tested | `test_unreadable_state_reads_as_due` |
| 30 | A timeout consumes its window; an unstartable producer does not | tested | `test_a_timed_out_producer_still_stamps`, `test_a_producer_that_could_not_start_does_NOT_stamp` |
| 31 | **Integration:** the SHIPPED chain runs clean with the producer registered | tested | `test_the_shipped_chain_runs_clean_with_the_producer_registered` + `test_the_producer_is_reached_and_stays_silent_on_an_unreadable_host` + `test_it_stays_silent_when_gh_itself_is_unavailable` (a real `git init` + origin so resolution succeeds, PATH rebuilt from a copied `git` so `gh` genuinely cannot resolve — asserted via `shutil.which("gh", path=…) is None`, because narrowing to git's own directory hides nothing on Linux where both live in `/usr/bin`, and the test would then hit the real API and still pass) |
| 32 | A filed card lands in the TRACKED log, not the gitignored outbox | tested | `test_one_divergence_files_one_card_across_repeated_invocations` (asserts `triage.jsonl` exists; `read_all_items` unions both stores and cannot tell them apart) + `test_drift_files_one_item_keyed_on_repo_and_branch` |
| 33 | A check that never succeeds eventually says so; a healthy one never nags | tested | `test_a_check_that_never_succeeds_eventually_says_so`, `test_a_succeeding_check_never_nags`, `test_a_fresh_project_is_not_greeted_with_a_staleness_warning` |
| 34 | An unrecordable window skips rather than running unthrottled | tested | `test_an_unwritable_state_file_skips_rather_than_running_unthrottled` |

  Also updated, and caught by the guard rather than by me:
  `test_consolidated_command_preserves_exact_ordered_targets` pins the exact
  ordered SessionStart target tuple per plugin and went red on the new
  registration.

- **Confidence-pattern check:**
  - **Asymptote (depth).** The wrapper's failure modes are enumerated from the
    *chain's* source, not imagined: stderr-forwarded-verbatim and
    first-non-zero-propagated are both read out of `run_if_cache_ready.py`, and
    the 30 s chain cap out of `test_hook_output_schema_compliance`. The three
    that survived review — an unguarded `main()`, a fallback wider than the
    canonical predicate, and a timeout budget incoherent with both neighbours —
    were found by a reviewer reading those same files, which is the evidence
    that depth here came from reading rather than asserting.
  - **Coverage (breadth).** Both wirings, both shells, both directions of the
    file guard, both throttle outcomes (stamped vs not), and the F7 boundary
    from both sides.
  - **Integration composition (`cross_component`).** Behavior 31 drives the real
    `run_if_cache_ready.py` over the targets parsed out of the **shipped**
    `hooks.json`, in order. A hand-assembled chain would have certified a
    composition nobody ships; the test asserts the producer is among those
    targets *before* running, so it cannot pass vacuously.
  - **Known limit, stated:** nothing proves the F0 step *ran*. It is documented
    prose plus a command, exactly like F0's leak-guard. The in-code alternative
    is bloat-blocked (518/518), and a verifier would be a Non-Goal.
