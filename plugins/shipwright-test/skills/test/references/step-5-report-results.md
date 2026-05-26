# Step 5: Report Results

**Print Summary:**
```
================================================================================
SHIPWRIGHT-TEST RESULTS
================================================================================
Unit tests:    {passed}/{total} passed ({duration}s)
Integration:   {passed}/{total} passed ({duration}s) | SKIP: {reason}
pgTAP:         {passed}/{total} passed ({duration}s) | SKIP: {reason}
Smoke test:    {PASS | FAIL | SKIP} ({url}, {response_time}ms)
E2E tests:     {passed}/{total} passed | SKIP
Consistency:   {passed}/{total} categories consistent | SKIP
Design fidelity: {passed}/{total} checked | SKIP
Performance:   LH {score}/100 (budget {budget}), bundle {size}KB (budget {budget}KB), gate {warn|block} | SKIP: {reason}
Security:      {via /shipwright-security | not run}

Overall:       {PASS | FAIL}
{Failed tests: list if any}
================================================================================
```

**If profile has UI** (component_library set, or client-side framework detected):
```
================================================================================
  Verify visually:  /shipwright-preview
  Preview URL:      {dev_url from shipwright_build_config.json}
================================================================================
```

If `--fix` was used:
```
Auto-fix attempts: {N}
Fixed: {list of fixed tests}
Remaining failures: {list}
```

For per-layer enforcement rules see [results-enforcement.md](results-enforcement.md).
For the per-layer Completion Gate (every layer must have an explicit result)
see [completion-gate.md](completion-gate.md).

**Reflection — Capture Test Learnings** (before marking phase complete):

If test failures required investigation or fixes:
1. Flaky test patterns worth documenting?
2. Infrastructure quirks (timing, ports, browser drivers)?
3. Test strategy insights (missing coverage, better approaches)?

If learnings exist:
- **Observations** -> append to `.shipwright/agent_docs/conventions.md` under `## Learnings`
  Format: `- ({YYYY-MM-DD}) test — {summary}`
- **Cross-project insights** -> save Claude Code feedback/project Memory
If none: skip.

**Record test_run event** (always, even on failure — captures layer results):
```bash
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" \
  --type test_run \
  --trigger "pipeline" \
  --unit-passed {unit_passed} \
  --unit-total {unit_total} \
  --e2e-passed {e2e_passed} \
  --e2e-total {e2e_total} \
  --smoke-status "{pass|fail|skip}"
```
Where `{shared_root}` = `{plugin_root}/../../shared`.

Omit `--e2e-passed`/`--e2e-total` if E2E was skipped. Omit `--smoke-status` if smoke was skipped.
Use `--trigger "iterate"` when invoked by `/shipwright-iterate`, `"manual"` when invoked standalone.

**Phase complete — update pipeline state** (only if Completion Gate passes):

Iterate 12.4 wires the test plugin into the Minimum Phase Completion
Canon at C1/C2/C3 only. **C4 is skipped by policy** — test runs are
events, not architectural decisions (both LLM reviewers flagged this
as CRITICAL). **C5 is also skipped** — test results live in
`shipwright_test_results.json`, not CHANGELOG.

```bash
# Derive a run id if the orchestrator didn't set one.
: "${SHIPWRIGHT_RUN_ID:=test-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID

# C1 — test_run event already recorded above.
# (The event-type is `test_run`, not `phase_completed`, but also emit
# a phase_completed event so the generic C1 verifier matches uniformly.)
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase test \
  --detail "{unit_passed}/{unit_total} unit, {e2e_passed}/{e2e_total} e2e"

# C2 — delivery dashboard
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase test --detail "{passed}/{total} passing" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 (NEW 12.4) — canon-marker handoff
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase test \
  --reason "test complete: {unit_passed}/{unit_total} unit, {e2e_passed}/{e2e_total} e2e, smoke {smoke_status}"

# C4 — SKIPPED by policy (test is not a decision-taking phase).
# C5 — SKIPPED by policy (test results belong in shipwright_test_results.json,
#      not CHANGELOG).

# phase_history (NEW 12.4) — audit trail
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase test --run-id "$SHIPWRIGHT_RUN_ID" \
  --entry-json '{"unit":"{unit_passed}/{unit_total}","e2e":"{e2e_passed}/{e2e_total}","smoke":"{smoke_status}","outcome":"passed"}'

# Mark test phase complete (triggers compliance update automatically).
# _validate_test() now runs the modular test_checks verifier (canon
# C1/C2/C3 + phase_history) in addition to the existing results-layer
# completion gate.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step test --status complete
```
