# Browser Verify (MANDATORY when frontend files changed)

Detail for Kern Step 4.5.

**Goal:** Visual sanity check after implementation — Replit-style browser preview.

**Gate semantics:** Browser Verify is MANDATORY whenever this section's diff
touches any frontend file. Missing `dev_server` config is a RESOLUTION problem,
not a skip trigger.

## Skip Trigger

Skip this step ONLY if the diff touches no frontend file extensions. Run the detector:

```bash
uv run "{shared_root}/scripts/lib/detect_frontend_changes.py" \
  --cwd {project_root} --since "$(git merge-base HEAD {branch_name})"
```

If `has_frontend_changes == false`, skip. Otherwise Browser Verify is mandatory.

## Prerequisite Self-Healing (before running — do NOT skip)

- If profile has no `dev_server` config but `shipwright_build_config.json` has `dev_url`: use that URL.
- If neither: autodetect via `package.json` scripts (Vite 5173 / Next 3000 / Astro 4321).
- If `.shipwright/designs/visual-guidelines.md` missing but mockups exist in `.shipwright/designs/screens/`: auto-generate from CSS `:root` variables (same derivation as test phase Step B3).
- If ALL resolution paths fail: escalate via AskUserQuestion with the list of changed frontend files. Do NOT silently skip.

## Flow

1. **Ensure Playwright is set up:**

```bash
uv run "{shared_root}/scripts/playwright_setup.py" --cwd {project_root}
```

2. **Start dev server** (if not already running):

```bash
uv run "{shared_root}/scripts/dev_server.py" start --profile {profile} --cwd {project_root}
```

If profile has no `dev_server` config: check `shipwright_build_config.json` for `dev_url` and start on that port. Then fall through to autodetect before escalating.

3. **Run browser verify:**

```bash
uv run "{shared_root}/scripts/browser_verify.py" --cwd {project_root}
```

4. **Evaluate result:**
   - **Success** (no console errors, page loads): Continue to Step 5
   - **Failure**: Invoke the `browser-fixer` subagent

5. **Auto-fix loop** (max 3 retries, follow [debugging-protocol.md](debugging-protocol.md)):
   a. Read the screenshot image at `{project_root}/e2e/screenshots/browser-verify.png`
   b. **Root-cause analysis:** Before each fix, identify what's wrong (Phase 1) and state hypothesis (Phase 3)
   c. Spawn `browser-fixer` subagent with:
      - Screenshot image path
      - Console errors from result JSON
      - DOM snippet from result JSON
      - Recently changed files (from `git diff --name-only`)
   d. Apply the recommended fix
   e. Re-run browser verify
   f. **If same root cause as previous attempt** -> change approach (different fix strategy, not same fix again)
   g. If still failing after 3 retries, present findings to user via AskUserQuestion with diagnosis summary

6. **Visual guidelines check** (if `.shipwright/designs/visual-guidelines.md` exists):
   When reviewing the screenshot, also check against the visual guidelines:
   - Brand colors match (primary, background, accent)
   - Typography consistent (font family, sizes, weights)
   - Component patterns followed (card shadows, button styles, border radius)

**Note:** The dev server stays running between sections. It gets stopped by shipwright-test or at the end of all sections.
