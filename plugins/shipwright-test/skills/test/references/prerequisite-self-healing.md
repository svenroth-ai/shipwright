# Prerequisite Self-Healing (First Actions step B4)

Before determining test strategy, check for missing artifacts and auto-generate where possible.
This follows the constitution rule: **never silently skip a test layer due to missing prerequisites.**

**1. `dev_url` missing from `shipwright_build_config.json`?**
   - Search `CLAUDE.md` for `PORT=` references or port numbers
   - Search `package.json` scripts for `--port` flags
   - If found: add `"dev_url": "http://localhost:{port}"` to `shipwright_build_config.json`
   - If not found: **ASK** user "What port does your dev server run on?"

**2. `.shipwright/designs/visual-guidelines.md` missing but `.shipwright/designs/screens/` has HTML files?**
   - Read CSS `:root` variables from the first mockup HTML file
   - Extract color, typography, spacing, radius, and shadow tokens
   - Generate `.shipwright/designs/visual-guidelines.md` using the template format
   - Commit: `chore(test): auto-generate visual-guidelines.md from mockup CSS`

**3. `.shipwright/designs/screen-routes.json` missing but mockups + router exist?**
   - List mockup HTML files in `.shipwright/designs/screens/`
   - Read router config (`src/router.tsx`, `src/App.tsx`, or framework equivalent)
   - Generate `.shipwright/designs/screen-routes.json` mapping each mockup to its route
   - Commit: `chore(test): auto-generate screen-routes.json from mockups + router`

**4. `.shipwright/planning/claude-plan-e2e.md` missing but `.shipwright/designs/screen-routes.json` exists?**
   - Generate a minimal E2E test plan with one flow per major screen/route
   - Include page object model suggestions and test data structure
   - Commit: `chore(test): auto-generate E2E test plan from screen routes`

**5. `playwright.config.ts` missing?**
   - Run `playwright_setup.py` (creates config, installs browser)
   - If `dev_url` was resolved in step 1: substitute the correct port in the config

**Print diagnostic summary:**
```
PREREQUISITE CHECK:
  dev_url:             v http://localhost:3847 (from CLAUDE.md)
  visual-guidelines:   v auto-generated from mockup CSS
  screen-routes.json:  v auto-generated (11 screens -> 5 routes)
  E2E test plan:       v auto-generated (6 flows)
  playwright.config:   v created with port 3847
```

Only **ASK** the user if auto-generation is not possible (no source data to derive from).
Each auto-generated artifact gets its own commit.
