# ADR-001: Multi-Session Pipeline Orchestration for `/shipwright-run`

- **Status:** Accepted
- **Date:** 2026-04-25
- **Branch:** `iterate/multi-session-run-orchestrator`
- **Deciders:** Sven Roth
- **Plan:** `~/.claude/plans/ich-m-chte-shipwright-run-vivid-scott.md` (v4)

## Context

Until 2026-04-25, `/shipwright-run` was a **single-session orchestrator**:
the master Claude session called every SDLC phase (`project → design → plan
→ build → test → changelog → deploy`) sequentially as inline slash commands
**within the same session**. That model produced four operational pain
points:

1. **Context pressure compounded across phases.** Every phase's transcript
   stayed in the master session's context. Long pipelines hit auto-compaction
   mid-build, silently dropping prior decisions.
2. **No failure isolation.** A blowup in any phase (build review loop,
   security findings, test flakiness) tore down the whole pipeline session.
3. **No granular resume / out-of-order execution.** The master tracked
   `current_step`, but you couldn't selectively re-run a phase from a fresh
   session, branch by split, or have multiple phases worked on concurrently.
4. **Single Kanban task in the WebUI.** Users saw one flat "Run-XXX" task
   with no per-phase visibility, no per-phase status, no per-phase artifacts.

We want each phase to run in its own CLI session for failure isolation,
clean context budgets, and per-phase Kanban cards in the WebUI — but without
breaking standalone `/shipwright-project`, `/shipwright-build`, etc.
invocations users rely on outside of `/shipwright-run`.

## Decision

The master `/shipwright-run` becomes a **pipeline coordinator** that does
nothing more than write the spec and print a launch card. Pipelines run
across many external Claude CLI sessions, one per phase. Specifically:

1. **Schema bump to v2.** `shipwright_run_config.json` carries
   `schemaVersion: 2`, an immutable `runId`, frozen `runConditions`
   (`securityEnabled`, `splitMode`, `aikidoClientIdPresent`), `splits_frozen[]`,
   and the authoritative `phase_tasks[]` array. v1 configs are
   **hard-fail** rejected by phase-lifecycle subcommands; standalone phase
   skills still work on legacy configs because they don't read the run
   config.
2. **`phase_tasks[]` is the state.** Each entry pre-binds a `sessionUuid`
   (uuid4), tracks `status ∈ {backlog, awaiting_launch, in_progress, done,
   failed, skipped}`, and carries CAS metadata: `version` (monotonic),
   `claimedBySessionUuid`, `claimAttemptedAt`, `executionCount`. The master
   writes only the project task; subsequent tasks are appended by the state
   machine when a phase completes.
3. **Declarative state machine.** A pure function in
   `phase_state_machine.py` maps `(predecessor_phase, splitId, run_conditions,
   splits_frozen) → next_phase_spec | None`. The orchestrator wraps it to
   generate IDs and write phase_tasks atomically. 14 transitions; no
   branching code outside the table. `phase` and `splitId` are stored
   separately throughout — never as combined strings like `"plan/01-core"`.
4. **CAS-protected lifecycle subcommands** on `orchestrator.py`:
   `plan-next-phase`, `claim-phase-task` (with `--expected-phase` for
   wrong-skill rejection), `complete-phase-task` (owner+version checked),
   `mark-phase-failed` (owner+version checked), `recover-phase-task`
   (version bump + claim release for crash recovery), `freeze-splits`,
   `validate-prerequisites`, `get-phase-task`,
   `find-phase-task-by-session-uuid`. Exit codes: `0=ok`, `1=generic
   error`, `2=fail-closed` (used by hooks to enforce blocking).
5. **External CLI launch via paste-able banner.** The master prints
   `claude --session-id <uuid> --add-dir <root> --name 'Run-XXX / phase' '/shipwright-<phase>'`.
   The user pastes this in a new terminal. The master never spawns
   subprocesses. The pre-bound `sessionUuid` is what makes phase-session
   discovery possible.
6. **Three new shared phase-session hooks** wired into all 8 phase
   plugins:
   - `phase_session_start.py` (SessionStart): sessionUuid match → CAS claim
     → write `sessionstart-validation.json` + optional `.block-pending`
     sentinel → emit `SHIPWRIGHT-PIPELINE-CONTEXT` via
     `hookSpecificOutput.additionalContext`.
   - `phase_user_prompt_validate.py` (UserPromptSubmit): reads
     `.block-pending` (single-use), returns `decision: "block"` plus exit 2
     to abort wrong-skill / failed-prereq launches before the LLM runs.
   - `phase_session_stop.py` (Stop, before audit/handoff): re-discovers
     `phaseTaskId`, parses `result.ok` from local config, calls
     `complete-phase-task` or `mark-phase-failed`, runs `freeze-splits`
     for the design phase.
7. **Step 0 Phase Session Context Recovery preamble** in every phase
   skill. If `SHIPWRIGHT-PIPELINE-CONTEXT` is in context, parse
   `phaseTaskId` and run `get_phase_context.py --phase-task-id <id>` to
   load prior phase artifacts before Step 1. If absent, this is a
   standalone invocation and Step 1 runs as before — no behaviour change.
8. **Final-status responsibility lives with the phase, not the master.**
   The deploy phase's `complete-phase-task` flips `run.status = "complete"`
   when the run-completion invariant holds (deploy `done` AND every other
   `phase_tasks[]` is in a terminal state). If the invariant fails, status
   becomes `needs_validation` and a `pipeline_completion_blocked` event is
   emitted. The master is observational only (`master_stop_check.py` prints
   a status banner to stderr, never writes state).
9. **Run conditions frozen at run creation.** `securityEnabled` is captured
   from `os.environ.get("AIKIDO_CLIENT_ID")` at `write-config` time;
   subsequent env changes do not retroactively reshape the pipeline.
   `splitMode` is frozen at design completion via `freeze-splits` (with
   fallback chain design → project → none, never abort).

## Consequences

### Positive

- **Clean context per phase.** Each phase session starts fresh and only
  loads its own prerequisites via `get_phase_context.py`.
- **Failure isolation.** A failed build session no longer torpedoes the
  pipeline state; the orchestrator records `failed`, the user runs
  `recover-phase-task` and re-launches.
- **Granular resume.** `recover-phase-task` releases the CAS lock and
  bumps `version`; the crashed session's stale `complete-phase-task` is
  rejected with exit 2.
- **Per-phase Kanban visibility** (delivered later in the WebUI repo, see
  *Follow-Up* below). The contract surface for that work is
  `shared/schemas/run_config.v2.schema.json`.
- **State machine is testable in isolation.** `phase_state_machine.py` is
  a pure function; the unit tests in `test_phase_state_machine.py` cover
  all 14 transitions including `splitMode=none`, multi-split, security
  on/off, and pipeline-terminal.

### Negative

- **More user interaction per pipeline.** The user pastes one launch
  command per phase (≈7-8 paste actions for a full pipeline) instead of
  watching the master drive everything. Mitigated long-term by the WebUI
  Kanban surfacing launch cards as buttons.
- **No automatic phase advancement when a session has crashed.** Stale
  `in_progress` tasks require `recover-phase-task`; we deliberately
  rejected heartbeat-based mtime stale detection for this iterate
  (kept as future work).
- **Hard cut on schema v1.** Legacy v1 `shipwright_run_config.json` files
  fail with a clear error pointing the user at "rename and re-run
  /shipwright-run". We do not maintain a dual-schema runtime.
- **More moving parts.** Three new hook scripts and a new tools script
  (`get_phase_context.py`) per pipeline launch; coordinated by the
  declarative state machine plus CAS subcommands.

### Neutral

- Standalone phase invocations (`/shipwright-build` without a run config,
  or with no `sessionUuid` match) are unaffected — both phase-session
  hooks no-op and Step 0 falls through to the existing Step 1.

## Alternatives Considered

1. **Subprocess spawning by the master.** Have the master `Popen` each
   phase as a child Claude CLI process. Rejected: violates the
   WebUI-spawn invariant (the WebUI is the only thing allowed to launch
   external CLI sessions on the user's behalf — this constraint exists
   so the WebUI's task tree stays accurate). Also bypasses the user's
   ability to launch in a worktree, alternate cwd, etc.
2. **Subagent / Task tool.** Have each phase run as a subagent spawned
   from the master. Rejected: subagent transcripts write to the **same
   JSONL** as the parent — they're not separate sessions in the
   WebUI/launcher sense. Same context-pressure failure mode as
   single-session, just with extra structure.
3. **Single-session with better auto-compaction.** Tune compaction so the
   master can run the whole pipeline. Rejected: doesn't address failure
   isolation, doesn't fix Kanban visibility, doesn't enable out-of-order.
4. **Master Stop hook sets final status.** Have the master's Stop hook
   call `update-step --step deploy --status complete` when it sees deploy
   is done. Rejected: requires the user to re-open the master session,
   which is the entire reason we want multi-session in the first place.
   Final-status delivery moved to `complete-phase-task` for
   exactly-once-without-master-reopen guarantees.
5. **`sessionUuid`-only discovery without CAS.** Match by sessionUuid
   alone, no version field, no claim. Rejected: race condition on
   duplicate launch (two terminals paste the same banner) — both would
   pass discovery and corrupt state. CAS gives fail-closed exit 2 on the
   second launch.
6. **Top-level `additionalContext` from SessionStart hook.** Initial
   plan v3 assumed top-level `additionalContext` reached the LLM prompt.
   Verified-false in F0 spike: the field name MUST be
   `hookSpecificOutput.additionalContext`. Plan v4 adopted the correct
   schema before F1.
7. **`CLAUDE_ENV_FILE` for env-based phase discovery.** Plan v3 assumed
   env vars set in `CLAUDE_ENV_FILE` would be visible to the Bash tool's
   subprocess. Verified-false in F0 spike. Plan v4 switched to
   context-block discovery + CLI-arg passing for `phaseTaskId`.
8. **SessionStart-hook-based blocking.** Plan v3 assumed hook exit ≠ 0
   would abort the skill. Verified-false in F0 spike. Plan v4 added a
   UserPromptSubmit hook (`phase_user_prompt_validate.py`) that reads a
   `.block-pending` sentinel and returns `decision: "block"` — the only
   reliably-blocking hook event we found.

## Verification

- **Unit:** `plugins/shipwright-run/tests/test_phase_state_machine.py`
  (23 tests, all transitions), `test_phase_task_lifecycle.py` (35 tests
  covering CAS, ownership, recovery, freeze-splits fallback, run-completion
  invariant), `test_lifecycle_cli.py` (10 CLI smoke tests), `test_master_stop_check.py`
  (6 observational behavior tests).
- **Hooks:** `shared/tests/test_phase_session_hooks.py`,
  `test_get_phase_context.py`, `test_phase_plugin_hooks_consistency.py`
  (verifies all 8 plugin hooks.json have identical Multi-Session hook
  ordering — drift guard).
- **Integration:** `integration-tests/test_multi_session_pipeline.py` —
  walks happy-path 7-phase pipeline through real subprocess CLI calls,
  failed-phase halt, recovery + stale-complete rejection, freeze-splits
  with multi-split design config, schema v1 hard-fail.
- **Manual end-to-end:** see plan §Verifikations-Plan §Manueller
  End-to-End-Test, 13 verification steps including wrong-skill block,
  recover-after-crash, stale-stop-after-recover, cross-cwd guard,
  empty-splits path.

## Follow-Up (Out of Scope for This Iterate)

- **WebUI integration** lives in the `shipwright-webui` repo. The
  contract surface is `shared/schemas/run_config.v2.schema.json` from F1.
  WebUI updates: schema-aware mirror, master Task Card with phase
  children, TaskBoard grouping, launch-card "paste / open new terminal"
  button.
- **Heartbeat-based stale detection.** Currently only user-driven via
  `recover-phase-task`. The WebUI iterate can add an mtime-based heuristic.
- **Step 0 enforcement via tool-use hooks.** Currently relies on prompt
  compliance. Real enforcement would need PreToolUse hook gating, which is
  out of scope here.
