# Expected result: social engagement companion (baseline fixture)

What the finished app must show after a real run from the Brief package `social-engagement-baseline/`.
This file lives NEXT TO the package, not inside it: a file inside the package changes its hash, and the
agent that builds the app must not read the answer key.

The baseline package is the finished Briefing package for a skill companion app, derived from the real `social-engagement`
Claude skill: 21 capabilities, seven approved mockups, synthetic service answers in the real shapes (`seed/recorded/`) and the
answers a stand-in agent stores (`seed/agent/run-synthetic.json`). Select it with
`SHIPWRIGHT_E2E_FIXTURE=social-engagement-baseline`. `social-engagement-real` is unchanged and keeps its own answer key.

Every item below is derived from a Fit criterion of `brief.md`; no behaviour is invented. The harness
(`integration-tests/e2e-webui/src/baseline/`) starts the BUILT companion itself, several times, each on a fresh data folder in a
temp directory, with a temp HOME, local fake servers for Syften, Apify and the Hacker News API (they replay `seed/recorded/`
through `index.json`), dummy tokens made up for the run, and the brief's clock override `SOCIAL_ENGAGEMENT_TODAY=2026-11-03`.
The real agent (Claude in the chat) is not part of the run: where a check needs an agent action (store a run, write a draft,
resolve feedback) the harness plays the agent over HTTP with `seed/agent/run-synthetic.json`.
No real network, no real key. The approval of the package is recorded by the harness in the run's COPY of the package (the
delivered package stays byte-identical).

Each item is **hard** (must hold; the run fails if it does not) or **soft** (recorded in the report and compared by eye). Item
lines keep the form `- [hard|soft] <ID>: <text>`; `integration-tests/e2e-webui` parses them. S03 and S09 are soft.

**First-run calibration.** The checks have only run against stand-in code; their expectations come from the brief text. Where the
brief leaves a detail open, the harness had to read it: the flags of `companion.py` (it passes `--port` and `--data-dir`, and retries
with `SOCIAL_ENGAGEMENT_HOME` when the helper rejects `--data-dir`), the format of `linkedin-queries.json` (a list of `{query, status}`),
the place of the helper (any `companion.py` outside `tests/` and `backend/`), and the board's hash format. A red B01-B05 or B11 in the
first real run may therefore be the harness reading the brief differently than the builder did; check the evidence text before blaming
the app, and calibrate the item afterwards.

## Pipeline and project (shared with the other fixtures)

- [hard] H01: The run finishes: `shipwright_run_config.json` in the project has status `complete`.
- [hard] H02: The run config names the profile `skill-companion-app` and records the Brief package (`brief_dir`).
- [hard] H03: All seven approved mockups are in `.shipwright/designs/uploads/`, byte-identical to the package.
- [hard] H04: `.shipwright/designs/screens/` holds a screen for every approved mockup.
- [hard] H05: The project preview button starts the companion and `GET /api/health` answers 200.
- [hard] H12: The project is a plugin with a skill: `.claude-plugin/plugin.json`, a `skills/<name>/SKILL.md`, `backend/server.py`, a `board/` page and pytest tests.
- [hard] H13: No design screen is still the plain mockup copy: each screen in `.shipwright/designs/screens/` carries the design kit (kit styles or kit component classes, plus a token block in `:root`), so Design composed it.
- [hard] S06: The Test phase ran pytest and Playwright against the served board (both recorded in `shipwright_test_results.json` with at least one test and all passed).
- [hard] S08: The gates the spec answered were the ones a person would answer (approving the design, screens or mockups, launching the next phase, resolving a contradiction between plan and mockup, submitting answers already given), with no unexpected escalation. A resumed run records its idle, budget or crash escalations from the earlier part, so S08 fails on it by design.

## Start and stop

- [hard] B01: The skill's helper `companion.py start` starts the companion and names the board address; `GET /api/health` then answers 200 with `ok`, the app name `social-engagement`, an absolute `data_dir` and a version, and `companion.pid` names a live process.
- [hard] B02: A second start while the companion runs reuses it: the pidfile still names the same process, which is still alive and healthy, and no second process is started.
- [hard] B03: `companion.py stop` ends the companion: the port refuses connections, the process is gone and the pidfile is removed.
- [hard] B04: A port held by another program gives a plain message that names the port and suggests `--port`, no success, and no pidfile or half-started process is left.
- [hard] B05: A pidfile with no live process behind it is removed and the start goes on: the companion answers and the pidfile names the new process.
- [hard] B27: The data folder is `--data-dir` when given, else `$SOCIAL_ENGAGEMENT_HOME`, else `~/.social-engagement` (the harness runs this under a temp home).

## The companion API

- [hard] B06: Every API answer is JSON (`application/json; charset=utf-8`) with `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`, no answer carries a CORS header, the page itself is `text/html`, `/board.css` and `/board.js` are served, and a cross-site preflight is not granted.
- [hard] B07: Only the local machine and the board's own header may use the API: a foreign Host gets 403 `local access only`, a POST or PUT without `X-Board: 1` gets 403 `local board only`, a foreign Origin is refused, and the board's own Origin passes.
- [hard] B08: An unknown route answers 404 `{"error": "not found"}`, a body that is not JSON answers 400 with an error text, a body over 20000 bytes answers 413 `too large`, and `POST /api/runs/check` accepts a larger body.
- [hard] B09: On a fresh data folder the read routes answer their documented shapes and error texts (`/api/version` changes on a write, `/api/board` with `daily_cap` 5, `/api/threads` with `unknown status x` and `unknown platform x`, `unknown thread reddit:nope`, runs, lessons, feedback, `after must be a number`, `give urls or items`).
- [hard] B24: The config starts as `{"configured": false}`; `PUT /api/config` merges and answers `configured: true`; `mode: loud` answers 400 `mode must be one of expertise, light, open`; an unknown key answers 400 `unknown setting colour`; a refused change writes nothing.
- [hard] B25: `POST /api/open` refuses everything but https links to Reddit, Hacker News, LinkedIn or X with the documented 400 text (the harness never opens a good link: it would start the OS browser).

## Fetching through the service adapter (local fake servers)

- [hard] B10: `POST /api/fetch/syften {}` answers 8 hits (4 Reddit, 4 Hacker News, among them the comment hit 46120103) and `dropped_other` 1; the config then holds `last_run` `2026-11-02T18:00:00Z`; Syften received `items/get` with limit 100 and `show` `ai_accepted` and `Authorization: Bearer <token>`; the next fetch asks only for newer items.
- [hard] B11: `POST /api/fetch/linkedin {"posted": "week"}` answers 4 posts, the company page with `flags.company` true, each with `known` false and an `item` skeleton; Apify received the documented payload (`postedLimit`, `maxPosts` 20, `sortBy` date, nested comments) with a cost cap, and the token from `.env.local`.
- [hard] B12: `POST /api/fetch/thread` loads a Hacker News comment url as its story with 3 comments in plain text, a Reddit thread with the kept comment and its parent, authors as `u/<name>`, comments ordered by score and the subreddit rules link, with the documented Apify input; a LinkedIn url answers 400 with the plain text; a thread Apify has no post for answers 502 `Apify returned no post for <url>`.
- [hard] B13: A failing service answers 502 naming the service, the status and the hint (Syften 401, Apify 402) and stores nothing; a missing `APIFY_TOKEN` or `SYFTEN_TOKEN` answers 503 with the fix (`APIFY_TOKEN missing: put it into .env.local in the data folder`) and the fake servers see no request; a Hacker News thread needs no token.
- [hard] B14: A token never leaves the adapter's Authorization header: it appears in no answer, no log line, no data file and no URL; `.env.local` in the data folder wins over the environment; every Syften and Apify request carries its own token and a User-Agent that names the app; the companion asks for nothing the package never recorded.
- [hard] B15: Hits on threads the backend already holds are not offered again: after storing the story 46120001 with its `syften_urls`, `POST /api/threads/unseen` drops the alias hit, answers the other once, and the same hits from `/api/fetch/syften` carry `known` true and false accordingly.

## Runs, lint, status, feedback, lessons

- [hard] B16: A run is stored all or nothing: the 11 synthetic items are stored (`stored` 11, `kept` []), a changed draft for a posted thread is answered in `kept` and the stored draft stays, a run with one bad item answers 422 `nothing written` and the board is unchanged, `GET /api/runs` lists both runs newest first, and a body without items answers 400.
- [hard] B17: The draft lint is backend validation with the documented texts: in mode expertise a bad item gets 422 with the dash, `reply.to`, beta, v1.0, Command Center and product/link errors and the tone-word warning; in mode open the link error is the UTM rule; bad date, http url and 11 comments without a summary get their texts; an item the lint cannot read is an error; warnings do not refuse.
- [hard] B18: Status rules: `posted` with a link without scheme answers the https link and counts in `posted_today`; `expired` cannot be set (400 `STATUS must be one of drafted, posted, skipped`); an http link or a link with whitespace is refused; an unknown key answers 404; Reopen clears `posted_at` and `posted_url`; Skip lists the thread under skipped.
- [hard] B19: Expired is derived, never stored: with the clock fixed to 2026-11-03 a drafted thread dated 15 days ago is expired and not open, one dated 14 days ago is still open, `state.json` keeps `drafted`, and Reopen of an old thread shows it as expired again.
- [hard] B20: Feedback is saved: `POST /api/feedback` answers an open entry with an `fb_` id and an ISO time, the queue holds it with a snapshot (angle, draft, reply_to, mode, date) equal to the stored thread, blank text answers 400 `empty feedback`, an unknown thread 404, and the text is trimmed.
- [hard] B21: The feedback queue lists only open entries, oldest first; resolving needs a note (400 `a note is required`), status `applied` or `declined` (400 `status must be applied or declined`) and a known id (404 `unknown feedback id fb_nope`); a resolved entry leaves the default list, stays under `status=all` and can be resolved again.
- [hard] B22: The events stream follows the board: after one feedback and one status change `GET /api/events?after=0` answers two events (`seq` 1 `feedback`, `seq` 2 `status` with `posted_url`) and `next` 2, `after=2` answers none, and `events.jsonl` holds both.
- [hard] B23: Lessons: a rule answers `- <rule> (<feedback id>)` and is in `GET /api/lessons`; the same rule again (case and final dot ignored) answers 409 `this lesson is already in lessons.md`; an unknown feedback id answers 404; an empty rule answers 400 `empty rule`.

## Data folder and code structure

- [hard] B26: After a run, a feedback, a status change and a lesson the data folder holds `data.json` (title and 11 items), `state.json` (one entry per thread with status, url, date, platform and aliases; posted ones with `posted_at` and `posted_url`), `feedback.json`, `config.json`, `lessons.md`, `runs/<YYYYMMDD-HHMMSS>.json`, and no `.tmp` file.
- [hard] B28: A data file that is not valid JSON gives 500 `data file data.json is not valid JSON` and is never overwritten by the next write.
- [hard] B30: The store module is the only code that touches the data files: `backend/store/` defines `Store` and has an in-memory next to the JSON implementation, and no other file under `backend/` names a data file.
- [hard] B31: The service adapter `backend/services/` (`syften.py`, `apify.py`, `hn_algolia.py`, each with its default host) is the only code that names a service host or reads a token or base-URL variable; no file in `backend/` imports or calls a model API; the board holds no lint rule (no dash list, no word beta).
- [hard] B33: The built `skills/social-engagement/SKILL.md` has a front matter whose description names the trigger phrases (social engagement, reply board, social listening, open the reply board, Syften, fetch new hits), the sections First start, Read first, Run, Feedback and lessons, Reply rules and Never, every data endpoint, `companion.py start|stop`, `X-Board: 1`, no instruction to edit a data file by hand, and the rule "When feedback needs more explanation than the new draft ... also write it in the chat to the person".

## The board

- [hard] B35: The board opens on Open with the platform switch LinkedIn 2, Reddit 1, Hacker News 2, X 1 and the filter Open 6; the filter offers Open 6, Posted 1, Skipped 1, Expired 3 and All 11; Posted shows only Reddit with one thread; there is no chat input.
- [hard] B36: Pressing `j` selects the next thread and `k` the previous one, the selected thread's key is in the address hash, and opening a posted thread's address switches the filter to All and shows that thread.
- [hard] B37: The selected thread shows Question, Others say and Our angle (bold) with the link "Jump to the draft (reply to u/maple_orbit)", the feedback field, the draft card inside the comment `mq1a009` (under the post when the reply goes to the post), the why line, the posted link, "No summary for this thread." when there is none, the orange bar and Verdana for Hacker News, and avatars plus grey bubbles for LinkedIn comments.
- [hard] B38: The comment count is one number, the stored tree's: `GET /api/threads/reddit:1oq7k2m` answers `comment_count` 12, and the list row and the post header both read it ("12 comments", "1 comment" for one); the platform's own total (13) is not shown.
- [hard] B39: Copy reply puts exactly the reply text on the clipboard and the button then reads Copied; Open thread posts /api/open with the thread's address (answered by the harness, no browser starts); the X draft card shows its character count against 280.
- [hard] B40: Feedback written on the board is saved (Save feedback and Ctrl+Enter), reaches the queue and shows under the summary with the chip open; a failed save shows "Not saved: <error>. Your text is still here." and keeps the typed text.
- [hard] B41: The status actions work on the board: Skip, Reopen and Mark posted with a comment link set the status (and the https link) in the backend.
- [hard] B42: At 390 pixels width the board has no horizontal scroll (the page is not wider than 390), the platform switch wraps onto a second row inside the screen, a picker with the thread titles and Previous thread / Next thread buttons replace the list, Previous is disabled on the first thread and Next on the last.
- [hard] B43: Colours, font sizes and fonts follow `visual-guidelines.md`: every colour and font-size token it declares has that value on the served board, and the font tokens name Inter and Geist Mono.
- [hard] B44: The board polls GET /api/version and, after a write it did not make itself, shows "Claude updated the board" with a Reload button.
- [hard] B45: An X draft above 280 characters (the harness stores one through POST /api/runs; the lint does not check X length) shows its count against 280 in red.
- [hard] B46: The agent's optional internal review (`review.internal`) shows under the thread, next to why.

## Soft

- [soft] S03: Each built screen resembles its approved mockup (the screenshot check of the Test phase records its metric). The report's screen tour attaches the built screen only when the screen's state was reached; otherwise it says so.
- [soft] S09: The skill triggers in a real Claude session: a headless `claude` session with the built plugin loaded, given the phrase "open the reply board", calls the plugin's skill. Needs a login and costs one short model call; skipped (recorded as not run) when `SHIPWRIGHT_E2E_SKILL_TRIGGER` is not `1`.
