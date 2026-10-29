# Architecture Brief — E5

**Problem.** The Test-phase screenshot capture (`screenshot_capture.mjs`) fails against a page with a strict Content-Security-Policy, because it injects an inline `<style>` to freeze animations. Also, a screen that is a state of one served board page (a tab, a pane) has no route of its own, so the check cannot compare it.

**Options**
1. Do nothing (document that CSP apps must relax their policy).
2. Launch the browser context with Playwright's `bypassCSP: true` and keep the injected style.
3. Drop the injected style; use Playwright's built-in `animations: "disabled"` / `caret: "hide"` screenshot options. For states, let a screen-routes entry carry optional `steps` (click / fill / wait_for) executed on the built page before the shot.
4. A separate new capture tool for served boards.

No new permanent file, schema or dependency under option 3; touches one .mjs, one .py, a reference doc.
