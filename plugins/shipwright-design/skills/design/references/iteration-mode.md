# Iteration Mode

## Mode 1: Iterate on a single screen

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

## Mode 2: Process feedback file

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

## Chrome Change Propagation

If **any** iteration (Mode 1 or Mode 2) changes a shared chrome element — navigation items, labels, icons, header, footer, or branding:

1. **Update `.shipwright/designs/chrome-definition.md` first** — edit the data tables AND regenerate the resolved HTML blocks
2. **Identify all affected screens** — every screen using the same layout (A or B) must be updated
3. **Re-copy the chrome blocks** — replace the sidebar/topbar/footer in each affected screen with the updated resolved blocks (preserve the correct `active` class per screen)
4. **Report** which screens were updated and what changed

> **Rule:** Never change chrome in a single screen without updating `chrome-definition.md`. The definition file is always authoritative.
