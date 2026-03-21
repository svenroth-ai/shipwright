# shipwright-design — UI Design Skill

> Turn IREB specs into interactive HTML mockups before a single line of code is written.

## What It Does

`shipwright-design` sits between requirements (shipwright-project) and planning (shipwright-plan) in the Shipwright pipeline. It reads your structured specs, recognizes which screens your app needs, and generates standalone HTML mockups you can open in any browser.

**Pipeline position:**
```
Requirements → Design → Planning → Build → Test → Deploy
```

## Why It Matters

Developers skip design. They jump from requirements to code, discover UX problems during implementation, and waste hours refactoring. shipwright-design prevents this by making the UI tangible before any code is written.

- **See before you build** — HTML mockups you can click through in your browser
- **Faster planning** — shipwright-plan references concrete screens instead of abstract descriptions
- **Fewer rewrites** — acceptance criteria + visual design = clear implementation target

## How It Works

### 1. Analyze Specs

The skill reads your IREB-aligned specs from shipwright-project. It scans Functional Requirements and automatically identifies which screen types your app needs:

| What you wrote in your spec | What shipwright-design creates |
|----------------------------|-------------------------------|
| "The system SHALL allow users to login" | Login screen with email/password form |
| "The system SHALL display a dashboard" | Dashboard with sidebar, header, content grid |
| "The system SHALL list all tasks" | Data table with filters, search, pagination |
| "The system SHALL allow creating tasks" | Form with validation, save/cancel actions |
| "The system SHALL provide user settings" | Settings page with tabs and form sections |

### 2. Quick Design Interview (3-5 questions)

Before generating, the skill asks a few targeted questions:

- **Branding:** Primary color, font preference, logo?
- **Layout:** Sidebar navigation or top navigation?
- **Existing designs:** Upload what you already have
- **Special needs:** Dark mode? Mobile-first? Accessibility requirements?

No lengthy interview. Best practices are built into the skill — it makes a proposal, you adjust.

### 3. Generate Screens + User Flows

**Screens** — Individual page mockups as standalone HTML:
```
designs/screens/01-login.html
designs/screens/02-dashboard.html
designs/screens/03-task-list.html
designs/screens/04-task-form.html
designs/screens/05-settings.html
```

**User Flows** — Multi-screen prototypes showing complete journeys:
```
designs/flows/auth-flow.html        → Login → Register → Verify Email → Dashboard
designs/flows/crud-flow.html        → List → Detail → Edit → Delete Confirm
```

Every file opens directly in your browser. No build step, no dependencies.

### 4. Iterate via Chat

Don't like the sidebar? Change it:
```
"Move navigation to the top"
"Make the dashboard cards bigger"
"Add a dark mode toggle to settings"
"The table needs an export button"
```

The skill regenerates the affected screens instantly.

### 5. Bring Your Own Designs

Already have mockups? Drop them in `designs/uploads/`:

```
designs/uploads/my-figma-export.png
designs/uploads/existing-login.html
```

The skill integrates uploaded designs into the manifest and only generates what's missing.

## Design System Support

The design system is configurable per stack profile. Your chosen component library determines the visual style of generated mockups:

| Design System | Type | Profile Config |
|--------------|------|---------------|
| **Untitled UI** | React Component Library | `supabase-nextjs` (default) |
| shadcn/ui | React Components | Configurable |
| Tailwind UI | Tailwind Templates | Configurable |
| Custom | Any | User-defined |

Switch your design system in the profile — the skill adapts automatically.

## Output: design-manifest.md

Every design session produces a manifest that downstream skills can read:

```markdown
# Design Manifest

## Screens

| # | Screen | File | Status | Linked FRs |
|---|--------|------|--------|-----------|
| 01 | Login | screens/01-login.html | complete | FR-01.01, FR-01.02 |
| 02 | Dashboard | screens/02-dashboard.html | complete | FR-02.01 |
| 03 | Task List | screens/03-task-list.html | complete | FR-02.02, FR-02.03 |

## User Flows

| Flow | File | Screens | Status |
|------|------|---------|--------|
| Authentication | flows/auth-flow.html | 01 → Register → Verify → 02 | complete |
| Task CRUD | flows/crud-flow.html | 03 → Detail → 04 → Delete | complete |
```

shipwright-plan reads this manifest and references specific screens in its implementation sections. shipwright-build uses the HTML mockups as visual targets.

## Integration with Shipwright Pipeline

```
/shipwright-project "Build a task tracker"
  → Creates IREB specs with Functional Requirements

/shipwright-design
  → Reads specs, asks 3-5 questions, generates HTML mockups
  → Output: designs/ folder + design-manifest.md

/shipwright-plan @01-auth/spec.md
  → References designs/screens/01-login.html in planning sections
  → "Section 01: Implement the login screen as shown in designs/screens/01-login.html"

/shipwright-build @sections/01-models.md
  → Uses HTML mockup as visual reference for implementation
```

## Standalone Usage

The skill works independently too:

```
/shipwright-design                           # Analyze specs and generate designs
/shipwright-design @designs/screens/02-dashboard.html  # Iterate on a specific screen
/shipwright-design --upload                  # Integrate uploaded designs
```

## Technical Details

- **Output format:** Standalone HTML with inline CSS
- **No dependencies:** Opens in any browser, no Node.js or build tools needed
- **Iterative:** Change via chat, regenerate instantly
- **Profile-aware:** Design system from stack profile
- **Spec-connected:** Links mockups to IREB Functional Requirements via FR IDs
