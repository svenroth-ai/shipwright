# Iterate: social-engagement-real ships its recordings, summary rule and draft template

Run: `iterate-2026-11-01-fixture-real-ship-data` | type: change | complexity: small | triage: trg-5da1201c

## Why

PR #970 aligned the five mockups to the recordings run 14 happened to write. The package still only *described* the recorded
answers, the summary rule and the reply template, so every build invents its own and the mockup text and the Test phase
screenshot check (tolerance 0.15, unchanged) agree only by chance.

## Change

Fixture and harness tests only (`integration-tests/`). Tolerance, metric, check and every plugin are untouched.

- **Recordings shipped.** `integration-tests/fixtures/social-engagement-real/seed/recorded/syften.json` (8 items: 4 Reddit, 4 Hacker News)
  and `apify_linkedin.json` (4 LinkedIn), copied unchanged from run 14 (`autorune2e/run-uRPOYL/project/seed/recorded/`). 12 items, 4 per
  platform, 3 older than 14 days than the newest (Reddit 10-04, HN 09-30, LinkedIn 10-02 vs 10-28), invented `.example` hosts and authors.
  The package copy lands in the project as `brief/seed/recorded/`; `brief.md` states the build copies both files byte for byte to
  `seed/recorded/` of the built project (S05 and the adapter read them there; S05 excludes `brief/` and `seed/` from its code scan).
- **Rule, angle line, template verbatim in `brief.md`** (taken from run 14's `backend/summary.py` / `drafter.py`): question = first sentence
  (`^(.+?[.!?])(?:\s|$)`, collapsed text, title if the text is empty, 300-char cut); others = comment texts collapsed and joined with one
  space, `No comments yet.`, 400-char cut; angle = `Answer the question plainly, share what worked for us and ask what they tried.`; draft =
  `Hi {author}, thanks for asking about "{title}". We ran into the same question. Happy to share what worked for us - what have you tried so far?`.
- **Fit criteria** added to "Read a thread" (summary fields equal the rule output, named thread), "Draft a reply" (draft equals the template
  for a named thread) and "Fetch new hits" (N is 12 with the shipped recordings).
- **Data decision:** the build must not replace, rewrite, shorten or extend the shipped recordings and adds no further recorded data (no extra
  items, no extra files); the same package then always yields the same 12 threads, 4/4/4 switcher counts and the mockup text.
- **Mockups unchanged:** the five mockups already equal the output of shipped data + rule + template (PR #970 took them from these recordings);
  a new test recomputes this instead of trusting it.
- **Pins:** `brief.json` `package_sha256`; `social-engagement-real-expected-result.md` (paragraph about shipped data); `test_e2e_real_fixture.py`
  (3 new tests); `e2e-webui/tests/unit/real-variant.spec.ts` (new test: `findRecorded` and S05 on the shipped files, 12 valid / 4 per platform / 3 old).
  `real-variant.spec.ts` needed no count change: S02 titles and counts already match the mockups.

## Harness checks against the shipped data

S05 passes (`findRecorded`: 12 valid, 4/4/4, old 3). H06 (fetch adds N>0 then 0): 12 distinct urls, so 12 then 0. H07-H10, H14 depend on the
build's API, not on the data; the shipped data has threads of every platform, one expired-by-age per platform, so skip/draft/posted/feedback
flows have `new` threads to act on.

## Acceptance criteria

1. The package ships valid recordings (12 items, 4 per platform, >= 2 older than 14 days than the newest) and `brief.md` says the build copies them.
2. `brief.md` states the summary rule, the angle line and the draft template verbatim, with fit criteria for a named thread.
3. The mockup text (summary, comments, draft, list rows) equals the output of data + rule + template (tested).
4. `brief.json` holds the new hash; package is warning-free; e2e-webui unit tests, typecheck and the two integration test files pass.

## Spec Impact

NONE (fixture data and test-harness data; no product behaviour).

## Review dispositions (doubt pass)

Fixed: list order (id ascending / file order), subreddit source, optional `points`, LinkedIn title rule, replay ignores the query, empty-text rule, cut wording, expiry window test, vacuous-test hardening. Deliberately not done: no harness item compares the built project's `seed/recorded/` with the package copy (it would change the answer key; the tolerance, metric and check are out of scope).

## Not proven

The path brief.md -> Project/Plan/Build decomposition -> built code is LLM-mediated; the regex, cut rule, angle line, template and the copy instruction reach the build only if the decomposition keeps them word for word. A build that ignores the shipped recordings still passes S05 (it checks counts, not bytes); the screenshot ratio of the next real run would show it.

The real end-to-end run is the only proof that a build now matches the mockups and the screenshot check passes; it was not run (operator decides).
