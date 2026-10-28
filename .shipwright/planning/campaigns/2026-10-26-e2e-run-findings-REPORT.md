# B7 operator E2E: findings report (input for a follow-up campaign)

Status: draft for the operator. Not a campaign brief yet, no triage cards filed (by decision).
Source: 11 real runs of `integration-tests/e2e-webui/` (test harness, PR #928). Run 11 finished: 70 min, pipeline
complete, hard items H01-H11 pass, S03 pass. Reports live outside the repo in `C:\01_Development\autorune2e\e2e-report\`.

## 1. What was proven

A Brief package (5 mockups, visual guidelines, scope) goes through the WebUI into a working chat-first app: project,
design, plan, build, test, all phases complete, app starts through the preview button, health answers 200, all six
chat commands behave as specified, screens match the approved mockups.

Not evaluated by the harness yet: soft items S01, S02, S04-S08 (layout, tabs, palette, no external calls, Test phase
ran, unknown-command answer, "gates a person would answer"). They need a rule or a reviewer; today they read
"not evaluated", which is not the same as pass.

## 2. Findings by plugin

"Guided too" = also hurts a person who runs the pipeline interactively. "Auto only" = only matters unattended.

| # | Plugin | Finding | Guided too? |
|---|---|---|---|
| F1 | design (Boundary gate) | Boundary gate looks at the dirty working tree. The project phase leaves its outputs uncommitted, so Design asks "Commit earlier output first?" in every brief run. | Yes |
| F2 | test (B3c screenshot check) | Cannot compare chat-only screens (pane states without a route) and cannot type chat commands. The harness had to take a recorded exemption in earlier runs. | Yes, any chat-first app |
| F3 | test (capture tool) | Capture can fail against the app's own security headers (CSP). | Yes |
| F4 | run / guided autonomy | Questions asked in guided mode appear only as a menu in the embedded terminal. The WebUI inbox does not list them. Someone watching only the inbox misses them. (WebUI side.) | Yes |
| F5 | Claude Code (not a plugin) | "Dangerous rm operation" safety dialog appears even under bypassPermissions. Plugins can avoid it by not issuing the pattern. | Yes |
| F6 | project (brief intake) | The project phase rejected the fixture brief with 42 "empty dimension" errors, which only showed in the Project phase, after the package was already accepted. Package intake should run the same content check. | Yes |
| F7 | run | Phase wording of gate questions varies ("Approve screens" / "Approve mockups"). Anything that answers gates has to match on meaning, not text. | Auto only |
| F8 | harness | Soft items not evaluated (see 1). Harness has no resume (a stopped run starts over, ~70-80 min). | n/a |

Harness-only issues found and fixed in PR #928 (no product change needed): task launch needs the Launch button,
profile card must be clicked, H11 pane check, preview alert.

## 3. Why the UI looks plain, and what it would take to look like the Social Engagement board

Observed: the built app looks like a clean but generic two-column chat plus list. That is faithful to the input,
not a pipeline defect. Evidence:

- Design phase handoff: "Approved Brief package mockups adopted as the design, unchanged" (DR-001). The build then
  followed those mockups; the screenshot check passes.
- The package's `visual-guidelines.md` is 8 lines: one accent colour, system sans-serif, 3 status colours. The
  mockups are minimal HTML with the same tokens. `styles.css` of the built app is 3.3 KB.
- The reference board (the social-engagement skill's `templates/board.html`, ~48 KB) differs in exactly what the
  package does not carry:
  - a warm, designed palette (cream/sand backgrounds, teal accent, rust highlight) instead of grey and blue
  - Inter plus a mono font, instead of system-ui
  - each platform drawn in its own native look (Reddit: IBM Plex, orange "where" label; Hacker News; LinkedIn
    with avatar and role line), instead of one identical card for all three
  - richer content per thread (post text, stats, comments, avatar), a comment-link popover, status per thread
  - the seed data that fills those fields

So the gap is input richness, plus one process question: when a package is present, Design copies it and does not
look for improvements. Brand extraction (step 2.5) and the design interview are skipped for packages.

## 4. What to try (hypotheses, cheapest first)

1. **Richer package, same pipeline.** Rebuild the fixture from the reference board: real tokens, fonts, per-platform
   card styles, richer seed. Re-run. If the app then looks like the board, the pipeline is fine and only the
   package guidance needs work. One run, ~70 min.
2. **Reference input.** Allow the package to carry a reference (screenshot or HTML of the target look) and have
   Design extract tokens from it (the step 2.5 brand extraction already exists, skipped today for packages).
3. **Package quality gate at intake.** Warn when visual guidelines are thin (few tokens, one font, no per-type
   component styles) so the weak input is visible before 70 minutes are spent. Ties to F6.
4. **Design polish pass inside package mode.** Today DR-001 adopts mockups unchanged. An optional pass that raises
   fidelity without changing structure would help when the package is a rough sketch. Riskier: it moves away from
   "approved package = contract". Only if 1 to 3 are not enough.
5. **Make fidelity measurable.** S01, S02, S04 become checks (colours from tokens, tab count, status badges), so
   "looks right" is not a matter of opinion in the next report.

Recommended order: 1, then 3 (cheap, guards the input), then 2. Hold 4.

## 5. Proposed campaign shape (to discuss, not decided)

Units, each guided and auto: (A) boundary gate vs uncommitted prior-phase output (F1); (B) screenshot check for
chat-first screens plus CSP-safe capture (F2, F3); (C) package intake content check at project intake (F6) and
thin-guidelines warning; (D) richer reference fixture and design-input path (section 4, 1 to 2); (E) soft items as
checks (F8); (F) WebUI inbox shows terminal questions (F4, lives in the WebUI repo, separate card there).
F5 and F7 need no unit: avoid the rm pattern, keep gate answering meaning-based.

## 6. Open questions for the operator

- Is the target look "the Social Engagement board as it is today" or "any good-looking app from a Brief"? The first
  is a fixture fix, the second needs a product change (section 4, items 2 and 4).
- Should the package stay a hard contract (mockups unchanged), or may Design improve it?
- Which of the soft items matter enough to become hard checks?

## 7. Operator direction (2026-10-27): replaces the guesses in sections 4 and 6

1. **The app shape was wrong.** A skill-backed app needs no chat interface: the chat is the Claude app. What it needs
   is a HTML frontend (the board), a Python backend and JSON files as data store. The skill owns a data folder for
   that JSON. The stack profile is modelled on the social-engagement skill (skill + local served board + data folder),
   not on `chat-first-json`. Consequence: the fixture, the chat map, harness checks H06-H11 (chat commands) and the
   B1-B3 chat-first design path describe the wrong product for this class of app and need rethinking.
2. **Look and feel comes from a kit, tokens come from the brand.** Design ships a complete Untitled UI profile (every
   component the screens need, as HTML/CSS). The visual guidelines or a brand guideline (e.g. from claude.ai) carry
   only colours, fonts and similar tokens. Mockups are composed from the kit, not invented. Today
   `untitled-ui-components.md` is a 52-line description of components to imitate, not a usable kit.

Effect on the campaign: unit (D) becomes "Untitled UI kit + tokens-only guidelines" (structural, replaces the richer
fixture idea); a new unit covers the app shape (skill + board + JSON profile and a Brief package for it); the harness
then tests backend API and board HTML instead of chat commands.

## 8. Operator addition (2026-10-27): the stack profile must describe the host

The chat-first stack profile has to say what the app IS, not only which files it has: a **skill (better: a plugin)**
that runs inside the Claude desktop app or in the terminal, where the **UI and the backend are a companion** to it
(the skill is the front door, the served board plus Python backend with JSON data folder are the companion the skill
starts and talks to). Today `chat-first-json` only knows `ui_host: served-pane`. Open design points for that unit:
profile fields for `host` (desktop app | terminal), `delivery` (skill | plugin), `companion` (ui + backend, started and
stopped by the skill), data folder location; and what Build/Test/Deploy do with a plugin-shaped app. Separate unit
from the Untitled UI kit (which is only look and feel).
