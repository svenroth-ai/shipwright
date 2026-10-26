# Mini-plan B3c: Screenshot check in the Test phase

Change: new BLOCKING check beside the non-blocking Step 3.7, applicable only when Design applied a Brief
package (`.shipwright/designs/brief-package-applied.json`); other projects get `{"applies": false}` and keep
today's behaviour byte-for-byte (design_fidelity_check.py and Step 3.7 are not touched).
- `png_compare.py`: dependency-free PNG decode (zlib) + metric: 32x20 grid of mean luminance + content
  (edge) flag per cell; a cell differs on a flag mismatch or a luminance step > 0.10; a screen passes when
  differing cells / cells <= 0.15. One rule, recorded with every result.
- `screenshot_capture.mjs`: Playwright (resolved from the project) screenshots the approved mockup
  (file:// of uploads/) and the built route at the same 1280x800 viewport.
- `screenshot_check.py`: resolves routes/mockups (screen-routes.json + brief screen-map), captures, compares,
  exit 0 pass / 1 fail / 2 error (both block).
- Docs: reference step-3.7b (outcome table for the unattended agent: STOP-and-report on fail/error, never
  waive/edit mockups/approve), SKILL.md step, completion gate, results enforcement, guide, hooks doc.
- Tests: unit planted-wrong-screen test on synthetic PNGs; Playwright-gated real-Chromium test (skips with
  an explicit reason); prose pins.
Calibration (real Chromium): right built screen 0.02, blank page 0.30, error page 0.31, other screen 0.99.
