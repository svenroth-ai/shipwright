# Blocking screenshot check beside the non-blocking fidelity step

The check lives in new files (`screenshot_check.py`, `png_compare.py`, `screenshot_capture.mjs`); the grandfathered
`design_fidelity_check.py` and Step 3.7 are untouched, so projects without a Brief package keep today's behaviour.

## Metric and tolerance
`grid-luma-occupancy-diff-ratio`: 32x20 grid; a cell differs on a content-flag mismatch or a luminance step > 0.10;
a screen passes at differing/all cells <= 0.15, viewport 1280x800 (first fold). Real Chromium: right built screen
0.02, blank page 0.30, error page 0.31, other screen 0.99. A luminance-only version passed blank/error pages (0.014/0.023).

## Architecture Review
GLM and OpenAI: both approve. GLM: tolerance must not become a per-project knob (accepted: one constant, tuning
is a recorded decision in the end-to-end procedure); record metric, tolerance and both screenshots (accepted).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Missing Playwright/browser is a hard error with no remedy (GLM) | accepted-and-fixed: reference tells the agent to run playwright_setup.py once, then STOP |
| Blank/odd-loading mockup could mask a wrong screen (GLM) | accepted-and-fixed: a blank approved mockup is an `error` |
| Viewport-only, record viewport (GLM) | accepted-and-fixed: documented and recorded in the result |
| Real-Chromium test may skip so the gate stays unverified (both) | accepted-in-part: the real test ran green locally (SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES) and skips with an explicit reason elsewhere; CI provisioning is a follow-up |
| Metric ignores colour/text (OpenAI) | rejected-with-reason: coarse by design; hue-only and wording changes are follow-ups, tolerance is tuned in the end-to-end procedure |
| Extend design_fidelity_check.py (OpenAI) | rejected-with-reason: grandfathered 411-line file (anti-ratchet); both read screen-routes.json |
| Package screen never built could give an empty pass (OpenAI) | accepted-and-fixed: every screen-map screen must appear in screen-routes.json, else `error` |
| HTTP error pages (OpenAI) | accepted-and-fixed: a non-OK navigation is a capture error |
| Authenticated screens, animations beyond CSS, scroll height | follow-up (not on the core path) |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| Stale screenshots of a previous run can pass a failed capture (OpenAI, high) | accepted-and-fixed: a capture run clears both picture folders first; a missing pair is an `error` |
| Blank built screen hides under the tolerance for a sparse mockup (OpenAI, high) | accepted-and-fixed: a built screen without content is a `fail` (separate guard + test) |
| Package screen with neither route nor upload is skipped (OpenAI) | accepted-and-fixed: reported as `error` |
| Same-stem mockups overwrite each other's pictures (GLM) | accepted-and-fixed: picture names carry the entry index |
| fonts not awaited (GLM) | accepted-and-fixed: `document.fonts.ready` before the shot |
| PNG chunk CRC never verified (GLM) | accepted-and-fixed |
| createRequire ignores NODE_PATH, opt-in test cannot pass (GLM, high) | rejected-with-reason: the real-Chromium test passes with NODE_PATH set (run locally) |
| Spec says extend design_fidelity_check.py (GLM) | rejected-with-reason: see plan review |

## Follow-ups (deferred, not built)
Login/auth screens; a per-run screenshot output dir; PNG decoder speed; hue/wording differences; Playwright provisioning in CI.
Package screens with no route of their own (modal, in-page) are an error today: an exemption code is a follow-up. Other follow-ups: Playwright config.js globbing, the route-parser duplicate with design_fidelity_check, wording nits.
