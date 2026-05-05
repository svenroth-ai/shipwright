---
name: shipwright-design
description: "Generate UI mockups from IREB specs as standalone HTML. Screens + user flows, iteratable via chat.\nTRIGGER when: user wants to create UI mockups, design screens, generate HTML wireframes, create visual designs, design a user interface, preview a layout, create user flow diagrams, iterate on a screen design, or process design feedback.\nDO NOT TRIGGER when: user asks to implement code (/shipwright-build), run tests (/shipwright-test), fix a bug or change code (/shipwright-iterate), deploy (/shipwright-deploy), create requirements (/shipwright-project), or plan implementation details (/shipwright-plan)."
license: MIT
compatibility: Requires uv (Python 3.11+). No external dependencies.
---

# Shipwright Design Skill

Turn IREB specs into interactive HTML mockups before a single line of code is written.

---

## CRITICAL: First Actions

**Governing rules:** Read and follow `shared/constitution.md` (ALWAYS / ASK FIRST / NEVER boundaries).

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-DESIGN: UI Mockups
================================================================================
Generate HTML mockups from your specs.

Usage:
  /shipwright-design                                       (analyze specs, generate all)
  /shipwright-design @.shipwright/designs/screens/02-dashboard.html    (iterate on one screen)
  /shipwright-design @.shipwright/designs/design-feedback-round2.md    (process feedback file)
  /shipwright-design --upload                              (integrate uploaded designs)

Output:
  - .shipwright/designs/screens/*.html         (individual screen mockups)
  - .shipwright/designs/flows/*.html           (multi-screen user flows)
  - .shipwright/designs/index.html             (review viewer with feedback panel)
  - .shipwright/designs/design-manifest.md     (screen registry)
  - .shipwright/designs/visual-guidelines.md   (design tokens for build phase)
  - .shipwright/designs/design-handoff.md      (session handoff at finalization)
================================================================================
```

### B. Detect Mode

**New Design Session** (no `.shipwright/designs/` directory):
- Read specs, generate from scratch
- Continue to Step 1

**Iterate on Existing** (@file argument pointing to HTML):
- Read the referenced HTML file
- Ask what to change
- Regenerate that screen only
- Skip to [Iteration Mode](#iteration-mode)

**Upload Integration** (`--upload` flag or `.shipwright/designs/uploads/` exists with files):
- Scan `.shipwright/designs/uploads/` for existing mockups
- Integrate into design-manifest.md
- Generate only missing screens
- Skip to [Upload Mode](#upload-mode)

### C. Detect Invocation Mode

Determine if running within the pipeline or standalone:

1. Read `shipwright_run_config.json` (if exists)
2. **Pipeline mode**: `status == "in_progress"` AND `current_step == "design"`
   - Full pipeline integration (update orchestrator state, enforce gates)
3. **Standalone mode**: file missing OR `status == "complete"` OR `current_step != "design"`
   - Skip pipeline state updates (no `orchestrator.py update-step` calls)
   - Skip upstream completion checks
   - Still produce all artifacts (mockup HTML files, design-manifest.md)
   - If no `shipwright_project_config.json` exists, work with whatever specs are available in `.shipwright/planning/`. If none exist, ask user to describe what screens they need.
   - Print: `"Running in standalone mode — pipeline state will not be updated."`
4. If `status == "in_progress"` AND `current_step != "design"`:
   - Warn: `"Pipeline is in progress at step {current_step}. Running /shipwright-design out of sequence may cause issues."`
   - Ask user before continuing.

Store the detected mode in a variable `invocation_mode` = `"pipeline"` | `"standalone"` for use in later steps.

### D. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

### C2. Load Project Context

Read these files for stack and architecture context before generating mockups:

1. `CLAUDE.md` — stack context (influences component and layout choices)
2. `.shipwright/agent_docs/architecture.md` — app structure, component hierarchy (if exists)

If a file does not exist, skip it silently.

**Early tracking:** Mark design phase as in-progress in the project config (for session handoff):
```bash
# Read existing project config, add design_phase field
python3 -c "
import json; from pathlib import Path
p = Path('shipwright_project_config.json')
c = json.loads(p.read_text()) if p.exists() else {}
c['design_phase'] = 'in_progress'
p.write_text(json.dumps(c, indent=2) + '\n')
"
```

---

## Step 0: Phase Session Context Recovery

If your context contains a `=== SHIPWRIGHT-PIPELINE-CONTEXT ===` block (injected
by the SessionStart hook), you are part of an active `/shipwright-run` pipeline.
Parse `phaseTaskId` from that block and run as your very first action:

```bash
uv run "${SHIPWRIGHT_PLUGIN_ROOT}/../../shared/scripts/tools/get_phase_context.py" \
  --phase-task-id <phaseTaskId-from-context>
```

The tool prints structured JSON with `runId`, `phase`, `splitId`, `prerequisites`,
`runConditions`, and a `skill_artifacts_to_read` list. Read those artifacts
before proceeding so this phase session has full context for what came before.

If NO `PIPELINE-CONTEXT` block is present, this is a standalone invocation —
continue with Step 1 below as normal.

---

## Step 1: Read Specs

**Goal:** Understand what the app needs from the IREB specs.

Read these files:
- `shipwright_project_config.json` → profile name, scope
- `.shipwright/planning/project-manifest.md` → split overview
- `.shipwright/planning/*/spec.md` → all split specs (Functional Requirements)

Extract from each spec:
- All FRs (Functional Requirements) with their IDs
- Any UI-related keywords (see screen type detection below)
- In/Out of Scope boundaries

---

## Step 2: Detect Screen Types

**Goal:** Map FRs to screen types automatically.

See [design-system-patterns.md](references/design-system-patterns.md) for patterns.

Scan each FR for keywords and map to screen types:

| FR Keywords | Screen Type | Default Layout |
|-------------|-----------|---------------|
| login, authenticate, sign in, register | Auth | Centered card with form |
| dashboard, overview, home, summary | Dashboard | Sidebar + header + content grid |
| list, browse, search, filter, table | List/Table | Filter bar + data table + pagination |
| create, add, edit, form, input, new | Form | Form sections + validation + actions |
| settings, profile, preferences, account | Settings | Tabs + form sections |
| detail, view, show, inspect | Detail | Content sections + actions bar |
| onboarding, wizard, setup, welcome | Onboarding | Step-by-step centered flow |
| notification, alert, inbox, messages | Notifications | List with badges + detail panel |

Build a proposed screen list from this analysis.

---

## Step 2.5: Brand Extraction

**Goal:** Auto-extract design tokens from the user's existing website before asking design questions.

**Trigger:** If the user has an existing website (mentioned in project interview, requirements, or `shipwright_project_config.json`).

**Skip if:** No existing website is known. Proceed directly to Step 3.

```
1. WebFetch the URL
2. Extract from HTML/CSS:
   - Fonts: <link> tags (Google Fonts), CSS font-family declarations
   - Colors: CSS custom properties, most frequent bg/text/accent colors
   - Background style: white vs. cream/beige vs. dark
   - Card style: border-based vs. shadow-based
   - Border radius patterns
3. Present findings:
   "I found these design tokens from your website:
    - Font: {font} ({weights})
    - Background: {hex} ({description})
    - Text: {hex}
    - Accent: {hex} ({description})
    - Cards: {style}, {radius} radius
    Shall I use these as the foundation?"
4. User confirms or adjusts
```

Confirmed tokens carry forward into Step 3 as defaults — the user can still override them.

---

## Step 3: Design Interview (3-5 questions)

**Goal:** Refine the proposal with user preferences. Quick, targeted.

```
AskUserQuestion:
  question: "Quick design questions before I generate mockups:"
```

**Questions to ask:**

1. **Design System Flavor**: "Which design system should I use as the visual foundation?"
   - **Untitled UI** — Clean, professional SaaS style (default)
   - **Material Design 3** — Google's design system, great for consumer apps
   - **Custom** — Upload your own guidelines to `.shipwright/designs/uploads/`
   See [design-flavors.md](references/design-flavors.md) for details.
2. **Brand Character**: "What character should the app have?"
   - **A) Warm & Premium** — Earth tones, beige/cream backgrounds, elegant feel (think: luxury brands, boutique)
   - **B) Clean & Modern** — Whites, subtle grays, one accent color (think: Stripe, Linear)
   - **C) Bold & Energetic** — Vibrant colors, strong contrasts (think: Vercel, Figma)
   - **D) I have specific brand guidelines** → upload to `.shipwright/designs/uploads/`
   If brand tokens were extracted in Step 2.5, present them here as suggestion and let the user confirm or override.
   See [design-system-patterns.md](references/design-system-patterns.md) → "Character Palettes" for full token sets.
3. **Layout**: "Sidebar navigation or top navigation bar?"
4. **Existing designs**: "Do you have existing mockups or screenshots to include? Drop them in .shipwright/designs/uploads/ if so."
5. **Special UX**: "Any specific UX requirements? (dark mode, mobile-first, accessibility focus, etc.)"

**Palette derivation:** After the user picks a character (or confirms extracted tokens), derive the full palette automatically:

| Character | Background | Card Style | Accent Strategy |
|-----------|-----------|------------|-----------------|
| Warm & Premium | Cream/beige (#f5f0eb) | Shadow, no border, 12px radius | Brown/earth tones from bg |
| Clean & Modern | White (#ffffff) | 1px border + subtle shadow, 8px radius | Single saturated color |
| Bold & Energetic | White or dark | Strong shadow, 8px radius | 2-color system (primary + secondary) |

**Flavor resolution:** User choice > profile default (`design_system.name`) > `untitled-ui`.

**If custom flavor selected:** Prompt user to upload guidelines to `.shipwright/designs/uploads/`. Read them and use as the design foundation for all mockups. Skip generating new guidelines in Step 6.5 — instead, reference the uploaded file.

**Then present the proposed screen list:**

```
Based on your specs, I'll generate these screens:

Screens:
  01. Login (FR-01.01, FR-01.02)
  02. Dashboard (FR-02.01)
  03. Task List (FR-02.02, FR-02.03)
  04. Task Form (FR-02.04)
  05. Settings (FR-03.01)

User Flows:
  A. Auth Flow: Login → Register → Verify → Dashboard
  B. CRUD Flow: List → Detail → Edit → Delete Confirm

Add, remove, or modify?
```

---

## Step 3.5: Design Preview

**Goal:** Validate the chosen palette and style on a small sample before generating all screens.

**After** the screen list is confirmed in Step 3, generate exactly 3 preview screens:

1. **Auth/Login screen** — Brand first impression, centered card layout
2. **Main layout screen** — Sidebar + content (or top nav), shows navigation feel
3. **One content-heavy screen** — Detail page with cards, buttons, and text hierarchy

Pick these from the confirmed screen list. Save them to `.shipwright/designs/screens/` as usual.

```
AskUserQuestion:
  question: |
    I've generated 3 preview screens. Open them in your browser:
      - .shipwright/designs/screens/{login-screen}.html
      - .shipwright/designs/screens/{layout-screen}.html
      - .shipwright/designs/screens/{content-screen}.html

    Does the look and feel match what you want?
    Specifically: colors, font, card style, overall warmth?
```

**If adjustments needed:**
- Swap hex values / font / radius in the 3 preview files
- Do NOT regenerate from scratch — just update the CSS variables
- Re-ask for confirmation

**Only after user confirms** → proceed to Step 3.7 (Chrome Definition) and then Step 4.

---

## Step 3.7: Generate Chrome Definition

**Goal:** Create a single source of truth for all shared UI elements (sidebar, topbar, footer, branding) so every screen has identical chrome.

**After** the design preview is confirmed in Step 3.5:

1. Read [snippets-chrome.md](references/snippets-chrome.md) for the chrome definition template
2. From the confirmed screen list (Step 3) and design choices, determine:
   - **App branding:** name + logo SVG icon (24x24 stroke icon)
   - **Navigation items:** one per screen that appears in nav. Include label, SVG icon path, target file name, section (main vs. bottom). Order: overview first, settings last.
   - **Topbar config:** search placeholder text, notification bell (yes/no), user avatar (yes/no)
   - **User info:** realistic name, initials, and role for the app domain
   - **Footer** (if the layout uses one)
3. Write `.shipwright/designs/chrome-definition.md` containing:
   - Filled data tables (the source of truth)
   - **Resolved HTML blocks** — fully expanded sidebar, topbar, top-nav, and footer HTML with all real labels, icons, and content. No `{{PLACEHOLDERS}}` remaining.
4. Present the navigation structure for user confirmation:

```
AskUserQuestion:
  question: |
    Navigation structure for all screens:

      {icon} Dashboard        ← active on: 02-dashboard.html
      {icon} Projects         ← active on: 03-projects.html
      {icon} Tasks            ← active on: 04-tasks.html
      ─────────────
      {icon} Settings         ← active on: 08-settings.html

    App: "{App Name}" with {logo description}
    User: "{User Name}" ({Initials}), {Role}

    Adjust navigation items, order, or labels?
```

5. After confirmation, the chrome definition is locked. All screens in Step 4 copy from it.

**Important:** This step runs ONCE per design session. If chrome needs changes later, see [Chrome Change Propagation](#chrome-change-propagation).

---

## Step 4: Generate Screens

**Goal:** Create standalone HTML mockups using the snippet assembly system for speed.

### Assembly Process

For each confirmed screen, **assemble from pre-built snippets** rather than writing from scratch:

1. **Page Shell** — Start with the Page Shell from [snippets-layout.md](references/snippets-layout.md). Replace `{{FONT_FAMILY}}` with the selected font.
2. **CSS Variables** — Copy the matching `:root` block from [snippets-variables.md](references/snippets-variables.md) based on the flavor × character chosen in Step 3. If brand extraction was done (Step 2.5), override specific variables with extracted values.
3. **Layout** — Pick the appropriate layout snippet from [snippets-layout.md](references/snippets-layout.md):
   - Auth screens → Layout C (Centered Card)
   - Dashboard/admin/list/detail/settings → Layout A (Sidebar + Content)
   - Public/marketing pages → Layout B (Top Navigation)
   - Always include the shared Button Styles block.
4. **Shared Chrome** — Read `.shipwright/designs/chrome-definition.md` (generated in Step 3.7). Copy the resolved HTML blocks **verbatim**:
   - **Layout A screens:** Copy the **Resolved Sidebar Block** into `<aside class="sidebar">`. Copy the **Resolved Topbar Block** into `<header class="topbar">`. Change ONLY which `.nav-item` has `class="nav-item active"` to match the current screen.
   - **Layout B screens:** Copy the **Resolved Top-Nav Block** into `<header class="topnav">`. Change ONLY which `.topnav-link` has `class="topnav-link active"` to match the current screen.
   - **Layout C screens:** Copy only the app name and logo SVG from the chrome definition into `.auth-logo`.
   - Do NOT improvise nav items, icons, labels, or user info. The `chrome-definition.md` is authoritative.
5. **Components** — Fill the layout's **content area** with component snippets from [snippets-components.md](references/snippets-components.md):
   - Tables, card grids, forms, stats rows, modals, tabs, badges, etc.
   - Pick components that match the screen type and FRs.
6. **Customize** — Replace remaining `{{PLACEHOLDERS}}` in the **content area only** (page title, subtitle, action labels, component data):
   - Realistic data (not "Lorem ipsum" — use plausible content)
   - Screen-specific labels, field names, table data
   - FR-specific functionality visible in the UI
   - SVG stroke icons (no emojis — premium, abstract feel)
   - Do NOT modify the sidebar, topbar, or footer — those come from `chrome-definition.md`.
7. **Unique elements** — Write from scratch ONLY for content that doesn't match any snippet (custom visualizations, domain-specific widgets, unique layouts).
8. **Save** to `.shipwright/designs/screens/{NN}-{name}.html`

### Design Context References

For understanding design intent and making good composition decisions, consult:
- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns, component patterns, color system, character palettes
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](references/material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)

### HTML Requirements
- Self-contained (no external dependencies except optional CDN font)
- Responsive (mobile + desktop)
- Realistic data (plausible content for the domain)
- Interactive elements visible (buttons, inputs, dropdowns styled)
- All icons: SVG stroke icons (no emojis)
- Color scheme from CSS variables (set once, applied everywhere)

---

## Step 5: Generate User Flows

**Goal:** Create multi-screen flow mockups.

For each confirmed flow:

1. Combine relevant screens into a single HTML file
2. Add navigation between steps (tabs, stepper, or side-by-side)
3. Show the complete journey
4. Save to `.shipwright/designs/flows/{flow-name}.html`

Flows show screens in sequence with arrows or step indicators.

---

## Step 6: Write Design Manifest

**Goal:** Create the registry that downstream skills read.

Write `.shipwright/designs/design-manifest.md`:

```markdown
# Design Manifest

> Generated by shipwright-design | Profile: {profile_name}

## Screens

| # | Screen | File | Status | Linked FRs |
|---|--------|------|--------|-----------|
| 01 | Login | screens/01-login.html | complete | FR-01.01, FR-01.02 |
| 02 | Dashboard | screens/02-dashboard.html | complete | FR-02.01 |

## User Flows

| Flow | File | Screens | Status |
|------|------|---------|--------|
| Auth | flows/auth-flow.html | 01 → Register → Verify → 02 | complete |

## Uploads

| File | Type | Integrated |
|------|------|-----------|
| uploads/existing-header.png | image | yes |

## Shared Chrome

- Chrome definition: `chrome-definition.md`
- Layout: {Sidebar / Top Nav}
- Nav items: {count}

## Design Decisions

- Layout: Sidebar navigation
- Colors: {primary}, {secondary}
- Font: Inter
```

---

## Step 6a: Generate Review Viewer (Index Page)

**Goal:** Create `.shipwright/designs/index.html` — a full review tool with grid view, fullscreen viewer, and integrated feedback panel.

### How to Generate

1. Read the complete template from [review-viewer-template.md](references/review-viewer-template.md)
2. Read `.shipwright/designs/visual-guidelines.md` → extract primary color, font, background, surface, text, muted, border colors, and border radius
3. Read `.shipwright/designs/design-manifest.md` → build the `screens` JavaScript array
4. Replace all `{{PLACEHOLDERS}}` in the template with project-specific values
5. Write to `.shipwright/designs/index.html`

### Placeholder Mapping

| Placeholder | Source |
|-------------|--------|
| `{{PROJECT_NAME}}` | `shipwright_project_config.json` → `project_name` |
| `{{FONT_FAMILY}}` | `visual-guidelines.md` → primary font |
| `{{FONT_URL}}` | Google Fonts URL for that font |
| `{{COLOR_PRIMARY}}` | `visual-guidelines.md` → Primary color |
| `{{COLOR_BG}}` | `visual-guidelines.md` → Background |
| `{{COLOR_SURFACE}}` | `visual-guidelines.md` → Surface/Card background |
| `{{COLOR_TEXT}}` | `visual-guidelines.md` → Foreground/Text |
| `{{COLOR_MUTED}}` | `visual-guidelines.md` → Muted text |
| `{{COLOR_BORDER}}` | `visual-guidelines.md` → Border |
| `{{RADIUS}}` | `visual-guidelines.md` → Card border radius |
| `{{PROJECT_SLUG}}` | `shipwright_project_config.json` → `project_name`, lowercase, spaces→hyphens |
| `{{SCREENS_ARRAY}}` | Built from `design-manifest.md` — see template for format |

### Features (built into template)

- **Grid View**: Thumbnail cards with scaled iframe previews, grouped by split, feedback dot indicators
- **Viewer Mode**: Full-size iframe with toolbar (prev/next, dropdown navigator, counter)
- **Feedback Panel**: 340px right side, toggleable, with status buttons (Approved/Changes/Rejected), textarea with auto-save (500ms debounce), previous rounds history
- **Keyboard navigation**: `←` `→` navigate, `Esc` grid, `F` toggle feedback
- **localStorage persistence**: Feedback, round number, and history survive browser refreshes
- **Export**: Generates `design-feedback-roundN.md` via File System Access API save dialog + fallback download
- **Theming**: Viewer uses the project's own design tokens — feels native to the project

**Important:** The index.html is self-contained (inline CSS + JS, no external dependencies except the optional font CDN). It references screen/flow files via relative paths.

---

## Step 6.5: Generate Visual Guidelines

**Goal:** Create a reusable design token document for shipwright-build.

**Skip if:** User uploaded existing visual guidelines in Step 3.

See `references/visual-guidelines-template.md` for the complete template and value sourcing rules.

---

## Step 7: Update Specs (Optional)

**Goal:** Add UI References back to the IREB specs.

If specs have a "UI Requirements" section (Section 7), update it with:
- Screen references (which HTML file maps to which FRs)
- Layout decisions made during the design interview

This is optional — skip if specs don't have the UI Requirements section.

---

## Step 8: Completion & Review Instructions

Print the completion summary followed by review instructions:

```
================================================================================
SHIPWRIGHT-DESIGN: Generation Complete
================================================================================
Screens:     {N} generated
Flows:       {M} generated
Uploads:     {K} integrated
Guidelines:  .shipwright/designs/visual-guidelines.md {generated | from upload}
Manifest:    .shipwright/designs/design-manifest.md
Index:       .shipwright/designs/index.html (with review viewer + feedback panel)
================================================================================

================================================================================
REVIEW YOUR SCREENS
================================================================================
1. Open .shipwright/designs/index.html in your FILE EXPLORER (not the IDE)
   → The file opens in your default browser with the review viewer

2. Use Grid View or Viewer Mode to review each screen
   → Keyboard: ← → navigate, Esc for grid, F for feedback panel

3. For each screen, set a status:
   → Approved / Changes Requested / Rejected
   → Add comments describing what to change

4. When done, click "Export Feedback"
   → A save dialog opens — save the file into the /designs folder
================================================================================
```

**Generate screen-routes.json** for design fidelity testing (`/shipwright-test --design-fidelity`):

After all screens are generated, create `.shipwright/designs/screen-routes.json` mapping each mockup to its app route:

```json
{
  "01-login.html": "/login",
  "02-signup.html": "/signup",
  "03-public-layout.html": "/",
  "04-admin-layout.html": "/admin/dashboard",
  "08-student-dashboard.html": "/dashboard"
}
```

Derive routes from the screen content (look at navigation links, page titles, form actions). Only include screens that map to a specific route (skip flow diagrams, modals shown within other pages, etc.).

Then immediately proceed to **Step 8.5**.

---

## Step 8.5: Design Review Loop

See `references/review-loop.md` for the complete review loop flow (Option A: Finalize with FR-Coverage Gate + Spec Backflow, Option B: Process Feedback, Option C: Pause, Decision Log Format, Flow Diagram).

---

## Step 9: Finalization (iterate 12.2 — Minimum Phase Completion Canon)

**Run this only after Step 8.5 Option A approves the design** (all screens
signed off, FR coverage satisfied, spec backflow complete). The design
plugin had zero finalization calls before iterate 12.2; this step brings
it to full canon coverage (C1/C2/C3/C5 + `phase_history`). **C4 is
skipped by design policy** — design is a transformation of an existing
spec, not a decision-taking phase.

Set `SHIPWRIGHT_RUN_ID` at the top of this step so the canon-marker
handoff (C3) and `phase_history` append share one run id. If the env
var is unset, `generate_session_handoff.py --canon-marker` logs a
stderr warning and writes the handoff without the marker (safe
degrade — the Stop hook then regenerates normally at turn end).

```bash
# If the orchestrator didn't already set it, derive one here:
export SHIPWRIGHT_RUN_ID="design-$(date +%Y%m%d-%H%M%S)"

# C1 — Record phase completion event (idempotent — skips if recorded).
uv run "{shared_root}/scripts/tools/record_event.py" \
  --project-root "$(pwd)" --type phase_completed --phase design \
  --detail "{N} screens, {M} flows"

# C2 — Update delivery dashboard.
uv run "{shared_root}/scripts/tools/update_build_dashboard.py" \
  --project-root "$(pwd)" --phase design --detail "{N} screens, {M} flows" \
  --session-id "{SHIPWRIGHT_SESSION_ID}"

# C3 — Canon-marked session handoff (iterate 12.1 conditional stop-hook skip).
uv run "{shared_root}/scripts/tools/generate_session_handoff.py" \
  --project-root "$(pwd)" --canon-marker --phase design \
  --reason "design complete: {N} screens, {M} flows"

# C4 — SKIPPED by policy (design is not a decision-taking phase).

# C5 — Append CHANGELOG [Unreleased] entry via helper (Keep-a-Changelog,
# dedupe, atomic). Category "Added" — designs are user-visible artifacts.
uv run "{shared_root}/scripts/tools/append_changelog_entry.py" \
  --project-root "$(pwd)" \
  --category Added \
  --entry "Design: {N} screens + {M} flows added"

# phase_history — audit trail in shipwright_run_config.json::phase_history[design]
uv run "{shared_root}/scripts/tools/append_phase_history.py" \
  --project-root "$(pwd)" --phase design --run-id "{SHIPWRIGHT_RUN_ID}" \
  --entry-json '{"screens":{N},"flows":{M},"outcome":"approved"}'

# Mark design phase complete. _validate_design() now runs the modular
# design_checks verifier (manifest screens exist, FR coverage, canon,
# phase_history) — missing artifacts block this call via ask-level issues.
uv run "{plugin_root}/../../plugins/shipwright-run/scripts/lib/orchestrator.py" \
  update-step --project-root "$(pwd)" --step design --status complete
```

Where `{shared_root}` = `{plugin_root}/../../shared`.

---

## Iteration Mode

### Mode 1: Iterate on a single screen

When invoked with a specific HTML file (e.g. `@.shipwright/designs/screens/02-dashboard.html`):

1. Read the HTML file
2. Ask: "What would you like to change?"
3. If the change affects shared chrome (nav, header, footer, branding) → follow [Chrome Change Propagation](#chrome-change-propagation) instead
4. Apply changes using the snippet assembly approach where applicable
5. Re-read `.shipwright/designs/chrome-definition.md` and verify the chrome blocks are still copied verbatim (with correct active state)
6. Regenerate the file
7. Update design-manifest.md if needed
8. Regenerate index.html
9. → Enter **Step 8.5** (review loop)

### Mode 2: Process feedback file

When invoked with a feedback file (e.g. `@.shipwright/designs/design-feedback-round2.md`):

1. Read the feedback file
2. For each screen with status **CHANGES** or **REJECTED**:
   - Read the current HTML file
   - Apply the requested changes from the feedback text
   - Regenerate the screen using snippet assembly
3. Identify and apply global changes to all affected screens
4. Update design-manifest.md (status → `revised-rN`)
5. Regenerate index.html
6. Run Spec Backflow (partial)
7. Report what was changed
8. → Enter **Step 8.5** (review loop)

### Chrome Change Propagation

If **any** iteration (Mode 1 or Mode 2) changes a shared chrome element — navigation items, labels, icons, header, footer, or branding:

1. **Update `.shipwright/designs/chrome-definition.md` first** — edit the data tables AND regenerate the resolved HTML blocks
2. **Identify all affected screens** — every screen using the same layout (A or B) must be updated
3. **Re-copy the chrome blocks** — replace the sidebar/topbar/footer in each affected screen with the updated resolved blocks (preserve the correct `active` class per screen)
4. **Report** which screens were updated and what changed

> **Rule:** Never change chrome in a single screen without updating `chrome-definition.md`. The definition file is always authoritative.

---

## Upload Mode

When `.shipwright/designs/uploads/` contains files:

1. Scan directory for images (PNG, JPG), HTML files, and markdown files
2. **Check for visual guidelines:** If a `.md` file contains "Visual Guidelines" or design tokens (colors, typography, spacing), treat it as the project's design foundation
3. Present found files to user
4. Ask which screens they represent (for images/HTML)
5. Add to design-manifest.md with status "uploaded"
6. Generate only screens not covered by uploads
7. If visual guidelines found: use them for all generated screens, skip Step 6.5

---

## Reference Documents

### Snippet System (primary — use for screen generation)
- [snippets-layout.md](references/snippets-layout.md) — Copy-paste HTML/CSS layout blocks (Page Shell, Sidebar, Top Nav, Centered Card, Buttons)
- [snippets-components.md](references/snippets-components.md) — Copy-paste HTML/CSS component blocks (Table, Card Grid, Form, Stats, Modal, Tabs, Badges, Empty State, Breadcrumbs, Detail, Notifications)
- [snippets-variables.md](references/snippets-variables.md) — Complete CSS `:root` variable blocks for each flavor × character combination
- [review-viewer-template.md](references/review-viewer-template.md) — Complete HTML template for .shipwright/designs/index.html (review viewer with feedback panel)

### Design Context (secondary — consult for design decisions and understanding)
- [design-flavors.md](references/design-flavors.md) — Design system flavor architecture and selection
- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns, component patterns, color system, character palettes
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](references/material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)
- [user-flow-patterns.md](references/user-flow-patterns.md) — Standard user flow templates
