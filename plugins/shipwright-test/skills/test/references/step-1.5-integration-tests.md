# Step 1.5: Run Integration Tests

**Skip if:** Profile has no `testing.integration` config, OR `tests/integration/` directory does not exist.

**Check prerequisites:**
1. Read profile `testing.integration` block
2. Verify env vars from `.env.test`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
3. Verify URL is localhost/127.0.0.1 (safety check)
4. **In CI:** Missing env vars = FAIL (not skip). **Locally:** Missing env vars = skip with warning.

**Run integration tests:**
```bash
npx vitest run --config vitest.integration.config.ts
```

Or via runner script:
```bash
uv run "{plugin_root}/scripts/lib/test_runner.py" \
  --profile "{profile}" \
  --layer integration \
  --cwd {project_root} \
  --skip-if-missing
```

**Autofix behavior:** Same structured debugging as unit tests (root cause -> hypothesis -> fix -> re-run), max 3 retries.

**Fast-fail rules:**
- If error matches `ECONNREFUSED`, `ETIMEDOUT`, `connect ENOENT` -> skip autofix, fail immediately with infrastructure diagnosis
- If >50% of integration tests fail simultaneously -> skip autofix, fail with diagnosis (likely global issue, not individual test bugs)

**Never auto-fix by:**
- Weakening RLS policies
- Switching test assertions to use service-role client
- Disabling URL safety checks

**Common auto-fixable patterns:**

| Error Pattern | Diagnosis | Auto-fix |
|---|---|---|
| `relation "x" does not exist` | Migration not applied | Run `supabase db push --linked` |
| `permission denied for table` | RLS policy issue | Check auth context setup in test |
| `null value in column "x"` | Test data setup incomplete | Fix `beforeAll` / seed data |
| `duplicate key value` | Previous cleanup failed | Fix `afterAll` cleanup |
| Auth sign-in failure | Test user not provisioned | Create test user or check credentials |

**Record results:**
- `integration_passed`: number of passing tests
- `integration_total`: total tests
- `integration_duration_s`: duration in seconds
- If skipped: `integration_skipped: true`, `integration_skip_reason: "..."`
