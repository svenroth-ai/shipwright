# End-to-end run report: social engagement board (skill-backed app)

Result: {{STATUS}}
Started: {{STARTED}}
Duration: {{DURATION}}
Plugins loaded from commit: {{PLUGIN_COMMIT}}
Run: {{RESUME}}

This file is the template that `src/report.ts` fills in (see the README). The report is produced even when
the run fails or is aborted, up to the point it stopped. The report folder is not committed.

## Operator inputs

No defaults exist for the permission mode, the WebUI directory and the time budget. For each input the
report says which source supplied it (process environment or env file), never a secret.

{{CONFIG}}

Optional input `SHIPWRIGHT_E2E_WORKDIR`: when set, the temp project, the temp HOME and `e2e-report/` are
created under that directory (the operator uses a folder outside the repository); when unset, the OS
temp directory is used.

Authentication source: {{AUTH_SOURCE}} (one of: env token, env key, copied login). A copied login is
deleted when the run ends.

## Steps

{{STEPS}}

## Checklist (every item is hard except S03, which is compared by eye)

How each item is evaluated: H01-H04 and H12-H13 and S05-S06 read the project files; H05-H11 and S07 call the companion's JSON API (the chat is the Claude app, so there are no chat commands to type); S01, S02 and S04 read the served board page in a browser; S08 classifies the gates answered below by meaning.

{{CHECKLIST}}

## Screenshot check of the Test phase (approved design screens against built screens)

The metric and tolerance are the Test phase's own. Whether a placed screen is still the plain mockup copy is a separate hard check (H13).

{{SCREENSHOT_CHECK}}

## Gates answered

{{GATES}}

## Escalations

{{ESCALATIONS}}

## Model and spend

{{MODEL_SPEND}}
