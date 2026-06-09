# B0 — Fail-open phase resolver + contract (shared core)

- **Type:** feature (new shared contract; no behaviour removed yet)
- **Complexity:** medium
- **Depends on:** —
- **Blocks:** B1, B2, B3, B4, B5

## Goal

Build the **single** primitive the whole campaign stands on: a
`resolve_engaged_phase(project_root, payload) -> PhaseVerdict` helper that
answers "which Shipwright phase actually ran / is active in this session?"
— **fail-open by construction**. Every downstream dispatcher (Stop,
SessionStart, Prompt, PostTool) consumes this instead of re-deriving it.

## Why this is the lynchpin

The fan-out fix = "run only the engaged phase's hooks." That is only safe
if "engaged phase" is resolved correctly **or errs toward running too
much**. A resolver that guesses wrong and runs *fewer* checks would hide
real Tier-1 FAILs — the cardinal sin this campaign must not commit.

## Acceptance Criteria

- [ ] **AC-1 (signals).** Resolves engaged phase from, in priority order:
      latest `phase_*` event in `events.jsonl` → `current_step` in
      `shipwright_run_config.json` → `phase_history` tail. Documented
      precedence.
- [ ] **AC-2 (fail-open verdict).** Returns a verdict that distinguishes
      `engaged={phase}` from `UNKNOWN`. On `UNKNOWN`, **every** consumer
      must default to running its full check set (never skip). Encoded in
      the type so a consumer cannot accidentally treat UNKNOWN as "skip".
- [ ] **AC-3 (no exceptions escape).** Any IO/parse error → `UNKNOWN`
      verdict (never raises). Pure function of inputs; no global state.
- [ ] **AC-4 (worktree-aware).** Resolves the correct root from a worktree
      (durable artifacts read the MAIN root; cf. memory
      `feedback_worktree_main_root_resolver`). events.jsonl is per-tree
      (cf. `project_events_jsonl_tracked`).
- [ ] **AC-5 (contract published).** Lives in `shared/contracts/` (B8
      cross-plugin API pattern) so all dispatchers import one symbol.
- [ ] **AC-6 (no topology change in B0).** B0 ships the resolver + tests
      ONLY. No `hooks.json` edits, no hook removed. Pure additive
      foundation that B1+ build on.

## Tests

- Each signal source in isolation + the precedence order between them.
- Missing/corrupt config, missing events.jsonl, empty phase_history →
  all yield `UNKNOWN` (never raise).
- Worktree vs. main-root resolution.
- Property: for any malformed input, verdict ∈ {engaged(x), UNKNOWN} and
  never an exception.

## Out of scope

- Using the resolver to actually gate any hook (that is B1–B4).
- PreToolUse hot-path concerns (B5).
