# Mini-plan E5
- screenshot_capture.mjs: remove addStyleTag; screenshot(animations:disabled, caret:hide); optional per-job steps (click/fill/wait_for).
- screenshot_check.py: validate and pass optional `steps` of a screen-routes entry onto the built job only; malformed steps = error.
- Tests: real-Chromium CSP board + state; unit tests for steps. Docs: step-3.7b reference, guide, "approved design screens" wording.
- Alternative considered: bypassCSP:true -- rejected because it renders the board differently from how users see it and hides the real cause (the injected tag).
