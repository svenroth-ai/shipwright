# Iterate Spec: design-kit-reply-board

- **Run ID:** iterate-2026-10-29-design-kit-reply-board
- **Type:** feature (design plugin kit)
- **Complexity:** medium (new kit components and layout, gallery, docs; two parts)
- **Source:** kit judgment G1-G6 of iterate-2026-10-29-e2e-fixture-real-skill-variant (trg-1dee28e1)

## Goal
A composed screen in the Untitled UI kit can look like the real reply board: post with nested comment tree, master-detail layout, counts on switchers, highlighted draft with copy action, mono eyebrow label. Everything derives from Untitled UI patterns and the existing tokens.

## Acceptance Criteria
- [ ] AC1 (G1) `thread`, `thread-meta`, `comment-tree`, `comment`, `comment-head`, `comment-body`: post with author, points, age and replies nested by depth; derived from the Untitled UI feed item.
- [ ] AC2 (G2) `master-detail`, `master-pane`, `master-picker`, `detail-pane`: fixed-width list pane beside one selected item with its own scroll; below 900px the list is replaced by a select picker.
- [ ] AC3 (G3) `count` slot inside `tab` and `segmented-item`, styled for the selected state (Untitled UI tab badge).
- [ ] AC4 (G4) `callout`, `callout-head`, `callout-text`, `copy-btn` (+ `copied` state), derived from the Untitled UI code snippet copy button.
- [ ] AC5 (G5) `eyebrow`: uppercase, letter-spaced `--font-mono` label.
- [ ] AC6 No new tokens, no literal colours or font sizes; gallery, examples and docs updated; G6 and the 16px floor documented as findings, not built.

## Spec Impact
- **Classification:** none
- **NONE justification:** design kit styling only; no phase, hook or FR behaviour changes. Tests carry `@covers FR-01.04`, the FR of the kit.

## Out of Scope
G6 (font reach check in brief_intake_checks): verify on the first live run of fixture social-engagement-real. Lowering the 16px base floor.

## Affected Boundaries
| Producer | Consumer | Format |
|---|---|---|
| `kit.css` classes | gallery/board fragments, snippets, examples builder | class inventory (tests both directions) |

## Confidence Calibration
- **Boundaries touched:** kit.css to fragments, examples, token contract.
- **Empirical probes run:** 222 design-plugin tests green; example builder `--check` current; ruff clean; verify_local 3/3.
- **Not probed:** rendering in a real browser, a live Design run composing the new classes.
- **Test Completeness Ledger:** see F5c entry; browser rendering is `requires-manual-visual-judgment`.

## Internal Architecture Review
architecture-internal-reviewer (opus), run after the build over the brief and this spec: verdict **build** as option (b), classes in `kit.css`. Alternatives rejected: (a) per-project CSS breaks the kit rule that the kit owns component looks; (c) a second optional file adds a second contract for ~45 lines. Changes made because of it: the remembered 72px Layout A offset was dropped (the pane scrolls with the page there; it sticks only below the fixed 56px Layout B top nav), the docs group was renamed neutrally ("Master-detail and discussion"), and the docs now say the picker is presentational and that other `master-pane` children are hidden below 900px. Kept as is: `callout` stays its own class (primary-soft fill plus a copy action, a different job than `alert`), indent below 900px already shrinks.

## Internal Plan Review
opus-plan-reviewer (opus), run after the build over this spec. Verdict revise. Its one HIGH (test, CSS and docs disagree on the Layout A sticky pane) was stale: it read the tree mid-edit, the current CSS, test and docs all say `position: static`, and the 224 tests were re-run on the current tree. Fixed: long URLs wrap (`overflow-wrap: anywhere` on thread, comment and callout text), the callout accent is `--color-primary`, the docs say `copy-btn` is used with `btn btn-secondary btn-sm`. Not done, by decision: a visually-hidden class for the `role="status"` copy region (the kit has none; the docs say how to announce it), a pixel-level screenshot check (browser rendering stays `requires-manual-visual-judgment`).

## External Plan Review and the browser check
External plan review (GLM + GPT, over this spec after the build): verdicts revise / revise. Both asked for a real render. Done with headless Edge on the built `gallery-warm.html` at 1280px and 600px: wide, the list pane sits beside the thread card; at 600px a picker with its chevron replaces the list and the thread card is full width; nested replies carry the left rule; the eyebrow is mono uppercase; counts show in the segmented control; the callout carries the primary accent and the copied button. Not exercised: independent scrolling of a long list, depth 5+ nesting, the Layout B sticky offset on a real page (the gallery has no top-nav page). Left as documented limits: the picker is presentational (docs say a mockup needs its own script), no indent cap beyond the narrow-screen reduction.
