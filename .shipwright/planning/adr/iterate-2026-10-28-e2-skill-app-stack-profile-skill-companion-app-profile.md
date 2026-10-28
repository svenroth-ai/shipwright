# Bundled stack profile for skill-backed apps, without schema keys

Run iterate-2026-10-28-e2-skill-app-stack-profile (campaign e2e-run-findings, unit E2).

## What exists
- A bundled profile `skill-companion-app` for the skill-backed app class: the chat is the Claude app, the app is a skill or plugin, the companion is a served HTML board plus a Python backend plus a JSON data folder. `deploy` is null (`deploy_target: none` skips the phase): no plugin-shaped deploy target exists.
- `chat-first-json` stays bundled so existing apps keep resolving.

## What was deliberately NOT added
The schema keys `host`, `delivery`, `companion`, `data_folder` in `shared/schemas/stack_profile.schema.json`. Nothing reads them. The concepts live in the profile under the comment key `_skill_companion` and as prose in `docs/stack-profiles.md`.

## Architecture review
- External, plan as first built (profile plus four typed schema keys): glm revise (ship the profile, hold the unread keys), openai reject (project-level profile only, option C).
- Resolution: the operator (Sven, 2026-10-28) took glm's trim.
- Re-run on the trimmed plan: glm approve, openai reject again on the same point (bundling at all); internal architecture reviewer (opus) approve. No new point.

## Rule for later units
Add the four keys to the schema only in the unit that introduces their reader, together with the reader and its tests. Do not delete the bundled profile. Port split: the real companion binds 3901, the dev_server block (preview, Browser Verify, Playwright with `reuseExistingServer: false`) uses 3911 and a throw-away `--data-dir`.
