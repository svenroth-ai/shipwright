# Build Phase Autopilot Loop

When executing the build phase (step 3b in the pipeline), use the autopilot loop:

1. **Get section progress:**
```bash
uv run {plugin_root}/scripts/lib/orchestrator.py get-build-progress \
  --project-root "$(pwd)"
```

2. **Initialize dashboard:**
```bash
uv run {shared_root}/scripts/tools/update_build_dashboard.py \
  --project-root "$(pwd)" --session-id "{SHIPWRIGHT_SESSION_ID}"
```

3. **For each incomplete section** (from `next_section` in progress output):

   a. **Reset tool counter** (prevents stale counter from prior section):
      ```bash
      uv run {shared_root}/scripts/tools/reset_tool_counter.py \
        --counter-file "$(pwd)/.shipwright_toolcall_count"
      ```

   b. Update dashboard: `--section "{section}" --step 1 --detail "Starting"`

   **--- Autonomous mode: Subagent delegation ---**

   c. **IF autonomy == "autonomous":** Spawn `section-builder` subagent (Agent tool):
      - `description`: "Build section {section}"
      - `subagent_type`: "shipwright-build:section-builder"
      - `prompt`: Provide all required parameters:
        - `section_file`: `{sections_dir}/{section}.md` (absolute path)
        - `project_root`: `$(pwd)` (absolute path)
        - `plugin_root`: `{build_plugin_root}` (sibling: `{plugin_root}/../shipwright-build`)
        - `shared_root`: `{shared_root}` (= `{plugin_root}/../../shared`)
        - `branch_name`: from `setup_implementation_session.py` output (pattern: `build/{slug}-{session-id}`)
        - `section_name`: `{section}`
        - `session_id`: `{SHIPWRIGHT_SESSION_ID}`
      - Do **NOT** use `run_in_background` — sections must be sequential
      - Do **NOT** use `isolation: "worktree"` — section N+1 needs section N's code

   d. **Parse subagent result JSON.** Expected fields:
      - `status`: "complete" or "failed"
      - `commit`, `branch`, `tests_passed`, `tests_total`, `review_findings`, `decisions`

   e. **If status == "failed":**
      - Update dashboard with `--status failed`
      - Print error summary from result
      - **STOP** — do not continue to next section
      - Inform user of failure with diagnosis from result

   f. **If status == "complete":**
      - Verify section state in config:
        ```bash
        uv run {shared_root}/scripts/tools/update_build_dashboard.py \
          --project-root "$(pwd)" --section "{section}" --status complete \
          --session-id "{SHIPWRIGHT_SESSION_ID}"
        ```
      - Log decisions from result to decision log (if any)
      - **No context pressure check needed** — subagent used its own context window
      - Continue to next section

   **--- Guided mode: Direct invocation (unchanged) ---**

   g. **IF autonomy == "guided":**
      - Invoke: `/shipwright-build @{sections_dir}/{section}.md`
      - On return: update dashboard with `--status complete`
      - Check context pressure:
        ```bash
        uv run {shared_root}/scripts/tools/estimate_context_pressure.py \
          --counter-file "$(pwd)/.shipwright_toolcall_count" --threshold 120
        ```
      - If `recommend_checkpoint` is true:
        - Update dashboard with `--status paused`
        - Generate session handoff
        - Print checkpoint banner (see above) and **STOP**

   h. Re-run `get-build-progress` and continue with next section

4. **All sections done:** Proceed to test phase (see `references/test-execution.md`)

**In guided mode:** Ask before each section:
```
AskUserQuestion:
  question: "Section {N-1} complete ({completed}/{total}). Continue with {next_section}?"
  options:
    - "Continue"
    - "Review first"
    - "Stop here"
```
