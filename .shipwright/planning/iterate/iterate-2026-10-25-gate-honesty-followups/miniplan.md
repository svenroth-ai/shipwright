# Mini-Plan — iterate-2026-10-25-gate-honesty-followups

Run ID: iterate-2026-10-25-gate-honesty-followups · complexity medium · CHANGE

## 1. Files
- edit `plugins/shipwright-run/scripts/lib/phase_task_recovery.py` — `recover_phase_task(..., reason=None)`: `skipped` requires a non-blank reason (`skip_reason_required`, checked before the lock, nothing written); persist `skipReason` (stripped, <=500 chars); drop `skipReason` on any non-skip recover. New `redispatch_phase_task(project_root, *, phase_task_id, session_uuid)`: under the lock, for an `in_progress` task claimed by `session_uuid`, bump `version`, stamp `redispatchedAt`; anything else returns the matching `_fail`.
- edit `phase_task_lifecycle.py` — re-export `redispatch_phase_task` (one import line, file stays <300).
- edit `orchestrator_pkg/single_session_loop.py` — `begin_dispatch`: when the claim is an idempotent re-entry, call `redispatch_phase_task` and build the descriptor from the rotated task.
- edit `orchestrator_pkg/phase_gate.py` — `evaluate_gate` returns the `run_id` it handed the gate; new `gate_record(task, verdict, *, overridden)` (pure) building the persisted block.
- edit `orchestrator_pkg/single_session_apply.py` — compose an `on_complete` hook that writes `task["gate"]` (and, under an override, runs the override hook first) for every gated completion.
- edit `orchestrator_pkg/events.py` — `record_phase_skipped(project_root, *, task, reason, recovered_from)` via `record_event.py --type phase_skipped`.
- edit `shared/scripts/tools/record_event.py` — accept `phase_skipped` in `--type` choices and the phase-event branch (no new lines; not deduped).
- edit `orchestrator_pkg/cli.py` + `router.py` — `--reason` on `recover-phase-task` and `single-session-recover`; router emits `record_phase_skipped` after a successful skip; `skip_reason_required` exits 1.
- edit `orchestrator_pkg/single_session_recovery.py` — pass `reason`, add it to the `recovery` loop event, emit `record_phase_skipped` on skip; module docstring: re-dispatch rotates `version`.
- edit messages naming the skip command: `scripts/hooks/master_stop_check.py`, `orchestrator_pkg/legacy_migration.py` (add `--reason "<why>"`).
- edit `shared/schemas/run_config.v2.schema.json` — declare `skipReason`, `gate`, `redispatchedAt`; fix `version` / `executionCount` descriptions.
- docs: `docs/hooks-and-pipeline.md` (Crash Recovery, driven-run gate section: skip decision replaced, inform-note decision kept with the new pass record, fencing), `skills/run/SKILL.md` (recover templates need `--reason`), `skills/run/references/single-session-loop.md` (descriptor version rotates; use the newest; pass record), `agents/phase-runner.md` (echo the version of THIS dispatch; an older one is refused).
- tests (new files, measured root `plugins/shipwright-run/tests`): `test_phase_skip_reason.py`, `test_phase_gate_pass_record.py`, `test_redispatch_fencing.py`; existing skip calls in `test_phase_task_lifecycle.py` / `test_phase_validators_split.py` gain a reason (same line). Integration test `integration-tests/test_gate_honesty_cli_integration.py` drives the real CLI.

## 2. Work breakdown
1. Skip reason (recovery + CLI + events + record_event) — tests: blank refused + unchanged bytes; reason persisted; cleared on re-open; event in events.jsonl for both CLIs.
2. Pass record (phase_gate + apply) — tests: pass writes block with canon run id; override writes `overridden:true`; rejection writes none; enforce off writes none.
3. Fencing (recovery + loop) — tests: re-dispatch bumps version, executionCount unchanged; stale ok:true and ok:false applies refused `stale_version`, task untouched; fresh apply completes.
4. Integration test through the CLI subprocess (category integration).
5. Docs + schema + message strings; run the run-plugin root, integration root, shared/tests (record_event / phase_quality / handoff), shared/scripts/tools/tests (record_event).

## 5. Test strategy
Unit tests with injected gates (existing `_gate` pattern) plus one CLI-level integration test. No E2E UI.

## 6. Alternative approach
Fencing by a separate random `claimToken` field on the task, echoed by the phase-runner, instead of bumping `version`. Rejected: every apply/complete/fail path already CAS-checks `version` and recover already fences by bumping it; a second token would need a new CLI flag on three subcommands and a second CAS check, for the same guarantee.
