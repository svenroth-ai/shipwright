# Step 5: Report Results

**Step 5.0 — File follow-ups for the warning-only layers (before printing).**

Three of the four non-blocking layers used to leave nothing behind once the
session ended; only the performance budget filed anything. Run the emitter over
the finished record so a suite that has been failing for weeks is
distinguishable from one that just started:

```bash
uv run "{plugin_root}/scripts/lib/warning_followups.py" \
  --project-root "{project_root}" --run-id "{run_id}" --commit "{commit}" --json
```

It reads `shipwright_test_results.json` (so it must run **after** every layer
result is written), and emits one durable item per failing spec file, per
inconsistent category, per diverging screen, and per test that only passed on
retry. Items are deduplicated on the finding — **not** on the commit — so a
persistent failure stays one open item instead of re-firing every commit.
Emission never changes an exit code: a warning layer must not become blocking
through its own bookkeeping.

Its `summary` block also gives you the known-vs-genuine split for the printed
summary below. Failures declared in `shipwright_known_failures.json` are
reported as known-and-accepted and file nothing — they are not new work.

**Print Summary:**
```
================================================================================
SHIPWRIGHT-TEST RESULTS
================================================================================
Unit tests:    {passed}/{total} passed ({duration}s)
               {n} known-and-accepted (shipwright_known_failures.json), {m} genuine
Integration:   {passed}/{total} passed ({duration}s) | SKIP: {reason}
pgTAP:         {passed}/{total} passed ({duration}s) | SKIP: {reason}
Smoke test:    {PASS | FAIL | SKIP} ({url}, {response_time}ms)
E2E tests:     {passed}/{total} passed, {flaky} passed only on retry | SKIP
               {n} known-and-accepted, {m} genuine
Journeys:      {covered}/{planned} planned journeys covered | {gaps listed}
Consistency:   {passed}/{total} categories consistent | SKIP
Design fidelity: {passed}/{total} checked | SKIP
Performance:   LH {score}/100 (budget {budget}), bundle {size}KB (budget {budget}KB), gate {warn|block} | SKIP: {reason}
Security:      {via /shipwright-security | not run}

Follow-ups filed: {n} (see .shipwright/triage.jsonl)

Overall:       {PASS | FAIL}
{Failed tests: list if any, genuine failures FIRST}
================================================================================
```

**Reporting rules for the honesty lines:**

- **Known-and-accepted is reported separately from genuine, never merged into
  one red number.** The audit phase already excuses baseline failures; if this
  phase reports them as fresh, the two components hold different truths about
  the same run — and the operator learns to ignore red, which is worse than any
  single failure.
- Omit the known/genuine line entirely when `shipwright_known_failures.json` is
  absent. Say so explicitly when it is present but unreadable — an unreadable
  list excuses nothing.
- **A flaky test is a pass.** It does not block and does not enter
  `Failed tests`. It is counted on its own so a test that has needed a retry
  for weeks becomes visible before it fails for good.
- The baseline is an **aggregate allowance** wherever only counts are
  available. Do not name particular failures as accepted unless they were
  matched by identity.

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

**Stamp the record with the state it describes** (always — run it here, after every
layer has merged into the file, so the stamp describes the *finished* record):

```bash
: "${SHIPWRIGHT_RUN_ID:=test-$(date +%Y%m%d-%H%M%S)}"
export SHIPWRIGHT_RUN_ID
uv run "{shared_root}/scripts/tools/stamp_test_results.py" \
  --project-root "$(pwd)" --run-id "$SHIPWRIGHT_RUN_ID"
```

Pass the shell variable, never a literal: `{run_id}` is not a placeholder this
plugin substitutes, and an unsubstituted template literal is refused rather than
stamped, leaving the record with no run id. The `:=` guard is idempotent, so this
works whether or not the phase-session step below already exported the variable.

This writes the top-level `source_state` block — the run id, the HEAD commit the
tests ran against, and whether tracked files were modified. **Do not hand-write the
commit or the modified flag**: the tool reads those from git, which is what makes
them evidence rather than a claim — the same defect as a self-declared
`"mode": "standalone"`. (The run id itself is declared by the caller; the tool
cannot verify it.)

Without this the record is not bound to a code version, so a leftover record from
an earlier commit satisfies the phase gate (card `trg-4d5b6a56`, FR-01.10). Exit
non-zero means the record is missing or unreadable — fix that rather than skipping
the stamp; the tool deliberately refuses to overwrite a record it cannot parse.

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
