# Token contract

What a brand or visual guideline must supply so the kit renders. `kit.css` reads only these names; every file in `tokens/`
(`warm`, `clean`, `bold`) is a complete example. All colours are solid hex (no rgba), except `--color-overlay`.

## Colours

| Token | Meaning | Rule |
|---|---|---|
| `--color-bg` | Page background | |
| `--color-surface` | Cards, inputs, modals | Usually white |
| `--color-table-header` | Table header, code block, subtle panel | A light solid colour, distinct from bg (guidance, not tested) |
| `--color-text` | Body text | 4.5:1 on bg and surface (aim 10:1+) |
| `--color-muted` | Secondary text, labels, inactive items | 7:1 on bg, surface, table-header, hover, primary-soft and border |
| `--color-primary` | Main action, active state | 4.5:1 against `--color-on-primary` |
| `--color-on-primary` | Text and icons on primary | |
| `--color-primary-hover` | Primary button on hover | Darker than primary (guidance); on-primary stays 4.5:1 on it (tested) |
| `--color-primary-soft` | Deliberate light selected / highlight colour | Solid, not a tint of primary; muted text stays 7:1 on it |
| `--color-primary-ring` | Optional soft ring colour; the kit's focus ring uses `--color-focus` | Solid |
| `--color-secondary` | Optional accent; the kit does not read it | |
| `--color-hover` | Row, menu and ghost-button hover | Solid; muted text stays 7:1 on it |
| `--color-border` | Dividers, card edges | Decorative only |
| `--color-border-strong` | Edge of inputs, selects, checkboxes, dropzones | 3:1 on surface and bg |
| `--color-focus` | Focus ring | 3:1 on surface and bg |
| `--color-success` `--color-warning` `--color-error` `--color-info` | Status text and icons | 4.5:1 on their `-bg` and on surface |
| `--color-success-bg` `--color-warning-bg` `--color-error-bg` `--color-info-bg` | Alert, badge and toast fill | Light, solid |
| `--color-overlay` | Dim layer behind modal and drawer | The only rgba |

## Type

| Token | Meaning | Rule |
|---|---|---|
| `--font-family` | UI and heading font | Load it in the page `<head>` |
| `--font-mono` | Code, keys, numbers in code | |
| `--font-size-base` | Body | 16px or more |
| `--font-size-sm` | Labels, table cells, meta | 14px or more |
| `--font-size-lg` `--font-size-h3` `--font-size-h2` `--font-size-h1` | Larger text and headings | h3 <= h2 <= h1 (tested) |
| `--font-weight-heading` | Heading weight | |

## Shape and depth

| Token | Meaning |
|---|---|
| `--radius` / `--radius-lg` | Controls / cards, modals |
| `--card-border` | `none` when cards use a shadow, else `1px solid <border>` |
| `--card-shadow` / `--card-shadow-hover` | Card at rest / hover; layered, soft |
| `--shadow-sm` | Inputs and small controls |
| `--shadow-lg` | Popover, modal, drawer, calendar |
| `--sidebar-width` | Width of the left sidebar layout |

## Spacing

`--space-1` 4px, `--space-2` 8px, `--space-3` 12px, `--space-4` 16px, `--space-5` 24px, `--space-6` 32px. Change only
with a reason; the kit's rhythm depends on the 4px grid.

## Checked by tests

Every token above defined in every token set; no literal colours or font sizes in `kit.css`; contrast rules in the
Rule column unless marked guidance; solid hex for colours; font-size minimums; every example class is defined in `kit.css`
and every `kit.css` class is shown by an example (page layouts and fixed overlays excepted).
