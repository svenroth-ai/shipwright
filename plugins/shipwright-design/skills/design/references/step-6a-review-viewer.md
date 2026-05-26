# Step 6a — Generate Review Viewer (Index Page)

**Goal:** Create `.shipwright/designs/index.html` — a full review tool with grid view, fullscreen viewer, and integrated feedback panel.

## How to Generate

1. Read the complete template from [review-viewer-template.md](review-viewer-template.md)
2. Read `.shipwright/designs/visual-guidelines.md` → extract primary color, font, background, surface, text, muted, border colors, and border radius
3. Read `.shipwright/designs/design-manifest.md` → build the `screens` JavaScript array
4. Replace all `{{PLACEHOLDERS}}` in the template with project-specific values
5. Write to `.shipwright/designs/index.html`

## Placeholder Mapping

| Placeholder | Source |
|-------------|--------|
| `{{PROJECT_NAME}}` | `shipwright_project_config.json` → `project_name` |
| `{{FONT_FAMILY}}` | `visual-guidelines.md` → primary font |
| `{{FONT_URL}}` | Google Fonts URL for that font |
| `{{COLOR_PRIMARY}}` | `visual-guidelines.md` → Primary color |
| `{{COLOR_BG}}` | `visual-guidelines.md` → Background |
| `{{COLOR_SURFACE}}` | `visual-guidelines.md` → Surface/Card background |
| `{{COLOR_TEXT}}` | `visual-guidelines.md` → Foreground/Text |
| `{{COLOR_MUTED}}` | `visual-guidelines.md` → Muted text |
| `{{COLOR_BORDER}}` | `visual-guidelines.md` → Border |
| `{{RADIUS}}` | `visual-guidelines.md` → Card border radius |
| `{{PROJECT_SLUG}}` | `shipwright_project_config.json` → `project_name`, lowercase, spaces→hyphens |
| `{{SCREENS_ARRAY}}` | Built from `design-manifest.md` — see template for format |

## Features (built into template)

- **Grid View**: Thumbnail cards with scaled iframe previews, grouped by split, feedback dot indicators
- **Viewer Mode**: Full-size iframe with toolbar (prev/next, dropdown navigator, counter)
- **Feedback Panel**: 340px right side, toggleable, with status buttons (Approved/Changes/Rejected), textarea with auto-save (500ms debounce), previous rounds history
- **Keyboard navigation**: `←` `→` navigate, `Esc` grid, `F` toggle feedback
- **localStorage persistence**: Feedback, round number, and history survive browser refreshes
- **Export**: Generates `design-feedback-roundN.md` via File System Access API save dialog + fallback download
- **Theming**: Viewer uses the project's own design tokens — feels native to the project

**Important:** The index.html is self-contained (inline CSS + JS, no external dependencies except the optional font CDN). It references screen/flow files via relative paths.
