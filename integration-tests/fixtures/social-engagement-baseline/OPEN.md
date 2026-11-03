# Open points

Assumptions made where the real skill was silent, and what could not be derived. Each one should be confirmed or corrected in the interview step before the package is approved.

## Assumptions

1. **Port 3901, not 8765.** The real board runs on 8765; the `skill-companion-app` profile reserves 3901 for real use and 3911 for development, so a dev run can never attach to real data. Kept the profile's ports.
2. **Data folder `~/.social-engagement`** (decided). As the profile says (`~/.<app-name>`, override `<APP_NAME>_HOME`): `--data-dir`, else `SOCIAL_ENGAGEMENT_HOME` (the folder itself, no longer its parent as in the real skill), else the default.
3. **`.env.local` lives in the data folder**, not in the skill folder, because a plugin update replaces the plugin folder. It still wins over the environment, as in the real `_env()`.
4. **The board is static and reads `/api/board`**; the real build bakes the data into a generated `board.html`. `/api/version` therefore changes on every data write instead of on the file's mtime.
5. **Runs are posted to the backend** (`POST /api/runs`, all or nothing, archived in `runs/<YYYYMMDD-HHMMSS>.json`); the real skill writes a run file and runs `build_board.py`. The SKILL.md says `runs/` holds the run JSONs but no script writes there; the archive format is invented.
6. **Paging and the Syften cursor move into the backend.** The real skill leaves paging to Claude. `last_run` is the newest timestamp seen including dropped sources (the skill's wording "newest item seen").
7. **Expiry counts 14 days from the run date** (decided): the day the agent put the thread on the board, as in `build_board.py`, not the platform post date. `SOCIAL_ENGAGEMENT_TODAY` was added so tests can fix the clock.
8. **Unknown thread is 404** on `/api/status` and `/api/feedback` (the real server answers 400 for every rejection); lint failures are 422 (the real build exits with a message); missing tokens 503 and service failures 502 (the real scripts exit). Error texts are kept where they exist.
9. **Lesson line format** `- <rule> (<feedback id>)` and the duplicate rule (same text ignoring case and trailing punctuation answers 409) are invented; the skill only says "one line, the rule plus the feedback id, two entries that say the same thing: one line".
10. **Feedback watcher** (decided): `/api/events` (`events.jsonl`) replaces `watch_board.py`'s file polling with the same behaviour; the event shape copies its two output lines (FEEDBACK, STATUS). When feedback needs more than the new draft (angle change, declined entry, question back), the agent also explains it in the chat.
11. **Config keys are strict** (unknown key = 400); the real `state.py config` accepts any key and validates only `mode`.
12. **A resolved feedback entry can be resolved again** (note replaced), as the real `state.py resolve` allows. A stricter rule (409) may be wanted.
13. **The X thread is pasted by the person** and stored like any run item; X has no service and no fetch endpoint.
14. **Lifecycle helper `companion.py start|stop|status` and `companion.pid`** are invented; the real skill uses a preview launcher config outside the skill.
15. **Kit token deviations** (visual-guidelines.md): muted text, strong border and the base and small font sizes differ from the real board so the kit's contrast and size checks pass; warning, info and status backgrounds are invented.
16. **ux_shape is `classic`**: the pipeline's own brief vocabulary reserves the older term for a chat pane inside an app, so this package says skill companion.
17. **Keys** (decided): only `SYFTEN_TOKEN` and `APIFY_TOKEN`. The external review is gone from v1 and from Later; the agent's internal Opus review stays as an optional skill step (the real skill had it), stored in the optional `review.internal` field.

## Corrected real-board defects

- **Phone overflow**: at 390 pixels the real platform switch ran off the screen. The spec now wraps it (no horizontal scroll, fit criterion `scrollWidth` 390) and `mockups/07-phone-picker` shows the corrected layout.
- **Two comment counts**: the real post header used the platform's total (deleted comments included, "13 comments") while the list counted the stored tree ("12 comments"). The spec now defines one number, `comment_count` = comments in the stored tree, shown in both places; `post.stats` no longer carries a count. Mockups 01 and 06 changed text accordingly (others already matched).

## Could not be derived

- **Syften item fields beyond the ones the scripts read.** Confirmed by code: `id`, `item.item_url`, `item.backend` ("Reddit" exact), `item.backend_sub`, `item.timestamp`, `item.title`, `item.text`. Assumed: the Hacker News backend name ("Hacker News"; the adapter compares without case and spaces), `item.type`, `item.author`, `item.lang`, `filter`, `ai`. Syften documentation was not read (no network).
- **Apify Reddit actor output** beyond the fields `fetch_thread.py` reads (`dataType`, `id`, `title`, `body`, `authorName`, `ageHours`, `score`, `commentsCount`, `parentKind`, `parsedParentId`); `parsedId`, `postId`, `url`, `communityName`, `createdAt` are assumed. Whether comment ids carry a `t1_` prefix is unknown.
- **Apify LinkedIn output**: the normaliser accepts several alternatives (`actor` or `author`, `commentary` or `content` or `text`, `postId` or `post_id`); the recording uses the first of each. Whether comments arrive nested in the post or as separate dataset items is unknown; both are handled by the real code.
- **Algolia** fields beyond `id, type, story_id, author, title, text, points, created_at_i, children` are assumed.
- **The person's voice, product, background and angle-bank files** are inputs the agent reads; their content was not read (private) and is not part of the app. Their rules appear in the skill instructions only as far as SKILL.md states them.
- **Reddit subreddit rules** cannot be loaded (Reddit blocks scripts); the app only links them.
- **Daily cap enforcement**: the real board only shows "posted today n/5"; kept as display, not a block.
- **Approval**: `brief.json` has no `approved_by` / `approved_at`. The package needs a person's approval (and a fresh `package_sha256` after any change) before `/shipwright-run --brief` accepts it.
- **Non-UI capabilities without a screen** (10 of 21) will show as `unmapped_frs` in Design; that is informational, but a deciding note may be wanted.
