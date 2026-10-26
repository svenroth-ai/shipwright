# End-to-end run report: social engagement desk

Result: {{STATUS}}
Started: {{STARTED}}
Duration: {{DURATION}}

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

## Checklist (hard items must hold, soft items are compared by eye)

{{CHECKLIST}}

## Screenshot check of the Test phase (approved mockups against built screens)

{{SCREENSHOT_CHECK}}

## Gates answered

{{GATES}}

## Escalations

{{ESCALATIONS}}

## Model and spend

{{MODEL_SPEND}}
