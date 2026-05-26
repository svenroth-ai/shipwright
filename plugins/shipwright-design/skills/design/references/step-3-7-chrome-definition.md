# Step 3.7 — Generate Chrome Definition

**Goal:** Create a single source of truth for all shared UI elements (sidebar, topbar, footer, branding) so every screen has identical chrome.

**After** the design preview is confirmed in Step 3.5:

1. Read [snippets-chrome.md](snippets-chrome.md) for the chrome definition template
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

**Important:** This step runs ONCE per design session. If chrome needs changes later, see [Chrome Change Propagation](iteration-mode.md#chrome-change-propagation).
