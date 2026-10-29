# Architecture Brief: end-to-end harness and fixture for the skill-backed app class

## The problem
The operator end-to-end run (`integration-tests/e2e-webui/`) builds an app from a committed Brief package and checks it. Both the package (`social-engagement`) and the checks (H06-H11) describe a chat-first app: a chat box on the left, a pane on the right, commands typed into the chat. The campaign decided that a skill-backed app has no chat of its own: the chat is the Claude app, and the app is a plugin whose companion is a served HTML board plus a Python backend over JSON files. Soft items S01, S02, S04-S08 are only ever "not evaluated". The harness has no resume (a stopped run costs 70-80 minutes again). Nothing detects a design screen that was left as the plain mockup copy.

## What already exists here
- The e2e-webui TypeScript harness (driver, report, checklist, progress, tour), the `social-engagement` chat-first fixture and its answer key, a CI structure test for the harness.
- Bundled profile `skill-companion-app` (dev server 127.0.0.1:3911), intake content check and kit-token warning, a screenshot check that can reach board states with steps.
- The legacy chat-first fixture is still used by other design tests.

## What would newly, permanently exist
A second fixture package and answer key for the board app class, harness modules that evaluate the built app (HTTP API, board DOM, project files) and the soft items as pure functions with unit tests, a resume plan, and an updated report template. The harness stays operator-started, never a CI gate.

## Options on the table
- **A:** add a new fixture package for the board app class next to the old one; switch the harness to it; replace chat checks with API/board/file checks as pure, unit-tested modules; add resume by reusing an earlier run folder; keep the legacy fixture for the legacy design tests.
- **B:** keep the chat-first fixture and harness, and only turn the soft items into hard checks.
- **C:** rewrite the old fixture in place (delete the chat-first package and its tests).
- **D:** do nothing; rely on a person reading the report by eye.

## Constraints that are not negotiable
The run stays operator-started with no defaults for permission mode, WebUI directory and budget. Files stay under 300 lines. Nothing secret is committed. The package must pass the new intake content check without warnings. No edit to ci.yml, pyproject.toml, verify_local.py or fr_classification.py.
