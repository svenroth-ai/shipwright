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
