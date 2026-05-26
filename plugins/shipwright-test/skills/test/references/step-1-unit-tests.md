# Step 1: Run Unit Tests

```bash
uv run "{plugin_root}/scripts/lib/test_runner.py" \
  --profile "{profile}" \
  --layer unit
```

**Expected output:** Test results with pass/fail counts.

**Autonomous mode** (check `autonomy` in `shipwright_run_config.json`):
If tests fail, automatically apply --fix behavior (structured debugging,
up to 3 retries) without requiring the explicit --fix flag.

**Guided mode:** Only attempt fixes if `--fix` flag was explicitly passed.

**Fix behavior** (max 3 retries, structured debugging):
1. **Root cause:** Read error output, identify what's failing and why
2. **Pattern check:** Same root cause as previous attempt? -> Change approach, don't retry same fix
3. **Hypothesis:** State what you'll change and why before editing
4. Attempt targeted fix based on hypothesis
5. Re-run tests
6. After 3 retries (or 2 with same root cause): report remaining failures with diagnosis
