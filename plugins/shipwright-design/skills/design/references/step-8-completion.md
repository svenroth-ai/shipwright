# Step 8 — Completion & Review Instructions

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
