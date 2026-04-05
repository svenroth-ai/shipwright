# Design & Testing Reference

Consolidated protocol for: Design Check, Scoped Testing, Browser Verify, Visual Comparison, E2E Update, Smoke Test.

---

## Design Check (2-tier)

### Tier 1 — Small + UI (text description)
1. Read `designs/visual-guidelines.md` for design tokens
2. Describe the UI change in structured text:
   - Which screen/component is affected
   - What changes visually (layout, components, colors, spacing)
   - Reference specific design tokens (colors, font sizes, spacing values)
3. Fill in "Design Notes" section of iterate spec (if exists)

### Tier 2 — Medium+ + UI (markdown component sketch)
All of Tier 1, plus:
1. Read `designs/chrome-definition.md` for shared chrome
2. Read relevant existing mockup HTML from `designs/screens/`
3. Write a markdown component tree:
   ```
   PageShell
   ├── Sidebar (shared chrome)
   ├── MainContent
   │   ├── PageHeader: "Course Search"
   │   ├── SearchBar: input + filter dropdowns
   │   ├── ResultsGrid
   │   │   ├── CourseCard (repeat)
   │   │   │   ├── CardHeader: thumbnail + title
   │   │   │   ├── CardContent: description + tags
   │   │   │   └── CardFooter: price + CTA button
   │   └── Pagination
   └── Footer (shared chrome)
   ```
4. Note prop structures for key components
5. Proceeds automatically unless `--pause` flag set

### Skip When
- No UI change
- Trivial complexity

---

## Scoped Testing

### Framework-Native Approach
Use Vitest's built-in dependency analysis instead of custom filename matching:
```bash
npx vitest --related {changed_files} --run
```

### Safety Floor
Changes touching these paths ALWAYS trigger full suite, regardless of complexity:
- `src/lib/`
- `src/middleware*`
- `src/components/ui/`
- `supabase/migrations/`

### Full Suite Trigger
- Medium+ complexity
- `--related` flag unavailable or returns no tests
- Safety floor paths touched

### Test Commands
```bash
# Scoped (trivial/small)
npx vitest --related $(git diff --name-only HEAD) --run

# Full suite (medium+ or safety floor)
npx vitest run
npx tsc --noEmit
```

---

## Browser Verify

### When
UI changes at any complexity level.

### Protocol
1. Start dev server via wrapper script:
   ```bash
   uv run {shared_root}/scripts/dev_server.py start --profile {profile} --cwd {project_root}
   ```
2. Run health check:
   ```bash
   uv run {shared_root}/scripts/playwright_setup.py --cwd {project_root}
   uv run {plugin_root}/scripts/lib/browser_verify.py --cwd {project_root}
   ```
3. If JS errors: read screenshot, diagnose, fix (max 3 retries)
4. Server stays running for smoke test / visual comparison

### Skip When
No UI change in this iteration.

---

## Smoke Test

### When
Dev server is already running (browser verify or visual comparison started it).

### Protocol
Quick HTTP 200 check on affected routes. Nearly free since server is up.
```bash
curl -sf http://localhost:{port}/{route} > /dev/null
```

### Blocking
Yes — if a route returns non-200, stop and investigate before proceeding.

---

## Design Fidelity + Visual Comparison

### Layer A: Code-Level Fidelity Check
Before taking screenshots, compare implementation code against mockup HTML:
1. **Layout Structure** — grid/flex match mockup?
2. **Component Order** — same visual hierarchy?
3. **Component Types** — table vs card grid? Tabs vs accordion?
4. **shadcn Rules** — gap not space-y? Semantic colors? Proper card composition?

Fix mismatches in code first, re-run unit tests to verify no regressions.

### Layer B: Screenshot Comparison with Root-Cause Grouping
After code-level fidelity passes:

1. Run visual comparison:
   ```bash
   uv run {test_plugin_root}/scripts/lib/visual_compare.py \
     --cwd "{project_root}" --base-url "http://localhost:{port}"
   ```
   Use `--screen` flag to filter to specific screens when only certain screens are relevant:
   ```bash
   uv run ... --screen 01-login.html --screen 02-register.html
   ```

2. Group failures by root cause:
   | Root Cause | Example | Fix Scope |
   |---|---|---|
   | **Layout structure** | Sidebar vs header, missing nav | Layout components, shell |
   | **Colors/typography** | Wrong primary color, font | globals.css, CSS variables |
   | **Missing components** | No logo, no stats section | Individual pages/components |
   | **Spacing/shadows/radius** | Wrong padding, no shadow | Tailwind classes, globals.css |

3. Fix loop per group (max 3 retries per group, max 8 total):
   a. Read mockup + live screenshots for representative screen
   b. Inspect DOM/classes FIRST, then targeted fix
   c. Re-run visual_compare.py for this group's screens
   d. If fix works: commit with `fix(visual): {description}`
   e. If same issue persists after 3 attempts: **revert uncommitted changes**, park it with diagnosis

4. After all groups:
   - Report summary (fixed vs parked groups with diagnosis)
   - ASK user for direction on parked groups
   - Each successful group fix gets its own commit

> **Note on full pipeline:** In `/shipwright-build`, visual comparison runs per-section with root-cause grouping (same taxonomy, same fix loop). In `/shipwright-test`, visual comparison runs as a regressions-only safety net — it triages screens against `visual-build-report.json` and only fixes regressions (screens that passed in build but now fail) and persistent failures. Iterate does NOT use this two-phase split — visual comparison happens once (Step 12) with the full fix loop above.

### Escalation
If still mismatched after fix loops:
- Mark `visual_fidelity: "partial"` in test results
- Log warning with diagnosis per parked group, continue (do NOT hard-fail)

### Skip When
No UI structural change, text/color-only tweaks, logic-only fixes.

---

## Incremental E2E Test Update

### When
Medium+ features/changes that introduce new routes, new user flows, or significantly alter existing flows.

### Protocol
1. Read existing `e2e/flows/*.spec.ts` to understand current coverage
2. For new routes/flows: **prefer creating a new spec file** (e.g., `course-search.spec.ts`)
   - Do NOT inline-modify existing 500+ line specs (LLMs are error-prone at surgical TypeScript edits)
3. For modified flows with simple selector changes: update inline
4. Create new Page Object Models in `e2e/pages/` if needed
5. Run affected E2E tests:
   ```bash
   npx playwright test e2e/flows/{new-or-modified-spec}.spec.ts
   ```

### Skip When
- Trivial/small complexity
- No route/flow changes
- BUG type (unless fix changes expected E2E behavior)

---

## Dev Server Lifecycle

Always stop the dev server when done with UI verification:
```bash
uv run {shared_root}/scripts/dev_server.py stop --cwd {project_root}
```
