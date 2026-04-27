# Chrome Snippets (Shared UI Elements)

Defines the **shared chrome** — navigation, header, footer, branding — that must be identical across all screens. Generated once in Step 3.7, then copied verbatim into every screen.

> **Why:** Each screen is a standalone HTML file. Without a single source of truth for chrome elements, sidebars drift between screens (different nav items, icons, order). This file prevents that.

---

## How It Works

1. **Step 3.7** generates `.shipwright/designs/chrome-definition.md` using the templates below
2. **Step 4** copies the resolved HTML blocks from `chrome-definition.md` into each screen
3. The **only per-screen change** is which `.nav-item` or `.topnav-link` gets the `active` class
4. All other chrome content (labels, icons, branding, user info) stays identical

---

## Chrome Definition Template

Write this to `.shipwright/designs/chrome-definition.md` after the design interview (Step 3) and preview confirmation (Step 3.5).

````markdown
# Chrome Definition

> Single source of truth for shared UI elements. Every screen copies these blocks verbatim.
> Only the `active` class changes per screen.

## App Branding

| Token | Value |
|-------|-------|
| App Name | {from project config or interview} |
| Logo SVG | `<svg ...>...</svg>` (24x24, stroke icon) |

## Navigation Items

| # | Label | SVG Icon (`<path>` content) | Screen File | Section |
|---|-------|-----------------------------|-------------|---------|
| 1 | {label} | `<path d="..."/>` | {NN}-{name}.html | main |
| 2 | {label} | `<path d="..."/>` | {NN}-{name}.html | main |
| — | divider | — | — | — |
| N | {label} | `<path d="..."/>` | {NN}-{name}.html | bottom |

> **Section values:** `main` = primary nav area, `bottom` = after divider (settings, help, etc.)
> **Order:** Overview/dashboard first, settings/admin last. Group logically.

## Topbar Configuration

| Token | Value |
|-------|-------|
| Search Placeholder | "{context-appropriate text, e.g. Search projects...}" |
| Show Notifications | yes / no |
| Show User Avatar | yes / no |

## User Info

| Token | Value |
|-------|-------|
| User Name | {realistic name for the domain} |
| User Initials | {2 letters} |
| User Role | {role from specs, e.g. Product Manager} |

## Footer (if applicable)

| Token | Value |
|-------|-------|
| Footer Text | {e.g. "(c) 2026 AppName. All rights reserved."} |

---

## Resolved Sidebar Block (Layout A)

Copy this `<aside>` element verbatim into every Layout A screen.
**Per-screen change:** Move `class="nav-item active"` to the nav item matching the current screen.

```html
<aside class="sidebar">
  <div class="sidebar-logo">
    <span class="logo-icon">{LOGO_SVG}</span>
    <span class="logo-text">{APP_NAME}</span>
  </div>
  <nav class="sidebar-nav">
    <a href="#" class="nav-item active">
      <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICON_1}</svg>
      <span>{LABEL_1}</span>
    </a>
    <a href="#" class="nav-item">
      <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICON_2}</svg>
      <span>{LABEL_2}</span>
    </a>
    <!-- ... all main section nav items ... -->
    <div class="nav-divider"></div>
    <span class="nav-section-label">{BOTTOM_SECTION_LABEL}</span>
    <a href="#" class="nav-item">
      <svg class="nav-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICON_N}</svg>
      <span>{LABEL_N}</span>
    </a>
  </nav>
  <div class="sidebar-footer">
    <div class="user-info">
      <div class="avatar">{USER_INITIALS}</div>
      <div class="user-details">
        <div class="user-name">{USER_NAME}</div>
        <div class="user-role">{USER_ROLE}</div>
      </div>
    </div>
  </div>
</aside>
```

> **Important:** The resolved block above is a TEMPLATE showing the structure.
> In `chrome-definition.md`, replace ALL `{...}` tokens with real values from the tables above.
> The result must be copy-paste ready — no placeholders remaining.

## Resolved Topbar Block (Layout A)

Copy this `<header>` element verbatim into every Layout A screen. No per-screen changes.

```html
<header class="topbar">
  <button class="sidebar-toggle" aria-label="Toggle sidebar">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>
  </button>
  <div class="topbar-search">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    <input type="text" placeholder="{SEARCH_PLACEHOLDER}" class="search-input">
  </div>
  <div class="topbar-actions">
    <!-- Include if Show Notifications = yes -->
    <button class="icon-btn" aria-label="Notifications">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
    </button>
    <!-- Include if Show User Avatar = yes -->
    <div class="avatar avatar-sm">{USER_INITIALS}</div>
  </div>
</header>
```

## Resolved Top-Nav Block (Layout B)

Copy this `<header>` element verbatim into every Layout B screen.
**Per-screen change:** Move `class="topnav-link active"` to the link matching the current screen.

```html
<header class="topnav">
  <div class="topnav-inner">
    <div class="topnav-brand">
      <span class="logo-icon">{LOGO_SVG}</span>
      <span class="logo-text">{APP_NAME}</span>
    </div>
    <nav class="topnav-links">
      <a href="#" class="topnav-link active">{LABEL_1}</a>
      <a href="#" class="topnav-link">{LABEL_2}</a>
      <!-- ... all nav items ... -->
    </nav>
    <div class="topnav-actions">
      <!-- Include if Show Notifications = yes -->
      <button class="icon-btn" aria-label="Notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
      </button>
      <!-- Include if Show User Avatar = yes -->
      <div class="avatar avatar-sm">{USER_INITIALS}</div>
    </div>
  </div>
</header>
```

## Resolved Footer Block (if applicable)

```html
<footer class="app-footer">
  <p>{FOOTER_TEXT}</p>
</footer>
```
````

---

## Active State Rules

When copying a resolved block into a screen:

| Layout | Element | Rule |
|--------|---------|------|
| A (Sidebar) | `.nav-item` | Set `class="nav-item active"` on the item whose **Screen File** matches the current screen. All others: `class="nav-item"`. |
| B (Top Nav) | `.topnav-link` | Set `class="topnav-link active"` on the matching link. All others: `class="topnav-link"`. |
| C (Centered) | N/A | No navigation chrome. Copy only `APP_NAME` and `LOGO_SVG` into `.auth-logo`. |

---

## Updating Chrome

If the user requests changes to shared chrome elements during iteration:

1. Update the **data tables** in `.shipwright/designs/chrome-definition.md` first
2. Regenerate the **resolved HTML blocks** from the updated tables
3. Re-copy the updated blocks into **all screens** that use the affected layout
4. Report which screens were updated
