# Expected result: social engagement board (skill-backed app)

What the finished app must show after a real run from the Brief package `social-engagement-board/`.
This file lives NEXT TO the package, not inside it: a file inside the package changes its hash, and the
agent that builds the app must not read the answer key.

The app class is a skill-backed app: the chat is the Claude app, so the app has no chat of its own. The
plugin's skill starts a companion (a Python backend that serves the board and a JSON API) and the data is JSON
files. The harness therefore checks the companion's HTTP API, the board page in a browser and the project files,
not chat commands.

Each item is **hard** (must hold; `integration-tests/e2e-webui` evaluates it and the run fails if it does not)
or **soft** (recorded in the report and compared by eye). Item lines keep the form
`- [hard|soft] <ID>: <text>`; `integration-tests/e2e-webui` parses them. Only S03 is soft: its metric is the Test
phase's own screenshot check and it needs a person's eye for the cases the metric cannot judge.

## Hard

- [hard] H01: The run finishes: `shipwright_run_config.json` in the project has status `complete`.
- [hard] H02: The run config names the profile `skill-companion-app` and records the Brief package (`brief_dir`).
- [hard] H03: All five approved mockups are in `.shipwright/designs/uploads/`, byte-identical to the package.
- [hard] H04: `.shipwright/designs/screens/` holds a screen for every approved mockup.
- [hard] H05: The project preview button starts the companion and `GET /api/health` answers 200.
- [hard] H06: `POST /api/fetch` answers a number added above zero on a fresh data folder; asking again answers zero. (The harness moves the Test phase's `.dev-data` aside first; a used folder fails the check.)
- [hard] H07: `GET /api/threads/1` answers thread 1; `GET /api/threads/99` answers 404 with "There is no thread 99".
- [hard] H08: `POST /api/threads/1/draft` stores a draft and sets the status to drafted; asking twice leaves the same draft.
- [hard] H09: `POST /api/threads/1/posted` marks the drafted thread posted; the same call on thread 2, which is not drafted, is refused and its status stays.
- [hard] H10: `PUT /api/keywords` with onboarding, pricing, integrations answers those keywords and `GET /api/keywords` returns them.
- [hard] H11: Every API answer is JSON, and every error answer carries a plain `error` text.
- [hard] H12: The project is a plugin with a skill: `.claude-plugin/plugin.json`, a `skills/<name>/SKILL.md`, `backend/server.py`, a `board/` page and pytest tests.
- [hard] H13: No design screen is still the plain mockup copy: each screen in `.shipwright/designs/screens/` carries the design kit (kit styles or kit component classes, plus a token block in `:root`), so Design composed it.
- [hard] S01: The board is the whole page: the tab strip and the cards, with no chat panel, no message log and no chat input.
- [hard] S02: The board has one tab per platform (Reddit, Hacker News, LinkedIn) and a status badge per thread (new, drafted, posted).
- [hard] S04: Colours and type follow `visual-guidelines.md`: every colour and font-size token it declares has that value on the served board.
- [hard] S05: No external service is called and no key is needed: nothing in the backend or board reaches beyond loopback or reads a key, and the seed holds at least nine matches, three per platform.
- [hard] S06: The Test phase ran pytest and Playwright against the served board (both recorded in `shipwright_test_results.json` with at least one test and all passed).
- [hard] S07: A request the companion does not know (an unknown route) answers 404 as JSON with a plain `error` text, not a page or a crash.
- [hard] S08: The gates the spec answered were the ones a person would answer (approving the design, screens or mockups, launching the next phase, submitting answers already given), with no unexpected escalation. A resumed run records its idle, budget or crash escalations from the earlier part, so S08 fails on it by design.

## Soft

- [soft] S03: Each built screen resembles its approved mockup (the screenshot check of the Test phase records its metric).
