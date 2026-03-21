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

## Step 3: Design Interview (3-5 questions)

**Goal:** Refine the proposal with user preferences. Quick, targeted.

```
AskUserQuestion:
  question: "Quick design questions before I generate mockups:"
```

**Questions to ask:**

1. **Branding**: "Any brand colors, fonts, or a logo? Or should I use a clean default palette?"
2. **Layout**: "Sidebar navigation or top navigation bar?"
3. **Existing designs**: "Do you have existing mockups or screenshots to include? Drop them in designs/uploads/ if so."
4. **Special UX**: "Any specific UX requirements? (dark mode, mobile-first, accessibility focus, etc.)"

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

## Step 4: Generate Screens

**Goal:** Create standalone HTML mockups.

For each confirmed screen:

1. Read the design system from profile (`design_system.name` in supabase-nextjs.json)
2. Load component patterns from [design-system-patterns.md](references/design-system-patterns.md)
3. Generate standalone HTML with inline CSS
4. Save to `designs/screens/{NN}-{name}.html`

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
Manifest:    designs/design-manifest.md

Open in browser:
  designs/screens/01-login.html
  designs/screens/02-dashboard.html
  ...

Next steps:
  1. Open HTML files in your browser to review
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

1. Scan directory for images (PNG, JPG) and HTML files
2. Present found files to user
3. Ask which screens they represent
4. Add to design-manifest.md with status "uploaded"
5. Generate only screens not covered by uploads

---

## Reference Documents

- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns and component best practices
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference
- [user-flow-patterns.md](references/user-flow-patterns.md) — Standard user flow templates
