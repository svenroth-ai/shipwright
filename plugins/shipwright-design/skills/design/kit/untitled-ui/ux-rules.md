# UX rules the kit follows

Short, checkable rules. Each says where the kit enforces it. Sources are the research behind the rule, not a standard
to cite verbatim.

## Accessibility (WCAG 2.2 AA)

| Rule | Kit |
|---|---|
| Text contrast 4.5:1, controls and focus 3:1 | `tests/test_untitled_ui_kit.py` checks every token set, including text on hover, selected and status backgrounds |
| Pointer targets at least 24x24 px (2.5.8); the kit uses 32 px for small and 40 px for normal controls | `.btn`, `.btn-sm`, `.segmented-item`, `.popover-item` |
| Visible focus on everything clickable, 3 px, 3:1 against the surface | `:focus-visible` in `kit.css`; search fields no longer switch it off |
| Never use colour alone for state | badges, alerts and errors always carry words ("Error: ...") |
| Errors named in text, with a suggested fix; link to the field in a long form | `.field-error`, `.error-summary` |
| Motion off when the system asks for it | `prefers-reduced-motion` block |
| Placeholder is a hint, never the label | gallery form: label above, hint below |

Sources: [WCAG 2.2 what's new](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/), [University of Arizona WCAG 2.2 highlights](https://accessibility.arizona.edu/policies-governance/wcag-22-highlights).
Focus Appearance (2.4.13) is AAA; the kit meets its size and contrast anyway because it costs nothing.

## Forms

- One column (`.form-grid`; `.form-grid-2` opts into two for short paired fields), label above the field, one primary action per form; Cancel is a secondary button.
- Validate when the user leaves a field, clear the message once the value is valid; long forms get an error summary
  on top with the count and one link per field.
- Dates and similar multi-part inputs may share a line; nothing else does.

Sources: [WFP form design](https://designsystem.wfp.org/how-tos/form-design), [Carbon form usage](https://v9.carbondesignsystem.com/components/form/usage/), [Aon form inputs](https://designsystem.aon.com/components-3/form-elements/form-inputs).

## Loading, empty and error are three different screens

| State | Show | Kit |
|---|---|---|
| Loading, shape known (lists, cards, pages) | skeleton | `.skeleton` |
| Loading, an action (button, save) | spinner inside the control, `aria-busy` | `.spinner` |
| Empty (loaded, nothing there) | what this is and the next step as a button; never a loader | `.empty-state` |
| Failed | message and a retry button; stop any skeleton or spinner | `.alert-error` + `.btn` |

Under 100 ms show nothing; past about 10 s show a progress bar with an estimate, an endless spinner reads as failure.

Sources: [PatternFly skeleton guidelines](https://patternfly.org/components/skeleton/design-guidelines), [Intility loading state](https://bifrost.intility.com/design/loading-state), [Staffbase loading pattern](https://spark.staffbase.com/patterns/loading), [UX Collective: loaders and empty states](https://uxdesign.cc/when-to-use-loaders-empty-states-ebd23cecc7d6).

## Lists, tables and dashboards

- Say when the data was last updated and which filter is active; offer a reset (`.meta-line`, `.tag-row`, "Reset filters").
- Reversible actions get a toast with Undo, not a confirmation dialog; confirm only for destructive ones.
- Numbers are right-aligned with tabular figures (`.num`); long tables scroll inside a container with a sticky header
  (`.table-container.scroll`).
- Every element has to help the user understand the data or the action; remove the rest.

Sources: [10 UX heuristics in dashboard design](https://nastengraph.substack.com/p/10-ux-heuristics-in-dashboard-design), [Playfair Data on Nielsen's heuristics](https://playfairdata.com/how-nielsens-usability-heuristics-apply-to-visual-analytics/), [Nielsen heuristics overview](https://helio.zurb.com/ux-research/laws-of-ux/nielsens-heuristics/).

## Type and spacing

- Body 16 px at least, small text 14 px at least (test-enforced), line height 1.5, headings 1.1 to 1.3.
- Running text at most about 70 characters wide (`.measure`, applied to descriptions).
- Spacing on a 4 px grid: `--space-1` (4) to `--space-6` (32); new rules use the tokens. Older component rules still hold some typed pixel values: only colours and font sizes are test-enforced.

Sources: [US Web Design System typography](https://designsystem.digital.gov/components/typography/), [EC component library typography](https://ec.europa.eu/component-library/ec/guidelines/typography), [10 principles for typography in UI](https://uxdesign.cc/10-principles-for-typography-usage-in-ui-design-a8f038f43ffd).

## Colour control

Hover, selected and ring colours are chosen solid colours (`--color-hover`, `--color-primary-soft`), never a transparent
tint of the primary. A test fails a token set that uses anything but solid hex for its colours (the page overlay excepted).
