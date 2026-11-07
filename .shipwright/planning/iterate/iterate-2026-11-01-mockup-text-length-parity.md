# Iterate: social-engagement-real mockups carry recorded-length sample text

Run: `iterate-2026-11-01-mockup-text-length-parity` | type: change | complexity: small | triage: trg-16835d8c

## Why

Run 14: the Test phase screenshot check (Step 3.7b, `grid-luma-occupancy-diff-ratio`, tolerance 0.15) failed on
`02-thread` (0.1766) and `03-reply-draft` (0.175). The approved mockups held the designer's short sample text
("A buddy for the first week beats any document."), the built page showed the recorded Syften thread text. The metric
counts per-cell text occupancy, so text length moves cells (finding in
`iterate-2026-11-01-plan-design-detail-and-screenshot-gap.md`, Part B, option a).

## Change

Fixture only (`integration-tests/fixtures/social-engagement-real/`). The tolerance, the metric, the check and every plugin
are untouched. The five mockups now use four Reddit threads of `seed/recorded/syften.json` as run 14's build wrote it (the package ships no recordings; the build creates them) with
their recorded title, author, points, post text and comments, the summary the deterministic backend function derives from them
(first sentence as the question, the comments joined, the fixed angle line) and the drafter's fixed template:

| Thread | Row status | Shown in detail on |
|---|---|---|
| Shipwright onboarding took me an hour, is that normal? (quiet_lantern_42, r/devtools) | new | 02-thread |
| How are you pricing AI dev tools like Shipwright for small teams? (copper_fieldmouse, r/SaaS) | drafted | 03-reply-draft |
| Any integrations between Shipwright and Jira? (velvet_parsnip, r/programming) | posted | 04-thread-posted |
| Shipwright vs. doing it by hand for an MVP? (amber_tortoise, r/startups) | expired | list only |

Same list rows, status labels and switcher on all five screens; switcher counts 4 / 4 / 4 (the recordings hold four items
per platform); `01-board` note reads "12 new hits added". Layout, CSS and structure are unchanged.

Pins updated: `brief.json` `package_sha256`; `integration-tests/e2e-webui/tests/unit/real-variant.spec.ts` (its per-platform counts and
the titles it clicks follow the new mockups); `social-engagement-real-expected-result.md` gets one paragraph about the sample text
(that file sits outside the hashed package).

## Acceptance criteria

1. The mockup thread, comment, summary, draft and list-row text is as long as the recorded answers, and identical across screens
   (same data, same status labels, same layout).
2. `brief.json` holds the hash of the changed package (`test_e2e_real_fixture.py` verifies it) and the package is still a warning-free input.
3. The e2e-webui unit tests, which read the mockups, pass with the new data.

## Spec Impact

NONE (fixture data and test-harness data; no product behaviour).

## Not proven

A later build matches these texts only if it writes recordings of similar length or copies the mockup text (not pinned in brief.md, deliberately out of scope). The real end-to-end run is the only proof that the screenshot check now passes; it was not run here (operator decides).
