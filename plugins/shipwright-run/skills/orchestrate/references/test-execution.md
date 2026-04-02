# Test Phase Execution

After all build sections are complete:

**--- Autonomous mode: Subagent delegation ---**

**IF autonomy == "autonomous":** Spawn `test-runner` subagent (Agent tool):
- `description`: "Run test suite"
- `subagent_type`: "shipwright-test:test-runner"
- `prompt`: Provide all required parameters:
  - `project_root`: `$(pwd)` (absolute path)
  - `plugin_root`: `{test_plugin_root}` (sibling: `{plugin_root}/../shipwright-test`)
  - `shared_root`: `{shared_root}`
  - `profile`: from `shipwright_project_config.json`
  - `session_id`: `{SHIPWRIGHT_SESSION_ID}`
  - `dev_url`: from `shipwright_build_config.json` → `dev_url`, or env `SHIPWRIGHT_DEV_URL`, or default `http://localhost:3000`

**Parse test-runner result JSON.** Expected fields:
- `status`: "pass" or "fail"
- `unit`: `{passed, total, duration_s}`
- `smoke`: `{status, url, response_ms}` or `{status: "skipped", reason: "..."}`
- `e2e`: `{passed, total, failures, skipped}` or `{status: "skipped", reason: "..."}`
- `fixes_applied`: list of auto-fixes attempted

**Validate test completeness:** The orchestrator's phase validator (`phase_validators.py`) automatically checks test completeness when `update-step --status complete` is called. It verifies:
- `unit` field exists and has results (always required)
- `smoke` field exists (result or skip reason)
- `e2e` field exists (result or skip reason)
If any field is missing, `update-step` returns `status: "needs_validation"` with the specific issues. Follow the standard validation handling (AskUserQuestion → fix or --force).

**If status == "fail":**
- Update dashboard: `--phase test --status failed`
- Print test failure summary from result
- **STOP** — do not proceed to deploy
- Inform user of which tests failed and why

**If status == "pass":**
- **Persist test results** (if not already written by test-runner):
  Verify `shipwright_test_results.json` exists in project root. If not, write the parsed JSON result to that file. This ensures compliance reports have access to unit/smoke/e2e results.
- Update pipeline state:
  ```bash
  uv run {plugin_root}/scripts/lib/orchestrator.py \
    update-step --project-root "$(pwd)" --step test --status complete
  ```
- Update dashboard:
  ```bash
  uv run {shared_root}/scripts/tools/update_build_dashboard.py \
    --project-root "$(pwd)" --phase test \
    --detail "{unit.passed}/{unit.total} unit, {e2e.passed}/{e2e.total} E2E" \
    --session-id "{SHIPWRIGHT_SESSION_ID}"
  ```
- Update compliance:
  ```bash
  uv run {compliance_plugin_root}/scripts/tools/update_compliance.py \
    --project-root "$(pwd)" --phase test
  ```
- Continue to security scan / changelog / deploy

**--- Guided mode: Direct invocation (unchanged) ---**

**IF autonomy == "guided":** Invoke `/shipwright-test` as before.
