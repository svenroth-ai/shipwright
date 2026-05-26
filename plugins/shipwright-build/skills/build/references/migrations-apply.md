# Migrations — Apply & Verify

Detail for Kern Step 4 (Implement) when migration files were created in this section.

See also [migration-safety.md](migration-safety.md) for `down.sql` and destructive-change rules.

## When to Run

Apply migrations immediately after their `up.sql` / `down.sql` files exist in the working tree and before re-running tests — otherwise tests run against a stale schema.

Read `migrations` config from the stack profile (via `shipwright_run_config.json` -> `profile` -> `shared/profiles/{profile}.json`).

## Preflight Sequence (mandatory before apply)

1. Verify new files exist in `{migrations.dir}`
2. Run `{migrations.preflight_cmd}` — verifies CLI, authentication, and connectivity
3. If `safe_nonprod_only` is true, verify target is non-production (check preflight output or project-ref)
4. If preflight fails: Print diagnostic and instruct user to fix environment. **Stop — do not run tests against stale schema.**

## Apply

5. Run `{migrations.apply_cmd}`
6. If apply fails: **Stop immediately.** Do not run tests. Do not attempt further schema changes. Database may be in partial state. Ask user for intervention.
7. Verify with `{migrations.list_cmd}` — no pending migrations should remain.

## Post-Migration Manual Steps

8. Check `migrations.post_apply_manual_steps` from the profile — match `trigger_tag` against migration content.
9. If a trigger matches: inform user via AskUserQuestion with the required action. Note which test areas (`blocks_tests_for`) are blocked until the step is completed. Wait for confirmation before running affected tests.

## After Apply — Running Tests

This ensures subsequent tests run against the current schema.

**Checkpoint:** All tests pass (green phase).

**Run integration tests** (if integration test files were created in the red phase):

```bash
npx vitest run --config vitest.integration.config.ts
```

Integration test failures are **blocking** — fix before proceeding. Autofix: structured debugging (root cause -> hypothesis -> fix -> re-run), max 3 retries. **Fast-fail:** if error matches `ECONNREFUSED`, `ETIMEDOUT`, or >50% of tests fail simultaneously, stop autofix and report infrastructure issue.

**Never auto-fix by weakening RLS policies or switching to service-role client for assertions.**

**Run pgTAP tests** (if pgTAP test files were created):

```bash
supabase test db
```

**Capture test counts** — note the numbers from the final test run for Kern Step 10:

- `tests_passed` = number of passing tests
- `tests_total` = total number of tests
- `integration_passed` / `integration_total` (if integration tests exist)
- `pgtap_passed` / `pgtap_total` (if pgTAP tests exist)

## Vite DX Scaffold

(if profile uses Vite — check `profile.stack.frontend.vite`)

When generating or modifying `vite.config.ts`, start from `{shared_root}/templates/vite.config.ts.template`. It gates dev-only plugins on `mode === 'development'` so they never ship to prod, and provides a slot for additional dev-only Vite plugins.

App entry (`client/src/main.tsx` or equivalent) should mount two dev-only React components from `{shared_root}/templates/`:

- `dev-error-overlay.tsx.template` — modal for runtime errors + unhandled-promise rejections during development. Self-contained, no external deps.
- `dev-banner.tsx.template` — small fixed-position pill so dev tabs cannot be confused with prod tabs.

Both render `null` in production via `import.meta.env.DEV`, so copying them into prod builds is harmless. Brownfield projects with an existing `vite.config.ts` are handled by `/shipwright-adopt` (offer-only, no auto-overwrite).

## Dashboard Update + Context Pressure Check

```bash
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --section "{section_name}" --step 4 --detail "Implementation complete (green phase)" --session-id "{SHIPWRIGHT_SESSION_ID}"

uv run "{shared_root}/scripts/tools/estimate_context_pressure.py" \
  --counter-file "$(pwd)/.shipwright/toolcall_count" --threshold 120
```

If `recommend_checkpoint` is true AND section is not yet complete:

1. Commit partial progress
2. Generate session handoff
3. Update dashboard with `--status paused`
4. Tell user: "Context pressure detected. Open a new session (+) or /clear, then /shipwright-run to continue."
5. **STOP** — do not continue to next step.
