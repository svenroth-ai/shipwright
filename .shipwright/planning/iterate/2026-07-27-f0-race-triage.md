# Iterate Spec: f0-race-triage

- **Run ID:** iterate-2026-07-27-f0-race-triage
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

The F0 suite runner re-runs a unit that failed under concurrency **alone**, and
treats that alone-run verdict as authoritative. That is right: the re-run exists
precisely so a race cannot false-STOP the gate. So a unit that is red in parallel
and green alone leaves the gate GREEN, and the runner prints:

> `red in parallel, GREEN alone. ... this is inter-unit pollution or a flaky test —
> triage it.`

Nothing creates that triage entry. `_retry_note` is a `print`, and no code path
appends anything anywhere, so the instruction is addressed to a human who may not
be reading, in a session that ends. When the session ends the observation is gone —
and a race nobody wrote down comes back at the least convenient moment.

Make the **runner itself** create the entry: durable (survives the session and the
worktree), deduplicated, and loud enough on the console that it is not skimmed past.
The runner already knows everything the entry needs — which unit, that it was red in
parallel and green alone, and that it cannot tell a process race from an unreliable
test.

**This does not change the verdict.** Red-in-parallel + green-alone still does not
stop the gate. The only new way to stop is failing to *record* the observation.

## Acceptance Criteria

- [ ] **AC1 — The runner files the entry itself.** When a unit reports a genuine
      pytest test failure in the parallel pass and PASSES its authoritative alone
      re-run, `shared/scripts/tools/run_test_suite.py` appends a Triage Inbox entry
      naming that unit, in the same process, before it exits. Not a hook, not a
      prose instruction to the agent, not a later phase.
- [ ] **AC2 — The entry outlives the run.** The append targets the **tracked**
      `.shipwright/triage.jsonl` under the run's `--project-root` (the iterate
      worktree), never the gitignored outbox — the same class as the other
      phase-invoked emitters (`generate_security_report.py`, `performance_check.py`,
      `artifact_sync.py`). F6 already stages that path, so the entry ships in the
      iterate PR and reaches `main` on merge; it does not die with the worktree.
- [ ] **AC3 — One open entry per unit; never auto-closed.** `source="f0-suite"`,
      `dedupKey="f0-race:<unit-id>"`, commit-independent and window-less, so a unit
      that races on ten consecutive runs has exactly one open entry. The producer
      **never** auto-dismisses: a race is intermittent by definition, so one clean
      parallel run is not evidence it is gone — auto-resolving would re-create the
      very "the record disappears" failure this closes, one run later. Only an
      operator (CLI / Command Center) closes it.
- [ ] **AC4 — The entry states only what was measured.** Title and detail name the
      unit, that it was red with the units running side by side and green when
      re-run on its own, both exit codes, and whether the unit is xdist-allowlisted;
      and they state explicitly that the runner **cannot** distinguish inter-unit
      pollution / a process race from an unreliable test. No claim of cause.
- [ ] **AC5 — No captured test output in the tracked log.** The failing unit's raw
      stdout/stderr is printed to the F0 console (as today) and is **never** copied
      into the triage entry: the tracked log ships in a PR to a public repo, and
      test output is untrusted text. Title ≤ 160 chars, detail length-capped.
- [ ] **AC6 — Ready to act on, with the REAL commands.** The entry carries a
      `launchPayload` — a `/shipwright-iterate --type bug` block naming the unit plus
      the two commands that reproduce each side of the observation — so the Fix-now
      CTA works from the inbox and the Command Center. The "unit alone" command is
      **the argv the runner actually executed for the authoritative alone re-run**
      (`build_command(unit, None)`, captured on the result), shell-quoted with
      `shlex.join`; the "whole suite in parallel" command is the runner's own CLI. A
      plausible-looking command that differs from what F0 ran would be an attractive
      but unreliable CTA.
- [ ] **AC7 — Loud on the console.** The existing retry WARNING block names, per
      unit, the durable handle that now tracks it (`tracked as trg-xxxxxxxx` — or a
      loud, explicit failure line when it could not be recorded). The operator sees
      an id to act on, not only a sentence to agree with.
- [ ] **AC8 — Fail closed on a lost record (the teeth).** Every raced unit must end
      the run holding a durable handle: the id the append returned, or — when the
      append was suppressed because an **open** entry for that unit already exists —
      that entry's id, resolved from the store by `(source, dedupKey, status=triage)`.
      The append is the authority on whether the write happened (it fsyncs inside the
      triage writer's own lock); a failure of the **read-back alone** never reddens
      the gate, so a damaged record elsewhere in the store cannot false-STOP F0. If a
      race was observed and no handle can be established, the runner prints an
      explicit `FAILED TO RECORD` line naming the unit and the reason, and
      **exit-code precedence** applies: a suite that would otherwise be GREEN exits
      **3**; a suite that is already RED keeps exit **1** — it already STOPs, and 3
      would misdescribe the run. Recording always runs after every retry outcome is
      known and before any return, so a red sibling unit can never skip it. The race
      itself still never stops the gate; only failing to write it down does.
- [ ] **AC9 — Infrastructure-fault retries are deliberately NOT filed.** Only the
      test-failure→green-alone class is tracked. A transient infra fault that did
      not reproduce (`RETRY_INFRA`) is a different diagnosis the runner already
      names — contention between concurrent `uv` processes — and fires on ordinary
      shared-cache noise; filing it would bury the real signal. Stated in code and
      docs, and pinned by a test, so it reads as a decision rather than an omission.
- [ ] **AC10 — The engine stays pure.** `run_suite()` gains no side effect (its
      callers, including every existing test, are unaffected); recording happens on
      the CLI path, and `main()` is exercised end-to-end by at least one test.
- [ ] **AC11 — Docs follow the code (Test-Update-Klausel).** `references/F0.md`
      and `docs/hooks-and-pipeline.md` (the F0 runner section **and** both triage
      artifact-write matrix rows) state the new producer, its dedup key, the
      no-auto-close rule, the tracked-not-outbox routing and exit code 3.
- [ ] **AC12 — Correlation, best-effort and never fatal.** An optional `--run-id`
      is threaded onto the entry (`runId`). The commit is resolved by a non-shell
      `git rev-parse HEAD` with `cwd=<project-root>` and a bounded timeout; a missing
      `git`, a non-repo root, or any other failure yields an entry **without** a
      commit — never an exception and never exit 3.
- [ ] **AC13 — The body is built from an allowlist, not from a result object.**
      `entry_detail` is assembled from named scalar fields only — unit id, the two
      exit codes, the xdist-allowlist boolean, the two quoted commands, and fixed
      explanatory text. No result `repr`, no exception `repr`, no captured-output
      field can reach it, so a later edit cannot accidentally leak test output into
      the tracked log (AC5). Pinned by a test that hands the producer a result whose
      `output` holds a distinctive string and asserts the string appears nowhere in
      `.shipwright/triage.jsonl`.
- [ ] **AC14 — Untrusted-looking text cannot break the entry or the command.**
      The unit id is stripped of control characters and length-capped before it is
      rendered, and is `shlex.quote`d wherever it enters a command string. Title and
      detail caps are enforced **inside the producer**, immediately before the writer
      call, with deterministic truncation. (Unit ids are repo-derived and validated
      against the discovered set today; this is defence in depth and is what
      FR-01.14 already requires of any entry carrying text the project does not
      author.)

## Spec Impact

- **Classification:** modify
- **ADD:** none
- **MODIFY:** FR-01.14 (Triage Inbox) — folds under the existing capability
  (`shared/fr-authoring.md` §3: this extends a capability the product already has,
  it does not mint a new one). One acceptance criterion is added: a local check that
  finds a defect and deliberately lets the run continue records it in the Inbox
  itself, and stops the run if it cannot.
- **REMOVE:** none
- **NONE justification:** n/a

## Out of Scope

- Fixing any actual racing unit. This iterate builds the record, not the repairs;
  the repo currently has no open race.
- Generalising the rule to every non-blocking check in the repo. The AC is written
  for what is delivered here — claiming repo-wide coverage would be a guarantee
  nothing enforces.
- Auto-resolution / staleness GC for these entries (deliberately excluded, AC3).
- Any change to the parallel/serial verdict, the xdist allowlist, CI's serial
  gate, or `run_suite()`'s exit-code contract for units.
- Persisting a captured-output evidence file (rejected: it would live in a worktree
  that is deleted after merge, or force a main-tree write past the leak guard —
  the reproduce commands in AC6 are the better artifact, since a race is reproduced,
  not read).

## Design Notes

No UI.

**Chosen shape: a separate producer module, called from the CLI path.**
`shared/scripts/tools/suite_race_triage.py` owns everything said and recorded about
a raced unit — the operator note, the entry body, the launch payload, the append,
the read-back. `run_test_suite.py` keeps the classification (`unrecorded_races()`,
one predicate next to the `RETRY_SERIAL` constant that defines it) and calls the
producer from `main()`. The existing `_retry_note` moves into the new module: what
we *say* about a raced unit and what we *record* about it are the same statement and
must not drift apart in two files. This also keeps `run_test_suite.py` from crossing
further past the 300-line limit.

**Rejected alternative 1 — record it as an event / in `degraded[]`.**
`shipwright_events.jsonl` is the "what happened" log, and
`shipwright_test_results.json.degraded[]` is per-run state that the *next* run
overwrites — the observation would die one run later instead of one session later.
Triage is the operator's "what is still open" surface (`read_all_items`), is rendered
by the Stop aggregator into `triage_inbox.md`, and is the WebUI Triage tab.

**Rejected alternative 2 — instruct the agent in `F0.md` to file it.**
That is today's failure mode with more words: `_retry_note` already says "triage it".
An instruction with no code behind it is not a record.

**Why fail-closed (AC8) is consistent with "the gate deliberately does not stop".**
Two different questions. The *verdict* question — is this unit red? — is answered by
the authoritative alone re-run, and that answer is unchanged. The *bookkeeping*
question — did the observation survive? — is new, and a producer that fails open
here reproduces the exact defect being fixed. This mirrors the repo's own posture on
gates that used to fail open (`pr_review` truncation, `anti_ratchet`, the scanner
degraded marker).

**Why no auto-dismiss (AC3), unlike `test-evidence`.** `emit_test_failure_triage`
auto-dismisses when a layer goes green, because a layer's red/green is deterministic
per run. A race is not: the *common* case is a clean parallel run. Copying that
pattern here would close the entry on the very next iterate.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `suite_race_triage.emit_race_followups` → `.shipwright/triage.jsonl` (via `triage.append_triage_item_idempotent`) | `triage.read_all_items` → `triage_cli.py`, `aggregate_triage.py` (`triage_inbox.md`), WebUI Triage tab | JSONL (`shared/schemas/triage_item.schema.json`) |
| `run_test_suite.main` (`--run-id`, `--project-root`) | `references/F0.md` invocation | argv |

`touches_io_boundary` does **not** fire: no `.env*` / `hooks.json` / `*_config.json`
/ `*_state.json` path is touched, and the module contains no
`json.dump(s)`/`json.load(s)`/`yaml.*` call — the wire format is produced entirely by
the existing `triage.py` writer, whose round-trip is already pinned by
`shared/tests/test_triage_schema.py`. The read-back in AC8 nevertheless exercises the
producer→consumer round-trip end to end (write via `append_triage_item_idempotent`,
resolve via `read_all_items`), which is what a boundary probe would have asked for.

`cross_component` does **not** fire: no merge/churn/event-log resolver, no
`hooks.json` or `hooks/*.py`, no phase validator, no campaign machinery. (The F11
verifier recomputes this from the diff.)

## Confidence Calibration

- **Boundaries touched:** one — `suite_race_triage.emit_race_followups` →
  `.shipwright/triage.jsonl` → `triage.read_all_items` (and through it
  `aggregate_triage` → `triage_inbox.md`, and the Command Center Triage tab). The
  wire format is produced entirely by the existing `triage.py` writer, so no new
  serializer was written; the round trip is nevertheless exercised end to end
  (append → read back → resolve by `(source, dedupKey, status)`).

- **Empirical probes run** (this machine, 2026-07-27):
  1. **Closed cards do not suppress a re-observation.** Probe against the live
     triage API: append → `None` on the open duplicate → `mark_status(dismissed)` →
     the next append returns a **new** id. The reviewers' worry (a regression months
     later silently dropped) is not reachable. *This was an assumption in the plan;
     it is now measured.*
  2. **Routing is argument-derived, not cwd-derived.** `to_outbox=False` with an
     explicit root writes `<root>/.shipwright/triage.jsonl` and creates no outbox.
  3. **A corrupt record does not raise.** A `{not json` line planted in the store
     yields a warning and the surviving records, not an exception — so the reviewers'
     "an unrelated syntax error exits 3" path does not exist. The redesign (append is
     the authority, read-back is display-only) closes the remaining `OSError` path.
  4. **Six negative controls — each new guard reverted, each reddens a named test:**
     emit nothing → 4 failures; route to the outbox → 3; leak captured output into
     the card → 1 (`test_captured_output_never_reaches_the_tracked_log`); exit 3
     regardless of the verdict → 1; file infra retries too → 1; drop the sanitation
     cap → 2. A guard nobody has watched fail is not a guard.
  5. **A real end-to-end run against a genuinely flaky unit** (throwaway project, one
     plugin unit that fails on its first run and passes on its second), through the
     real `uv`/subprocess/JUnit path — not a stub:
     - run 1: gate **GREEN**, exit 0, card `trg-…` written, console named the handle;
     - run 2, unit now passes in parallel: the card is **still open** — the
       no-auto-close rule holds against the real runner, which is the single design
       decision most likely to have been wrong;
     - run 3, racing again: the **same** card, no duplicate.
     Verified on disk: no `AssertionError`, no `short test summary`, none of the unit's
     output in the store; both reproduce commands present and correct.
  6. **The parallel reproduce command was WRONG until the code review caught it.**
     Probe 5 originally recorded `--project-root .`; re-run after the fix records the
     actual root and `--run-id`, shell-quoted. Kept here because it is the finding
     that most justifies the external pass.

- **Test Completeness Ledger** — principle: testable ⇒ tested. 0 untested-testable.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | A confirmed race writes a tracked entry with the agreed source/severity/kind/dedup key/runId/commit/suiteId | tested | `test_a_confirmed_race_is_written_to_the_tracked_store` |
  | 2 | It lands in the tracked store, never the outbox | tested | same test (asserts the outbox is absent) |
  | 3 | The store is resolved from `--project-root`, not the cwd | tested | `test_the_store_is_resolved_from_the_passed_root_not_the_cwd` |
  | 4 | A repeat sighting reuses the open card and still surfaces the handle | tested | `test_a_second_sighting_reuses_the_open_entry_instead_of_spamming` |
  | 5 | A card the operator closed does NOT suppress a fresh one | tested | `test_a_race_after_the_operator_closed_the_card_opens_a_fresh_one` (+ probe 1) |
  | 6 | Two units racing get one card each | tested | `test_two_units_racing_get_one_entry_each` |
  | 7 | Only the test-failure→green-alone class is filed (infra retry, rc 5, hang, red-both-ways, plain green) | tested | `test_only_a_confirmed_race_is_filed` (5 cases, driven through the real `unrecorded_races` → producer path) |
  | 8 | …and that holds through the CLI, not just the predicate | tested | `test_an_infra_retry_is_not_filed_end_to_end` |
  | 9 | Captured test output never reaches the published log | tested | `test_captured_output_never_reaches_the_tracked_log` (+ negative control) |
  | 10 | Control characters stripped, title capped after formatting | tested | `test_control_characters_and_length_are_neutralised`, `test_the_title_is_capped_after_formatting` |
  | 11 | The dedup key is identity and is never truncated (no prefix collision) | tested | `test_the_dedup_key_is_identity_and_is_never_truncated` |
  | 12 | Reproduce commands are never truncated (a command cut mid-quote is a broken CTA) | tested | `test_the_reproduce_commands_are_never_truncated` |
  | 13 | Commands are shell-quoted and carry the unit's directory | tested | `test_a_command_is_shell_quoted_and_carries_the_units_directory` |
  | 14 | The alone-run command is the argv the runner actually re-ran | tested | `test_the_launch_payload_reproduces_both_sides_with_the_real_command` |
  | 15 | The parallel command names the real root + run id, not a hard-coded `.` | tested | `test_the_parallel_command_names_the_root_and_the_run`, `test_the_recorded_parallel_command_targets_the_run_root` |
  | 16 | The card states the cause is undetermined and that it is never auto-closed | tested | `test_the_card_says_what_was_measured_and_claims_no_cause` |
  | 17 | An append failure / unimportable triage API is reported, never raised | tested | `test_an_append_failure_is_reported_not_raised`, `test_an_unimportable_triage_api_is_reported_not_raised` |
  | 18 | A read-back failure after a successful append is still "recorded" | tested | `test_a_read_back_failure_after_a_successful_append_is_still_recorded` |
  | 19 | Only this producer's open entries resolve a handle | tested | `test_only_this_producers_open_entries_resolve_a_handle` |
  | 20 | The console names the handle / shouts when the record was lost | tested | `test_the_console_names_the_durable_handle`, `test_the_console_shouts_when_the_record_was_lost` |
  | 21 | An infra retry keeps its own note and gets no handle; no retries renders nothing | tested | `test_an_infra_retry_keeps_its_own_note_and_no_handle`, `test_no_retries_renders_nothing` |
  | 22 | The summary table and a red unit's captured output still print (refactor is behaviour-preserving) | tested | `test_the_summary_table_tags_every_outcome_and_flags_a_retry`, `test_a_failing_units_captured_output_IS_shown_on_the_console`, `test_the_summary_still_prints_after_the_refactor` |
  | 23 | Green suite + lost record → exit 3 | tested | `test_a_green_run_that_could_not_record_the_race_exits_three` |
  | 24 | Red suite + lost record → exit 1, still shouted about | tested | `test_a_red_run_keeps_its_own_exit_code` |
  | 25 | A red sibling never skips the recording | tested | `test_a_red_sibling_never_skips_the_recording` |
  | 26 | A clean run writes nothing and leaves exit 0; a config error still exits 2 | tested | `test_a_clean_run_writes_nothing_and_keeps_exit_zero`, `test_a_config_error_still_exits_two_without_touching_the_store` |
  | 27 | `--run-id` is optional; its absence is a null field, not a placeholder | tested | `test_run_id_is_optional_and_its_absence_is_recorded_as_absent` |
  | 28 | Commit resolution on a non-repo root / missing git yields no commit, no error | tested | `test_commit_resolution_on_a_non_repo_root_yields_no_commit`, `test_a_missing_git_binary_yields_no_commit` |
  | 29 | Operator-facing strings stay ASCII in the two NEW modules | tested | `test_operator_facing_strings_are_ascii_only` (extended to `suite_report`, `suite_race_triage`) |
  | 30 | The whole path works against a real flaky unit, incl. no-auto-close over three consecutive runs | untestable | `requires-external-nondeterministic-service` — a genuine inter-process race cannot be produced deterministically in CI; a marker-file stand-in in a unit test would only re-assert rows 1/4/7. Measured instead as probe 5 (three real runs of the real CLI). |

  Counts: testable 29 · tested 29 · untestable 1 · **untested-testable 0**.
  Enumeration basis: 14 ACs → all covered (AC1 rows 1/8, AC2 rows 2/3, AC3 rows 4-6,
  AC4 row 16, AC5 row 9, AC6 rows 12-15, AC7 row 20, AC8 rows 17/18/23/24/25,
  AC9 rows 7/8/21, AC10 rows 22/26, AC11 = docs (below), AC12 rows 27/28,
  AC13 row 9, AC14 rows 10/11).

  AC11 (docs follow the code) is not a runtime behavior: `references/F0.md`,
  `docs/hooks-and-pipeline.md` (F0 table + both triage write-matrix rows) and the
  FR-01.14 criterion are in this diff and reviewed by eye.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two ways this change could be worse than doing nothing
    were both driven empirically rather than asserted. **(a) It files noise** — bounded
    by restricting the producer to the test-failure→green-alone class (row 7, negative
    control 5) and by one open card per unit (rows 4-6). **(b) It turns a green gate
    red for a bookkeeping problem** — bounded by making the append, not the read-back,
    the authority (row 18, probe 3) and by the exit-code precedence rule (row 24). The
    external code review then found a third way to be worse than nothing that neither
    I nor the plan review had seen: a card carrying a *plausible but wrong* reproduce
    command (rows 12/15) — worse than no command, because it is trusted.
  - *Coverage (breadth):* every AC maps to at least one row; the boundary is probed
    from both sides (this producer writes, `read_all_items` reads) and against the
    live API rather than a mock.
  - *Integration composition:* the `cross_component` flag does **not** fire — the diff
    touches no hook, `hooks.json`, phase validator, or campaign/event/merge machinery.
    The F11 verifier recomputes this from the diff; if it fires, an
    `category:"integration"` behavior must be added.

- **Degraded conditions (recorded in `shipwright_test_results.json.degraded[]`):**
  1. The `touches_auth` risk flag from `classify_complexity` is a **prose false
     positive** — the taxonomy matches the literal `session` in "outlives the
     session". The diff-driven `risk_detectors` predicates, which are authoritative,
     return no flag. Overridden.
  2. The **Gemini leg of the external CODE review returned a degraded reply** (an
     unfinished internal monologue, not a review) although the transport reported
     success. Recorded as `parse_status: partial`; the OpenAI leg returned 4 findings,
     all dispositioned and fixed. The plan-review round had both legs healthy.
  3. The **`code` and `doubt` review passes did not run** — a session directive
     forbids spawning subagents. Both are closed explicitly in the review record with
     that rule named, and substituted (external code review on the same diff; six
     negative-control probes for the adversarial role).
