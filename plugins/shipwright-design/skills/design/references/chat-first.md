# Chat-first design (`ux_shape: chat-first`) -- LEGACY

**Retired for the skill-backed app class.** There the chat is the Claude app and the companion is a served HTML board (profile `skill-companion-app`, `ux_shape: classic`, `ui_host: served-board`; the brief vocabulary has no `skill-companion` shape, the profile's own value is informational, and a package for this class says `classic`): its Design composes from the kit ([brief-compose.md](brief-compose.md)) and never builds a chat layout. A package with that profile is composed as a board even if its `ux_shape` says `chat-first`. The rest of this file applies only to an older package that still declares `chat-first` with another profile.

Read this after `apply-brief-package.py` exited 0 and its result says `"ux_shape": "chat-first"` and the run profile is not `skill-companion-app` (the field is also present on `already_applied`). A classic package (`"ux_shape": "classic"`) never reads this file.

## What a chat-first design is

A chat on the left, a pane on the right ([Layout D](snippets-layout.md)). `ui_host` comes from the result (the bundled profile `chat-first-json` hosts the pane itself: `served-pane`); report it, do not change it. The package carries `chat-map.json` next to `screen-map.json`:

```json
{"version": 1,
 "capabilities": [{"id": "fetch-matches", "command": "fetch new matches",
                   "requirements": ["fetch-new-matches"], "screen": "board-new"}],
 "golden_paths": [{"id": "triage-a-thread", "title": "Triage a thread",
                   "steps": [{"say": "fetch new matches", "screen": "board-new"}]}]}
```

- A **chat-only capability** is something the user does by typing a command. Its **pane-state screen** is the `screen-map.json` entry named by `screen`; that entry's `requirements` list the capability's requirement slugs. The FR ids in the screen's `<!-- Requirements: ... -->` comment are the ones Project minted: the tool writes them, you never type an FR id.
- A **golden path** is the happy-path conversation: per step what the user says and which pane-state screen shows. The tool turns each golden path into one **flow mockup** `flows/NN-<path id>.html` (generated, standalone, written once; later review-loop edits survive). The flows gate therefore needs nothing from you.
- Re-entry (a resumed Design, upload mode coming back): the tool answers `already_applied` and writes nothing, so flows and screens edited in the review loop stay as they are; a deleted flow turns `brief_chat_first_applied` red (restore it by deleting `brief-package-applied.json` and re-running, as for any missing target).
- `chat-map.json` is where chat-only capabilities are declared; their pane-state screens live in `screen-map.json` (the single namespace for screens). A dangling screen reference is a `bad_chat_map` issue, never silently skipped.
- Mockups stay untouched in `uploads/`; the screens in `screens/` are copies with Linked FRs (see the Brief section of [upload-mode.md](upload-mode.md)).

## What you do

1. The tool already did everything above. Generate NO screen and NO flow by hand. Skip Step 3.7 (a chat-first design has no shared chrome: no `chrome-definition.md`, no navigation markup).
2. Run `check-design-gates.py --gate all`, then go on with Step 6a, 8, 8.5, 9 as in upload mode. The `design.preview-approval` checkpoint is still a human gate; you never answer it.
3. The design verifier check `brief_chat_first_applied` runs with `brief_design_applied` at the phase gate.

## Every outcome, for an unattended agent

| Outcome | Action |
|---|---|
| tool exit 0, `flows` lists the package's flow files (also on `already_applied`) | continue; report `kept_existing_differs` entries (an existing flow that is not the generated one) |
| tool exit 1 `applied_files_missing` for a flow | STOP and report; the operator restores it (delete `brief-package-applied.json`, re-run) |
| tool exit 1 with `bad_chat_map` issues | STOP and report the issues (a package defect: the fix is a re-approved package, never an edit of `brief/`) |
| tool exit 3 | STOP and report (package refused) |
| gate `chrome` red with "chip used as navigation" | STOP and report: a mockup uses `nav-item`/`topnav-link` on a chip (package defect; a chip inside an HTML comment counts too); do not edit the mockup, the upload or the screen |
| any other gate red | the rules of the Brief section in [upload-mode.md](upload-mode.md) apply unchanged |
| `brief_chat_first_applied` red | STOP and report; never retype FR ids, never edit `chat-map.json` or approved files |
| preview rejected | the Brief section's rule applies: STOP and report, the operator decides |

Never waive an FR, never write a `## Non-UI FRs` entry or an ADR, never edit `brief/`.

## Authoring a chat-first package (for the person who writes it)

Pane-state mockups follow Layout D: chips use class `chip` (never `nav-item`/`topnav-link`), pane tabs `pane-tab`; every file is self-contained HTML. `integration-tests/fixtures/social-engagement/` is a complete example. The chip rule applies to every project's screens (a filter chip used as a tab is a violation too). Out of scope here (follow-ups): a chat-only FR that is linked to some screen but has no `chat-map.json` entry gets no command and no golden-path step and is not detected (an FR with no screen at all is caught by `fr-coverage`; `unmapped_frs` stays informational), and flow mockups are not hand-authored per package.
