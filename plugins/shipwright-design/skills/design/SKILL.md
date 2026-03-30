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
  /shipwright-design                                       (analyze specs, generate all)
  /shipwright-design @designs/screens/02-dashboard.html    (iterate on one screen)
  /shipwright-design @designs/design-feedback-round2.md    (process feedback file)
  /shipwright-design --upload                              (integrate uploaded designs)

Output:
  - designs/screens/*.html         (individual screen mockups)
  - designs/flows/*.html           (multi-screen user flows)
  - designs/index.html             (review viewer with feedback panel)
  - designs/design-manifest.md     (screen registry)
  - designs/visual-guidelines.md   (design tokens for build phase)
  - designs/design-handoff.md      (session handoff at finalization)
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
4. **Components** — Fill the layout's content area with component snippets from [snippets-components.md](references/snippets-components.md):
   - Tables, card grids, forms, stats rows, modals, tabs, badges, etc.
   - Pick components that match the screen type and FRs.
5. **Customize** — Replace all `{{PLACEHOLDERS}}` with screen-specific content:
   - Realistic data (not "Lorem ipsum" — use plausible content)
   - Screen-specific labels, field names, nav items
   - FR-specific functionality visible in the UI
   - SVG stroke icons (no emojis — premium, abstract feel)
6. **Unique elements** — Write from scratch ONLY for content that doesn't match any snippet (custom visualizations, domain-specific widgets, unique layouts).
7. **Save** to `designs/screens/{NN}-{name}.html`

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

## Step 6a: Generate Review Viewer (Index Page)

**Goal:** Create `designs/index.html` — a full review tool with grid view, fullscreen viewer, and integrated feedback panel.

### How to Generate

1. Read the complete template from [review-viewer-template.md](references/review-viewer-template.md)
2. Read `designs/visual-guidelines.md` → extract primary color, font, background, surface, text, muted, border colors, and border radius
3. Read `designs/design-manifest.md` → build the `screens` JavaScript array
4. Replace all `{{PLACEHOLDERS}}` in the template with project-specific values
5. Write to `designs/index.html`

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

## Step 8: Completion & Review Instructions

Print the completion summary followed by review instructions:

```
================================================================================
SHIPWRIGHT-DESIGN: Generation Complete
================================================================================
Screens:     {N} generated
Flows:       {M} generated
Uploads:     {K} integrated
Guidelines:  designs/visual-guidelines.md {generated | from upload}
Manifest:    designs/design-manifest.md
Index:       designs/index.html (with review viewer + feedback panel)
================================================================================

================================================================================
REVIEW YOUR SCREENS
================================================================================
1. Open designs/index.html in your FILE EXPLORER (not the IDE)
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

Then immediately proceed to **Step 8.5**.

---

## Step 8.5: Design Review Loop

**Goal:** Wait for the user's review, then process feedback or finalize.

Present an `AskUserQuestion` dialog that stays open while the user reviews in the browser:

```
AskUserQuestion:
  question: |
    Take your time reviewing in the browser. When you're done, choose:
  options:
    A) All screens approved — finalize design phase
       → Updates specs & decisions, writes session handoff, ready for /shipwright-plan
    B) Feedback ready — I've reviewed and exported the feedback file
       → Reads designs/design-feedback-roundN.md, revises flagged screens, then asks again
    C) Pause for now
       → State is saved, continue later with /shipwright-design
```

### Option A — Finalize

**FR-Coverage Gate** (verify before finalizing):
- Read the spec's Functional Requirements that have UI relevance
- Verify each UI-relevant FR has at least one screen in `designs/design-manifest.md`
- Verify `designs/visual-guidelines.md` exists and contains: Colors, Typography, Spacing
- If uncovered FRs or missing guidelines → fix before proceeding to Spec Backflow

1. **Spec Backflow (full)**:

   | Artifact | What to update |
   |----------|---------------|
   | `designs/visual-guidelines.md` | Final color values, token changes |
   | `designs/design-manifest.md` | Final screen titles, statuses |
   | `designs/index.html` | Regenerate screens array |
   | `planning/*/spec.md` Section 7 (UI Requirements) | Add screen references per FR: "FR-01.09 → screens/03-dashboard.html" |
   | `planning/*/spec.md` Section 5 (Functional Requirements) | Add `[UI: Screen #NN]` cross-reference tags to FRs that have mockups |
   | `agent_docs/decision_log.md` | All final design decisions (DR-NNN format, see below) |
   | `shipwright_project_config.json` | Set `design_phase: "complete"` |

2. **Write session handoff** to `designs/design-handoff.md`:

   ```markdown
   # Design Phase — Session Handoff

   > Completed: {date}
   > Rounds: {N}
   > Screens: {total} ({approved} approved, {revised} revised)

   ## Status
   All screens approved. Ready for implementation planning.

   ## Key Design Decisions
   {List of DR-NNN decisions made during design phase}

   ## Files for Implementation
   - Visual system: `designs/visual-guidelines.md`
   - Screen registry: `designs/design-manifest.md`
   - Screen mockups: `designs/screens/*.html`
   - User flows: `designs/flows/*.html`

   ## Notes for /shipwright-plan
   {Any implementation-relevant notes from feedback, e.g.
   "Sidebar CTA must be purchase-aware — hide when user has active Masterclass"}
   ```

3. Print completion message with next step (`/shipwright-plan`)

### Option B — Process Feedback

1. Find the latest `designs/design-feedback-round*.md` file (highest round number)
2. Parse it: identify screens with status **CHANGES** or **REJECTED**
3. Identify **global changes** (changes that affect multiple screens — e.g. color shifts, icon style changes, nav label renames). Apply these to ALL screens, not just flagged ones.
4. Revise only flagged screens — use the snippet assembly process from Step 4
5. **Spec Backflow (partial)**:

   | Artifact | What to update | Condition |
   |----------|---------------|-----------|
   | `designs/visual-guidelines.md` | Color values, token changes | If global design changes were made |
   | `designs/design-manifest.md` | Screen titles (if renamed), status → `revised-rN` | Always |
   | `designs/index.html` | Regenerate screens array with updated data | Always |
   | `agent_docs/decision_log.md` | New design decisions (DR-NNN format) | If non-trivial decisions |

6. Print review instructions again (same banner as Step 8)
7. → **Loop back** to the AskUserQuestion (same 3 options)

### Option C — Pause

1. Print current state summary (N screens, N approved, guidelines saved)
2. End — user can resume later with `/shipwright-design`

### Decision Log Format

Design decisions are logged to `agent_docs/decision_log.md` using this format:

```markdown
### DR-{NNN}: {Title}

**Date:** {date}
**Source:** Design Round {N} feedback
**Decision:** {What was decided}
**Rationale:** {Why — user feedback, UX reason, brand requirement}
**Impact:** {What changed — screens, colors, patterns}
```

### Complete Flow Diagram

```
/shipwright-design
  │
  ├── Generate/revise screens + index.html
  ├── Print review instructions
  ├── AskUserQuestion (A/B/C) ← dialog stays open
  │
  │   [User reviews in browser meanwhile]
  │   [User exports feedback to designs/]
  │
  ├─[B]─→ Read feedback file
  │        Revise CHANGES/REJECTED screens
  │        Spec Backflow (partial)
  │        Regenerate index.html
  │        Print review instructions
  │        → AskUserQuestion again (loop)
  │
  ├─[A]─→ Spec Backflow (full)
  │        Write session handoff
  │        → Done, ready for /shipwright-plan
  │
  └─[C]─→ Print state summary → End
```

---

## Iteration Mode

### Mode 1: Iterate on a single screen

When invoked with a specific HTML file (e.g. `@designs/screens/02-dashboard.html`):

1. Read the HTML file
2. Ask: "What would you like to change?"
3. Apply changes using the snippet assembly approach where applicable
4. Regenerate the file
5. Update design-manifest.md if needed
6. Regenerate index.html
7. → Enter **Step 8.5** (review loop)

### Mode 2: Process feedback file

When invoked with a feedback file (e.g. `@designs/design-feedback-round2.md`):

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

### Snippet System (primary — use for screen generation)
- [snippets-layout.md](references/snippets-layout.md) — Copy-paste HTML/CSS layout blocks (Page Shell, Sidebar, Top Nav, Centered Card, Buttons)
- [snippets-components.md](references/snippets-components.md) — Copy-paste HTML/CSS component blocks (Table, Card Grid, Form, Stats, Modal, Tabs, Badges, Empty State, Breadcrumbs, Detail, Notifications)
- [snippets-variables.md](references/snippets-variables.md) — Complete CSS `:root` variable blocks for each flavor × character combination
- [review-viewer-template.md](references/review-viewer-template.md) — Complete HTML template for designs/index.html (review viewer with feedback panel)

### Design Context (secondary — consult for design decisions and understanding)
- [design-flavors.md](references/design-flavors.md) — Design system flavor architecture and selection
- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns, component patterns, color system, character palettes
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](references/material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)
- [user-flow-patterns.md](references/user-flow-patterns.md) — Standard user flow templates
