# Step 4 — Generate Screens

**Goal:** Create standalone HTML mockups using the snippet assembly system for speed.

## Assembly Process

For each confirmed screen, **assemble from pre-built snippets** rather than writing from scratch:

1. **Page Shell** — Start with the Page Shell from [snippets-layout.md](snippets-layout.md). Replace `{{FONT_FAMILY}}` with the selected font.
2. **CSS Variables** — Copy the matching `:root` block from [snippets-variables.md](snippets-variables.md) based on the flavor × character chosen in Step 3. If brand extraction was done (Step 2.5), override specific variables with extracted values.
3. **Layout** — Pick the appropriate layout snippet from [snippets-layout.md](snippets-layout.md):
   - Auth screens → Layout C (Centered Card)
   - Dashboard/admin/list/detail/settings → Layout A (Sidebar + Content)
   - Public/marketing pages → Layout B (Top Navigation)
   - Always include the shared Button Styles block.
4. **Shared Chrome** — Read `.shipwright/designs/chrome-definition.md` (generated in Step 3.7). Copy the resolved HTML blocks **verbatim**:
   - **Layout A screens:** Copy the **Resolved Sidebar Block** into `<aside class="sidebar">`. Copy the **Resolved Topbar Block** into `<header class="topbar">`. Change ONLY which `.nav-item` has `class="nav-item active"` to match the current screen.
   - **Layout B screens:** Copy the **Resolved Top-Nav Block** into `<header class="topnav">`. Change ONLY which `.topnav-link` has `class="topnav-link active"` to match the current screen.
   - **Layout C screens:** Copy only the app name and logo SVG from the chrome definition into `.auth-logo`.
   - Do NOT improvise nav items, icons, labels, or user info. The `chrome-definition.md` is authoritative.
5. **Components** — Fill the layout's **content area** with component snippets from [snippets-components.md](snippets-components.md):
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

## Design Context References

For understanding design intent and making good composition decisions, consult:
- [design-system-patterns.md](design-system-patterns.md) — Layout patterns, component patterns, color system, character palettes
- [untitled-ui-components.md](untitled-ui-components.md) — Untitled UI component reference (flavor: `untitled-ui`)
- [material-design-components.md](material-design-components.md) — Material Design 3 component reference (flavor: `material-design`)

## HTML Requirements
- Self-contained (no external dependencies except optional CDN font)
- Responsive (mobile + desktop)
- Realistic data (plausible content for the domain)
- Interactive elements visible (buttons, inputs, dropdowns styled)
- All icons: SVG stroke icons (no emojis)
- Color scheme from CSS variables (set once, applied everywhere)
