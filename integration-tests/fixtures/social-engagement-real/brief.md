# Social engagement reply board

A skill-backed app for a person who answers public conversations about their product. The chat is the Claude app itself; this app is a plugin with one skill. The skill is the front door: it starts a small local companion (a Python backend that serves a board page and a JSON API) and stops it again. The board is a master-detail page: the list of threads on the left, one thread on the right with its summary, its reply draft, a feedback field and its status. Hits come from a **source adapter** that can be exchanged; in every test and without keys it replays recorded answers shaped like Syften (Reddit, Hacker News) and Apify (LinkedIn). All data is local JSON files in a data folder.

## Open the board from the skill
Requirement: The skill starts the local companion on request, opens the board in the browser and stops the companion when the person ends the round.
- Outcome: the person says "open the social engagement board" in the Claude app and the board is in the browser; "stop the board" ends the companion
- Fit criterion: `GET /api/health` answers 200 as soon as the board opens and a second start does not start a second companion
- Purpose: the person never starts a server by hand
- Boundaries: the companion binds 127.0.0.1 only, takes `--host`, `--port` and `--data-dir`, and keeps its data in the data folder
- Failure: a port already in use or a data folder that cannot be written gets a plain message from the skill and no half-started companion
- Glossary: Skill, Companion, Data folder
- Rationale: the skill owns the lifecycle so the board and the data never outlive the round by accident
- Out of scope: running the companion as a system service
The plugin holds `.claude-plugin/plugin.json` and `skills/social-engagement/SKILL.md`. The skill description names its trigger phrases ("social engagement", "reply board", "open the social engagement board", "fetch new hits"). The skill starts `backend/server.py`, waits for `GET /api/health`, tells the person the board address and stops the process when asked.

## View the board
Requirement: The board is one master-detail page: a switcher with one entry per platform, a status filter, the thread list on the left and the selected thread on the right.
- Outcome: the person picks a platform and a status and sees only those threads in the list; selecting a thread shows it on the right without leaving the page
- Fit criterion: `GET /api/threads?platform=reddit` returns only Reddit threads and `GET /api/threads?status=skipped` only skipped ones; each list row shows a status badge
- Purpose: the person works through the day's threads one after the other without losing the list
- Boundaries: three platforms (Reddit, Hacker News, LinkedIn); the platform switcher shows a count per platform; the status filter offers all, new, drafted, posted, skipped and expired and starts at all; the board has no chat panel, no message log and no chat input and no separate keywords tab
- Failure: a platform or status without threads shows an empty list and an empty-state text, not an error
- Glossary: Board, Thread, Status
- Rationale: master-detail keeps the list in view while one thread is read and answered
- Out of scope: search, sorting and keyboard shortcuts
The board is the whole page. The header holds the title and the platform switcher (Reddit, Hacker News, LinkedIn, each with its count) and the status filter. Below, the list of threads is on the left and the selected thread is on the right. A list row shows platform label, author, title and a status badge (`new`, `drafted`, `posted`, `skipped`, `expired`). On a narrow screen the list becomes a picker above the thread.

## Fetch new hits
Requirement: A "Fetch new hits" button asks the source adapter for items and adds every item that is not yet a thread as a new thread.
- Outcome: the board shows the new threads and tells the person how many were added
- Fit criterion: `POST /api/fetch` answers `{"added": N}` with N above zero on a fresh data folder and `{"added": 0}` the second time
- Purpose: the person sees fresh conversations without searching platforms by hand
- Boundaries: items are read through `fetch_items(sources)` only (see Source adapter); an item whose url is already a thread is not added twice
- Failure: an adapter that fails answers a plain `error` text with status 502 and the board does not change
- Glossary: Source adapter, Recorded answer, Item, Thread
- Rationale: the board does not care where the hits come from, so the source can change and tests need no network and no keys
- Out of scope: scheduling, paging and cost limits
Fetching calls `fetch_items(sources)` with the active sources, turns every item into a thread with status `new` and answers with the number added.

## Read a thread
Requirement: Selecting a thread shows it on the right the way its platform shows it, with a short summary above it.
- Outcome: the right side shows the summary (the question, what others say, our angle), then the post with author and points and its comment tree
- Fit criterion: `GET /api/threads/99` for an unknown id answers 404 with `{"error": "There is no thread 99"}`; a known thread carries `summary` (an object with `question`, `others`, `angle`) and `comments` (a list, each with `author`, `text`, `depth`)
- Purpose: the person understands the conversation before replying
- Boundaries: read only; the thread text is never edited; comments are nested at most three levels
- Failure: an unknown id gets a plain error answer
- Glossary: Thread, Summary, Comment
- Rationale: the person judges a reply by the conversation around it
- Out of scope: loading comments live from a platform
The summary is made by a deterministic local function from the thread (first sentence as the question, the comments joined as what others say, a fixed angle line). Comments come from the item; an item without comments shows the post only.

## Draft a reply and copy it
Requirement: A "Draft reply" button on the selected thread stores a reply draft, sets the status to drafted and shows the draft in its own card with a "Copy reply" button.
- Outcome: the draft card is below the thread and "Copy reply" puts the draft text on the clipboard and says so
- Fit criterion: `POST /api/threads/1/draft` twice gives the same draft text and replaces the old draft
- Purpose: the person starts from a ready draft and posts it by hand
- Boundaries: the drafter is a deterministic local function behind an interface; no model, no network; the app never posts anything
- Failure: an unknown id gets a plain error answer and nothing is stored; a copy that the browser refuses shows a plain message
- Glossary: Reply drafter, Thread
- Rationale: a fixed template makes the run repeatable and key-free
- Out of scope: model-written replies and reviews by other models
The drafter fills a fixed template with the thread's author and title; the draft is stored on the thread and the status becomes `drafted`.

## Give feedback on a draft
Requirement: A feedback field on a drafted thread stores the person's note about the draft.
- Outcome: the note is saved and shown again when the thread is selected later
- Fit criterion: after `PUT /api/threads/1/feedback` with `{"feedback": "shorter, no greeting"}`, `GET /api/threads/1` returns that text in `feedback`
- Purpose: the person's corrections stay with the draft for the next round
- Boundaries: only a drafted thread takes feedback; one note per thread, a new one replaces the old
- Failure: an unknown id answers 404 and a thread that is not drafted answers 409, each with a plain `error` text
- Glossary: Thread, Feedback
- Rationale: feedback is how the drafts get better
- Out of scope: applying the feedback automatically
`PUT /api/threads/<id>/feedback` stores the text on the thread and answers the thread.

## Mark a thread as posted or skipped
Requirement: "Mark as posted" on a drafted thread sets it to posted, "Skip" on a new or drafted thread sets it to skipped.
- Outcome: the status changes, the list badge changes and the right side shows a note
- Fit criterion: `POST /api/threads/2/posted` on a thread that is not drafted answers 409 with an `error` text and the status stays
- Purpose: the person records what they did with each thread
- Boundaries: only a drafted thread can be marked posted; a posted thread cannot be skipped; the app never posts anything itself; a new or drafted thread that is older than 14 days shows the derived status `expired` and takes neither action
- Failure: an unknown id answers 404 and a wrong status answers 409, each with a plain `error` text
- Glossary: Thread, Status
- Rationale: the person stays in control of every public post
- Out of scope: posting to a platform
`POST /api/threads/<id>/posted` changes `drafted` to `posted` (an optional `{"url": "..."}` body stores the link of the person's own comment); `POST /api/threads/<id>/skipped` changes `new` or `drafted` to `skipped`.

## Set the sources
Requirement: The sources view stores the filters the source adapter searches with: Syften filters for Reddit and Hacker News and queries for LinkedIn.
- Outcome: the list replaces the old one and the view shows it with a status per source
- Fit criterion: after `PUT /api/sources` with `{"sources": [{"kind": "syften", "query": "shipwright", "status": "active"}, {"kind": "linkedin", "query": "ai coding agent", "status": "active"}]}`, `GET /api/sources` returns them
- Purpose: the person steers what the board finds
- Boundaries: `kind` is `syften` or `linkedin`; `status` is `active`, `test` or `dropped`; only active sources are passed to the adapter; the sources are a dialog or a side panel of the board, never a tab of their own
- Failure: an unknown `kind` or `status` answers 400 with a plain `error` text and the list stays
- Glossary: Source, Source adapter
- Rationale: keywords are search filters of the sources, not a view of the board
- Out of scope: validating the filter syntax and a trial run against the real service
`GET /api/sources` answers `{"sources": [...]}`; `PUT /api/sources` replaces the list and answers it.

## Glossary
- **Skill**: the front door in the Claude app: `skills/social-engagement/SKILL.md`, which starts and stops the companion.
- **Companion**: the local Python backend (`backend/server.py`) that serves the board page and the JSON API on 127.0.0.1; the skill starts and stops it.
- **Board**: the served HTML page (`board/`), composed from the design kit and the package's colour, size and font tokens; plain HTML, CSS and vanilla JavaScript. Its `:root` declares every colour, font-size and font token of `visual-guidelines.md`.
- **Data folder**: the folder given to the companion with `--data-dir`, outside the plugin install; it holds only JSON files.
- **Item**: one hit as the source adapter returns it: `platform` (`reddit`, `hackernews` or `linkedin`), `title`, `author`, `text`, `url`, `found_at` (ISO timestamp), `comments` (list, may be empty).
- **Thread**: one item the board holds: `id` (integer, 1 upward), the item's fields, `status` (`new`, `drafted`, `posted`, `skipped`; `expired` is derived and never stored), `summary`, `draft` (text or null), `feedback` (text or null), `posted_url` (text or null).
- **Status**: the five values a list row can show; `expired` is shown for a `new` or `drafted` thread whose `found_at` is more than 14 days ago.
- **Source**: one search filter: `kind` (`syften` or `linkedin`), `query`, `status` (`active`, `test`, `dropped`).
- **Source adapter**: the only place that names an external service. Package `backend/sources/` exposes `fetch_items(sources) -> list[Item]`. Its Syften part reads `https://syften.com/api/v1/items` with the token in the environment variable `SYFTEN_TOKEN`; its Apify part runs the actor `harvestapi/linkedin-post-search` with `APIFY_TOKEN`. **Replay of the recorded answers is the default: the adapter calls a service only when the environment variable `SOCIAL_ENGAGEMENT_LIVE` is `1` and that service's token is set; otherwise, with or without tokens in the environment, it replays the recorded answers and never touches the network.** No other file in the plugin may name a service, a URL outside loopback or read a key.
- **Recorded answer**: a saved real-shaped answer of a service, kept in `seed/recorded/`. `seed/recorded/syften.json` is a list, newest first, of `{"id": ..., "item": {"item_url", "backend" ("reddit" or "hackernews"), "timestamp" (ISO), "title", "author", "text", "comments": [{"author", "text", "depth"}]}}`; `seed/recorded/apify_linkedin.json` is a list of `{"id", "linkedinUrl", "author": {"name"}, "content", "postedAt": {"date" (ISO)}, "comments": [{"author", "text", "depth"}]}`. Authors, handles and urls in the recordings are invented, never real people or accounts. Record at least nine items in total, at least three per platform (Reddit and Hacker News from Syften, LinkedIn from Apify), some mentioning onboarding, pricing or integrations, and at least two more than 14 days older than the newest item. On replay the adapter shifts every timestamp by the same amount so that the newest item is one day old at that moment; the recordings therefore always yield recent threads and at least two expired ones. Tests use the recorded answers through the same adapter code path as the app; no test needs the network or a key.
- **Reply drafter**: an interface `draft_reply(thread) -> str` with one local implementation that fills a fixed template with the thread's author and title. No model, no network, no key.
- **Summary**: `{"question", "others", "angle"}` derived locally from a thread.
- **Comment**: `{"author", "text", "depth"}` with depth 0 to 2.
- **Feedback**: the person's one note about a draft.
- **Store**: `threads.json` (threads) and `sources.json` (list of sources) in the data folder. Created on first use; a fresh data folder starts with one active source of each kind.
- **Companion API**: JSON over HTTP. `GET /api/health` answers 200. `GET /api/threads[?platform=P][&status=S]` answers `{"threads": [...]}`. `GET /api/threads/<id>` answers the thread. `POST /api/fetch` answers `{"added": N}`. `POST /api/threads/<id>/draft`, `POST /api/threads/<id>/posted` and `POST /api/threads/<id>/skipped` answer the thread. `PUT /api/threads/<id>/feedback` answers the thread. `GET /api/sources` and `PUT /api/sources` answer `{"sources": [...]}`. Every answer is JSON; an error carries a plain `error` text (400 bad input, 404 unknown route or id, 409 wrong status, 502 adapter failure). State-changing routes take `Content-Type: application/json` and check the Origin is same-origin.
