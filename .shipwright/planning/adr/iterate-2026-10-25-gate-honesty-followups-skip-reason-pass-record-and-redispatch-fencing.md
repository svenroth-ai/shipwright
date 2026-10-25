# Skip reason, gate pass record and re-dispatch fencing for driven runs

Run: `iterate-2026-10-25-gate-honesty-followups` · spec: `.shipwright/planning/iterate/iterate-2026-10-25-gate-honesty-followups.md` · FR-01.01 (AC02, AC03), requirement text unchanged.

## Context

The A5 review of campaign `brief-driven-run-a-real-gates` left three gaps open: a phase forced to `skipped` recorded no reason and no event; a phase whose gate passed left nothing durable (the `gate` block was only in apply's stdout); and a gate retry re-claimed the task with the same `sessionUuid` and `version`, so the first dispatch's phase-runner result still passed the CAS after the phase was re-dispatched.

## Decisions

1. **A skip always needs a reason** (supersedes A5 decision 4). `recover_phase_task(force_status="skipped")` refuses a blank reason (`skip_reason_required`, before the lock, nothing written). The reason is normalised (control characters and line breaks to spaces, whitespace collapsed, max 500 chars) and stored as `phase_tasks[].skipReason`. Both CLIs (`recover-phase-task`, `single-session-recover`) take `--reason` and append one `phase_skipped` event (new `record_event` type, not deduped) to the tracked `shipwright_events.jsonl`; `single-session-recover` also carries the reason on its `recovery` loop event. The legacy security-decouple migration stamps `skipReason: "security-decouple-migration"`. Option "require it only after a gate rejection" was not taken: a stuck phase that never reached its gate needs the trace as much.
2. **A gated completion writes `phase_tasks[].gate`** (supersedes A5's "a pass leaves nothing"; keeps A5 decision 5). `{result, checked, phase, splitId, runId, at, issueCount, informCount, overridden}` is written by the `on_complete` hook of `complete_phase_task`, in the same locked write as the completion; the override record runs first in that hook, so `override_requires_human` is unchanged. `result` reuses `gate_summary` (`pass` / `not_checked` / `fail`); `runId` is the id the canon check was run against (`evaluate_gate` now returns it). Inform notes stay returned only; the record counts them. The task is the one home; `validation_overrides[]` keeps meaning "a person waived something".
3. **Every re-dispatch rotates `version`.** `begin_dispatch` calls the new `redispatch_phase_task` when the claim is an idempotent re-entry (gate retry, crash resume): `version` +1 and `redispatchedAt` under the lock; `executionCount`, the claim and `startedAt` are kept (the canon `phase_history` window still opens at the claim). An earlier dispatch's apply is refused `stale_version` (exit 2) and changes nothing. The design freeze moved into the completion's locked write: apply resolves the splits before the lock and `completion_hook` (override, then freeze via `apply_frozen_splits`, then the gate record) applies them after the owner + version check, so a stale design apply (also one whose re-dispatch landed while its gate ran) freezes nothing. `freeze_splits` keeps its signature for the design-stop hook. A second token field was not added: every apply path already CAS-checks `version`, and recover already fences by bumping it.
4. **Every recover drops `skipReason`, `gate` and `redispatchedAt`** — they describe an attempt the recover has just undone.

## Consequences

- Readers of `shipwright_run_config.json` see three new optional `phase_tasks[]` keys (declared in `run_config.v2.schema.json`); readers of the tracked log see a new `phase_skipped` type.
- The master must apply with the descriptor of the LATEST `single-session-next`; the read-only `next` previews of apply / resume are not dispatches, and calling `next` again while a runner is out supersedes it.
- Residual, disclosed: a stale runner that obtained the newer version by reading the task (not through its own dispatch) is fenced only by the phase-runner contract (it never applies).
- The `phase_skipped` append is best-effort like the other phase events (a failure is reported on stderr); the reason is on the task either way.

## Reviews

Internal plan review (12 findings, all fixed), internal architecture review (approve option A), external architecture review (glm approve, openai approve), external plan review (glm revise, openai revise — integrated, one rejected with reason), external code review (round 1 openai revise, fixed by moving the freeze into the completion lock; final round openai approve, glm revise — table below). Spec/code/doubt review passes were delegated to the orchestrator.

## Self-Review

1. Spec Compliance — pass: AC-1..7 each have a test (unit roots + the real-CLI integration test), and every refusal path asserts byte-identical config.
2. Error Handling — pass: blank reason refused before the lock; redispatch refusals surface as `claim_failed` with no loop-state write; a split-read raise returns `freeze_splits_failed` before completion.
3. Security Basics — pass: the operator reason is normalised to one printable line, capped at 500, JSON-encoded into the event detail, and the schema says to render it as data.
4. Test Quality — pass: mutation checks (rotation, freeze guard, gate hook, in-lock freeze) make the new tests fail; no assertion was weakened (the e2e guided test now also asserts the first descriptor is refused `stale_version`).
5. Performance Basics — pass: one extra locked read-modify-write per re-dispatch only; the freeze adds no lock (it rides the completion's).
6. Naming & Structure — pass: new `completion_hook.py` (52 LOC) keeps `single_session_apply.py` under 300; `apply_frozen_splits` is shared by `freeze_splits` and the hook; the grandfathered files did not grow.
7. Affected Boundaries — pass: all four producer/consumer rows round-trip through the real CLI (run_config `skipReason` / `gate` / `version`, tracked `phase_skipped` event).
8. Test Hygiene Probe — pass: `scan_test_hygiene.py --diff` reports no findings for the changed test files.

## External-Code-Review-Findings

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai (r1) | high | a stale design apply froze splits when its re-dispatch landed during its gate | accepted-and-fixed: freeze inside the completion's locked write (`completion_hook`) |
| 2 | glm | medium | freeze conditioned on `gate_due` skips ungated design completions | rejected-with-reason: `gate_due` is the CAS check, not `enforce_gate`; pinned by the `ungated` test case |
| 3 | glm | low | freeze failure lost its structured `blockMessage` | rejected-with-reason: the lock timeout is now the completion's own; the split read never fails by return |
| 4 | glm | low | idempotent claim result replaced, dropping fields | accepted-and-fixed: merged |
