# First Actions (CRITICAL)

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

## A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-TEST: Test Runner
================================================================================
Runs tests across all layers based on stack profile.

Usage: /shipwright-test
   or: /shipwright-test --fix        (auto-fix failures, max 3 retries)
   or: /shipwright-test --e2e-only   (only Playwright E2E)
   or: /shipwright-test --design-fidelity  (only design fidelity check)
   or: /shipwright-test --report-boundary-coverage  (audit Affected Boundaries declarations across iterate-specs, ADR-027)
   or: Invoked by /shipwright-run (orchestrator)

Test layers:
  1.  Unit tests (Vitest / pytest)
  1.5 Integration tests (if profile has testing.integration)
  1.6 pgTAP database tests (if supabase/tests/database/ exists)
  2.  Smoke test (HTTP 200 on DEV URL)
  3.  Playwright E2E (if UI project + DEV URL available)
  3.6 Cross-page consistency (if .shipwright/designs/visual-guidelines.md exists)
  3.7 Design fidelity (if .shipwright/designs/screen-routes.json exists)
  3.8 Performance budget (if profile has testing.performance.enabled)
  3.9 Stop dev server (always, finally-block — runs even if 3.7 / 3.8 failed)
  4.  Security scan -> out-of-band; see /shipwright-security (not auto-invoked)
================================================================================
```

## B. Detect Profile

Read `shipwright_project_config.json` from project root:
```json
{
  "profile": "supabase-nextjs",
  ...
}
```

Load profile from `{plugin_root}/../../shared/profiles/{profile}.json`.

If no config: detect from package.json / pyproject.toml.

## B2. Detect Invocation Mode

**The `phaseTaskId` the orchestrator hands you at dispatch is the authority** — NOT any
state field inside `shipwright_run_config.json`. The pipeline's v1 state fields are no
longer advanced, so keying on them made every driven phase past the first misclassify
itself as standalone; the rationale is in `shared/scripts/lib/phase_invocation_mode.py`.
**Never re-derive the mode yourself.** Ask the resolver:

```bash
uv run "{shared_root}/scripts/tools/get_phase_context.py" \
  --phase-task-id "{phaseTaskId}" --phase test --project-root "{project_root}"
```

Omit `--phase-task-id` if you were not handed one. Set `invocation_mode` from the returned
`mode`, which is exactly one of:

- **`pipeline`** — you were dispatched. Enforce gates, and do the phase's real work.
  **Do NOT call `orchestrator.py update-step`** (nor any other run-state write): in a
  driven run `single-session-apply` owns phase completion — it records your status when
  it applies your result. See `plugins/shipwright-run/skills/run/SKILL.md`. (`update-step`
  is inert in a driven run anyway, but do not rely on that.)
  Do NOT mark `shipwright_test_results.json` standalone.
- **`standalone`** — no token, so this is a hand-invoked run:
  - Skip pipeline state updates (no `orchestrator.py update-step` calls)
  - Skip upstream completion checks
  - Still produce all artifacts (`shipwright_test_results.json`, event log)
  - **Mark artifacts**: when writing `shipwright_test_results.json`, add `"mode": "standalone"` at the top level. This tells the pipeline validator to ignore standalone results and require a fresh pipeline test run.
  - Print: `"Running in standalone mode — pipeline state will not be updated."`
  - If `requires_out_of_sequence_warning` is `true`, a driven run is LIVE at
    `active_phases`. Warn that running `/shipwright-test` out-of-band may collide with it,
    and **ask the user before continuing**. (The `test` phase has no cataloged gate id yet
    — it is a tracked `pending_phases` follow-up in `shared/config/gate_catalog.json` — so
    ask interactively rather than resolving a gate policy.)
- **`error`** (exit code 2) — you were dispatched but the token does not resolve (stale,
  terminal, wrong phase, or an unreadable config). **STOP.** Do NOT continue as
  standalone. This phase is where that mistake bites hardest: a driven run whose results
  are stamped `"mode": "standalone"` is *rejected* by `phase_validators._validate_test`,
  which then demands a re-run "within the pipeline" that would misclassify identically —
  a deadlock. Surface it to the orchestrator as an `ok: false` result.

Store the resolver's verdict as `invocation_mode` — `"pipeline"` | `"standalone"` | `"error"` (STOP) — for use in later steps.

## B3. Load Project Context

Read these files for app context before running tests:

1. `.shipwright/agent_docs/architecture.md` — app structure (understand what to test)
2. `shipwright_test_results.json` — previous test state (if exists, for comparison)

If a file does not exist, skip it silently.

## B4. Prerequisite Self-Healing

See [prerequisite-self-healing.md](prerequisite-self-healing.md) for the full
auto-generation flow (missing dev_url, visual-guidelines.md, screen-routes.json,
E2E plan, playwright.config.ts).

## C. Determine Test Strategy

Based on profile:

| Profile | Unit Runner | E2E | Smoke URL Pattern |
|---------|------------|-----|-------------------|
| `supabase-nextjs` | `npx vitest run` | Playwright | `http://localhost:3000` |
| (future) | configurable | configurable | configurable |
