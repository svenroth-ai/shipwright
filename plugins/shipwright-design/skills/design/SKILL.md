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
- Skip to [Iteration Mode](references/iteration-mode.md)

**Upload Integration** (`--upload` flag or `.shipwright/designs/uploads/` exists with files):
- Scan `.shipwright/designs/uploads/` for existing mockups
- Integrate into design-manifest.md
- Generate only missing screens
- Skip to [Upload Mode](references/upload-mode.md)

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

Map FRs to screen types automatically using the keyword table.
See [step-2-screen-type-detection.md](references/step-2-screen-type-detection.md) for the FR-keyword → screen-type table and the proposed screen-list output.

---

## Step 2.5: Brand Extraction

If the user has an existing website, auto-extract design tokens before asking design questions.
See [step-2-5-brand-extraction.md](references/step-2-5-brand-extraction.md) for the WebFetch flow and token-extraction procedure.

---

## Step 3: Design Interview (3-5 questions)

Ask 3–5 targeted questions covering design system flavor, brand character, layout, existing designs, and special UX. Then present the proposed screen list for confirmation.
See [step-3-design-interview.md](references/step-3-design-interview.md) for the full question list, palette derivation table, and confirmation prompt.

---

## Step 3.5: Design Preview

Generate exactly 3 preview screens (auth + main layout + content-heavy) and confirm the look-and-feel before generating all screens.
See [step-3-5-design-preview.md](references/step-3-5-design-preview.md) for the procedure and confirmation prompt.

---

## Step 3.7: Generate Chrome Definition

Create a single source of truth (`.shipwright/designs/chrome-definition.md`) for all shared UI elements (sidebar, topbar, footer, branding) so every screen has identical chrome.
See [step-3-7-chrome-definition.md](references/step-3-7-chrome-definition.md) for the resolved-HTML procedure and confirmation prompt.

---

## Step 4: Generate Screens

Create standalone HTML mockups using the snippet assembly system.
See [step-4-generate-screens.md](references/step-4-generate-screens.md) for the 8-step assembly process, design-context references, and HTML requirements.

---

## Step 5: Generate User Flows

**Goal:** Create multi-screen flow mockups.

For each confirmed flow:

1. Combine relevant screens into a single HTML file
2. Add navigation between steps (tabs, stepper, or side-by-side)
3. Show the complete journey
4. Save to `.shipwright/designs/flows/{flow-name}.html`

Flows show screens in sequence with arrows or step indicators. See [user-flow-patterns.md](references/user-flow-patterns.md) for standard flow templates.

---

## Step 6: Write Design Manifest

Create the registry `.shipwright/designs/design-manifest.md` that downstream skills read.
See [step-6-design-manifest.md](references/step-6-design-manifest.md) for the manifest template.

---

## Step 6a: Generate Review Viewer (Index Page)

Create `.shipwright/designs/index.html` — a full review tool with grid view, fullscreen viewer, and integrated feedback panel.
See [step-6a-review-viewer.md](references/step-6a-review-viewer.md) for the template + placeholder mapping and feature list.

---

## Step 6.5: Generate Visual Guidelines

**Goal:** Create a reusable design token document for shipwright-build.

**Skip if:** User uploaded existing visual guidelines in Step 3.

See [visual-guidelines-template.md](references/visual-guidelines-template.md) for the complete template and value sourcing rules.

---

## Step 7: Update Specs (Optional)

**Goal:** Add UI References back to the IREB specs.

If specs have a "UI Requirements" section (Section 7), update it with:
- Screen references (which HTML file maps to which FRs)
- Layout decisions made during the design interview

This is optional — skip if specs don't have the UI Requirements section.

---

## Step 8: Completion & Review Instructions

Print the completion summary, review instructions, and generate `screen-routes.json` for design fidelity testing, then proceed to Step 8.5.
See [step-8-completion.md](references/step-8-completion.md) for the completion banner, review instructions, and screen-routes derivation rules.

---

## Step 8.5: Design Review Loop

See [review-loop.md](references/review-loop.md) for the complete review loop flow (Option A: Finalize with FR-Coverage Gate + Spec Backflow, Option B: Process Feedback, Option C: Pause, Decision Log Format, Flow Diagram).

---

## Step 9: Finalization (iterate 12.2 — Minimum Phase Completion Canon)

Run this only after Step 8.5 Option A approves the design. Performs the canon minimum (C1/C2/C3/C5 + `phase_history`); C4 is skipped by design policy.
See [step-9-finalization.md](references/step-9-finalization.md) for the full bash sequence and the `SHIPWRIGHT_RUN_ID` handling.

---

## Iteration Mode

See [iteration-mode.md](references/iteration-mode.md) for Mode 1 (single-screen iteration), Mode 2 (feedback-file processing), and the Chrome Change Propagation rule.

---

## Upload Mode

See [upload-mode.md](references/upload-mode.md) for the `.shipwright/designs/uploads/` integration procedure.

---

## Reference Documents

### Step-by-step procedures (this iterate's split)
- [step-2-screen-type-detection.md](references/step-2-screen-type-detection.md) — FR-keyword → screen-type table
- [step-2-5-brand-extraction.md](references/step-2-5-brand-extraction.md) — WebFetch + token extraction
- [step-3-design-interview.md](references/step-3-design-interview.md) — Question list + palette derivation
- [step-3-5-design-preview.md](references/step-3-5-design-preview.md) — 3-screen preview validation
- [step-3-7-chrome-definition.md](references/step-3-7-chrome-definition.md) — Resolved chrome blocks
- [step-4-generate-screens.md](references/step-4-generate-screens.md) — Snippet assembly process
- [step-6-design-manifest.md](references/step-6-design-manifest.md) — Manifest template
- [step-6a-review-viewer.md](references/step-6a-review-viewer.md) — Review viewer template
- [step-8-completion.md](references/step-8-completion.md) — Completion banner + screen-routes
- [step-9-finalization.md](references/step-9-finalization.md) — Phase completion canon
- [iteration-mode.md](references/iteration-mode.md) — Iteration modes + chrome propagation
- [upload-mode.md](references/upload-mode.md) — Upload integration

### Snippet System (primary — use for screen generation)
- [snippets-layout.md](references/snippets-layout.md) — Copy-paste HTML/CSS layout blocks (Page Shell, Sidebar, Top Nav, Centered Card, Buttons)
- [snippets-components.md](references/snippets-components.md) — Copy-paste HTML/CSS component blocks (Table, Card Grid, Form, Stats, Modal, Tabs, Badges, Empty State, Breadcrumbs, Detail, Notifications)
- [snippets-variables.md](references/snippets-variables.md) — Complete CSS `:root` variable blocks for each flavor × character combination
- [snippets-chrome.md](references/snippets-chrome.md) — Chrome definition template
- [review-viewer-template.md](references/review-viewer-template.md) — Complete HTML template for .shipwright/designs/index.html (review viewer with feedback panel)
- [review-loop.md](references/review-loop.md) — Step 8.5 review loop options (A/B/C) + flow diagram

### Design Context (secondary — consult for design decisions and understanding)
- [design-flavors.md](references/design-flavors.md) — Design system flavor architecture and selection
- [design-system-patterns.md](references/design-system-patterns.md) — Layout patterns, component patterns, color system, character palettes
- [untitled-ui-components.md](references/untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](references/material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)
- [user-flow-patterns.md](references/user-flow-patterns.md) — Standard user flow templates
- [visual-guidelines-template.md](references/visual-guidelines-template.md) — Visual guidelines template
