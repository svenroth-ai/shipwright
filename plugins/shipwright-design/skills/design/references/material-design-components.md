# Material Design 3 Component Reference

> https://m3.material.io/components

## Overview

Material Design 3 (M3) is Google's open-source design system. For mockups,
we translate its visual patterns into standalone HTML+CSS using M3 tokens.

## Key Components to Replicate in Mockups

### Navigation
- **Navigation Rail**: Vertical icon bar (collapsed sidebar), 3-7 destinations
- **Navigation Drawer**: Full sidebar with labels, sections, dividers
- **Top App Bar**: Title + leading icon + trailing actions, scrollable variants
- **Bottom Navigation**: Mobile tab bar with icons + labels
- **Tabs**: Primary (full-width) or secondary (scrollable)

### Data Display
- **Card**: Elevated, filled, or outlined variants; 3 zones (media, header, body)
- **List**: Single-line, two-line, three-line with leading/trailing elements
- **Chip**: Assist, filter, input, suggestion variants
- **Badge**: Small (dot) or large (count) on icons
- **Tooltip**: Plain or rich with title + body

### Input
- **Text Field**: Filled or outlined, with label animation
- **Select/Menu**: Dropdown menus with dividers and icons
- **Checkbox / Radio**: M3 rounded checkbox, radio with ripple
- **Switch**: Thumb + track with optional icon
- **Date Picker**: Modal or docked calendar with range support
- **FAB**: Floating Action Button (primary, secondary, tertiary)
- **Segmented Button**: Single or multi-select toggle group

### Feedback
- **Snackbar**: Bottom-center, single action + dismiss
- **Dialog**: Basic, full-screen, or confirmation with headline + body + actions
- **Progress Indicator**: Linear (determinate/indeterminate) or circular
- **Skeleton Loader**: Shimmer animation on content shapes

### Layout
- **Top App Bar**: Center-aligned, small, medium, or large with collapse
- **Divider**: Full-width or inset horizontal rule
- **Bottom Sheet**: Standard or modal overlay from bottom edge

## M3 Design Tokens

### Color System (Tonal Palettes)
```css
:root {
  /* Primary */
  --md-sys-color-primary: #6750A4;
  --md-sys-color-on-primary: #FFFFFF;
  --md-sys-color-primary-container: #EADDFF;
  --md-sys-color-on-primary-container: #21005D;

  /* Secondary */
  --md-sys-color-secondary: #625B71;
  --md-sys-color-on-secondary: #FFFFFF;
  --md-sys-color-secondary-container: #E8DEF8;

  /* Tertiary */
  --md-sys-color-tertiary: #7D5260;
  --md-sys-color-on-tertiary: #FFFFFF;

  /* Error */
  --md-sys-color-error: #B3261E;
  --md-sys-color-on-error: #FFFFFF;

  /* Surface */
  --md-sys-color-surface: #FFFBFE;
  --md-sys-color-on-surface: #1C1B1F;
  --md-sys-color-surface-variant: #E7E0EC;
  --md-sys-color-outline: #79747E;
  --md-sys-color-outline-variant: #CAC4D0;
}
```

### Typography (Roboto)
```css
/* Display */
--md-sys-typescale-display-large: 57px / 64px Roboto;
--md-sys-typescale-display-medium: 45px / 52px Roboto;

/* Headline */
--md-sys-typescale-headline-large: 32px / 40px Roboto;
--md-sys-typescale-headline-medium: 28px / 36px Roboto;

/* Title */
--md-sys-typescale-title-large: 22px / 28px Roboto 500;
--md-sys-typescale-title-medium: 16px / 24px Roboto 500;

/* Body */
--md-sys-typescale-body-large: 16px / 24px Roboto;
--md-sys-typescale-body-medium: 14px / 20px Roboto;

/* Label */
--md-sys-typescale-label-large: 14px / 20px Roboto 500;
--md-sys-typescale-label-medium: 12px / 16px Roboto 500;
```

### Shape (Rounded Corners)
```
None:   0px   (chips in compact, some buttons)
XS:     4px   (text fields, chips)
S:      8px   (cards, small buttons)
M:      12px  (FAB, dialogs)
L:      16px  (large cards, sheets)
XL:     28px  (large FAB)
Full:   50%   (avatars, icon buttons)
```

### Elevation (Tonal Surface + Shadow)
```
Level 0: Surface (no shadow)
Level 1: Surface + 3% primary tint + 1dp shadow
Level 2: Surface + 5% primary tint + 3dp shadow
Level 3: Surface + 8% primary tint + 6dp shadow
Level 4: Surface + 11% primary tint + 8dp shadow
Level 5: Surface + 14% primary tint + 12dp shadow
```

## Mockup Translation Rules

When generating HTML mockups with Material Design 3:
1. Use CSS custom properties with `--md-sys-` prefix for all tokens
2. Use Roboto font from Google Fonts CDN
3. Apply M3 shape system (rounded corners per component type)
4. Use tonal surface elevation (background tint, not just box-shadow)
5. Include state layers: hover (8% opacity), focus (12%), pressed (12%)
6. Use M3 spacing: 4px base grid, 16px standard padding, 24px section gaps
7. Use realistic data, not placeholders
8. Apply ripple-style hover effects on interactive elements
