# Social engagement desk

A small desk for a person who answers public conversations about their product. A chat on the left, a pane on the right. The person types a command in the chat; the app does it and the pane shows the result. All data is local JSON; **no external service is called**.

## Fetch new matches
Requirement: Typing "fetch new matches" adds every seeded match that is not yet on the board as a new thread.
- Outcome: the board shows the new threads and the chat names how many were added
- Fit criterion: a second "fetch new matches" in a row adds zero threads
- Purpose: the person sees fresh conversations without searching platforms by hand
- Boundaries: only seeded local matches are read; no external service is called
- Failure: a missing or unreadable seed file gets a plain answer in the chat and the board does not change
- Glossary: Match, Thread, Store
- Rationale: a local seed keeps the run free of keys and network
- Out of scope: live fetching from Reddit, Hacker News or LinkedIn
The user types "fetch new matches". The app reads the seeded matches file, adds every match that is not yet on the board as a thread with status `new`, and the pane shows the board. The chat answers with the number of new threads. Fetching twice adds nothing the second time.

## View the board
Requirement: The pane shows one tab per platform with that platform's threads and a status badge.
- Outcome: each tab lists its threads with title, author, a one-line excerpt and the status
- Fit criterion: clicking a tab shows only that platform's threads and leaves the chat untouched
- Purpose: the person sees at a glance what is new, drafted or posted
- Boundaries: three platforms only (Reddit, Hacker News, LinkedIn); statuses new, drafted, posted
- Failure: a platform without threads shows an empty tab, not an error
- Glossary: Thread, Served pane
- Rationale: a board per platform matches how the person works through conversations
- Out of scope: sorting, filtering and search
The pane is a board with one tab per platform: Reddit, Hacker News, LinkedIn. Each tab lists that platform's threads (title, author, a one-line excerpt) with a status badge: `new`, `drafted` or `posted`. Clicking a tab switches the platform; the chat stays as it is.

## Show a thread
Requirement: Typing "show thread N" shows that thread in full in the pane.
- Outcome: the pane shows platform, author, the whole text, the status and the draft if one exists
- Fit criterion: "show thread 99" for an unknown id answers "There is no thread 99" and the pane does not change
- Purpose: the person reads the whole conversation before replying
- Boundaries: the number is the thread id; read only, nothing is changed
- Failure: an unknown id gets a plain answer in the chat
- Glossary: Thread, Chat commands
- Rationale: the board only has excerpts, so the full text needs its own view
- Out of scope: editing the thread text
The user types "show thread 3" (the number is the thread's id). The pane shows that thread in full: platform, author, the whole text, its status and its draft if one exists. An unknown id gets a plain answer in the chat ("There is no thread 99") and the pane does not change.

## Draft a reply
Requirement: Typing "draft a reply for thread N" stores a reply draft and sets the status to drafted.
- Outcome: the pane shows the thread with the draft and the badge reads drafted
- Fit criterion: drafting the same thread twice gives the same text and replaces the old draft
- Purpose: the person starts from a ready draft and edits it elsewhere
- Boundaries: the drafter is a deterministic local function behind an interface; no model, no network
- Failure: an unknown id gets a plain answer in the chat and nothing is stored
- Glossary: Reply drafter, Thread
- Rationale: a fixed template makes the run repeatable and key-free
- Out of scope: model-written replies and posting the reply
The user types "draft a reply for thread 3". The app asks the reply drafter for a text, stores it as the thread's draft, sets the status to `drafted` and the pane shows the thread with the draft. Drafting again replaces the draft. The drafter is a deterministic local function behind an interface, so the same thread always gets the same draft.

## Mark a thread as posted
Requirement: Typing "mark thread N as posted" sets a drafted thread to posted.
- Outcome: the status becomes posted, the pane shows a posted note and the board badge changes
- Fit criterion: marking a thread that is not drafted gets a plain answer in the chat and the status stays
- Purpose: the person records that they posted the reply themselves
- Boundaries: only a drafted thread can be marked; the app never posts anything itself
- Failure: an unknown id or a wrong status gets a plain answer in the chat
- Glossary: Thread, Chat commands
- Rationale: the person stays in control of every public post
- Out of scope: posting to a platform
The user types "mark thread 3 as posted" after they posted the reply themselves. The status becomes `posted`, the pane shows the thread with a posted note, and the board badge changes. The app never posts anything itself. Only a `drafted` thread can be marked; any other status gets a plain answer in the chat.

## Set keywords
Requirement: Typing "set keywords: a, b, c" stores the comma-separated list as the watch keywords.
- Outcome: the list replaces the old one and the pane shows it
- Fit criterion: after setting keywords, "fetch new matches" only adds seeded matches that contain one of them, case-insensitive
- Purpose: the person narrows the matches to the topics they care about
- Boundaries: with no keywords set every seeded match counts; the list is stored in the Store
- Failure: an empty list clears the keywords and says so in the chat
- Glossary: Store, Match, Chat commands
- Rationale: keyword filtering is the simplest way to cut noise
- Out of scope: phrase or boolean search syntax
The user types "set keywords: onboarding, pricing, integrations". The app stores the comma-separated list as the watch keywords, replacing the old list, and the pane shows the keyword list. "fetch new matches" afterwards only adds seeded matches that contain at least one keyword (case-insensitive). With no keywords set, every seeded match counts.

## Glossary
- **Thread**: one public conversation found on a platform: `id` (integer, 1 upward), `platform` (`reddit`, `hackernews` or `linkedin`), `title`, `author`, `text`, `url`, `status` (`new`, `drafted`, `posted`), `draft` (text or null).
- **Match**: a seeded candidate thread in `data/seed_matches.json` (a list of objects with `platform`, `title`, `author`, `text`, `url`). Seed at least nine matches, three per platform, some mentioning onboarding, pricing or integrations.
- **Store**: `data/threads.json` (threads) and `data/keywords.json` (list of strings). Created on first use.
- **Reply drafter**: an interface `draft_reply(thread) -> str` with one local implementation that fills a fixed template with the thread's author and title. No model, no network, no key.
- **Chat commands**: case-insensitive, the number is a thread id; `fetch new matches`, `show thread N`, `draft a reply for thread N`, `mark thread N as posted`, `set keywords: a, b, c`. Anything else gets the list of commands as the answer.
- **Served pane**: one local web server serves the pane and the chat API (`POST /api/chat` takes `{"message": ...}` and answers `{"reply": ..., "pane": ...}`; `GET /api/health` answers 200).
