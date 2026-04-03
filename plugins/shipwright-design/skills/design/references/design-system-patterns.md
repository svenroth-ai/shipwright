# Design System Patterns

## Layout Patterns

### Sidebar + Content (Default for dashboards)
```
┌──────┬──────────────────────────┐
│ Logo │      Header / Topbar      │
│      ├──────────────────────────┤
│ Nav  │                          │
│      │      Content Area         │
│      │                          │
│      │                          │
└──────┴──────────────────────────┘
```
- Sidebar: 240-280px, collapsible on mobile
- Header: User avatar, notifications, search
- Content: Max-width 1200px, responsive grid

### Top Navigation (Simpler apps)
```
┌─────────────────────────────────┐
│  Logo    Nav Items    User Menu  │
├─────────────────────────────────┤
│                                 │
│         Content Area            │
│                                 │
└─────────────────────────────────┘
```

### Centered Card (Auth screens)
```
┌─────────────────────────────────┐
│                                 │
│         ┌───────────┐           │
│         │   Logo    │           │
│         │   Form    │           │
│         │   Actions │           │
│         └───────────┘           │
│                                 │
└─────────────────────────────────┘
```
- Card: max-width 400px, centered
- Background: subtle gradient or illustration

## Component Patterns

### Data Table
- Header row: sortable columns, aligned labels
- Filter bar: search input + filter dropdowns + active filters as chips
- Rows: hover state, checkbox for bulk actions
- Pagination: page numbers + items per page selector
- Empty state: illustration + "No results" + CTA

### Form
- Sections with headings
- Labels above inputs (not floating)
- Inline validation messages below inputs
- Required indicator (asterisk or explicit)
- Actions: Primary (save) left, Secondary (cancel) right
- Multi-step: stepper indicator at top

### Card Grid
- 1-4 columns responsive (1 mobile, 2 tablet, 3-4 desktop)
- Consistent card height or masonry
- Card content: title, description, metadata, actions
- Hover: subtle shadow elevation

### Modal/Dialog
- Centered overlay with backdrop
- Close button top-right
- Actions at bottom (confirm right, cancel left)
- Max-width: 480px for confirms, 640px for forms

## Color System

### Default Palette (when no branding provided)
- Primary: #2563EB (blue-600)
- Secondary: #64748B (slate-500)
- Success: #059669 (emerald-600)
- Warning: #D97706 (amber-600)
- Error: #DC2626 (red-600)
- Background: #FFFFFF
- Surface: #F8FAFC (slate-50)
- Text: #0F172A (slate-900)
- Muted: #94A3B8 (slate-400)

### Dark Mode Palette
- Background: #0F172A
- Surface: #1E293B
- Text: #F8FAFC
- (Accent colors stay the same)

### Character Palettes

Used by Step 3 (Brand Character question) to derive a full palette from a mood choice.

#### A) Warm & Premium

| Role | Value | Notes |
|------|-------|-------|
| Background | #f5f0eb | Warm cream |
| Surface | #faf7f4 | Lighter cream for cards |
| Text | #1a1a1a | Near-black |
| Muted Text | #6b5e54 | Warm gray |
| Primary | #5c4033 | Dark brown (CTA, links) |
| Primary Hover | #4a3328 | Darker brown |
| Secondary | #8b7355 | Medium brown (secondary actions) |
| Border | #e8e0d8 | Warm light border |
| Success | #2d6a4f | Forest green |
| Error | #c1121f | Deep red |

- **Cards:** Shadow-based (`0 1px 3px rgba(0,0,0,0.08)`), no border, 12px radius
- **Buttons:** Rounded (8px), solid fill primary, ghost secondary
- **Font suggestion:** Libre Baskerville, DM Serif Display, or Inter with 300/400/600 weights

#### B) Clean & Modern

| Role | Value | Notes |
|------|-------|-------|
| Background | #ffffff | Pure white |
| Surface | #f8fafc | Slate-50 |
| Text | #0f172a | Slate-900 |
| Muted Text | #64748b | Slate-500 |
| Primary | #2563eb | Blue-600 (single accent) |
| Primary Hover | #1d4ed8 | Blue-700 |
| Secondary | #64748b | Slate-500 |
| Border | #e2e8f0 | Slate-200 |
| Success | #059669 | Emerald-600 |
| Error | #dc2626 | Red-600 |

- **Cards:** 1px border (`#e2e8f0`) + subtle shadow (`0 1px 2px rgba(0,0,0,0.05)`), 8px radius
- **Buttons:** 6px radius, solid fill primary, outline secondary
- **Font suggestion:** Inter, system-ui

#### C) Bold & Energetic

| Role | Value | Notes |
|------|-------|-------|
| Background | #ffffff | White (or #09090b for dark variant) |
| Surface | #f4f4f5 | Zinc-100 |
| Text | #09090b | Zinc-950 |
| Muted Text | #71717a | Zinc-500 |
| Primary | #7c3aed | Violet-600 (vivid) |
| Primary Hover | #6d28d9 | Violet-700 |
| Secondary | #f97316 | Orange-500 (contrast pair) |
| Border | #e4e4e7 | Zinc-200 |
| Success | #10b981 | Emerald-500 |
| Error | #ef4444 | Red-500 |

- **Cards:** Strong shadow (`0 4px 12px rgba(0,0,0,0.1)`), 8px radius
- **Buttons:** 8px radius, bold fill, gradient option for CTAs
- **Font suggestion:** Plus Jakarta Sans, Space Grotesk, or Inter with 500/700 weights

#### Combining Character with Extracted Tokens

When Step 2.5 extracts tokens from an existing website:
1. Use the extracted colors as the starting point
2. Map them to the closest character palette
3. Fill any missing roles (success, error, muted) from the matched character palette
4. Let the user confirm the merged result

## Typography

- Font: Inter (Google Fonts CDN)
- Headings: 600-700 weight
- Body: 400 weight
- Small/Caption: 500 weight, muted color
- Line height: 1.5 for body, 1.2 for headings

## Spacing System

- Base unit: 4px
- Common spacings: 4, 8, 12, 16, 24, 32, 48, 64px
- Component padding: 16-24px
- Section gaps: 24-48px

## Responsive Breakpoints

- Mobile: < 640px (1 column)
- Tablet: 640-1024px (2 columns, sidebar collapses)
- Desktop: > 1024px (full layout)
