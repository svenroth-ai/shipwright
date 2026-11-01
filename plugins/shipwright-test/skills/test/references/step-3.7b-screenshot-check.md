# Step 3.7b: Screenshot Check — BLOCKING, Brief-package projects only

**Condition:** runs ONLY when Design applied a Brief package, i.e. `.shipwright/designs/brief-package-applied.json`
exists. Every other project: the tool answers `{"applies": false, "status": "skipped"}` (exit 0) and this step does
nothing — Step 3.7 stays exactly what it was (non-blocking, structural). Needs the running app (dev server from
Step 3) and Playwright (`playwright_setup.py` has run).

**What it is:** a Test-phase gate that compares the BUILT screens with the APPROVED design screens. It is **not** a
design-approval gate (D9): it never approves, waives, or changes a design.

**1. Run it** (after Step 3.7, before Step 3.8, dev server still up):
```bash
uv run "{plugin_root}/scripts/lib/screenshot_check.py" --cwd "{project_root}" --base-url "{dev_url}"
```
Per screen of `screen-routes.json` it screenshots the approved design screen (`.shipwright/designs/uploads/`, found through the
package's `screen-map.json`) and the built route in the same Chromium at 1280x800, then compares them.
`screen-routes.json` is read in Design's flat form (`{"01-login.html": "/login"}`) or the nested form
(`{"screens": [{"mockup": ..., "route": ...}]}`). A screen is compared as Design left it
(`.shipwright/designs/screens/NN-id.html`, review-loop edits included), else the approved upload; the result names the file
(`compared_with`). A dynamic route (`/items/[id]`) needs a `sample_route` key: switch that entry to the nested form.
You MAY add `sample_route` or missing route entries to `screen-routes.json`: that is test wiring, not a mockup.
A screen that is a STATE of one served page (a board tab, a pane, a modal) has no route of its own: give its entry the page's `route` plus `steps`, run on the built page before the shot: `{"click": "#tab-queue"}`, `{"fill": ["#q", "text"]}`, `{"wait_for": ".card"}` (nested form, e.g. `{"mockup": "04-queue.html", "route": "/", "steps": [{"click": "#tab-queue"}]}`). The step list is closed: click, fill, wait_for, selectors only, at most 10 per entry; no navigation or script step, anything else is an `error` for that screen. A step that cannot run fails that screen only, naming the step number; a polling board pays up to 5 s of network-idle wait per step. Each state needs its OWN design screen file (steps run on the built page only): a state with no screen of its own is an `error` to report, not a `fail` to fix. Steps must reach the state the screen shows, never a page that merely looks alike. Design writes the flat form, so add `steps` (flat dict value or nested entry) as test wiring. Only CSS animations are frozen, not JS-driven motion. Every screen is captured in a fresh browser context, so state one screen saves never reaches the next; the `steps` used are recorded in the screen's result. A screen with neither a route nor steps is an `error`. The capture injects nothing into the page, so the app's own Content-Security-Policy cannot block it. Every screen of the
package's `screen-map.json` must appear in `screen-routes.json` (a package screen that was never built is an `error`),
and an approved design screen that renders blank is an `error`. Only the first viewport (1280x800, the fold) is compared;
the viewport is recorded in the result. Run it only when the marker file exists (the tool also checks).

**Metric and tolerance (recorded in every result):** `grid-luma-occupancy-diff-ratio`. Each shot becomes a 32x20 grid;
a cell DIFFERS when its content flag (text/borders/controls present) differs or its mean luminance differs by more
than 0.10. A screen PASSES when differing cells / all cells <= **0.15**. One rule for every screen (plus two guards: a built screen with no content at all is a `fail`, an approved design screen with none an `error`). First calibration
on real Chromium: the right built screen scored 0.02, a blank page 0.30, an error page 0.31, another screen 0.99.
It sees layout and text occupancy, not wording. A `fail` is a STOP: nothing in this reference licenses continuing past it,
changing the tolerance, fonts or a screen, or waiving it; this step never waives it.

> Note (informational, not a rule): the approved screen holds the designer's sample text and the built page the app's real data, and text of a
> different length moves cells. In one end-to-end run (social-engagement-real) two screens showing a long recorded thread scored 0.158 and 0.163
> with system fonts and 0.1766 and 0.175 with the fonts bundled, while three short screens passed (0.08-0.13).

**2. What to do — every outcome (an unattended agent follows this table, nothing else):**

| Exit / `status` | Meaning | Do |
|---|---|---|
| 0 `pass` | every screen within tolerance | record it (step 3), continue to Step 3.8 |
| 0 `skipped` (`applies: false`) | no Brief package | record `skipped: no Brief package`, continue |
| 1 `fail` | at least one screen is over the tolerance | **STOP the test phase and report** the failing screens with `diff_ratio` and both screenshot paths. Do not continue to "done". |
| 2 `error` | the check could not run or compare a screen (no app, no browser, missing mockup, size mismatch, route not concrete) | **STOP and report** the `error` / `capture_error` text. An error is NOT a pass. If the text says Playwright or the browser is missing, run `playwright_setup.py` once (setup, not a waiver) and re-run; still `error` → STOP and report. |

Never: raise the tolerance, edit or regenerate an approved design screen or `uploads/`, delete a screenshot, mark a screen
"expected", skip the step, or approve anything. A fix is allowed only in the BUILT app (the screen's route/component)
followed by a re-run of the tool, max 3 rounds; still red → STOP and report as above.

**3. Record** in `shipwright_test_results.json`:
```json
{"screenshot_check": {"applies": true, "status": "pass", "captured": true, "metric": "grid-luma-occupancy-diff-ratio",
  "tolerance": 0.15, "passed": 2, "total": 2,
  "screens": [{"mockup": "01-dashboard.html", "route": "/dashboard", "status": "pass", "diff_ratio": 0.02}]}}
```
Record the tool's output unchanged (`captured` and `tolerance` are checked). With a Brief package the test-phase validator
BLOCKS unless this block has `applies: true`, `status: "pass"`, `captured: true` and the standard tolerance; never use
`--no-capture` or `--tolerance` for the recorded run. Completion gate: with a Brief package the layer's result must be `pass` — `fail`/`error` keep the test phase
`incomplete`. Without one: `skipped: no Brief package`.
