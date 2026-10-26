# Step 3.7b: Screenshot Check — BLOCKING, Brief-package projects only

**Condition:** runs ONLY when Design applied a Brief package, i.e. `.shipwright/designs/brief-package-applied.json`
exists. Every other project: the tool answers `{"applies": false, "status": "skipped"}` (exit 0) and this step does
nothing — Step 3.7 stays exactly what it was (non-blocking, structural). Needs the running app (dev server from
Step 3) and Playwright (`playwright_setup.py` has run).

**What it is:** a Test-phase gate that compares the BUILT screens with the APPROVED mockups. It is **not** a
design-approval gate (D9): it never approves, waives, or changes a design.

**1. Run it** (after Step 3.7, before Step 3.8, dev server still up):
```bash
uv run "{plugin_root}/scripts/lib/screenshot_check.py" --cwd "{project_root}" --base-url "{dev_url}"
```
Per screen of `screen-routes.json` it screenshots the approved mockup (`.shipwright/designs/uploads/`, found through the
package's `screen-map.json`) and the built route in the same Chromium at 1280x800, then compares them.
A dynamic route (`/items/[id]`) needs a `sample_route` key in its `screen-routes.json` entry. Every screen of the
package's `screen-map.json` must appear in `screen-routes.json` (a package screen that was never built is an `error`),
and an approved mockup that renders blank is an `error`. Only the first viewport (1280x800, the fold) is compared;
the viewport is recorded in the result. Run it only when the marker file exists (the tool also checks).

**Metric and tolerance (recorded in every result):** `grid-luma-occupancy-diff-ratio`. Each shot becomes a 32x20 grid;
a cell DIFFERS when its content flag (text/borders/controls present) differs or its mean luminance differs by more
than 0.10. A screen PASSES when differing cells / all cells <= **0.15**. One rule for every screen (plus two guards: a built screen with no content at all is a `fail`, an approved mockup with none an `error`). First calibration
on real Chromium: the right built screen scored 0.02, a blank page 0.30, an error page 0.31, another screen 0.99.
It sees layout, not wording: a correct layout with wrong text passes (Step 3.7's structural check and the review
loop own that). The tolerance is tuned in the end-to-end procedure, not here.

**2. What to do — every outcome (an unattended agent follows this table, nothing else):**

| Exit / `status` | Meaning | Do |
|---|---|---|
| 0 `pass` | every screen within tolerance | record it (step 3), continue to Step 3.8 |
| 0 `skipped` (`applies: false`) | no Brief package | record `skipped: no Brief package`, continue |
| 1 `fail` | at least one screen is visibly not the approved mockup | **STOP the test phase and report** the failing screens with `diff_ratio` and both screenshot paths. Do not continue to "done". |
| 2 `error` | the check could not run or compare a screen (no app, no browser, missing mockup, size mismatch, route not concrete) | **STOP and report** the `error` / `capture_error` text. An error is NOT a pass. If the text says Playwright or the browser is missing, run `playwright_setup.py` once (setup, not a waiver) and re-run; still `error` → STOP and report. |

Never: raise the tolerance, edit or regenerate an approved mockup or `uploads/`, delete a screenshot, mark a screen
"expected", skip the step, or approve anything. A fix is allowed only in the BUILT app (the screen's route/component)
followed by a re-run of the tool, max 3 rounds; still red → STOP and report as above.

**3. Record** in `shipwright_test_results.json`:
```json
{"screenshot_check": {"applies": true, "status": "pass", "metric": "grid-luma-occupancy-diff-ratio",
  "tolerance": 0.15, "passed": 2, "total": 2,
  "screens": [{"mockup": "01-dashboard.html", "route": "/dashboard", "status": "pass", "diff_ratio": 0.02}]}}
```
Completion gate: with a Brief package the layer's result must be `pass` — `fail`/`error` keep the test phase
`incomplete`. Without one: `skipped: no Brief package`.
