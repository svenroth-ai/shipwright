# External plan review — iterate-2026-07-27-phase-gate-override-evidence

Mode: `iterate` · Provider: openrouter · Reviewers: **gemini** + **openai (gpt)** ·
Both succeeded, `degraded: false`.

Reviewed: `…-MINIPLAN.md` against `…-phase-gate-override-evidence.md`.

---

## gemini

**G1 — high — edge-case.** Removing the execution bypass from `--force` eliminates
the escape hatch for a fundamentally broken validator. If `validate_phase` throws,
`update_step` will crash and the operator cannot force completion at all.
*Suggestion:* wrap `run_phase_gate()` in `try/except Exception`; record the
exception as a synthetic ask-level issue so the operator can still override and the
failure is logged.

**G2 — medium — edge-case.** Reading `.shipwright/run_loop_state.json` from a second
process can hit a partial write → `JSONDecodeError`. Catch it alongside
`FileNotFoundError` as part of the intended corrupt-degradation path.

**G3 — medium — risk.** Hardcoding the cross-plugin loop-state path inside `shared/`
is silent coupling: because missing/corrupt state degrades silently, a rename in the
orchestrator would silently stop the handoff rendering loop status with no test
failing. *Suggestion:* an explicit cross-boundary test guaranteeing
`handoff_progress.py` and the orchestrator agree on the path and schema.

**G4 — low — approach.** Allowing `force_reason=None` for library callers leaves a
loophole for headless scripts to override without an audit trail.

**Overall:** grounded and pragmatic; address the validator-crash escape hatch and the
file-read concurrency and it is ready to implement.

---

## openai (gpt)

**O1 — medium — approach.** CLI-only validation of `--force-reason` is insufficient;
require a non-blank reason in `update_step` itself for a non-standalone forced
completion, and strip whitespace so `"   "` is rejected.

**O2 — medium — risk.** Extracting the gate risks changing validator semantics
(critical-gate promotion, inform-note handling). Extract with minimal semantic edits,
make `record_inform_notes` explicit in the flow, and test the matrix:
inform-only/no-force, inform-only/force, ask+inform/no-force, ask+inform/force,
critical-gate on/off.

**O3 — medium — dependency.** `validation_overrides` is a new persistent run-config
contract. Audit whether any schema or reserialization path drops unknown keys, declare
the field where a schema exists, and round-trip through the **real** config writer, not
an in-memory dict.

**O4 — medium — risk.** Re-exports do not control the symbol a lazy import resolves.
Inventory the actual patch targets before extracting; do not add shim exports unless
they really intercept.

**O5 — medium — edge-case.** A prior unforced attempt leaves `validation_issues` in
the config; a later forced completion over a now-clean gate could record
`gate_result: "pass"` while stale issues still imply failure. Define retry behaviour
and test pause → clean → forced completion.

**O6 — medium — risk.** A 50-entry cap silently discards the only durable record
distinguishing "passed" from "waved through". Prefer no small global cap; if one is
required, document it and do not discard silently.

**O7 — medium — edge-case.** The dispatch pointer may name a task absent from
`phase_tasks`, a terminal task, or carry a missing/non-numeric attempt. Resolve
`currentPhaseTaskId` against `phase_tasks` before naming a phase; label an
unresolvable pointer as stale rather than asserting a current phase. Test stale IDs,
terminal pointed-to tasks, multiple `in_progress`, missing attempts.

**O8 — low — dependency.** The status vocabulary is owned by `phase_task_lifecycle`.
Confirm the real enum, render unknown statuses visibly as unknown, and validate that
`phase_tasks` is a list of mappings.

**O9 — low — security.** JSON-derived phase/split names go straight into markdown
tables; embedded `|` or newlines corrupt the table. Normalize to single-line and
escape delimiters.

**O10 — low — approach.** `validation_record.py` plus `__init__`/shim re-export layers
may be more indirection than needed — `step_planning.py` would stay under 300 with the
logic inline. Keep the handoff extraction (justified by anti-ratchet); reconsider the
public re-export surface.

**Overall:** both core directions are sound. The work needed is making the override
record reliably durable and reason-bearing across all invocation paths, and making the
handoff robust against stale or malformed cross-file state.

---

## Disposition

| # | Verdict | What was done |
|---|---|---|
| G1 | **accepted** | `run_phase_gate` catches `Exception` and returns a synthetic ask-level issue `[gate-error] …`. Applies to both paths: unforced → `needs_validation` (fail-closed, visible) instead of a traceback; forced → recorded as overridden. Test: `test_a_crashing_validator_does_not_wedge_the_force_path`. |
| G2 | **accepted** | `_read_loop_state` catches `OSError` + `JSONDecodeError` + non-dict payloads. Test: `test_corrupt_loop_state_degrades_without_crashing`. |
| G3 | **accepted** | `integration-tests/test_handoff_reads_real_loop_state.py` imports the orchestrator's own `LOOP_STATE_REL_PATH` / `loop_state_path` and asserts the shared copy agrees — a real drift-guard, not a comment. |
| G4 / O1 | **accepted (stronger than proposed)** | Not a warning — `update_step` **raises `ValueError`** when `force=True` on a non-standalone completion without a non-blank reason (`.strip()` applied). The CLI adds a friendlier `parser.error` on top. In-repo callers updated. |
| O2 | **accepted** | Gate block extracted with no semantic edit (critical-gate promotion identical). `record_inform_notes` is called on both the pause path and the completion path. Full 5-case matrix tested + critical-gate on/off. |
| O3 | **accepted** | Audited: root `additionalProperties: true`, and `save_run_config` / `_write_config` write the whole dict — nothing drops unknown keys. `validation_overrides` nevertheless **declared** in `shared/schemas/run_config.v2.schema.json` next to `validation_issues`. Round-trip test goes through the real `update_step` → `save_run_config` → on-disk JSON. |
| O4 | **accepted (already the design)** | Verified before extracting: the only patch target is `mocker.patch("phase_validators.validate_phase")` (`test_orchestrator.py:538`), which works because the import is **lazy inside the function**. The lazy import is preserved in `validation_record.run_phase_gate` and pinned by `test_the_validate_phase_patch_target_still_intercepts`. No new shim re-exports added. |
| O5 | **accepted** | `update_step` already `pop`s `validation_issues` on completion; behaviour pinned by `test_a_forced_retry_clears_the_stale_pause_issues`. |
| O6 | **accepted (modified)** | Cap raised 50 → 200 **and made non-silent**: evictions bump `validation_overrides_dropped` in the config, so a lost record is still counted. Test: `test_override_retention_is_capped_and_the_drop_is_counted`. |
| O7 | **accepted** | The pointer is resolved against `phase_tasks`; unresolvable → rendered as `(stale — not in phase_tasks)`. Multiple `in_progress`, terminal pointee, and missing/non-numeric attempt all handled and tested. |
| O8 | **accepted** | Real enum confirmed from `run_config.v2.schema.json` `PhaseTaskStatus`: `backlog, awaiting_launch, in_progress, done, failed, skipped`. Only `done`/`skipped` count as finished; `failed` is called out separately; anything else renders verbatim. `phase_tasks` is validated as a list of mappings. |
| O9 | **accepted** | `_cell()` collapses newlines and escapes `|`. Test: `test_markdown_delimiters_in_producer_data_cannot_break_the_table`. |
| O10 | **partially accepted** | The **module is kept**: inline would put `step_planning.py` at ~293/300, leaving no headroom for the next change, and the record-keeping is a genuinely separable pure function. The **re-export surface is dropped** — `validation_record` is imported directly by `step_planning`; nothing new is added to `orchestrator_pkg/__init__.py` or the `orchestrator.py` shim. |

No finding was rejected outright.
