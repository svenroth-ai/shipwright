# Iterate Spec: e2e-fixture-real-skill-variant

- **Run ID:** iterate-2026-10-29-e2e-fixture-real-skill-variant
- **Type:** feature (test fixture + operator harness; no shipped plugin behaviour)
- **Complexity:** medium (raised from the history-calibrated `small`: five scope items, a new Brief package, three harness checks, positive evidence from the card)
- **Status:** in progress
- **Source:** triage card trg-5fd4e7b1 (run 12 comparison `autorune2e/vergleich-echte-skill-vs-testapp.md`); depends on trg-af4fff29, whose harness items are on main (#954: loopback ignored by S05, S06 total rule, preview origin in the report, auth-failure stop).

## Goal
The E2E run can build a second skill-backed app that is shaped like the real `social-engagement` skill (master-detail board, svenroth.ai tokens and fonts, platform-like thread rendering, Copy reply, status filter with skipped/expired, keywords as sources) whose hits come from an exchangeable `fetch_items()` adapter replaying recorded Syften/Apify answers, and the harness evaluates it with matching checks. The default fixture is unchanged.

## Acceptance Criteria
- [x] AC1 New Brief package `integration-tests/fixtures/social-engagement-real/` (brief.md/json, scope, screen-map, visual-guidelines with brand tokens, five master-detail mockups) plus its answer key `social-engagement-real-expected-result.md`; package hash valid, intake warning-free.
- [x] AC2 The hit source is specified as `backend/sources/` exposing `fetch_items(sources)`; without a token it replays `seed/recorded/syften.json` and `seed/recorded/apify_linkedin.json` (Syften- and Apify-shaped), so tests need no network and no keys.
- [x] AC3 Harness: `SHIPWRIGHT_E2E_FIXTURE=social-engagement-real` selects the variant; S02 (master-detail, counts, status filter incl. skipped/expired, Copy reply, no Keywords tab), S04 (colours, sizes, and font families) and S05 (only `backend/sources/` may name a service; `fetch_items`; recorded answers complete) are evaluated in their variant form; H06-H11 + new H14 have a real-API checker. Default fixture and its 48 existing unit specs unchanged and green.
- [x] AC4 The design kit is judged against the new mockups; gaps are listed below and filed as triage cards.
- [x] AC5 Optional soft check S09: a headless `claude -p` session with the built plugin loaded and the phrase "open the social engagement board" calls a skill. Opt-in (`SHIPWRIGHT_E2E_SKILL_TRIGGER=1`), never fails the run.

## Spec Impact
- **Classification:** none
- **NONE justification:** test fixtures and the operator E2E harness only (`integration-tests/`); no plugin, hook, phase or FR behaviour changes. Tests carry `@covers FR-01.06`, the FR the E2E harness already belongs to.

## Out of Scope
- Running the real E2E (operator-started, costs tokens); the new variant is unproven against a live run until then.
- Making the Plan/Build/Design pipeline plugins handle the new brief better (findings go to the operator after a real run).
- A skill that works by itself (modes run/keywords/setup) instead of start/stop: the card's point 3 beyond the S09 trigger check is a pipeline-plugin topic, not a fixture one.

## Design Notes (decisions)
- **Opt-in selector, default unchanged.** `activeFixture()` refuses an unknown name instead of defaulting, so a typo cannot silently run the other app. Per-fixture differences sit behind one `Variant` interface (`src/variant.ts`), so the spec does not branch.
- **Statuses.** `expired` is derived (new/drafted older than 14 days), never stored; the recorded answers must therefore contain at least two old items, so a fresh run shows the status.
- **Brand fonts are checked by the harness itself.** The intake token check reads only `--color-*` and `--font-size-*`; font families would otherwise go unverified. S04 compares the first family of the served `--font-family` / `--font-mono` with the guidelines.
- **Base size 16px, not the real board's 15px.** The kit's token check demands base >= 16px (accessibility) and the fixture must stay warning-free at intake; the difference is a recorded kit finding, not a fixture divergence to hide.
- **S05 variant.** Services may be named only under `backend/sources/`; key reads are allowed only there too. The recordings live in `seed/recorded/` (excluded from the code scan like `seed/`), `tests/` use them through the same adapter code path.
- **S09 is soft.** `claude -p ... --allowedTools Skill --max-turns 2 --plugin-dir <project>`: only the Skill tool is allowed, so the call cannot start the companion. Not run unless asked for; the output parser is unit-tested on a recorded stream shape, **the live `claude` flags are unverified until an operator run**.

## Kit judgment (item 4): the Untitled UI kit against the new mockups
Judged statically against `kit.css` (class inventory), `tokens-contract.md`, `brief-compose.md` and the kit examples; a real Design run on the package was **not** made (operator-started, model cost). Covered means a kit class does the job as is.

| Need in the mockups | Kit today | Verdict |
|---|---|---|
| Status filter | `.filter-select` / `.select` | covered |
| Status badges incl. skipped (neutral) and expired (error) | `.badge-neutral`, `.badge-error` | covered |
| Selected list row | `.list-item.active` | covered |
| Buttons, inputs, textarea, feedback field | `.btn*`, `.field-*` | covered |
| Sources panel (rows with kind, query, status) | `.list`, `.tag`, `.modal` / `.drawer` | covered |
| **G1 Thread rendering like the platform**: post with author/points/age and a nested comment tree | no comment, post or thread class; `.feed-item` is a timeline with a rail, not a tree; `.card-meta` is a single line | **gap** |
| **G2 Master-detail page**: fixed-width list pane that keeps its place beside one selected item, own scroll, collapses to a picker on a narrow screen | `.detail-layout` is main + 320px *sidebar* (fields), `.sidebar`/`.app-layout` is navigation; `.list` is a card with no pane behaviour | **gap** |
| **G3 Count on a switcher entry** (Reddit 4 / Hacker News 3 / LinkedIn 3) | `.segmented-item` and `.tab` have no count slot; `.badge` inside them is unstyled for the selected state | **gap** (small) |
| **G4 Draft callout with a Copy action** | `.card` + `.btn`; no highlighted callout variant, no copy affordance or "copied" feedback | **gap** (small) |
| **G5 Mono eyebrow / label style** (uppercase, letter-spaced, `--font-mono`) | `--font-mono` is used only by `.kbd` and `.code` | **gap** (small) |
| **G6 Brand font families through the package path** | `brief_intake_checks` reads `--color-*`/`--font-size-*` only; `tokens-contract` lists `--font-family`/`--font-mono` but nothing checks that a package's declared families reach the composed screen | **verify**: S04 now checks it on a real run |
| Base size 15px (real board) | token check demands >= 16px | finding: the kit's accessibility floor is stricter than the real board; fixture follows the kit |

Gaps G1 and G2 decide whether a composed screen can look like the real board at all; G3-G5 are polish; G6 is answered by the first real run of the variant.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| Fixture `brief.md` (route and adapter contract) | `board-api-real.ts`, `project-checks-adapter.ts` | routes, `backend/sources/`, `seed/recorded/*.json` |
| `visual-guidelines.md` | `tokens.ts` (`parseTokens`, `parseFontTokens`) | `- --name: value` lines |
| `claude -p --output-format stream-json` | `skill-trigger.ts` (`skillsCalled`) | JSON lines, `assistant` events with `tool_use` blocks |

## Confidence Calibration
- **Boundaries touched:** the three above. No serialized format owned by the framework changed.
- **Empirical probes run:** package hash verified through `verify_package`; intake content and token checks return no issues; `tsc --noEmit` clean; 54/54 harness unit specs (48 existing + 6 new: faithful in-memory companion passes, each flaw fails its own item; the five approved mockups in a real browser satisfy S01/S02/S04 including fonts); 24/24 fixture and harness structure tests.
- **Not probed:** a real E2E run on the new variant; the live `claude -p` flags of S09; how Design composes the new mockups (G6).
- **Test Completeness Ledger:** see the F5c entry; the live run, the live `claude` call and the Design composition are `untestable` (`requires-external-nondeterministic-service`).

## Reviews and what changed because of them
- **spec-reviewer (opus):** PASS, no divergence.
- **code-reviewer (opus):** PASS with 7 findings, all fixed: recorded timestamps are re-based on replay and the status filter starts at "all" (brief.md); S09 counts only the project's own skills and names the Windows `.cmd` limit; `openRow` falls back to buttons/links and matches a title prefix; the status-filter detection matches whole option text and ignores the platform switcher.
- **External code review (GPT + GLM, full diff):** verdicts revise / approve. Fixed: a switcher count of 0 where threads exist fails S02; `skipped` and `expired` must be rendered when the run's data has them; recordings are validated field by field and must hold two items more than 14 days older than the newest; a unit test where only a click reveals the thread.
- **External plan review (run after the build, over this spec; no mini-plan existed before build):** verdicts revise / revise. Fixed: replay is the default even when tokens are set (`SOCIAL_ENGAGEMENT_LIVE=1` is the explicit opt-in), recordings use invented handles.
- **CI PR review (Tier 3, haiku):** BLOCK on two findings. (1) S09 loaded the model-written project with `--plugin-dir`, which can run plugin hooks: fixed, S09 now loads a scratch copy holding only `skills/` and a manifest without `hooks`/`mcpServers`/`agents`/`commands` (`stagePluginCopy`, unit-tested). (2) "recorded answers absent from the diff": not a defect, the fixture is a Brief and the build creates `seed/recorded/` from `brief.md`; stated in the answer key. Non-blocking comments left as is.
- **Not done:** `plan_internal` and `architecture_internal` were not run (recorded `not_run`). **Known limit (G6):** S04 compares the declared font tokens, not that the font files loaded or are applied to body and mono elements; a computed-style check is a follow-up for the first live run. `doubt` is `not_applicable` (no migration, async, cross-plugin or irreversible touch).
