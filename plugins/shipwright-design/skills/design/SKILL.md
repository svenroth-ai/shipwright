---
name: shipwright-design
description: Generate UI mockups from IREB specs as standalone HTML. Screens + user flows, iteratable via chat. Use after /shipwright-project, before /shipwright-plan.
license: MIT
compatibility: Requires uv (Python 3.11+). No external dependencies.
---

# Shipwright Design Skill

Turn IREB specs into interactive HTML mockups before a single line of code is written.

---

## CRITICAL: First Actions

### A. Print Intro Banner

```
================================================================================
SHIPWRIGHT-DESIGN: UI Mockups
================================================================================
Generate HTML mockups from your specs.

Usage:
  /shipwright-design                              (analyze specs, generate all)
  /shipwright-design @designs/screens/02-dashboard.html  (iterate on one screen)
  /shipwright-design --upload                     (integrate uploaded designs)

Output:
  - designs/screens/*.html    (individual screen mockups)
  - designs/flows/*.html      (multi-screen user flows)
  - designs/design-manifest.md (screen registry)
================================================================================
```

### B. Detect Mode

**New Design Session** (no `designs/` directory):
- Read specs, generate from scratch
- Continue to Step 1

**Iterate on Existing** (@file argument pointing to HTML):
- Read the referenced HTML file
- Ask what to change
- Regenerate that screen only
- Skip to [Iteration Mode](#iteration-mode)

**Upload Integration** (`--upload` flag or `designs/uploads/` exists with files):
- Scan `designs/uploads/` for existing mockups
- Integrate into design-manifest.md
- Generate only missing screens
- Skip to [Upload Mode](#upload-mode)

### C. Discover Plugin Root

The SessionStart hook injects `SHIPWRIGHT_PLUGIN_ROOT=<path>`. Use it directly.

---

## Step 1: Read Specs

**Goal:** Understand what the app needs from the IREB specs.

Read these files:
- `shipwright_project_config.json` → profile name, scope
- `planning/project-manifest.md` → split overview
- `planning/*/spec.md` → all split specs (Functional Requirements)

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
   - **Custom** — Upload your own guidelines to `designs/uploads/`
   See [design-flavors.md](references/design-flavors.md) for details.
2. **Brand Character**: "What character should the app have?"
   - **A) Warm & Premium** — Earth tones, beige/cream backgrounds, elegant feel (think: luxury brands, boutique)
   - **B) Clean & Modern** — Whites, subtle grays, one accent color (think: Stripe, Linear)
   - **C) Bold & Energetic** — Vibrant colors, strong contrasts (think: Vercel, Figma)
   - **D) I have specific brand guidelines** → upload to `designs/uploads/`
   If brand tokens were extracted in Step 2.5, present them here as suggestion and let the user confirm or override.
   See [design-system-patterns.md](references/design-system-patterns.md) → "Character Palettes" for full token sets.
3. **Layout**: "Sidebar navigation or top navigation bar?"
4. **Existing designs**: "Do you have existing mockups or screenshots to include? Drop them in designs/uploads/ if so."
5. **Special UX**: "Any specific UX requirements? (dark mode, mobile-first, accessibility focus, etc.)"

**Palette derivation:** After the user picks a character (or confirms extracted tokens), derive the full palette automatically:

| Character | Background | Card Style | Accent Strategy |
|-----------|-----------|------------|-----------------|
| Warm & Premium | Cream/beige (#f5f0eb) | Shadow, no border, 12px radius | Brown/earth tones from bg |
| Clean & Modern | White (#ffffff) | 1px border + subtle shadow, 8px radius | Single saturated color |
| Bold & Energetic | White or dark | Strong shadow, 8px radius | 2-color system (primary + secondary) |

**Flavor resolution:** User choice > profile default (`design_system.name`) > `untitled-ui`.

**If custom flavor selected:** Prompt user to upload guidelines to `designs/uploads/`. Read them and use as the design foundation for all mockups. Skip generating new guidelines in Step 6.5 — instead, reference the uploaded file.

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

Pick these from the confirmed screen list. Save them to `designs/screens/` as usual.

```
AskUserQuestion:
  question: |
    I've generated 3 preview screens. Open them in your browser:
      - designs/screens/{login-screen}.html
      - designs/screens/{layout-screen}.html
      - designs/screens/{content-screen}.html

    Does the look and feel match what you want?
    Specifically: colors, font, card style, overall warmth?
```

**If adjustments needed:**
- Swap hex values / font / radius in the 3 preview files
- Do NOT regenerate from scratch — just update the CSS variables
- Re-ask for confirmation

**Only after user confirms** → proceed to Step 4 and generate the remaining screens using the validated palette.

---

## Step 4: Generate Screens

**Goal:** Create standalone HTML mockups.

For each confirmed screen:

1. Read the selected design flavor (from Step 3 or profile fallback)
2. Load component patterns from the flavor's reference file:
   - `untitled-ui` → [untitled-ui-components.md](references/untitled-ui-components.md)
   - `material-design` → [material-design-components.md](references/material-design-components.md)
   - `custom` → user's uploaded guidelines
3. Load layout patterns from [design-system-patterns.md](references/design-system-patterns.md)
4. Generate standalone HTML with inline CSS
5. Save to `designs/screens/{NN}-{name}.html`

**HTML Requirements:**
- Self-contained (no external dependencies except optional CDN font)
- Responsive (mobile + desktop)
- Realistic data (not "Lorem ipsum" — use plausible content)
- Interactive elements visible (buttons, inputs, dropdowns styled)
- Color scheme from user preferences or clean default

**Template:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{Screen Name} — {Project Name}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    /* Reset + variables + component styles inline */
  </style>
</head>
<body>
  <!-- Screen content -->
</body>
</html>
```

---

## Step 5: Generate User Flows

**Goal:** Create multi-screen flow mockups.

For each confirmed flow:

1. Combine relevant screens into a single HTML file
2. Add navigation between steps (tabs, stepper, or side-by-side)
3. Show the complete journey
4. Save to `designs/flows/{flow-name}.html`

Flows show screens in sequence with arrows or step indicators.

---

## Step 6: Write Design Manifest

**Goal:** Create the registry that downstream skills read.

Write `designs/design-manifest.md`:

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

## Design Decisions

- Layout: Sidebar navigation
- Colors: {primary}, {secondary}
- Font: Inter
```

---

## Step 6a: Generate Index Page

**Goal:** Create an interactive `designs/index.html` that lets you browse all screens and flows.

Save to `designs/index.html`. The page has two modes:

1. **Grid View** (default): All screens + flows as thumbnail cards with live iframe preview, grouped by split
2. **Viewer Mode**: Click a card or the "Viewer" button → full-size iframe with navigation

**Features:**
- Keyboard navigation: `←`/`→` prev/next, `Esc` back to grid
- Dropdown to jump to any screen directly
- Prev/Next buttons
- Screen counter (e.g. "5 / 25")
- Cards show: number, title, type badge (screen/flow), linked FRs
- Responsive (single column on mobile)

**Data structure:** Build a JavaScript `screens` array from the design manifest:

```javascript
const screens = [
  // Split 01 — {Split Name}
  { split: "01 — {Split Name}", num: "01", title: "{Screen Title}", file: "screens/01-{name}.html", frs: "FR-01.01, FR-01.02", type: "screen" },
  // ...
  // User Flows
  { split: "User Flows", num: "A", title: "{Flow Name}", file: "flows/{flow-name}.html", frs: "Screen1 → Screen2 → Screen3", type: "flow" },
];
```

**HTML structure:**

```html
<!-- Header: project title + Grid/Viewer toggle buttons -->
<div class="header">
  <h1><span>Shipwright</span> Design Review</h1>
  <div class="mode-toggle">
    <button id="btn-grid" class="active" onclick="showGrid()">Grid</button>
    <button id="btn-viewer" onclick="showViewer(currentIndex)">Viewer</button>
  </div>
</div>

<!-- Grid: cards with scaled iframe previews, grouped by split headings -->
<div class="grid-view" id="gridView"></div>

<!-- Viewer: toolbar (back, prev, next, title, counter, dropdown) + full iframe -->
<div class="viewer" id="viewer">
  <div class="kbd-hints"><!-- ← → Esc hints --></div>
  <div class="viewer-toolbar"><!-- nav buttons, title, dropdown --></div>
  <iframe class="viewer-frame" id="viewerFrame"></iframe>
</div>
```

**Card thumbnails:** Use iframes scaled to 50% (`transform: scale(0.5)` with `200%` width/height) inside a fixed-height container. Set `pointer-events: none` and `loading="lazy"` on grid iframes.

**Styling rules:**
- Use the same font as the mockups (from user preferences or Inter as default)
- Keep the index page visually neutral — it's a review tool, not part of the app design
- Primary accent color: `#4d65ff` (Shipwright blue) for active states and hover
- Cards: white background, subtle border, hover lift effect

**Important:** The index.html is self-contained (inline CSS + JS, no external dependencies except the optional font CDN). It references screen/flow files via relative paths.

---

## Step 6.5: Generate Visual Guidelines

**Goal:** Create a reusable design token document for shipwright-build.

**Skip if:** User uploaded existing visual guidelines in Step 3.

Based on interview answers and generated mockups, write `designs/visual-guidelines.md`:

```markdown
# Visual Guidelines

> Generated by shipwright-design | Profile: {profile_name}
> Reusable: upload this file to designs/uploads/ in future projects.

## Typography

- **Primary font:** {font_name} ({weights})
- **Monospace:** {mono_font} (for code blocks, if applicable)
- **Headings:** h1: {size} weight {weight}, h2: {size}, h3: {size}
- **Body:** {size}, line-height {lh}
- **Labels:** {size}, weight {weight}

## Colors

### Light Mode
| Role | Value | Usage |
|------|-------|-------|
| Background | {hex} | Page background |
| Foreground | {hex} | Primary text |
| Primary | {hex} | Brand color, CTAs, links |
| Secondary | {hex} | Secondary actions |
| Muted | {hex} | Subtle backgrounds, disabled states |
| Destructive | {hex} | Errors, delete actions |
| Border | {hex} | Dividers, card borders |

### Dark Mode (if applicable)
| Role | Value |
|------|-------|
| Background | {hex} |
| Foreground | {hex} |
| Primary | {hex} |

## Spacing & Layout

- **Base unit:** {value} (e.g., 4px)
- **Card padding:** {value}
- **Section gaps:** {value}
- **Page max-width:** {value}

## Border Radius

| Element | Radius |
|---------|--------|
| Cards | {value} |
| Buttons | {value} |
| Inputs | {value} |
| Avatars | full |

## Shadows

| Level | Usage |
|-------|-------|
| xs | Inputs, subtle elements |
| md | Cards (default) |
| lg | Dropdowns, popovers |
| xl | Modals |

## Component Patterns

- **Buttons:** {primary style description}
- **Cards:** {border, shadow, padding}
- **Navigation:** {sidebar/topnav, active state style}
- **Forms:** {label position, validation style}
- **Tables:** {header style, row hover, pagination}
```

**Sources for values:**
1. User's uploaded guidelines (custom flavor) → primary source
2. Interview answers (brand colors, font choice) → overrides
3. Selected flavor defaults (Untitled UI or Material Design tokens) → fallback
4. Mockups already generated (extract what was used) → verification

**This file is designed to be reusable.** The user can upload it to `designs/uploads/` in their next project and skip the design interview.

---

## Step 7: Update Specs (Optional)

**Goal:** Add UI References back to the IREB specs.

If specs have a "UI Requirements" section (Section 7), update it with:
- Screen references (which HTML file maps to which FRs)
- Layout decisions made during the design interview

This is optional — skip if specs don't have the UI Requirements section.

---

## Step 8: Completion

```
================================================================================
SHIPWRIGHT-DESIGN COMPLETE
================================================================================
Screens:     {N} generated
Flows:       {M} generated
Uploads:     {K} integrated
Guidelines:  designs/visual-guidelines.md {generated | from upload}
Manifest:    designs/design-manifest.md
Index:       designs/index.html

Open in browser:
  designs/index.html  (← start here — grid + viewer for all screens)

Next steps:
  1. Open designs/index.html in your browser to review all screens
  2. Iterate: /shipwright-design @designs/screens/02-dashboard.html
  3. Continue: /shipwright-plan @planning/01-auth/spec.md
================================================================================
```

---

## Iteration Mode

When invoked with a specific HTML file:

1. Read the HTML file
2. Ask: "What would you like to change?"
3. Apply changes
4. Regenerate the file
5. Update design-manifest.md if needed

Examples:
- "Make the header sticky"
- "Add a search bar to the table"
- "Change the primary color to blue"
- "Add a dark mode toggle"

---

## Upload Mode

When `designs/uploads/` contains files:

1. Scan directory for images (PNG, JPG), HTML files, and markdown files
2. **Check for visual guidelines:** If a `.md` file contains "Visual Guidelines" or design tokens (colors, typography, spacing), treat it as the project's design foundation
3. Present found files to user
4. Ask which screens they represent (for images/HTML)
5. Add to design-manifest.md with status "uploaded"
6. Generate only screens not covered by uploads
7. If visual guidelines found: use them for all generated screens, skip Step 6.5

---

## Reference Documents

- [design-flavors.md](references/design-flavors.md) — Design system flavor architecture and selection
- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns and component best practices
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](references/material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)
- [user-flow-patterns.md](references/user-flow-patterns.md) — Standard user flow templates
