# Mini-Plan: gate-hardening-leftovers

Run: `iterate-2026-10-25-gate-hardening-leftovers` · spec: `.shipwright/planning/iterate/iterate-2026-10-25-gate-hardening-leftovers.md`

## Files
- edit `plugins/shipwright-run/scripts/lib/phase_validators_split.py` — `_validate_plan` docstring (item 1); new `sections_for_split(build_config, split_id)` (item 3).
- edit `plugins/shipwright-run/scripts/lib/phase_validators.py` — `_validate_build` judges the task's split via `sections_for_split`, passes `split_id` to the canon bridge.
- edit `plugins/shipwright-run/scripts/lib/phase_validators_canon.py` — `_run_canon_checks(..., split_id=None)`, forwarded to `run_build_checks` only for build and only when set; a `run_build_checks` without a `split_id` parameter (`inspect.signature`) is an ask-level `canon_degraded` note (version skew), an internal `TypeError` still propagates.
- new `shared/scripts/tools/verifiers/build_split.py` — leaf `sections_for_split` (no imports) + `build_config_for_split` view.
- edit `shared/scripts/tools/verifiers/build_checks.py` (baselined at 461, must not grow) — every section read goes through the split view (`current_split` becomes the requested split, so `phase_history` prefers that split's own entry); `run_build_checks(..., split_id=None)`.
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py` — `archived_split` is a non-retryable kind.
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/completion_hook.py` — `except phase_gate.OverrideRefused` records the refusal and re-raises (item 2a).
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_apply.py` — read that record instead of the class-name string; `DEFAULT_TASK_VERSION` (item 5).
- edit `plugins/shipwright-run/scripts/lib/single_session/loop_state.py` — `record_gate_terminal` / `gate_terminal_for` (`gateTerminal = {phaseTaskId, version, issues}`).
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_apply.py` `_gate_rejected` — records the marker whenever the rejection's terminal is `ask_human`.
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_loop.py` — the read-only `resolve_next_dispatch` answers `ask_human` while the marker matches the frontier task's run, id and version (so `next`, the apply preview and the resume card agree); descriptor version default.
- edit `plugins/shipwright-run/scripts/lib/orchestrator_pkg/single_session_cli.py` — `ask_human` is an exit-0 `next` action.
- edit `plugins/shipwright-run/scripts/lib/phase_task_core.py` — `DEFAULT_TASK_VERSION`, `task_version()`; owner check uses it.
- edit `plugins/shipwright-run/scripts/lib/phase_task_recovery.py` — both version reads use it.
- edit tests: `test_phase_validators_split.py`, `_canon.py`, `_late.py` (AC02 tag, item 1 test), new `test_gate_hardening_leftovers.py` (run root), new `shared/tests/test_verifiers_build_archived_split.py`, one subprocess CLI test in `integration-tests/`.
- docs: `docs/hooks-and-pipeline.md` (override limit, ask_human action, build split, raw claim), `plugins/shipwright-run/skills/run/references/single-session-loop.md` (ask_human action; the stale "nothing is capped" line), run `SKILL.md` terminal signal list.

## Work breakdown
1. Item 5: constant + helper, red test (version-less task completes with 1), then switch the five reads.
2. Item 2a: red test (impostor class named `OverrideRefused` → today `override_requires_human`; subclass with another name → today `on_complete_failed`), then the hook-side `except` + apply reads the captured refusal.
3. Item 2b: pin test (rejected design apply freezes nothing).
4. Item 3: red tests (validator + build_checks after a real `archive_split`), then `sections_for_split` in both packages + a mirror test pinning they agree on a case matrix.
5. Item 2c: red test (guided run, three rejections, then `next` re-dispatches today), then the persisted marker (writer in `_gate_rejected`, reader in `resolve_next_dispatch`), CLI exit code, docs. Tests: run/task/version matching, recover, override completion, a plain pass, unreadable state, crash-resume after retryable rejections, unknown autonomy, non-retryable finding, autonomous unchanged.
6. Item 1 + 4: docstring, test assertions, tag change.
7. Item 2d + 6: docs + ADR.

## Test strategy
Unit tests in the run root and `shared/tests` (in-process for diff coverage), one integration subprocess test for the `ask_human` CLI answer and one for the archived-split build gate through `single-session-apply`. One pytest root per process.

## Alternative approach
For item 2c: derive the refusal from the two existing counters (`attempt`, `gateRejections`) instead of a persisted marker — rejected in the internal plan review: the counters cannot tell a crash-resumed dispatch from a capped one and miss the early non-retryable terminal.
For item 3: make the build skill archive the split only after its result was applied (move `archive_split` to the next plan phase) instead of teaching the gate the archived layout.
