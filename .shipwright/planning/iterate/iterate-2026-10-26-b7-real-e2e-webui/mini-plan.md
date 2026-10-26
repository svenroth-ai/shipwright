# Mini-plan: B7 real end-to-end run through the WebUI (tooling only)

Scope: new files only. A Node/Playwright project `integration-tests/e2e-webui/` that an operator starts by hand,
an answer key `integration-tests/fixtures/social-engagement-expected-result.md`, and one pytest file that checks
what needs no model. The social engagement package already exists (B3b) and is not edited, so its hash is unchanged.

Design:
- Operator inputs read from the process env first, then an env file outside the repo; three have no defaults and the
  spec refuses to start without them; the report records only the source name per value.
- Temp HOME under an optional workdir, provisioned with the real plugins copied from this checkout, permission mode
  written into settings.json, onboarding and folder trust written into .claude.json.
- Auth: env token, env key, else a copy of the login file that is deleted in finally, on signals and on process exit.
- Own stack starter: build the WebUI server and client, start the server (it serves the built client) with
  HOME/USERPROFILE at the temp HOME, SHIPWRIGHT_MONOREPO_PATH at this checkout, fixture acceptance flag set. Fixed argv only.
- Drive the WebUI by its test ids: expert wizard, New pipeline modal, design-gate approve, next-phase launch, preview button.
- Progress read from the project's run config and file activity; idle abort after 20 minutes without change.
- Hard checks on the built app go through its documented POST /api/chat; screenshots through the chat box, each beside its mockup.
- Report writer renders report-template.md; written in finally so a failed run still has a report.
- Answer key placed beside the package (inside it would change the hash and let the building agent read it).

Tests: pytest (package validates, dry harness, structure rules); in the project, playwright unit project with no browser
(config, auth copy/delete, provisioning, report, idle watch, chat checks) and `npm run typecheck`.
