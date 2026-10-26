# Social engagement desk

A small desk for a person who answers public conversations about their product. A chat on the left, a pane on the right. The person types a command in the chat; the app does it and the pane shows the result. All data is local JSON; **no external service is called**.

## Fetch new matches
The user types "fetch new matches". The app reads the seeded matches file, adds every match that is not yet on the board as a thread with status `new`, and the pane shows the board. The chat answers with the number of new threads. Fetching twice adds nothing the second time.

## View the board
The pane is a board with one tab per platform: Reddit, Hacker News, LinkedIn. Each tab lists that platform's threads (title, author, a one-line excerpt) with a status badge: `new`, `drafted` or `posted`. Clicking a tab switches the platform; the chat stays as it is.

## Show a thread
The user types "show thread 3" (the number is the thread's id). The pane shows that thread in full: platform, author, the whole text, its status and its draft if one exists. An unknown id gets a plain answer in the chat ("There is no thread 99") and the pane does not change.

## Draft a reply
The user types "draft a reply for thread 3". The app asks the reply drafter for a text, stores it as the thread's draft, sets the status to `drafted` and the pane shows the thread with the draft. Drafting again replaces the draft. The drafter is a deterministic local function behind an interface, so the same thread always gets the same draft.

## Mark a thread as posted
The user types "mark thread 3 as posted" after they posted the reply themselves. The status becomes `posted`, the pane shows the thread with a posted note, and the board badge changes. The app never posts anything itself. Only a `drafted` thread can be marked; any other status gets a plain answer in the chat.

## Set keywords
The user types "set keywords: onboarding, pricing, integrations". The app stores the comma-separated list as the watch keywords, replacing the old list, and the pane shows the keyword list. "fetch new matches" afterwards only adds seeded matches that contain at least one keyword (case-insensitive). With no keywords set, every seeded match counts.

## Glossary
- **Thread**: one public conversation found on a platform: `id` (integer, 1 upward), `platform` (`reddit`, `hackernews` or `linkedin`), `title`, `author`, `text`, `url`, `status` (`new`, `drafted`, `posted`), `draft` (text or null).
- **Match**: a seeded candidate thread in `data/seed_matches.json` (a list of objects with `platform`, `title`, `author`, `text`, `url`). Seed at least nine matches, three per platform, some mentioning onboarding, pricing or integrations.
- **Store**: `data/threads.json` (threads) and `data/keywords.json` (list of strings). Created on first use.
- **Reply drafter**: an interface `draft_reply(thread) -> str` with one local implementation that fills a fixed template with the thread's author and title. No model, no network, no key.
- **Chat commands** (case-insensitive, the number is a thread id): `fetch new matches`, `show thread N`, `draft a reply for thread N`, `mark thread N as posted`, `set keywords: a, b, c`. Anything else gets the list of commands as the answer.
- **Served pane**: one local web server serves the pane and the chat API (`POST /api/chat` takes `{"message": ...}` and answers `{"reply": ..., "pane": ...}`; `GET /api/health` answers 200).
