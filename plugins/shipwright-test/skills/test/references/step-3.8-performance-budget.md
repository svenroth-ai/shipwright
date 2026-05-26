# Step 3.8: Performance Budget Check (if applicable)

**Condition:** Runs if the profile has `testing.performance.enabled: true`.
The check is also activated when the project's `shipwright_test_config.json`
sets `performance.enabled: true`. If neither opts in, the runner emits a
structured `skipped: profile opts out` result (no silent omission — the
result still appears in `shipwright_test_results.json.performance` with
`skipped: true`).

**Note for the bundle sub-check:** the bundle measurement requires a prior
production build (`npm run build` or equivalent — the artifact directory
declared in `profile.testing.performance.bundle.build_output_dir`). If no
build has been produced, the bundle sub-check is `skipped` with reason —
the Lighthouse sub-check still runs.

**Tooling:** Lighthouse runs via the project's existing Playwright Chromium
through a small Node script (`{plugin_root}/scripts/perf/lighthouse-runner.mjs`).
No extra browser install required. The plugin pins `lighthouse@13.x` in
`{plugin_root}/scripts/perf/package.json`; the Python wrapper lazy-installs
that dep on first invocation.

**1. Run the performance check:**
```bash
uv run "{plugin_root}/scripts/lib/performance_check.py" \
  --cwd "{project_root}" \
  --profile-path "{shared_root}/profiles/{profile}.json" \
  --dev-url "{dev_url}" \
  --gate inherit
```

`--gate inherit` (default) honors the profile / `shipwright_test_config.json`
value (`warn` or `block`). Pass `--gate warn` or `--gate block` to override
for a one-off run.

**2. Parse the JSON output** — single object on stdout matching:
```json
{
  "success": true,
  "skipped": false,
  "gate": "warn",
  "lighthouse": {
    "ran": true, "skipped": false,
    "score": 92, "score_budget": 85, "score_passed": true,
    "lcp_ms": 1840, "lcp_budget_ms": 2500, "lcp_passed": true
  },
  "bundle": {
    "ran": true, "skipped": false,
    "total_kb_gz": 187.4, "budget_kb_gz": 250, "passed": true,
    "files_measured": 14,
    "measurement_semantic": "gzipped *.js + *.css payload — excludes assets, source-maps, precompressed siblings"
  },
  "duration_seconds": 12.7
}
```

**Bundle measurement semantic:** the `total_kb_gz` figure is the gzip-compressed
size of `*.js` + `*.css` files in `build_output_dir` (excludes source maps,
precompressed siblings). It is the **JavaScript + CSS payload only**, not the
full transfer size of the page (fonts, images, etc., are not counted).
Static-asset budgets are out of scope for v1.

**3. Record results** in `shipwright_test_results.json`:
```json
{
  "performance": {
    "ran": true,
    "passed_layers": 2,
    "total_layers": 2,
    "gate": "warn",
    "lighthouse": { ... mirrors stdout ... },
    "bundle": { ... mirrors stdout ... },
    "skipped": false,
    "skip_reason": ""
  }
}
```

**4. Gate behavior:**
- `gate: "warn"` (default): result `success: true` even on failures.
  Failures are logged but do NOT fail the test phase.
- `gate: "block"` (opt-in): non-skipped layer failures set `success: false`
  and exit code 1. Test phase fails.

**5. Skip semantics** (these all return `success: true` and are valid
completion states):
- `profile opts out` — `testing.performance.enabled: false`
- `no dev_url available` — Lighthouse can't run; bundle still measured
- `no build artifacts found` — bundle skipped; Lighthouse still runs
- `no bundle assets matched` — `build_output_dir` exists but no `*.js`/`*.css`
- `lighthouse_unavailable` — Node/Playwright/Chromium not reachable

**Override mechanism (precedence, most-specific wins):**
1. `--gate` CLI flag
2. `shipwright_test_config.json` -> `performance.{lighthouse,bundle,gate}` (deep-merged)
3. Profile `testing.performance.{...}`
4. Built-in defaults (Lighthouse 85, bundle 250 KB gz, LCP 2500 ms, gate `warn`)

The deep-merge means a project that sets only
`shipwright_test_config.json.performance.lighthouse.min_score: 95` inherits
`lcp_max_ms` from the profile.
