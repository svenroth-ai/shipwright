# Iterate: correct the harness checks of fixture `social-engagement-baseline` after run 20, add a re-check command

Run: `iterate-2026-11-03-baseline-harness-fixes` | type: bug | complexity: small | no triage card

## Goal

The first real run of the baseline fixture (run 20) reported many hard items red. Reading the checks against the built project
showed the harness was wrong, not the app. Correct the checks, and let the operator re-run them against an already built project
without a 6.5 hour run.

## Acceptance criteria

1. A thread is clicked through its visible list row (`[data-k]`, by key), never through the first text match (a hidden `<option>` of
   the phone picker). Banner and comment-count text counts visible elements only. B36-B41, B45, B46 and the screen tour reach their states.
2. B31 accepts the default service hosts anywhere in `backend/services/`; only files outside the adapter package are barred.
3. B17 compares the brief's error texts as text (quotes were compared JSON-escaped, so `never write "beta"` never matched).
4. B30 does not count the brief's own 409 sentence "this lesson is already in lessons.md" as a file access; a real access still fails.
5. B37 reads the summary labels without case (innerText follows `text-transform`); B39 keeps the Copy button element (its label changes to "Copied"); tour recipe `list-thread` matches its marker without case and `expired` selects the expired thread's platform and matches without case (the mockup of `list-thread` shows the first thread auto-selected, so it opens nothing).
6. `npm run recheck` with `SHIPWRIGHT_E2E_RECHECK_PROJECT=<built project>` runs the static and dynamic baseline checks and the tour with no pipeline and no model.

## Spec Impact

NONE (test harness only; no product behaviour). Tests carry `FR-01.06`.

## Out of Scope

A full e2e run; changing the package or the answer key; the built app.

## Affected Boundaries

The built app's JSON error list (consumed by B17), the board DOM (consumed by B36-B46 and the tour). Probed by running the checks against the real built project `run-phse68`.

## Confidence Calibration

- **Boundaries touched:** error list text, board DOM.
- **Empirical probes run:** recheck against the real built project before and after each fix (7 red B items, then 4, then 0; the tour went from 2 unreached states to 0).
- **Edge cases not probed:** a different built project; acceptable since the checks are written against the brief.

## Self-Review

Seven items pass (see `iterate-2026-11-03-baseline-harness-fixes/self-review-payload.json`).

## Architecture Review

glm approve, openai approve (brief: nothing permanent is added).

## External-Plan-Review-Findings

| Finding | Disposition |
|---|---|
| Loosened checks need negative tests (B30 sentence, B31 scope) | accepted-and-fixed: unit cases for a reworded message, an access in another file, a host outside the adapter |
| Define visibility for visibleText | accepted-and-fixed: Playwright `visible` filter, documented in the helper, unit test with a hidden option and a hidden banner |
| recheck must fail on red items / bad path | accepted-and-fixed: non-zero exit while a hard B item is red; clear error for a missing folder |
| recheck could pull in pipeline or model setup | rejected-with-reason: the `recheck` project has no global setup and imports only `src/baseline` |
| stale build gives confusing reds | accepted-and-fixed: README note |

## External-Code-Review-Findings

| Finding | Disposition |
|---|---|
| expired recipe compared case-sensitively | accepted-and-fixed |
| list-thread selects no platform | rejected-with-reason: the mockup shows the first thread auto-selected; AC5 reworded |
| leafCount counts hidden elements | rejected-with-reason: leafCount already counts only elements with client rects |
| sentence masks a real access in the same file | rejected-with-reason: only the sentence is removed; unit case with a real access in the same file stays red |
| stale ElementHandle in B39 | accepted-and-fixed: the button is looked up again by role |

## Internal Code Review

Spec PASS; code PASS. Fixed: draft-card recipe uses visibleText, posted marker `/i`, `data-k` named as a mockup contract, recheck skips when unset. Accepted: B37 'Question' is weak (the other two labels carry it); checks-board.ts is at 299 lines.
