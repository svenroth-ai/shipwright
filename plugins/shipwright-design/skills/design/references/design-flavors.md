# Design System Flavors

## Overview

Design flavors define the visual language for generated mockups. Each flavor provides
component patterns, spacing rules, color tokens, and typography conventions that the
mockup generator applies consistently across all screens.

## Available Flavors

| Flavor | Design System | Best For | Reference |
|--------|--------------|----------|-----------|
| `untitled-ui` | [Untitled UI](https://www.untitledui.com/) | SaaS dashboards, admin panels, B2B apps | [untitled-ui-components.md](untitled-ui-components.md) |
| `material-design` | [Material Design 3](https://m3.material.io/) | Consumer apps, Android-first, Google ecosystem | [material-design-components.md](material-design-components.md) |
| `custom` | User-provided | Existing brand guidelines or design system | Upload to `designs/uploads/` |

## Flavor Selection

The design interview (Step 3) asks the user which flavor to use:

```
Which design system should I use as the visual foundation?

  1. Untitled UI — Clean, professional SaaS style (default)
  2. Material Design 3 — Google's design system, great for consumer apps
  3. Custom — I'll upload my own guidelines to designs/uploads/

Choice [1]:
```

## Flavor Resolution Order

1. **User choice** from interview → selected flavor
2. **Profile default** → `design_system.name` from profile JSON (e.g., `supabase-nextjs.json`)
3. **Fallback** → `untitled-ui`

## Snippet Assembly System

Screen generation uses a **snippet-based assembly** approach for speed. Instead of writing HTML from scratch, Claude composes screens from pre-built building blocks.

### Architecture

```
snippets-variables.md     → CSS :root blocks (6 flavor × character combos)
        ↓
snippets-layout.md        → Page Shell + Layout HTML (Sidebar / Top Nav / Centered Card)
        ↓
snippets-components.md    → Component HTML (Table, Form, Cards, Stats, Modal, etc.)
        ↓
Assembled Screen          → designs/screens/NN-name.html
```

### How Flavors Map to Snippets

Each flavor × character combination has a complete `:root` CSS variable block in [snippets-variables.md](snippets-variables.md). The same layout and component snippets work across all flavors — only the variables change.

| Flavor | Character | Variable Set |
|--------|-----------|-------------|
| `untitled-ui` | Warm & Premium | Inter/Libre Baskerville, earth tones, shadow cards, 8px radius |
| `untitled-ui` | Clean & Modern | Inter, blue accent, border cards, 6px radius |
| `untitled-ui` | Bold & Energetic | Plus Jakarta Sans, violet+orange, strong shadows, 8px radius |
| `material-design` | Warm & Premium | Roboto, warm browns, tonal elevation, 12px radius |
| `material-design` | Clean & Modern | Roboto, M3 purple, outlined cards, 12px radius |
| `material-design` | Bold & Energetic | Roboto, vivid violet, tonal shadows, 12px radius |
| `custom` | (any) | Mapped from user's uploaded tokens (see guide in snippets-variables.md) |

### Design Context References

The original flavor reference files remain as **design context** for Claude to understand intent:
- [untitled-ui-components.md](untitled-ui-components.md) — Component patterns and design philosophy
- [material-design-components.md](material-design-components.md) — M3 tokens, shapes, elevation

These are consulted for design decisions but NOT used as HTML templates.

## Adding a New Flavor

1. Create `references/{flavor-name}-components.md` with component patterns (design context)
2. Add 3 variable blocks (one per character) to `references/snippets-variables.md`
3. Add the flavor to the table above
4. Add a choice option in SKILL.md Step 3
5. Optionally add profile support in `shared/profiles/{profile}.json` → `design_system.name`

## Flavor Interface

Each flavor reference document must cover:

| Section | Required | Description |
|---------|----------|-------------|
| Navigation | yes | Sidebar, top nav, breadcrumbs, tabs |
| Data Display | yes | Tables, cards, stats, badges, avatars |
| Input | yes | Text fields, selects, checkboxes, toggles, date pickers |
| Feedback | yes | Toasts, alerts, modals, progress, loaders |
| Layout | yes | Page headers, dividers, empty states |
| Mockup Translation Rules | yes | How to replicate the design system in HTML+CSS |

## Custom Flavor

When the user selects `custom`:

1. Prompt user to upload guidelines to `designs/uploads/`
2. Read uploaded `.md` or `.pdf` files for design tokens
3. Extract: colors, typography, spacing, border radius, shadows
4. Map extracted tokens to the snippet variable structure (see [snippets-variables.md](snippets-variables.md) → "Custom Flavor: Variable Mapping Guide")
5. Use extracted tokens instead of a built-in flavor
6. Skip Step 6.5 (visual guidelines generation) — the upload is authoritative
