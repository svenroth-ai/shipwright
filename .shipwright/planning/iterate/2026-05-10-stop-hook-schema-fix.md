# Iterate Spec: stop-hook-schema-fix

- **Run ID:** iterate-2026-05-10-stop-hook-schema-fix
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal
Stop the 35 "Hook JSON output validation failed — (root): Invalid input" errors that Claude Code surfaces at every Shipwright session end by removing the invalid `hookSpecificOutput.additionalContext` payload from all Stop and SubagentStop hook scripts. Per the official Claude Code hooks docs the `Stop` event accepts only top-level `decision`/`reason` (or silent exit 0); `additionalContext` belongs to `SessionStart`, `Setup`, `UserPromptSubmit`, `UserPromptExpansion`, and `PreToolUse`/`PostToolUse*`.

## Acceptance Criteria
- [ ] **AC1:** Running each enumerated hook-script subprocess with a minimal-but-realistic JSON stdin (per-event payload skeleton including `cwd`, `session_id`, etc.) MUST produce stdout that is EITHER (a) empty/whitespace OR (b) valid JSON whose `hookSpecificOutput` (if present) contains ONLY the fields documented for that event (see mini-plan schema table). stderr MAY contain diagnostic text. Exit code is NOT asserted (scripts may legitimately bail out on missing project state).
- [ ] **AC2:** AC1 applies uniformly to **all** events registered across `plugins/*/hooks/hooks.json`: Stop, SubagentStop, PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd.
- [ ] **AC3:** A new parametrized regression test in `shared/tests/test_hook_output_schema_compliance.py` discovers hooks via JSON parse of every `plugins/*/hooks/hooks.json`, follows `${CLAUDE_PLUGIN_ROOT}/...` substitutions to resolve shared-scripts paths, runs each command with the per-event payload, and asserts AC1. The test must also strictly fail on any non-empty stdout that is not parseable JSON (no plain-text leakage).
- [ ] **AC4:** All existing pytest suites stay green: `shared/tests/`, `plugins/shipwright-iterate/tests/`, `plugins/shipwright-build/tests/`, `plugins/shipwright-plan/tests/`, `plugins/shipwright-adopt/tests/`, `plugins/shipwright-compliance/tests/`. Every test that previously asserted on stdout `hookSpecificOutput.additionalContext` for Stop/SubagentStop is updated. The mini-plan includes a repo-wide grep step to discover ALL such consumers.
- [ ] **AC5:** Existing hook side effects are preserved: `audit_phase_quality_on_stop.py` still writes finding JSON and aggregates; `generate_handoff_on_stop.py` still writes `session_handoff.md` + dashboards; `write_terminal_marker.py` still writes the `DONE` marker; `check_documentation.py` still surfaces missing docs.
- [ ] **AC6:** Error semantics preserved: `write-section-on-stop.py` (SubagentStop) currently uses `_hook_error()` to surface failures. Error sites MUST emit `{"decision": "block", "reason": <single-line stable-prefix message>}` on stdout (still valid for SubagentStop) so Claude Code halts the flow on transcript-extraction failure — NOT just stderr (which would silently allow the subagent run to be marked successful).
- [ ] **AC7:** No changes to any `hooks.json` registration — only the scripts' stdout-emission contracts change.
- [ ] **AC8:** stderr diagnostic messages use a stable single-line prefix `[shipwright:<scope>]` (e.g. `[shipwright:phase-quality]`, `[shipwright:handoff]`) and do NOT include multi-line tracebacks, raw exception repr, or full file contents.

## Affected FRs
- n/a — framework hook protocol fix, no product FR mapping in `shipwright_sync_config.json`.

## Out of Scope
- Refactoring the audit/handoff side effects themselves.
- Changing hook ordering or adding new hook registrations.
- Restructuring or "improving" hook scripts whose stdout ALREADY validates per-event-schema — touch only true violators.
- Refactoring `_hook_error()` callers in non-hook code paths (only the SubagentStop hook entry point is in scope).

## Design Notes
- Mirror the already-correct pattern in `shared/scripts/hooks/phase_session_stop.py` and `plugins/shipwright-run/scripts/hooks/master_stop_check.py`: write diagnostic text to `sys.stderr.write(...)`, never to `stdout` as JSON. Claude Code surfaces hook stderr to the user, so diagnostic visibility is preserved.
- For low-value emissions (e.g. `write_terminal_marker.py` — the file on disk IS the signal), drop the emission entirely.
- No structural refactor — minimal-diff replacement of `print(json.dumps({"hookSpecificOutput": ...}))` with `sys.stderr.write(...)` or a deletion.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `shared/scripts/hooks/audit_phase_quality_on_stop.py:_emit_hook_output` | Claude Code hook subsystem | JSON on stdout (Stop event) |
| `shared/scripts/hooks/generate_handoff_on_stop.py` (3 print sites) | Claude Code hook subsystem | JSON on stdout (Stop event) |
| `shared/scripts/hooks/write_terminal_marker.py:main` | Claude Code hook subsystem | JSON on stdout (Stop event) |
| `plugins/shipwright-build/scripts/hooks/check_documentation.py:main` | Claude Code hook subsystem | JSON on stdout (Stop event) |
| `plugins/shipwright-plan/scripts/hooks/write-section-on-stop.py` (6 emission sites) | Claude Code hook subsystem | JSON on stdout (SubagentStop event) |

Triggers Boundary Probe sub-step (`touches_io_boundary` fires — JSON hook protocol with Claude Code as consumer). The drift-protection parametrized test in AC3 IS the round-trip protection: it runs the producer (script) and asserts the consumer's schema constraints on the producer's stdout.

## Confidence Calibration

- **Boundaries touched:** hook scripts (producers) → stdout (file-on-disk) → Claude Code hook subsystem (consumer). 5 scripts × 7 hook events.
- **Empirical probes run:**
  1. **Schema-fetch probe (2× independent fetches):** first WebFetch returned ambiguous schema table; second WebFetch (per-event, explicit) confirmed `Stop`/`SubagentStop` hookSpecificOutput accepts ONLY `hookEventName`. Asymptote-rule applied — the first answer was vague, second resolved.
  2. **Parametrized audit (88 cases × 7 events × 13 plugins):** ran with empty `{}` stdin → 1 violation (`write-section-on-stop`). Ran with realistic stdin + seeded `shipwright_run_config.json` + `CLAUDE_PLUGIN_ROOT` env → 27 violations exposed. The fixture richness made the difference; trusting the first result would have silently shipped 26 unfixed violators.
  3. **Side-effect preservation probe:** after each script fix, re-ran existing tests (`test_audit_phase_quality.py`, `test_generate_handoff_on_stop.py`, integration `TestStructuredErrorsInPipeline`) — all green. Confirmed finding JSON, handoff file, DONE marker, doc warnings, section file writes still happen.
  4. **Integration round-trip:** the new `test_hook_output_schema_compliance.py` IS the producer→consumer round-trip — runs each producer (hook script), captures stdout, validates against per-event consumer (Claude Code harness) schema constraints.
  5. **Pre-existing failure delta probe:** stashed my diff, re-ran `shipwright-build/tests/test_hooks.py` — same 3 failures on main as on branch. Confirms the 3 bash-script failures are pre-existing, not regressions from this iterate.
- **Edge cases NOT probed + why acceptable:**
  - POSIX `export` prefix, inline `# comment`, quoted `#` — N/A for the hook-stdout protocol (machine-only consumer is the Claude Code harness; no operator hand-authors hook stdout).
  - Hook-payload stdin fuzzing beyond the documented event shape — out of scope; tested with the documented minimal-stdin per event.
- **Confidence-pattern check:** YES — I had a "wait, are the docs ambiguous?" moment after the first WebFetch and ran a second focused WebFetch (the extra probe before F0). Then a second yes-then-finding fired when my initial test passed but I noticed the seeded-fixture path wasn't being exercised — ran another probe (added CLAUDE_PLUGIN_ROOT to test env), which uncovered 11 more violations. Asymptote was reached at "27 violations, all 5 scripts fixed, audit re-runs 0 fails."

## Verification (medium+)
- **Surface:** cli  (these are CLI subprocesses; no web/api surface for hook scripts themselves)
- **Runner command:** `uv run pytest shared/tests/test_stop_hook_schema_compliance.py -v` (the new parametrized regression test from AC3)
- **Evidence path:** pytest stdout captured to `.shipwright/runs/iterate-2026-05-10-stop-hook-schema-fix/surface_verification.json` by `shared/scripts/surface_verification.py`.
- **Justification:** N/A (cli surface available).
