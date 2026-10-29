# Social engagement board

A skill-backed app for a person who answers public conversations about their product. The chat is the Claude app itself; this app is a plugin with one skill. The skill is the front door: it starts a small local companion (a Python backend that serves a board page and a JSON API) and stops it again. The board shows the conversations; the person works through them on the board. All data is local JSON files in a data folder; **no external service is called**.

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
The plugin holds `.claude-plugin/plugin.json` and `skills/social-engagement/SKILL.md`. The skill starts `backend/server.py`, waits for `GET /api/health`, tells the person the board address and stops the process when asked.

## View the board
Requirement: The board shows one tab per platform with that platform's threads and a status badge per thread.
- Outcome: each tab lists its threads with title, author, a one-line excerpt and the status
- Fit criterion: opening a tab shows only that platform's threads; `GET /api/threads?platform=reddit` returns only Reddit threads
- Purpose: the person sees at a glance what is new, drafted or posted
- Boundaries: three platforms only (Reddit, Hacker News, LinkedIn); statuses new, drafted, posted; the board has no chat panel, no message log and no chat input
- Failure: a platform without threads shows an empty tab, not an error
- Glossary: Board, Thread
- Rationale: a board per platform matches how the person works through conversations
- Out of scope: sorting, filtering and search
The board is the whole page. A tab strip has one tab per platform: Reddit, Hacker News, LinkedIn. Each tab lists that platform's threads (title, author, a one-line excerpt) with a status badge: `new`, `drafted` or `posted`. A button fetches new matches and a link opens the keywords.

## Fetch new matches
Requirement: A "Fetch new matches" button on the board adds every seeded match that is not yet on the board as a new thread.
- Outcome: the board shows the new threads and tells the person how many were added
- Fit criterion: `POST /api/fetch` answers `{"added": N}` with N above zero on a fresh data folder and `{"added": 0}` the second time
- Purpose: the person sees fresh conversations without searching platforms by hand
- Boundaries: only seeded local matches are read; no external service is called
- Failure: a missing or unreadable seed file gets a plain error answer and the board does not change
- Glossary: Match, Thread, Store
- Rationale: a local seed keeps the run free of keys and network
- Out of scope: live fetching from Reddit, Hacker News or LinkedIn
Fetching reads the seed file, adds every match that is not yet a thread with status `new` and answers with the number added. Fetching twice adds nothing the second time.

## Show a thread
Requirement: Clicking a thread on the board shows it in full.
- Outcome: the detail shows platform, author, the whole text, the status and the draft if one exists
- Fit criterion: `GET /api/threads/99` for an unknown id answers 404 with `{"error": "There is no thread 99"}`
- Purpose: the person reads the whole conversation before replying
- Boundaries: the number is the thread id; read only, nothing is changed
- Failure: an unknown id gets a plain error answer
- Glossary: Thread, Companion API
- Rationale: the board only has excerpts, so the full text needs its own view
- Out of scope: editing the thread text
`GET /api/threads/<id>` returns the thread with all its fields.

## Draft a reply
Requirement: A "Draft reply" button on the thread detail stores a reply draft and sets the status to drafted.
- Outcome: the detail shows the draft and the badge reads drafted
- Fit criterion: `POST /api/threads/1/draft` twice gives the same draft text and replaces the old draft
- Purpose: the person starts from a ready draft and edits it elsewhere
- Boundaries: the drafter is a deterministic local function behind an interface; no model, no network
- Failure: an unknown id gets a plain error answer and nothing is stored
- Glossary: Reply drafter, Thread
- Rationale: a fixed template makes the run repeatable and key-free
- Out of scope: model-written replies and posting the reply
The drafter fills a fixed template with the thread's author and title, the draft is stored on the thread and the status becomes `drafted`.

## Mark a thread as posted
Requirement: A "Mark as posted" button on a drafted thread sets it to posted.
- Outcome: the status becomes posted, the detail shows a posted note and the board badge changes
- Fit criterion: `POST /api/threads/2/posted` on a thread that is not drafted answers 409 with an `error` text and the status stays
- Purpose: the person records that they posted the reply themselves
- Boundaries: only a drafted thread can be marked; the app never posts anything itself
- Failure: an unknown id answers 404 and a wrong status answers 409, each with a plain `error` text
- Glossary: Thread, Companion API
- Rationale: the person stays in control of every public post
- Out of scope: posting to a platform
`POST /api/threads/<id>/posted` changes `drafted` to `posted`; any other status is refused.

## Set keywords
Requirement: The keywords view stores a comma-separated list as the watch keywords.
- Outcome: the list replaces the old one and the view shows it
- Fit criterion: after `PUT /api/keywords` with `{"keywords": ["onboarding", "pricing", "integrations"]}`, `POST /api/fetch` only adds seeded matches that contain one of them, case-insensitive
- Purpose: the person narrows the matches to the topics they care about
- Boundaries: with no keywords set every seeded match counts; the list is stored in the Store
- Failure: an empty list clears the keywords and the view says so
- Glossary: Store, Match
- Rationale: keyword filtering is the simplest way to cut noise
- Out of scope: phrase or boolean search syntax
`GET /api/keywords` answers `{"keywords": [...]}`; `PUT /api/keywords` replaces the list and answers the new list.

## Glossary
- **Skill**: the front door in the Claude app: `skills/social-engagement/SKILL.md`, which starts and stops the companion.
- **Companion**: the local Python backend (`backend/server.py`) that serves the board page and the JSON API on 127.0.0.1; the skill starts and stops it.
- **Board**: the served HTML page (`board/`), composed from the design kit and the package's colour and size tokens; plain HTML, CSS and vanilla JavaScript. Its `:root` declares every colour and font-size token of `visual-guidelines.md`.
- **Data folder**: the folder given to the companion with `--data-dir`, outside the plugin install; it holds only JSON files.
- **Thread**: one public conversation found on a platform: `id` (integer, 1 upward), `platform` (`reddit`, `hackernews` or `linkedin`), `title`, `author`, `text`, `url`, `status` (`new`, `drafted`, `posted`), `draft` (text or null).
- **Match**: a seeded candidate thread in the plugin's seed file `seed/matches.json` (a list of objects with `platform`, `title`, `author`, `text`, `url`). Seed at least nine matches, three per platform, some mentioning onboarding, pricing or integrations.
- **Store**: `threads.json` (threads) and `keywords.json` (list of strings) in the data folder. Created on first use.
- **Reply drafter**: an interface `draft_reply(thread) -> str` with one local implementation that fills a fixed template with the thread's author and title. No model, no network, no key.
- **Companion API**: JSON over HTTP. `GET /api/health` answers 200. `GET /api/threads[?platform=P]` answers `{"threads": [...]}`. `GET /api/threads/<id>` answers the thread. `POST /api/fetch` answers `{"added": N}`. `POST /api/threads/<id>/draft` and `POST /api/threads/<id>/posted` answer the thread. `GET /api/keywords` and `PUT /api/keywords` answer `{"keywords": [...]}`. Every answer is JSON; an error carries a plain `error` text (404 unknown route or id, 409 wrong status). State-changing routes take `Content-Type: application/json` and check the Origin is same-origin.
