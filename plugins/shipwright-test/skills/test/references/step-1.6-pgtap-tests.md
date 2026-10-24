# Step 1.6: Run pgTAP Database Tests

**Skip if:** `supabase/tests/database/` directory does not exist.

**Run pgTAP tests:**
```bash
supabase test db
```

Or via runner script:
```bash
uv run "{plugin_root}/scripts/lib/test_runner.py" \
  --profile "{profile}" \
  --layer pgtap \
  --cwd {project_root} \
  --skip-if-missing
```

**Autofix:** Same as integration tests (structured debugging, max 3 retries).

**Record results:**
- `pgtap_passed` / `pgtap_total` / `pgtap_duration_s`
- If skipped: `pgtap_skipped: true`, `pgtap_skip_reason: "no supabase/tests/database/ directory"`
