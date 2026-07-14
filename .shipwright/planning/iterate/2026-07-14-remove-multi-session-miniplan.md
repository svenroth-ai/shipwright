# Mini-Plan — Remove the multi-session pipeline mode

Run ID: `iterate-2026-07-14-remove-multi-session` · Complexity: medium · Spec Impact: REMOVE

## Chosen approach — "delete the engine, keep the lifecycle, rename the sentinel"

The removal splits cleanly into three layers, because the scout established that the
external-session engine sits *on top of* a mode-agnostic lifecycle:

**Layer 1 — the engine (pure delete).** The 3 phase hooks + their 3 private helpers
(`phase_context_blocks`, `hook_session`, `phase_event_emit`) have **no consumer outside
themselves**. Delete the files, deregister them from the 8 phase `hooks.json`. Under
`single_session` they already never fire (they match on a live Claude session id that a
subagent never has), so this is a no-op for the surviving mode.

**Layer 2 — the shared lifecycle (do not touch).** `phase_task_lifecycle`,
`phase_state_machine`, `phase_tasks[]`, `sessionUuid`, the v2 schema, every
`get-/claim-/complete-/recover-/freeze-/plan-next-` subcommand: **all shared with
single-session** and all staying. `sessionUuid` in particular is the single-session CAS
claim token — deleting it because it *sounds* multi-session would be the classic
over-cut. This layer is what the integration test exists to prove intact.

**Layer 3 — the mode model (rename, don't collapse).** `multi_session` is doing two jobs:
it is a mode *and* it is the "not a single-session pipeline run" inert sentinel that keeps
phase gates `interactive` for standalone/adopted/v1 configs. Kill the mode; keep the
sentinel under an honest name (`gate_policy.INERT_MODE = "standalone"`), leaving the
activation predicate explicit-literal-only so every non-pipeline config behaves
byte-identically. A leftover `mode: "multi_session"` config fails closed with a migration
message rather than being silently reinterpreted.

## Alternative considered — "collapse the mode field entirely"

Delete `mode` from the schema and from `run_config` altogether; treat every v2 config as
single-session by definition.

**Rejected.** Three reasons:
1. It walks straight into the regression trap: with no `mode`, `gate_policy` has nothing
   to key inertness on, so either every standalone project starts auto-answering gates
   (a real behavior change on this very monorepo, whose run_config is v1/mode-less), or a
   second sentinel has to be invented anyway — the same work with a worse name.
2. `mode` is part of the **versioned run_config v2 contract the WebUI renders**. Dropping
   a field from a published contract is a `schema_version` event with a frozen-fixture
   obligation; renaming a literal inside an existing optional field is not.
3. It destroys the ability to *detect* a stale `multi_session` config, converting an
   actionable error (AC4) into silent misexecution — the opposite of fail-closed.

Keeping `mode` as a single-valued, fail-closed field costs ~8 lines and buys all three.

## Order of work (each step leaves the tree green)

1. **Mode model** — `constants` (`RUN_MODES`, tombstone literal), `config_io`
   (`run_mode` + `is_legacy_multi_session`), `gate_policy` (sentinel rename), v2 schema.
2. **Engine delete** — 6 modules; deregister in 8 `hooks.json`.
3. **Per-phase Continue** — `master_stop_check.py` (launch cards → single-session status
   banner), `generate_handoff_on_stop.py` (drop the phase-namespaced branch only).
4. **Skill + agent** — `run/SKILL.md` (the master now *drives*; Steps 5/6/Resume folded
   onto the single-session loop), `single-session-loop.md`, `phase-runner.md`,
   `single-session-gate-discipline.md`.
5. **Docs** — `hooks-and-pipeline.md` (mandatory), `guide.md`, `gate-catalog.md` +
   `gate_catalog.json`, migration doc retitled.
6. **Tests** — delete the 4 multi-session test files; rewire `test_phase_completed_per_split_integration`
   onto the surviving emitter; **add `integration-tests/test_single_session_sole_mode.py`**
   (the `cross_component` integration coverage: residue guard + survivor contract +
   full 7-phase pipeline with the engine deleted).
7. **Baseline** — `shipwright_bloat_baseline.json` entries for the deleted files.

## External review (GPT-5.6 + Gemini 3.1 Pro via OpenRouter) — findings adopted

Both reviewers independently flagged the same high-severity risk: the stale
`multi_session` literal must not fall through gate-policy's deliberately permissive
"anything that isn't `single_session` is inert" fallback. Gemini added the constraint
that fixes *where* the rejection belongs. Adopted deltas:

- **D1 (Gemini, high) — reject on the EXECUTION path, never in the read path.** Putting
  the AC4 rejection in `load_run_config` / deserialization would crash every *read-only*
  inspection of a historical run (WebUI run history, `.shipwright/runs/**` rendering).
  The guard therefore sits on the pipeline **entry points** (`write-config`,
  `single-session-next` / `-apply` / `-resume` / `-recover`), not in config I/O.
  `load_run_config` stays a pure reader.
- **D2 (GPT, high) — one centralized guard, not N scattered checks.** The same predicate
  backs every execution entry point, so an explicit `multi_session` config can never
  reach a lifecycle mutation, a gate resolution, or an event append. Tested at the
  *command* entry points, not just at the predicate. (This is why the guard stays a named
  helper rather than an inline compare — Gemini's reducibility note is outvoted by the
  centralization requirement: 5 call sites, one rule.)
- **D3 (Gemini, med) — keep `multi_session` in the `--mode` argparse `choices`.** Dropping
  it makes argparse emit a generic `invalid choice:` error *before* our code runs, hiding
  the actionable migration message. Accept the literal at the parser, trap it in the handler.
- **D4 (GPT, med) — registry-driven SSoT meta-test.** The 8-vs-11 `hooks.json` gap is a
  real dangling-registration class. New test parses **every** shipped hook manifest and
  asserts each referenced script exists on disk (forward drift) — per the skill's
  registry-driven SSoT rule.
- **D5 (GPT, med) — assert the surviving event stream.** Removing the `phase_event_emit`
  producer changes *who* emits `phase_started`, not *whether* it is emitted (the
  orchestrator twin remains, and single-session is now the sole mode). The integration
  test asserts complete `phase_started` + `phase_completed` pairs, per split.
- **D6 (GPT, med) — three config fixtures, not one.** A freshly `create_config`'d run is
  insufficient: the regression trap lives in an *existing mode-less* config. Fixtures:
  (a) v1/mode-less + missing config → gates interactive; (b) v2 `single_session` → gates
  active + pipeline completes; (c) v2 `multi_session` → fails closed **with no claim, no
  completion, no handoff write, no event append**.
- **D7 (GPT, low) — repo-wide residue guard.** Test greps live source + shipped docs for
  the `claude --session-id` launch-card syntax and the deleted hook names, excluding only
  the retained migration record and historical artifacts.
- **D8 (GPT, med) — WebUI contract.** `mode` stays in the v2 schema (single-valued enum),
  so the published contract the WebUI renders does not break and no `schema_version` bump
  is owed. The WebUI's *own* per-phase Continue affordance is out of scope here — it is
  the `webui-pipeline-convergence` campaign's work (`trg-01db884a`). Verified + triaged,
  not silently left.

## Rollback

One squashed commit on `iterate/remove-multi-session`; revert restores the engine
wholesale. No data migration is performed (no in-flight multi-session run exists — this
repo's own config is v1/standalone), so revert is state-safe.
