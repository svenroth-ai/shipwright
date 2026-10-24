# Sub-Iterate: A4 — Gate seam, rejection mechanics, v2 override (enforcement OFF)

## Scope

Read BRIEF section 1 (D4) and 2/A4. Injectable gate seam in apply_phase_result (enforcement off by default), phase_gate_failed non-mutating rejection, MAX_GATE_RETRIES on loop_state.attempt, issues[] brief for the phase-runner, v2 --override-reason through a lifecycle hook, master prose, constitution ASK FIRST text, guide 7.5, hooks doc rows. Architecture review first (large).

## Acceptance Criteria

- [ ] Acceptance A4 of BRIEF section 2

## Binding design (verbatim from the campaign BRIEF, .shipwright/planning/campaigns/2026-10-24-brief-driven-unattended-run-BRIEF.md)

| **F18** In a driven run the per-phase validators never run: `update-step` is inert; `single-session-apply` checks result shape, artifact existence and `freeze_splits` only. | `cli_update_step.py:47-60`, `single_session_apply.py:123-180`, `validation_record.py:29-34` |
| **F18b** Wiring is not a path swap. There are **eight** validators (`_VALIDATORS`, `phase_validators.py:486-494`). `_validate_design` asks per split (`:133-159`) while screens are project-global; a non-UI run gets "No mockups found"; `_validate_plan` uses `build_config.current_split` (`:184-188`); `_run_canon_checks` swallows `ImportError` (`:59-60`) and reads the run id from the environment (`:62-63`). Every ask-level issue is worded as a human question. The v2 path has **no override surface**: `record_validation_override` (`validation_record.py:206-266`) is called only from v1 `step_planning.py:234`. The master has **no handling for any apply rejection** and nothing caps retries: `record_dispatch` only increments `attempt` (`loop_state.py:99-105`); a rejection exits 1 and `single-session-next` re-dispatches the same in-progress task. Stub-artifact tests that call apply: 6 in `integration-tests/` and 6 in the run root. | *review*, spot-checked |

**D4 Gates are real, in this order, without breaking the contract.** (1) Fix the validators first (A3). (2) Introduce the gate behind an **injectable seam** in `apply_phase_result` with enforcement **off by default**, reusing `validation_record.run_phase_gate` (already turns a crash into an ask-level issue and reports `checked`) extended with `split_id`; place it between the artifact guard and `freeze_splits`, only when `result.ok and cas_current` and the task is `in_progress` (a stale or double apply keeps its CAS/idempotent answer); pass `config.runId` explicitly (A4). (3) Migrate tests, then flip the default to enforcing (A5). On failure the gate returns a **non-mutating rejection** `{"ok": false, "reason": "phase_gate_failed", "issues": [...]}`; the task stays in progress. Master behaviour is specified, not implied: re-dispatch with an `issues[]` brief (phase-runner contract gains that input), a hard cap `MAX_GATE_RETRIES` on `loop_state.attempt`, and a terminal per autonomy level (guided: ask the human; autonomous: `mark_phase_failed` with the issues, recoverable through `single-session-recover`). A real v2 **override**: `single-session-apply --override-reason` (reason required, `normalise_override_reason`) runs the gate, then writes the override record and the completion under the same lock through a lifecycle hook; `constitution.md` ASK FIRST text and guide §7.5 are updated in the same diff.

Touch set row: | **A4** | Gate seam, rejection mechanics, v2 override (enforcement OFF) | `single_session_apply.py`, `validation_record.run_phase_gate`, the lifecycle override hook, `single_session_cli.py` (`--override-reason`), `loop_state` (`MAX_GATE_RETRIES`), `single-session-loop.md`, run `SKILL.md` Step 5, `phase-runner.md` (`issues[]` input), `constitution.md`, guide §7.5, hooks doc rows | A1, A2, A3 | large |

Acceptance:
- **A4:** with enforcement ON in the test, a planted failing artifact (with a planted transcript so the zero-traces check runs) is rejected and passes when fixed; a stale apply and a double apply of a done task keep their CAS/idempotent answer (no gate rejection); retries stop at `MAX_GATE_RETRIES` with the specified terminal per autonomy level; `--override-reason` requires a reason, writes the record and completion under one lock and is visible in `run_config`; the canon checks demonstrably executed in the apply path; with enforcement OFF behaviour is unchanged.

## Hand-offs from A3 reviews (binding)
- Pass `config.get("runId")` into the gate (None when absent). Never coerce to "" (an explicitly empty run_id is ask-level in the canon bridge and would brick legacy runs).
- A canon result with kind=canon_degraded must count as ASK (not pass) in unattended/enforcing mode; gate_result must not read 'pass' for a degraded canon run.
- `validate_phase` takes `split_id` and `run_id` keywords; v1 run_phase_gate passes split_id=None. Extend run_phase_gate with split_id.
- A design 'skipped' phase_task is NOT an exemption; do not reintroduce.
- v2 run-config scope enum is full_app|extension, so the scope=library no-UI rule cannot fire for v2 yet (campaign B adds ux_shape/ui_host).
- With enforcement OFF existing behaviour must be unchanged.
