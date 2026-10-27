# CSS Variable Sets

Complete `:root` blocks for each **flavor x character** combination. Copy the matching block into the Page Shell from `snippets-layout.md`.

> **Custom flavor**: If the user uploads their own guidelines, map their tokens to the same variable names listed in the **Variable Reference** section below.

---

## Variable Reference

Every snippet in `snippets-layout.md` and `snippets-components.md` uses these variables:

| Variable | Purpose |
|----------|---------|
| `--font-family` | Primary font stack |
| `--font-size-base` | Body text (14-16px; flavor `untitled-ui` needs at least 16px) |
| `--font-size-sm` | Small text (13-14px; flavor `untitled-ui` needs at least 14px) |
| `--font-size-lg` | Subheadings (18px) |
| `--font-size-h1` | Page title (24-28px) |
| `--font-size-h2` | Section title (20-22px) |
| `--font-size-h3` | Card/section heading (16-18px) |
| `--font-weight-heading` | Heading weight (600-700) |
| `--color-bg` | Page background |
| `--color-surface` | Card/panel background |
| `--color-text` | Primary text |
| `--color-muted` | Secondary/hint text |
| `--color-primary` | Accent color |
| `--color-primary-hover` | Accent hover |
| `--color-primary-ring` | Soft ring behind a focused input (solid colour in the kit; snippets may still use a tint) |
| `--color-on-primary` | Text on primary bg |
| `--color-secondary` | Secondary accent |
| `--color-border` | Borders and dividers |
| `--color-hover` | Row/item hover background |
| `--color-success` | Success state |
| `--color-warning` | Warning state |
| `--color-error` | Error/danger state |
| `--color-table-header` | Table header row bg |
| `--radius` | Default border-radius |
| `--radius-lg` | Card/container radius |
| `--card-border` | Card border style (e.g. `1px solid var(--color-border)` or `none`) |
| `--card-shadow` | Card shadow |
| `--card-shadow-hover` | Card shadow on hover |
| `--sidebar-width` | Sidebar width (Layout A only) |

**Additional tokens the Untitled UI kit needs** (full meaning and contrast rules: [tokens-contract.md](../kit/untitled-ui/tokens-contract.md)):

| Variable | Purpose |
|----------|---------|
| `--font-mono` | Code and keys |
| `--color-primary-soft` | Solid light selection colour (not a tint of primary) |
| `--color-border-strong` | Edge of inputs and controls (3:1 on the surface) |
| `--color-focus` | Focus ring colour (3:1) |
| `--color-info` | Info state text and icon |
| `--color-{info,success,warning,error}-bg` | Light solid fill for alerts, badges, toasts |
| `--color-overlay` | Dim layer behind modal and drawer |
| `--space-1` … `--space-6` | 4px grid: 4, 8, 12, 16, 24, 32 |
| `--shadow-sm` / `--shadow-lg` | Inputs / popovers, modals, drawers |

---

## Untitled UI x Warm / Clean / Bold

All three untitled-ui looks live in the kit as real token sets, not as blocks here: `../kit/untitled-ui/tokens/warm.css`,
`clean.css`, `bold.css` and `svenroth.css`. Paste the one that matches into the `:root` of the page together with
`../kit/untitled-ui/kit.css` (see [untitled-ui-components.md](untitled-ui-components.md)). They are contrast-tested; a
copy here would drift. Token meanings and rules: [tokens-contract.md](../kit/untitled-ui/tokens-contract.md).

---

## Material Design x Warm & Premium

```css
:root {
  /* Typography */
  --font-family: 'Roboto', system-ui, sans-serif;
  --font-size-base: 14px;
  --font-size-sm: 13px;
  --font-size-lg: 18px;
  --font-size-h1: 28px;
  --font-size-h2: 22px;
  --font-size-h3: 16px;
  --font-weight-heading: 500;

  /* Colors — M3 tonal with warm palette */
  --color-bg: #fdf8f4;
  --color-surface: #ffffff;
  --color-text: #1c1410;
  --color-muted: #7a6e64;
  --color-primary: #6d4c3d;
  --color-primary-hover: #5a3d30;
  --color-primary-ring: rgba(109, 76, 61, 0.12);
  --color-on-primary: #ffffff;
  --color-secondary: #9c7c62;
  --color-border: #e6ddd6;
  --color-hover: rgba(109, 76, 61, 0.04);
  --color-success: #2d6a4f;
  --color-warning: #b45309;
  --color-error: #b3261e;
  --color-table-header: #f8f3ef;

  /* Shape — M3 uses larger radii */
  --radius: 12px;
  --radius-lg: 16px;
  --card-border: none;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(109,76,61,0.03);
  --card-shadow-hover: 0 4px 16px rgba(0,0,0,0.12);
  --sidebar-width: 260px;
}
```

---

## Material Design x Clean & Modern

```css
:root {
  /* Typography */
  --font-family: 'Roboto', system-ui, sans-serif;
  --font-size-base: 14px;
  --font-size-sm: 13px;
  --font-size-lg: 18px;
  --font-size-h1: 28px;
  --font-size-h2: 22px;
  --font-size-h3: 16px;
  --font-weight-heading: 500;

  /* Colors — M3 default palette */
  --color-bg: #fef7ff;
  --color-surface: #ffffff;
  --color-text: #1c1b1f;
  --color-muted: #79747e;
  --color-primary: #6750a4;
  --color-primary-hover: #574394;
  --color-primary-ring: rgba(103, 80, 164, 0.12);
  --color-on-primary: #ffffff;
  --color-secondary: #625b71;
  --color-border: #cac4d0;
  --color-hover: rgba(103, 80, 164, 0.04);
  --color-success: #059669;
  --color-warning: #d97706;
  --color-error: #b3261e;
  --color-table-header: #f7f2fa;

  /* Shape — M3 */
  --radius: 12px;
  --radius-lg: 16px;
  --card-border: 1px solid #cac4d0;
  --card-shadow: none;
  --card-shadow-hover: 0 2px 8px rgba(0,0,0,0.1);
  --sidebar-width: 260px;
}
```

---

## Material Design x Bold & Energetic

```css
:root {
  /* Typography */
  --font-family: 'Roboto', system-ui, sans-serif;
  --font-size-base: 14px;
  --font-size-sm: 13px;
  --font-size-lg: 18px;
  --font-size-h1: 28px;
  --font-size-h2: 22px;
  --font-size-h3: 16px;
  --font-weight-heading: 500;

  /* Colors — M3 with vivid accents */
  --color-bg: #fffbfe;
  --color-surface: #ffffff;
  --color-text: #09090b;
  --color-muted: #71717a;
  --color-primary: #7c3aed;
  --color-primary-hover: #6d28d9;
  --color-primary-ring: rgba(124, 58, 237, 0.12);
  --color-on-primary: #ffffff;
  --color-secondary: #f97316;
  --color-border: #e4e4e7;
  --color-hover: rgba(124, 58, 237, 0.04);
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  --color-table-header: #faf9fc;

  /* Shape — M3 with bold character */
  --radius: 12px;
  --radius-lg: 16px;
  --card-border: none;
  --card-shadow: 0 4px 16px rgba(0,0,0,0.08), 0 0 0 1px rgba(124,58,237,0.05);
  --card-shadow-hover: 0 8px 32px rgba(0,0,0,0.12);
  --sidebar-width: 260px;
}
```

---

## Custom Flavor: Variable Mapping Guide

When the user uploads their own design guidelines, map their tokens to the snippet variables:

1. **Read uploaded file** — Extract: primary color, font, background, border style, radius, shadow
2. **Map directly** where the user provides explicit values
3. **Derive missing values** from provided ones:

| If user provides... | Derive... |
|---------------------|-----------|
| Primary color | `--color-primary-hover` (darken 10%), `--color-primary-ring` and `--color-primary-soft` (a chosen light solid colour, never a transparent tint), `--color-hover` (a chosen light solid colour) |
| Background color | `--color-surface` (lighter or white), `--color-table-header` (a light solid colour next to bg and surface) |
| Font family | All `--font-size-*` keep defaults, `--font-weight-heading` from user or default 600 |
| Border color | `--card-border` (`1px solid {border}`), if no border specified use shadow-only |
| Border radius | `--radius` (default), `--radius-lg` (radius + 4px) |

4. **Always provide** success/warning/error colors — use defaults if not in user's guidelines:
   - Success: `#047857`
   - Warning: `#b45309`
   - Error: `#b91c1c`

   (These pass 4.5:1 on white; the lighter Tailwind defaults do not.) For flavor `untitled-ui` also supply every kit token in [tokens-contract.md](../kit/untitled-ui/tokens-contract.md).

5. **Write the `:root` block** following the same structure as the preset blocks above

### Brand Extraction Override

If Step 2.5 (Brand Extraction) was performed, the extracted tokens take precedence over the flavor defaults:

```css
:root {
  /* Start with selected flavor × character block */
  /* Then override with extracted values: */
  --font-family: {{EXTRACTED_FONT}};
  --color-primary: {{EXTRACTED_PRIMARY}};
  --color-bg: {{EXTRACTED_BACKGROUND}};
  /* ... only override what was extracted, keep defaults for the rest */
}
```
