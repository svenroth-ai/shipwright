# Provenance

Where each part of this Briefing would come from in the future process (a reverse-engineering tool, REA, reads the existing app; an interview skill turns it into a skill companion app: the Claude app is the chat, the skill is the front door, the served board plus backend is the companion for the person and the agent; HTML mockups are approved along the UI kit). For this baseline one author played both roles against the working `social-engagement` skill (SKILL.md, `scripts/*.py`, `templates/board.html`). REA was assumed to read everything; nothing was limited to what a real REA could see.

How the REA part was observed: the scripts and the template were read in full; `state.py`, `build_board.py` and `serve_board.py` were copied (without any key file) and run against a throwaway data folder with synthetic data; the real board was rendered and every route of the real server was called, error cases included; the lint was run on a deliberately bad run in all three modes. No network script (`syften.py`, `fetch_thread.py`, `linkedin_search.py`, `review.py`, `test_filters.py`) was run, no key file was opened, and no private content folder was read.

| Section of brief.md | REA (observed) | Interview (copied from the skill's instructions) | Mockup |
|---|---|---|---|
| Intro: architecture rules | - | skill companion split, stdlib backend, storage and adapter seams, env base URLs | - |
| Intro: Later list, keys | `test_filters.py`, `syften.py filters-*` exist; only Syften and Apify tokens in use | which of them wait; external review dropped | - |
| Start and stop the board from the skill | `serve_board.py` flags, bind, `/api/version` | lifecycle owned by the skill (SKILL.md step 8) | 01 |
| Split the work between agent, backend and board | which script does what | which steps are Claude's judgement | - |
| Serve the companion API | kept routes, headers, limits, error texts (observed live) | the added agent routes | - |
| Fetch hits from the sources | `syften.py items`, `linkedin_search.py run/normalize`, paging rule | when to fetch, `ai_rejected` once a day | - |
| Drop threads that are already known | `state.py key/unseen`, aliases in `build_board.py` | - | - |
| Load a thread with its comment tree | `fetch_thread.py` (actor input, Algolia, cut, ages, hints) | paste fallback, repo-reading rule | - |
| Store the agent's drafts as a run | `build_board.py merge`, template header item shape | - | 02 |
| Lint a draft before it is stored | `build_board.py lint`, messages observed in each mode | - | - |
| Track the status of a thread | `set_status`, expiry, `posted_today`, header line (observed) | cap 5 a day | 03, 05 |
| Give feedback on a draft | `add_feedback` with snapshot, board save flow | - | 04 |
| Work the feedback queue | `state.py feedback/resolve` (observed) | act before closing, quoted text is data | 04 |
| Learn lessons from feedback | - | the whole rule (SKILL.md "Learn"); line format invented | - |
| Watch the board for changes | `watch_board.py`, version polling, `rev` and seen state | re-arm every 30 minutes | 01 |
| Set the posting mode and handles | `state.py config`, `MODES` | mode meanings, first-start questions | 01 (header) |
| Keep the data behind one store module | file names and shapes (observed in the throwaway folder) | - | - |
| Reach external services through one adapter | hosts, auth header, payloads, hints | env base URLs, fake server for tests | - |
| View the board | `board.html` | - | 01, 03, 05 |
| Read a thread the way its platform shows it | `board.html` renderers | - | 01, 02 |
| Copy a draft and open the thread | copy and open handlers, `/api/open` allow list | - | 02, 06 |
| Use the board on a phone | media query and picker | product owner: fix the sideways overflow | 07 (corrected) |
| Guide the agent with skill instructions | `watch_board.py` (feedback watcher) | SKILL.md steps 1 to 9, reply rules, never-list, optional Opus internal review (SKILL.md review cascade step 2); product owner: explain in the chat when the new draft is not enough | - |

Other files:
- `visual-guidelines.md`: REA (the board's `:root` tokens and component CSS), three values adjusted to the kit's contrast and size rules.
- `mockups/*.html` and `*.png`: Mockup, rendered from the real board (REA-observed UI) on synthetic data and frozen; then two real-board defects corrected on the product owner's decision (one comment count from the stored tree in the post header and the list; the platform switch wraps at 390px). PNGs re-rendered from the static HTML.
- `seed/recorded/*.json`: REA for the shapes (as the scripts parse them), synthetic content; `index.json` maps requests to files for the fake server.
- `seed/agent/run-synthetic.json`: a stand-in for the agent's output (Interview rules applied by hand), used by fit criteria; lint-clean in mode expertise against the real `build_board.py --check`.
- `scope.md`: Interview (the scope decision given with this task, and the product owner's answers to OPEN.md: no external review, data folder `~/.social-engagement`, expiry from the run date, feedback explained in the chat when needed).

Rough split: of 21 capabilities, 13 are mainly REA (API, fetch, dedupe, load, store, lint, status, feedback, watch, and the four board capabilities), 3 mainly Interview (split of work, lessons, skill instructions) and 5 mixed (lifecycle, feedback queue, config, storage interface, service adapter); 11 are bound to a mockup in `screen-map.json`, the other 10 are backend or agent capabilities without a screen.
