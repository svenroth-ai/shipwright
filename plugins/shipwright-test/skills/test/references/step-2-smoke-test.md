# Step 2: Run Smoke Test (if DEV URL available)

```bash
uv run "{shared_root}/scripts/smoke_test.py" \
  --url "{dev_url}" \
  --timeout 10 \
  --health-path "/api/health"
```

**DEV URL sources (in order):**
1. `shipwright_build_config.json` -> `dev_url`
2. Environment variable `SHIPWRIGHT_DEV_URL`
3. Default: `http://localhost:3000`

If no DEV URL and app not running: skip with note.

**Note:** The smoke test script is a **shared plugin script** (`{shared_root}/scripts/smoke_test.py`),
not a project file. Do NOT search for smoke test files in the project directory.

**If smoke test fails (any reason) — diagnose before skipping:**
1. **Diagnose:** Read error output, identify root cause
2. **Attempt autonomous fix** based on diagnosis. Examples:
   - Connection refused -> check if dev server is running, start/restart it
   - HTTP error (non-200) -> check app logs, report to user (real app bug)
   - Timeout -> increase timeout, retry
   - Process hung -> kill stale process, restart
3. **Retry** smoke test after fix
4. After 2 failed fix attempts: **ASK user** how to proceed
