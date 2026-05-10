# Mini-Plan: stop-hook-schema-fix

- **Run ID:** iterate-2026-05-10-stop-hook-schema-fix
- **Branch:** `iterate/stop-hook-schema-fix` (from `main`)
- **Strategy (revised after user approval):** audit-first, targeted fix. Build a comprehensive event-aware schema validator FIRST that walks every `plugins/*/hooks/hooks.json` entry across all events (Stop, SubagentStop, PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd). Then fix only the scripts that actually violate per-event schema.

## Per-event schema (source: https://code.claude.com/docs/en/hooks, fetched 2026-05-10)

| Event | hookSpecificOutput permitted? | Allowed fields inside |
|---|---|---|
| Stop | yes | hookEventName ONLY (no additionalContext) |
| SubagentStop | yes | hookEventName ONLY |
| PreToolUse | yes | hookEventName, permissionDecision, permissionDecisionReason, updatedInput, additionalContext |
| PostToolUse | yes | hookEventName, additionalContext |
| UserPromptSubmit | yes | hookEventName, additionalContext, sessionTitle |
| SessionStart | yes | hookEventName, additionalContext |
| SessionEnd | NO | (no decision control at all) |

Top-level `decision`/`reason` is always permitted for events with decision control (Stop, SubagentStop, PreToolUse, PostToolUse, UserPromptSubmit — NOT SessionEnd).

## Files to change

### Production scripts (5)
1. `shared/scripts/hooks/audit_phase_quality_on_stop.py`
   - Replace `_emit_hook_output(payload)` helper so it writes `payload["additionalContext"]` (if present) to `sys.stderr` as `[phase-quality] <message>\n`, no JSON on stdout.
   - Keep 3 call sites; the payload shape they pass stays the same internally, so we don't need to touch them.

2. `shared/scripts/hooks/generate_handoff_on_stop.py`
   - 3 inline emission sites (lines ~239, ~329, ~337). Replace each `print(json.dumps({...}))` with `sys.stderr.write(f"[session-handoff] {message}\n")`.

3. `shared/scripts/hooks/write_terminal_marker.py`
   - Drop the print entirely — the `DONE` file on disk is the actual signal the loop polls for. Keep `sys.stderr.write(...)` line as a low-cost diagnostic.

4. `plugins/shipwright-build/scripts/hooks/check_documentation.py`
   - Replace single emission with `sys.stderr.write(f"[doc-check] {message}\n")`.

5. `plugins/shipwright-plan/scripts/hooks/write-section-on-stop.py` (SubagentStop)
   - `_hook_error()` helper builds 5 error payloads + 1 success payload. SubagentStop also doesn't accept `hookSpecificOutput` per docs. Replace stdout-JSON emission with stderr-text emission. Keep `structuredError` info in the stderr message for operator visibility.

### Tests (2 modified + 1 new)
6. `shared/tests/test_audit_phase_quality.py`
   - Find every assertion on `hookSpecificOutput["additionalContext"]` and update to assert on `capfd.readouterr().err` content instead.

7. `shared/tests/test_generate_handoff_on_stop.py`
   - Same update.

8. `shared/tests/test_stop_hook_schema_compliance.py` **(NEW)** — the parametrized regression test from AC3. Enumerates `plugins/*/hooks/hooks.json` Stop entries, runs each script with `echo '{}'` stdin, asserts AC1.

## Test strategy

**RED phase first.** Before any production fix:
1. Write the new `test_stop_hook_schema_compliance.py` parametrized test. Run it — it MUST fail for the 4 affected Stop-hook scripts (the SubagentStop script tests separately).
2. Update one existing test in `test_audit_phase_quality.py` to assert on stderr instead of stdout-JSON. Run it — it MUST fail until the production fix lands.

**GREEN phase.** Apply the 5 production fixes one script at a time, re-running the new regression test + existing tests after each. Stop only when:
- new regression test green for all enumerated Stop entries
- existing tests green
- diagnostic stderr text still visible

**Boundary Probe.** The new `test_stop_hook_schema_compliance.py` IS the round-trip test:
- producer = each hook script
- file-on-disk = stdout capture
- consumer = the schema check (replicates Claude Code's validator: top-level `decision`/`reason` only, no `hookSpecificOutput`)
- 8 probe categories: not all apply (machine-only protocol; operator-input categories N/A — justify in self-review).

## Alternative considered (and rejected)

**Alt-1: Move to top-level `decision: "block"` + `reason` shape.** This is the OTHER valid Stop output, but it would block session stopping (the schema docs are explicit). Rejected — these hooks are explicitly observability-only ("Never blocks." comment in `audit_phase_quality_on_stop.py:13`). Blocking session stop on every audit/handoff would be a regression worse than the current schema warning.

**Alt-2: Wrap output in `try`/`except` that swallows the validation error.** Rejected — we don't control Claude Code's validator; the error comes from Claude Code AFTER our script exits. Only the producer (our script) can fix this.

**Alt-3: Move the diagnostics into `additionalContext` for a `PostToolUse` hook instead.** Rejected — the diagnostics are about session-lifecycle state (audit complete, handoff written), not tool calls. Wrong event semantics.

## Work breakdown

1. **RED**: Write new parametrized regression test + update 2 existing tests to assert stderr. Verify all fail.
2. **GREEN**: Fix `audit_phase_quality_on_stop.py`. Re-run tests.
3. **GREEN**: Fix `generate_handoff_on_stop.py`. Re-run tests.
4. **GREEN**: Fix `write_terminal_marker.py`. Re-run tests.
5. **GREEN**: Fix `check_documentation.py`. Re-run tests.
6. **GREEN**: Fix `write-section-on-stop.py` (SubagentStop bonus). Re-run tests.
7. **Boundary Probe**: extended categories review per `references/boundary-probes.md`; document the N/A categories.
8. **Self-Review + Confidence Calibration**: populate iterate spec.
9. **Full test suite + Code Review Cascade**.
10. **F0 / F0.5 / F1-F12 finalization**.
