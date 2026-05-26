# Step 3.7: Design Fidelity Verification — Regressions-Only (if applicable)

**Condition:** Runs if `.shipwright/designs/screen-routes.json` exists in the project root. Also runs standalone via `--design-fidelity` flag.

**Purpose:** Detect and fix design fidelity regressions introduced by later build sections (cross-section side effects). Build handles the bulk of fidelity checks per-section; Test is the safety net. Non-blocking (WARNING level) — fidelity differences don't fail the pipeline.

**1. Run structural extraction:**
```bash
uv run "{plugin_root}/scripts/lib/design_fidelity_check.py" \
  --cwd "{project_root}"
```

Parse the JSON output:
- `skipped: true` -> no screen-routes.json, skip to step 6
- All screens `status: "pass"` -> PASS, skip to step 5
- Some screens `status: "needs_review"` -> proceed to triage

**2. Read build fidelity results:**
Read `design-fidelity-report.json` from the project root. Build a screen-status map: `{screen: status}`.
- If file is missing or fails to parse -> **fallback**: treat all screens as unchecked (full analysis, backward-compatible).
- If `build_complete: false` -> log WARNING ("Build may still be in progress"), proceed with triage anyway.

**3. Triage against build results:**

For each screen with `status: "needs_review"`, determine its category using `design-fidelity-report.json`:

| Category | Condition | Priority | Action |
|----------|-----------|----------|--------|
| **Resolved** | Screen was `partial` in Build, now auto-passes | Log only | Log as positive outcome |
| **Regression** | Screen was `full` in Build, now has failures | Prio 1 | Cross-section side effect — agent deep review |
| **Persistent Failure** | Screen was `partial` in Build, still fails | Prio 2 | Build gave up — one more try |
| **Unchecked** | Screen not in build report | Prio 3 | Never verified — full agent review |

**4. Agent deep review (for flagged screens):**

For each flagged screen:
a. Read the mockup HTML source at `{mockup_path}`
b. Read the implementation TSX source at `{implementation_files[0]}`
c. Compare against 5 dimensions: Layout Structure, Component Order, Component Types, Card Patterns, shadcn Rules
d. If mismatches found: fix implementation, run unit tests, commit: `fix(test-fidelity): {description}`
e. Re-run `design_fidelity_check.py --screen {screen}` to verify fix
f. Max 3 retries per screen; if unresolvable: park with diagnosis

**After all screens attempted:**
- Report summary: which screens fixed, which parked, with diagnosis per parked screen
- **ASK user** for direction on parked screens (one consolidated dialog)
- **Commit between fix rounds** — each fix gets its own commit

**5. Record results** in `shipwright_test_results.json`:
```json
{
  "design_fidelity": {
    "passed": N,
    "total": N,
    "skipped": false,
    "screens": [
      {"mockup": "01-login.html", "route": "/login", "status": "pass"},
      {"mockup": "08-dashboard.html", "route": "/dashboard", "status": "needs_review"}
    ],
    "triage": {
      "regressions": 1,
      "persistent_failures": 0,
      "unchecked": 0,
      "resolved": 2
    }
  }
}
```

**6. Continue to Step 3.8 (Performance Budget) without stopping dev server.**
The dev server is stopped in Step 3.9 below as a `finally` step (runs even if
3.7 / 3.8 fail), so Lighthouse in 3.8 can audit the live URL.
