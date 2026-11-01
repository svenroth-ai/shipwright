# Expected result: social engagement reply board (skill-backed app, real-skill variant)

What the finished app must show after a real run from the Brief package `social-engagement-real/`.
This file lives NEXT TO the package, not inside it: a file inside the package changes its hash, and the
agent that builds the app must not read the answer key.

This variant is closer to the real `social-engagement` skill than `social-engagement-board`: a master-detail
page (thread list left, one thread right), the svenroth.ai brand tokens including fonts, platform-like thread
rendering, a status filter with skipped and expired, and the hits fetched through an exchangeable source adapter
that replays recorded Syften and Apify answers (no network, no keys). Keywords are sources, not a board tab. Select
it with `SHIPWRIGHT_E2E_FIXTURE=social-engagement-real`; the harness then evaluates S02, S04 and S05 in their variant form.

The package ships the recorded answers (`seed/recorded/syften.json`, `seed/recorded/apify_linkedin.json`: twelve items, four per platform, three of them more than 14 days older than the newest), the exact summary rule, the angle line and the reply-draft template (`brief.md`). The build copies the two files byte for byte to `seed/recorded/` of the built project and adds no other recorded data; S05 reads them there. The sample text in the five approved mockups (thread titles, post text, comments, summary, draft) is the output of those recordings, that rule and that template, so the Test phase screenshot check (Step 3.7b, grid-luma-occupancy-diff-ratio, tolerance unchanged) measures layout and not wording. The mockups use four Reddit threads from the recordings, with the same data and status labels on every screen. `test_e2e_real_fixture.py` recomputes the mockup text from the shipped files and fails when they drift apart.

Each item is **hard** (must hold; `integration-tests/e2e-webui` evaluates it and the run fails if it does not)
or **soft** (recorded in the report and compared by eye). Item lines keep the form
`- [hard|soft] <ID>: <text>`; `integration-tests/e2e-webui` parses them. S03 and S09 are soft.

## Hard

- [hard] H01: The run finishes: `shipwright_run_config.json` in the project has status `complete`.
- [hard] H02: The run config names the profile `skill-companion-app` and records the Brief package (`brief_dir`).
- [hard] H03: All five approved mockups are in `.shipwright/designs/uploads/`, byte-identical to the package.
- [hard] H04: `.shipwright/designs/screens/` holds a screen for every approved mockup.
- [hard] H05: The project preview button starts the companion and `GET /api/health` answers 200.
- [hard] H06: `POST /api/fetch` answers a number added above zero on a fresh data folder; asking again answers zero. (The harness moves the Test phase's `.dev-data` aside first; a used folder fails the check.)
- [hard] H07: `GET /api/threads/<id>` of a fetched thread answers it with a `summary` (question, others, angle) and a `comments` list; `GET /api/threads/99` answers 404 with "There is no thread 99".
- [hard] H08: `POST /api/threads/<id>/draft` stores a draft and sets the status to drafted; asking twice leaves the same draft.
- [hard] H09: `POST /api/threads/<id>/posted` marks a drafted thread posted and the same call on a thread that is not drafted is refused with 409 and the status stays; `POST /api/threads/<id>/skipped` marks a new thread skipped; `GET /api/threads?status=skipped` lists it.
- [hard] H10: `PUT /api/sources` with a Syften and a LinkedIn source answers them, `GET /api/sources` returns them, and an unknown `kind` is refused with 400.
- [hard] H11: Every API answer is JSON, and every error answer carries a plain `error` text.
- [hard] H12: The project is a plugin with a skill: `.claude-plugin/plugin.json`, a `skills/<name>/SKILL.md`, `backend/server.py`, a `board/` page and pytest tests.
- [hard] H13: No design screen is still the plain mockup copy: each screen in `.shipwright/designs/screens/` carries the design kit (kit styles or kit component classes, plus a token block in `:root`), so Design composed it.
- [hard] H14: `PUT /api/threads/<id>/feedback` on a drafted thread stores the note and `GET /api/threads/<id>` returns it; on a thread that is not drafted it answers 409.
- [hard] S01: The board is the whole page: the list, the thread and the filters, with no chat panel, no message log and no chat input.
- [hard] S02: The board is master-detail: a platform switcher with one entry and a count per platform (Reddit, Hacker News, LinkedIn), a status filter that offers new, drafted, posted, skipped and expired, a thread list with a status badge per row, and one thread shown beside the list after a row is selected, with a Copy reply button once a draft exists; no tab is called Keywords.
- [hard] S04: Colours, font sizes and fonts follow `visual-guidelines.md`: every colour and font-size token it declares has that value on the served board, and the board's font and mono font tokens name Inter and Geist Mono.
- [hard] S05: No service is named outside the source adapter: nothing outside `backend/sources/` reaches beyond loopback or reads a key; the adapter package defines `fetch_items`; the recorded Syften and Apify answers are in `seed/recorded/` and hold at least nine items, three per platform.
- [hard] S06: The Test phase ran pytest and Playwright against the served board (both recorded in `shipwright_test_results.json` with at least one test and all passed).
- [hard] S07: A request the companion does not know (an unknown route) answers 404 as JSON with a plain `error` text, not a page or a crash.
- [hard] S08: The gates the spec answered were the ones a person would answer (approving the design, screens or mockups, launching the next phase, submitting answers already given), with no unexpected escalation. A resumed run records its idle, budget or crash escalations from the earlier part, so S08 fails on it by design.

## Soft

- [soft] S03: Each built screen resembles its approved mockup (the screenshot check of the Test phase records its metric).
- [soft] S09: The skill triggers in a real Claude session: a headless `claude` session with the built plugin loaded, given the phrase "open the social engagement board", calls the plugin's skill. Needs a login and costs one short model call; skipped (recorded as not run) when `SHIPWRIGHT_E2E_SKILL_TRIGGER` is not `1`.
