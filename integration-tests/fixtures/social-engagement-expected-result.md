# Expected result: social engagement desk

What the finished app must show after a real run from the Brief package `social-engagement/`.
This file lives NEXT TO the package, not inside it: a file inside the package changes its hash, and the
agent that builds the app must not read the answer key.

Each item is **hard** (must hold; the operator spec checks it and the run fails if it does not) or
**soft** (recorded in the report and compared by eye). Item lines keep the form
`- [hard|soft] <ID>: <text>`; `integration-tests/e2e-webui` parses them.

## Hard

- [hard] H01: The run finishes: `shipwright_run_config.json` in the project has status `complete`.
- [hard] H02: The run config names the profile `chat-first-json` and records the Brief package (`brief_dir`).
- [hard] H03: All five approved mockups are in `.shipwright/designs/uploads/`, byte-identical to the package.
- [hard] H04: `.shipwright/designs/screens/` holds a screen for every approved mockup (the pane states of the chat-only capabilities included).
- [hard] H05: The project preview button starts the app and `GET /api/health` answers 200.
- [hard] H06: "fetch new matches" answers with a number of new threads above zero; asking again adds nothing (answers none or zero).
- [hard] H07: "show thread 1" shows thread 1; "show thread 99" answers "There is no thread 99".
- [hard] H08: "draft a reply for thread 1" stores a draft; asking twice leaves the same pane (the drafter is deterministic).
- [hard] H09: "mark thread 1 as posted" marks the drafted thread posted; marking thread 2, which is not drafted, gets a plain refusal.
- [hard] H10: "set keywords: onboarding, pricing, integrations" answers with those keywords.
- [hard] H11: Every chat answer carries a `reply` and a `pane`.

## Soft

- [soft] S01: The chat sits on the left and the pane on the right, nothing else on screen.
- [soft] S02: The board has one tab per platform (Reddit, Hacker News, LinkedIn) and a status badge per thread (new, drafted, posted).
- [soft] S03: Each built screen resembles its approved mockup (the screenshot check of the Test phase records its metric).
- [soft] S04: Colours and type follow `visual-guidelines.md` (one accent colour, status colours for new, drafted, posted).
- [soft] S05: No external service is called and no key is needed; the seed holds at least nine matches, three per platform.
- [soft] S06: The Test phase ran pytest and Playwright against the served pane.
- [soft] S07: A command the app does not know answers with the list of commands.
- [soft] S08: The gates the spec answered were the ones a person would answer, with no unexpected escalation.
