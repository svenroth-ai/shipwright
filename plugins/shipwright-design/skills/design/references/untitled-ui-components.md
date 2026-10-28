# Untitled UI Kit

> Design language: https://www.untitledui.com/ . The kit is a real CSS file, not a description.

## Overview

For flavor `untitled-ui` a screen is **composed from the kit**, not styled from scratch:

| File | What it is | Who changes it |
|---|---|---|
| `kit/untitled-ui/kit.css` | Every component and layout. Colours, fonts, radii and shadows come from `var(--token)`; no colour or font-size literal (test-enforced). | The kit (a framework change) |
| `kit/untitled-ui/tokens/*.css` | One `:root` block per look: colours, fonts, radii, spacing, shadows. | The project (brand, visual guidelines) |
| `kit/untitled-ui/fragments/*.html` | Screen bodies built from kit classes (board, gallery). | The screen |
| `kit/untitled-ui/examples/*.html` | Fragment + tokens + kit as standalone pages. Built by `scripts/tools/build_kit_examples.py`; do not edit by hand. | The build script |

Look and feel comes from the token set alone. A project's `visual-guidelines.md` or brand guideline supplies tokens
(colours, fonts, radii, spacing) and nothing else: it never restyles a component. To change how a button looks
everywhere, change `kit.css`; to change what colour it is, change the token.

## Composing a screen

Kit paths in these docs (`kit/untitled-ui/...`) are relative to the design skill folder, `${CLAUDE_PLUGIN_ROOT}/skills/design/`, never to the project or to `references/`.

1. Page shell from [snippets-layout.md](snippets-layout.md) (or copy a built example).
2. `:root` block: paste a complete shipped token set first, then put the project's overrides after it, so every token stays defined. Start from `tokens/warm.css`, `tokens/clean.css` or `tokens/bold.css`, or map brand tokens
   to the names in the **Variable Reference** of [snippets-variables.md](snippets-variables.md). The kit also needs
   `--space-1` to `--space-6`, `--color-primary-soft`, `--color-border-strong`, `--color-focus`, `--color-info`, `--color-{info,success,warning,error}-bg`, `--color-overlay`, `--shadow-sm`, `--shadow-lg`. A brand kept in a claude.ai Design System is mapped, checked and corrected per [brand-from-design-system.md](brand-from-design-system.md), then laid over a shipped set. Colour tokens are solid hex (no transparent tints). The shipped token sets are contrast-tested; a project's own overrides are not checked by the tests, so run `scripts/tools/check_brand_tokens.py --base <set> --overrides <file>` and keep to the rules in [tokens-contract.md](../kit/untitled-ui/tokens-contract.md).
3. Paste `kit.css` once into the page `<style>`.
4. Body: layout, then components, with the class names below.

## Components (class names)

| Group | Classes |
|---|---|
| Layout A / B / C | `app-layout` `sidebar*` `topbar*` · `app-topnav` `topnav*` `content-topnav` · `auth-*`; page parts `page-header` `page-body` `page-actions` |
| Buttons | `btn` + `btn-primary` `btn-secondary` `btn-ghost` `btn-danger` · `btn-sm` `btn-lg` · `icon-btn` |
| Data | `data-table` `table-container` `table-toolbar` `pagination` · `card-grid` `card*` · `stats-row` `stat-card*` · `list` `list-item*` |
| Input | `form-container` `form-grid` `field` `field-label` `field-input` `field-textarea` `field-hint` `field-error` (modifier on `field`) · `toggle-row` `toggle*` · `search-input` |
| Navigation | `tabs-container` `tabs-nav` `tab` · `segmented` `segmented-item` · `breadcrumbs*` · `pagination` |
| Feedback | `badge` + `badge-success/warning/error/info/neutral` · `tag` `tag-remove` `tag-row` · `alert` + `alert-info/success/warning/error` · `toast` · `progress` `progress-bar` · `empty-state*` · `notification-list` `notif-*` |
| Overlay | `modal-overlay` `modal*` · `popover-anchor` `popover` `popover-item` |
| Choice and input extras | `choice-group` `choice-legend` `choice` (checkbox, radio) · `select-wrap` `select` · `multi-select` · `range` · `code-input` `code-input-box` · `dropzone` `file-item*` · `calendar*` |
| Menus and panels | `popover-sep` `popover-label` `popover-item danger` · `command*` `kbd` · `drawer-overlay` `drawer*` · `tooltip-anchor` `tooltip` · `filter-bar` |
| Structure | `steps` `step` (progress steps) · `tree` `tree-item` · `feed` `feed-item*` · `card-header` · `section-footer` · `cta` · `code` · `btn-group` · `badge-group` · `featured-icon` · `rating` · `empty-code` (404) |
| Loading | `skeleton` `skeleton-line` `skeleton-title` · `spinner` · `error-summary` |
| Misc | `avatar` `avatar-sm` `avatar-group` · `section-header` `section-title` · `divider` · `detail-layout` `detail-*` |

The gallery (`examples/gallery-*.html`) shows every one of them. Layout D (chat + pane) is not part of the kit.

## Coverage of the Untitled UI component list

Checked against https://www.untitledui.com/react/components (base and application UI). In the kit: avatars, badges, badge
groups, button groups, buttons, checkboxes, dropdowns and context menus, featured icons, inputs, progress indicators,
radios, rating, select, multi select, sliders, tags, textareas, toggles, tooltips, verification code inputs; alerts,
breadcrumbs, calendars and date picker panel, card headers, code snippets, command menus, content dividers, drawers,
empty states, file uploaders, filter bars, header and sidebar navigation, inline CTAs, loading indicators, metrics,
modals, notifications, page headers, pagination, progress steps, section headers and footers, tables, tabs, tree views,
activity feeds, log in and sign up layout (Layout C), 404.

Deliberately not in the kit (each needs its own library or is marketing, not app UI): charts and gauges (use a chart
library and colour it from tokens), carousels, rich text editors, colour, gradient and image pickers, credit cards, QR
codes, video players, app-store and social buttons, illustrations, chat messaging, marketing website sections and
email templates. Add one when a project needs it, together with its gallery entry.

## Rules

- UX and accessibility rules the kit follows, with sources: [ux-rules.md](../kit/untitled-ui/ux-rules.md).
- No literal colours, fonts or sizes in a screen's own CSS: use a token. A missing token is added to the token sets,
  not hard-coded.
- A new component goes into `kit.css` and the gallery fragment in the same change; `tests/test_untitled_ui_kit.py`
  keeps the pieces consistent (all tokens defined, no literals, examples current).
- Rebuild the examples after any change: `uv run plugins/shipwright-design/scripts/tools/build_kit_examples.py`.
