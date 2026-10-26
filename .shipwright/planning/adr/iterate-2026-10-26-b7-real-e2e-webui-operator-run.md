# Operator-started real end-to-end run through the WebUI

## Decision
A small Node/Playwright project at `integration-tests/e2e-webui/` that an operator starts by hand drives a second WebUI instance
like a person and writes a screenshot report. CI checks only what needs no model (package validation, dry harness, structure rules).
The answer key sits next to the package (`integration-tests/fixtures/social-engagement-expected-result.md`), not inside it, because
a file inside the package changes its hash and the building agent could read it.

## Architecture Review
Both external reviewers ran over the architecture brief (options: A Playwright project, B manual procedure, C do nothing).
- glm: approve (low findings: the env-file layer and the idle abort are more than a bare driver).
- openai: **reject**, recommending option B (manual checklist plus report template), because no recurring run frequency was shown to justify a second automation harness that must track the WebUI repo.
- Internal architecture reviewer: approve (option A is the smallest thing that answers the question).

**Disposition of the reject: overridden.** Scope fixed by the approved campaign brief (rev 4, section 3 B7); the operator decided to build the
project, the env-file layer and the idle abort; the reviewer was not given that context. The maintenance cost it names is accepted: the project
runs in no pipeline, and the local `npm run typecheck` and `npm run test:unit` are its only guards.

## Follow-ups not done in this unit
- Copy the referenced mockups into the report folder (the report links screenshots only).
- Record the WebUI commit in the report and fail fast with a clear message when a WebUI test id is missing.
- Hard checks H07 and H09 judge replies by wording; assert resulting thread state through a follow-up read.
- Define the idle abort as "no progress AND a pending prompt" strictly; today it aborts on no progress and records whether the inbox held a prompt.
- Stand-alone cost note: a run costs real tokens; the first real run is operator acceptance, outside the campaign.
- Fix round 1 skipped on purpose: SIGHUP handling, masking secrets in terminal screenshots, a hard barrier against the agent reading the answer key, a check that the workdir is not inside the repo.
