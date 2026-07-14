# Iterate Spec — Remove the multi-session pipeline mode

- **Run ID:** `iterate-2026-07-14-remove-multi-session`
- **Intent:** CHANGE (removal)
- **Complexity:** medium
- **Spec Impact:** REMOVE
- **Risk flags:** `cross_component` (diff-derived: `hooks.json` ×8, `**/hooks/*.py`,
  pipeline phase validators) → **integration coverage mandatory**.
  `touches_auth` was raised by the classifier from the *prose* ("session") and is a
  known message-keyword false positive — no auth/RLS/middleware path is touched.
  Recorded in `degraded[]`; the diff predicates in `risk_detectors.py` are authoritative.
- **Triage anchor:** `trg-0e8e7f90` (multi-session removal)

## Context — the decision being executed

Decision 2026-07-08 (Sven): **single-session is the sole pipeline mode.** Multi-session
is no longer needed (one user, no back-compat consumers). SS8 (#353) already flipped the
default; multi-session survived only as a deprecated read-fallback. This iterate is the
deferred cleanup: *mark deprecated → remove the external per-phase-session engine and
the per-phase Continue*.

Sven's constraint: the load-bearing cross-plugin hooks are their **own effort** (this
one), explicitly not folded into the webui-pipeline-convergence campaign. Requirement:
**no regression** — prove by integration test that nothing still needed was cut.

## What multi-session actually *is* (the thing being removed)

Each pipeline phase ran as its **own external UUID-bound Claude session**
(`claude --session-id <sessionUuid> '/shipwright-build'`). Three hooks, wired into the
8 phase plugins, formed that engine:

| Component | LOC | Role in the external-session engine |
|---|---|---|
| `shared/scripts/hooks/phase_session_start.py` | 292 | SessionStart: match live session id against `phase_tasks[].sessionUuid`, validate (wrong-skill / duplicate / terminal / prereqs), CAS-**claim** the task, or write a `.block-pending` sentinel |
| `shared/scripts/hooks/phase_user_prompt_validate.py` | 133 | UserPromptSubmit: consume `.block-pending` → `decision=block` (SessionStart cannot block) |
| `shared/scripts/hooks/phase_session_stop.py` | 271 | Stop: collect the phase's result config, freeze splits, **complete** the phase task, plan the successor |
| `shared/scripts/hooks/phase_context_blocks.py` | 48 | context blocks emitted by `phase_session_start` only |
| `shared/scripts/lib/hook_session.py` | 126 | stdin-payload identity resolver — used *only* by those three hooks |
| `shared/scripts/lib/phase_event_emit.py` | 73 | `phase_started` emit wrapper — used *only* by `phase_session_start` |

Plus the **per-phase Continue** surfaces: `master_stop_check.py`'s paste-able
`claude --session-id …` launch cards, the same cards in `run/SKILL.md` (Steps 5/6/Resume),
and the phase-namespaced handoff branch in `generate_handoff_on_stop.py`.

## Why removal is behavior-preserving for single-session

The three hooks discover their phase task by matching the **live Claude session id**
against `phase_tasks[].sessionUuid`. Under `single_session` the phase runner is a
**subagent** of the master conversation — it never gets its own bound Claude session, and
`sessionUuid` is a synthetic `uuid4()` that can never equal a live session id. So under
single-session **these hooks never match and are already dead code**. Deleting them is a
no-op for the surviving mode; the risk is entirely in what they *shared*, not what they did.

**`sessionUuid` itself STAYS.** Single-session reuses it as the CAS **claim token**
(`single_session_loop.py:74,149`). Only its meaning as an *external Claude session id* dies.

## The regression trap (found in scout, must not be tripped)

`multi_session` is not only a mode — it is currently the **"this is not a single-session
pipeline run" inert sentinel**:

- `gate_policy.DEFAULT_RUN_MODE = "multi_session"` is what a **missing / mode-less /
  corrupt / standalone / v1** config reads as, and it is what keeps every phase gate
  `interactive` (i.e. the SS2 gate mechanism inert).
- Naively "defaulting everything to single_session" would therefore **activate
  auto-default gates on every standalone and adopted project** — including this monorepo,
  whose own `shipwright_run_config.json` is a v1 standalone config with no `mode` key.

**Mitigation:** keep the sentinel, rename it honestly. `gate_policy` gets
`INERT_MODE = "standalone"`; the activation predicate stays *explicit-literal-only*
(`mode == "single_session"` activates, everything else is inert) — byte-identical
behavior for every non-pipeline config. AC7/AC8 pin both directions.

## Acceptance Criteria

- **AC1** — The external per-phase-session engine is gone: the 6 modules above are
  deleted, and no `hooks.json` in any of the 8 phase plugins registers
  `phase_session_start` / `phase_session_stop` / `phase_user_prompt_validate`.
- **AC2** — The per-phase Continue is gone: no `claude --session-id` launch card is
  emitted by `master_stop_check.py` or `run/SKILL.md`; `generate_handoff_on_stop.py`
  loses its phase-namespaced handoff branch and keeps the generic path intact.
- **AC3** — `single_session` is the sole mode: `RUN_MODES == ("single_session",)`;
  `create_config` writes it unconditionally; the `--mode` flag no longer offers
  `multi_session`.
- **AC4** — A stale `mode: "multi_session"` config **fails closed with an actionable
  migration message** (not silently reinterpreted, not silently executed).
- **AC5** — The shared lifecycle survives untouched: `phase_task_lifecycle`
  (claim/complete/mark_failed/recover/freeze_splits/plan_next_phase),
  `phase_state_machine`, the v2 schema, and every `single-session-*` subcommand still
  drive a full 7-phase pipeline to `status: complete`.
- **AC6** — `generate_handoff_on_stop.py` still writes `runtime/session_handoff.md`
  and still runs the phase-completion fallback (the 95% of it that was never multi-session).
- **AC7** — Phase gates stay **inert** for a standalone / v1 / mode-less / missing config
  (the regression trap above).
- **AC8** — Phase gates still **activate** for a `mode: single_session` v2 config.
- **AC9** — `phase_completed` per-split dedup (iterate-2026-07-11) survives the loss of
  the `phase_event_emit` emitter, proven through the surviving orchestrator emitter.
- **AC10** — `docs/hooks-and-pipeline.md` (mandatory per CLAUDE.md), `docs/guide.md`,
  `docs/gate-catalog.md` + `shared/config/gate_catalog.json`, and the v2 schema reflect
  the removal.

## Affected Boundaries

- `hooks.json` × 8 phase plugins (hook registry — cross-plugin fan-out)
- `shipwright_run_config.json` (v2 schema, `mode` field) — WebUI reads this contract
- `shared/config/gate_catalog.json` → `gate_policy` mode resolution
- `shipwright_events.jsonl` producer set (`phase_started` / `phase_completed`)
- `.shipwright/agent_docs/…/handoff.md` path selection

## Confidence Calibration

- **Boundaries touched:** hook registry (8 plugins), run_config v2 `mode` contract,
  gate-policy mode resolution, event-emitter set, handoff path selection.
- **Empirical probes run:**
  1. *Who imports the removal candidates?* → `hook_session` and `phase_context_blocks`
     are imported **only** by the three hooks; `phase_event_emit` **only** by
     `phase_session_start`. No other consumer. → clean cut.
  2. *Is `sessionUuid` multi-session-only?* → No: `single_session_loop.py:74,149` claims
     with it. → field stays; only its external-session meaning dies.
  3. *What reads `mode` outside the run plugin?* → `gate_policy.read_run_config_mode`,
     and it treats **any non-`single_session` value as inert**. → the literal is a
     sentinel, not a mode. → rename, don't delete (AC7).
  4. *Does this repo's own run_config have a mode?* → **No** (v1 standalone, no
     `schemaVersion`). → it must stay gate-inert after the change. → AC7 is a live,
     not theoretical, regression.
  5. *What is the current cross_component integration coverage?* →
     `integration-tests/test_phase_hook_main_lifecycle.py`, which tests the removed
     hooks. → removing it obligates a replacement (AC5–AC9).
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  (`iterate_latest.test_completeness`) — every AC maps to a `tested` behavior;
  one `category:"integration"` behavior covers the `cross_component` composition.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the mode model is followed to its two real consumers (loop +
    gate policy), not just its declaration site; the sentinel/mode conflation was found
    by chasing the second consumer.
  - *Coverage (breadth):* all 11 `hooks.json`, all 6 modules, all 8 phase plugins, the
    schema, the WebUI-facing contract, and both docs SSoTs are in the diff.
  - *Integration composition:* `integration-tests/test_single_session_sole_mode.py`
    drives the real orchestrator CLI end-to-end **with the engine deleted** — the
    composition proof that the surviving pieces still compose without it.

## Out of scope

- The `webui-pipeline-convergence` campaign (separate, `trg-01db884a`).
- `.shipwright/runs/**` historical artifacts and `CHANGELOG.md` / `decision_log.md`
  history — provenance, not live code. Not rewritten.
- `docs/migrations/multi-session-to-single-session.md` — kept, retitled as the terminal
  migration record (the migration path it documents is exactly what a stale config's
  AC4 error message tells the user to do).
