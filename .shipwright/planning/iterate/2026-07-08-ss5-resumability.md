# Iterate: SS5 — Single-session resumability / recovery + dual-mode back-compat + observability

- **Run ID:** iterate-2026-07-08-ss5-resumability
- **Campaign:** 2026-07-07-single-session-pipeline (sub-iterate SS5, hand-run)
- **Intent:** FEATURE (additive) · **Complexity:** medium · **Spec Impact:** ADD
- **Sub-iterate spec:** `.shipwright/planning/iterate/campaigns/2026-07-07-single-session-pipeline/sub-iterates/SS5-resumability-backcompat.md`

## Goal

Make a `single_session` `/shipwright-run` pipeline recoverable when the orchestrator
conversation dies mid-run, keep in-flight `multi_session` runs on the OLD path
untouched (dual-mode back-compat), and emit structured observability events for the
loop's own transitions. Builds on SS1 (loop-state), SS3 (orchestrator loop), SS4
(phase-runner persistence + `single-session-reload`).

## User decisions (confirmed by Sven, 2026-07-08)

1. **Resume UX = auto-detect + confirm card.** Re-invoking bare `/shipwright-run`
   detects `mode==single_session` + a live loop-state on a non-terminal run, prints a
   Resume? card (last-done / current / attempt), and asks Resume vs Abandon. Mirrors
   the `/shipwright-iterate` + campaign-loop dead-run offer. No new flag.
2. **Mid-flight task = re-run idempotently.** A task left `in_progress` (claimed, master
   died before apply) is re-dispatched under its own `sessionUuid` (the existing
   `begin_dispatch` idempotent re-claim); the SS4 artifact persistence-guard still
   verifies outputs on apply. `recover-phase-task` stays the manual escape for a wedged
   task.

## Acceptance Criteria (from sub-iterate spec)

- [ ] AC1 — kill-and-resume test for a single-session run (idempotent replay)
- [ ] AC2 — multi-session resume/recover unchanged (back-compat suite green)
- [ ] AC3 — observability events emitted + asserted
- [ ] AC4 — resume UX confirmed by Sven ✅ (done above)

## Design

Observability + recovery emission live ONLY in single-session code paths; the
`multi_session` lifecycle (router → claim/complete/recover) is never touched → the
events/loop-state files never appear for it (the dual-mode guarantee, asserted by AC2).

### New — `single_session/observability.py` (pure-data package member)
Append-only JSONL telemetry at `.shipwright/run_loop_events.jsonl` (distinct from the
tracked pipeline `shipwright_events.jsonl` and from `run_loop_state.json`; auto-ignored
by the `/.shipwright/*` wildcard). No `orchestrator_pkg` import, no run_config mutation
(same discipline as `loop_state`).
- `EVENTS_REL_PATH`, `EVENTS_SCHEMA_VERSION`, `LOOP_EVENT_TYPES` =
  `(dispatch, phase_result, strict_stop, human_gate_pause, human_gate_resume, resume, recovery)`
- `build_event(event_type, run_id, **fields)` — validates the type (raises like `set_status`), stamps `schemaVersion`+`at`.
- `emit_event(project_root, event)` — durable append (read existing + append + `durable_atomic_write`); best-effort (telemetry never crashes the loop).
- `emit(project_root, *, event_type, run_id, **fields)` — build+emit convenience (compact call sites).
- `load_events(project_root)` — read all (corrupt-line tolerant) for tests/introspection.

### New — `orchestrator_pkg/single_session_recovery.py`
Recovery + resume — CALLS a lifecycle mutator (`recover_phase_task`), so it sits in
`orchestrator_pkg` (the `single_session` package is forbidden from calling mutators),
alongside `single_session_loop`.
- `resume_run(project_root, *, confirm=False)` — READ-ONLY resume decision for the confirm
  card (`resolve_next_dispatch` + `reload_orchestrator_context` + `load_loop_state`); emits
  a `resume` event ONLY when `confirm=True` AND the run is genuinely resumable (a live
  dispatch frontier). Actions: `no_config | wrong_mode | not_resumable | runid_mismatch |
  resume`; a terminal/blocked run passes its real signal through
  (`complete | failed | needs_validation | blocked`) and emits nothing. Return carries
  `resumeAction`, `context`, `loopState`, `next` (+ `confirmed` on the resume branch).
- `mark_human_gate(project_root, *, phase_task_id, phase, paused, split_id=None)` — flips
  loop-state `paused_human_gate`⇄`running`, emits `human_gate_pause|human_gate_resume`.
- `recover_single_session(project_root, *, phase_task_id, force_status)` — calls
  `recover_phase_task`, resets the loop pointer (attempt=0, status back to running when
  the run lifts to in_progress), emits `recovery`. Generic `recover-phase-task` untouched.

### Edits
- `single_session_loop.py` — emit `dispatch` in `begin_dispatch`; emit `phase_result`
  (+`strict_stop` on a failed run) in `_advance_loop_state`. Compact one-liners; keep <300 LOC.
- `single_session_cli.py` + `cli.py` — three subcommands: `single-session-resume`,
  `single-session-gate` (`--state pause|resume`), `single-session-recover`.
- `single_session/__init__.py` — export the observability surface.
- `references/single-session-loop.md` — expand "Resumability" with the confirm-card flow,
  the three subcommands, the event list, and `run_loop_events.jsonl`.
- `docs/hooks-and-pipeline.md` — add `run_loop_events.jsonl` to the write matrix + the
  new subcommands (verify during build).

### NOT doing (scope discipline)
- NOT touching `master_stop_check.py` / any `hooks/*.py` — strict-stop is authoritatively
  captured in `apply_phase_result`; coupling telemetry to a Stop hook is the anti-pattern
  SS4 removed. Keeps the diff off the hook surface.
- No parallel-split resume (serial only, per SS3 v1).
- Rejected-result (invalid/artifacts_missing) telemetry is out of scope — those are
  transient master-retry states, not applied phase outcomes.

## Affected Boundaries
- `.shipwright/run_loop_events.jsonl` (NEW write surface — JSON round-trip; append-log).
- `.shipwright/run_loop_state.json` (status transitions on gate/recover; existing surface).
- `shipwright_run_config.json` (READ-only in new code; recover goes through the lifecycle).
- Orchestrator CLI subcommand surface (3 new subcommands).

## Test Plan (TDD)
- `test_single_session_observability.py` — event build/validate, durable append, round-trip, corrupt tolerance, best-effort swallow, path distinctness.
- `test_single_session_resume.py` — `resume_run` decision table; `resume` event; `mark_human_gate` status+event; `recover_single_session` lifecycle+event+pointer reset.
- `test_single_session_backcompat.py` (AC2) — multi-session run through claim/complete/recover leaves NO `run_loop_state.json`/`run_loop_events.jsonl`; `resume_run` → `wrong_mode`, emits nothing.
- `test_single_session_kill_resume_integration.py` (AC1, `category:"integration"`) — fixture run: next→(kill)→resume_run→next (idempotent re-claim, no double executionCount)→apply→advance; events asserted end-to-end. Proves the loop composes with the lifecycle across a crash (cross_component integration coverage).

## Confidence Calibration
- **Boundaries touched:** `run_loop_events.jsonl` (new write surface), `run_loop_state.json`
  (status transitions), `shipwright_run_config.json` (read-only in new code), 3 CLI subcommands.
- **Empirical probes run:**
  - *Dual-mode isolation (live CLI):* multi_session config → `single-session-resume`
    returns `wrong_mode`, `single-session-recover` returns `ok:false/wrong_mode`, and
    NEITHER `run_loop_state.json` NOR `run_loop_events.jsonl` is created. ✅
  - *Resume detection vs commitment (live CLI):* `next`→1 event; read-only
    `single-session-resume`→still 1 (no emit on detection); `--confirm`→2 events
    (`dispatch`,`resume`). ✅
  - *Kill-and-resume idempotent replay (integration subprocess):* next→(kill)→resume→next
    re-claims the SAME task (`idempotent:true`, `executionCount` NOT re-bumped)→apply
    completes; event log = `dispatch,resume,dispatch,phase_result`. ✅
  - *Human-gate + recover (live CLI):* gate pause→`paused_human_gate`, resume→`running`,
    recover→ok; event sequence `dispatch,human_gate_pause,human_gate_resume,recovery`. ✅
  - *Best-effort emit:* OSError and a non-serializable field both swallowed with a stderr
    diagnostic; nothing written. ✅
- **Test Completeness Ledger:** every behavior this diff introduces is `tested` (0
  testable-but-untested):

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | event build + type validation | tested | `test_build_event_shape*`, `*_rejects_unknown_type` |
  | durable append + round-trip + corrupt-line tolerance | tested | `test_emit_appends*`, `*_round_trips`, `*_torn_trailing_line` |
  | best-effort swallow (OSError + non-serializable) | tested | `test_emit_event_swallows_io_error_but_warns`, `*_non_serializable_field` |
  | typed emitters (dispatch; phase_result+strict_stop pairing) | tested | `test_emit_dispatch*`, `test_emit_phase_result_*` |
  | loop dispatch/phase_result/strict_stop emission | tested | integration event-sequence + `test_emit_phase_result_*` |
  | `resume_run` read-only vs `--confirm` | tested | `test_resume_is_read_only*`, `*_confirm_emits*` |
  | `resume_run` guards (no_config/wrong_mode/not_resumable/runid_mismatch) | tested | 4 × `test_resume_*` |
  | `resume_run` terminal pass-through (no spurious event) | tested | `test_resume_terminal_run_passes_through*` |
  | `mark_human_gate` status flip + event + mode gating | tested | `test_human_gate_*` |
  | `recover_single_session` pointer reset + event + lift-gating + guards | tested | `test_recover_*`, `*_unrelated_task_does_not_lift*` |
  | `begin_dispatch` stale-runId reinit | tested | `test_next_dispatch_reinits_stale_loop_state*` |
  | idempotent double-apply preserves pointer | tested | `test_double_apply_is_idempotent*` |
  | CLI dispatch + exit codes (resume/gate/recover) | tested | `test_resume_exit*`, `test_gate_exit*`, `test_recover_exit*`, `test_cli_main_routes_single_session_resume` |
  | **kill-and-resume idempotent replay (composition)** | tested — `category:"integration"` | `integration-tests/test_single_session_resume_integration.py` |
  | dual-mode: multi_session leaves no single-session files | tested | `test_multi_session_*_creates_no_single_session_files`, multi_session integration |
  | pre-SS5 loop_state resumes (no events file) | tested | `test_pre_ss5_single_session_loop_state_resumes*` |

- **Confidence-pattern check:**
  - *Asymptote (depth):* each new function has happy + guard/error paths (mode, runId,
    terminal, IO failure) — not just the golden path.
  - *Coverage (breadth):* both modes exercised (single_session resume flow + multi_session
    isolation), all 7 event types emitted-and-asserted, both live-CLI and in-process/subprocess.
  - *Integration composition:* the `category:"integration"` kill-and-resume test proves the
    loop + lifecycle + loop_state + observability compose across a simulated crash — the
    `cross_component` coverage the F11 verifier recomputes from the diff (touches
    `orchestrator_pkg` loop + a resume path; NO `hooks/*.py` touched, so `cross_component`
    may not auto-fire, but the integration behavior is recorded regardless).

## External review triage (2026-07-08, GPT-5.4 + Gemini 3.1 via OpenRouter)

Full JSON: `.shipwright/runs/iterate-2026-07-08-ss5-resumability/external_review.json`.
Both models: "direction sound, dual-mode isolation safe." Accepted revisions folded in:

1. **Append-mode event writer** (was read+rewrite → O(N²)): `emit_event` uses `open("a")`
   + `flush` + `fsync` (O(1); single-writer master; torn trailing line skipped by `load_events`).
2. **`resume_run` truly read-only** for the card; emits `resume` ONLY on explicit
   `--confirm` (detection ≠ commitment; no telemetry on mere card display).
3. **Run-identity matching**: resume/gate/recover refuse when `loop_state.runId !=
   run_config.runId` → `runid_mismatch` (never attach to the wrong/stale run).
4. **Subagent-dies-with-master invariant** documented: in `single_session` the phase-runner
   is a SUBAGENT of the master conversation, so master death = runner death — no orphaned
   live worker to race (the split-brain risk is a `multi_session`-only property). This is
   why idempotent re-dispatch is safe here.
5. **Explicit mode-gating at every new entry point** (resume/gate/recover → `wrong_mode`,
   zero file creation for `multi_session`) + a regression test (don't rely on "we don't call it").
6. **Human-gate wired to the master protocol** in `single-session-loop.md` (the master calls
   `single-session-gate --state pause|resume` at an orchestrator-approve/hard-stop gate).
7. stderr diagnostic on emit failure (not fully silent); event fields whitelisted to compact
   pointers (no full context/next blobs); pre-SS5 loop-state back-compat fixture test;
   schemaVersion assertions in tests.

## Degraded / overrides
- `touches_auth` risk flag is a PROSE false-positive (matched the `session` keyword in
  "multi-session"/"single-session"; no auth/middleware/supabase code exists in this
  monorepo). Overridden; recorded in `degraded[]`. Diff-predicate recompute at F11 is
  authoritative and will not re-raise it.
- Complexity overridden small→medium (cross-component orchestration machinery; integration
  coverage gate).
