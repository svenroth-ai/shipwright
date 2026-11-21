# Campaign brief: reminders, part 1 of 2 (`reminders-core`, repo `shipwright`)

Date: 2026-11-21 · Status: operator-approved in chat, nothing built · Part 2 is `reminders-webui` (repo `shipwright-webui`), created only after this campaign has merged.
Branch strategy: `serial`. Units: E1a, then E1b (`depends_on` E1a).

## 0. Goal
Shipwright can hold reminders with real context, and one call returns everything that is due: the reminders themselves AND the parked triage entries whose revisit day has come. The WebUI (part 2) shows the alert and sends mail from that one call. This campaign builds no UI, no mail and no hook.

## 1. What exists today (verified 2026-11-21)
- No reminder, mail, SMTP or scheduler code anywhere in `shipwright` or `shipwright-webui`.
- A parked triage entry is status `snoozed` with `revisitAt`; it counts as open again from that day by DERIVATION at read time (`shared/scripts/lib/triage_defer.py`, field `revisitDue`). `triage_cli.py list --json` is the machine contract and is never capped.
- `triage_cli.py` is the only writer of `triage.jsonl` and owns its locking.

## 2. Operator decisions (2026-11-21)
1. Reminders are created ONLY when the operator asks ("make me a reminder"). No campaign, hook or tool creates one on its own. Auto-creation (e.g. when something is parked) is a later follow-up, not in scope.
2. No SessionStart hook. If the WebUI server is not running there is no reminder; accepted.
3. No secrets in any reminder text, ever. Reminders hold title, date, plain-language context, a command and links, nothing else.
4. Parked triage entries are NOT copied into the reminder store. They are read from the triage store; `due` merges both sources in one answer.

## 3. Units

**E1a: the reminder store and its CLI. Medium.**
1. Store: `.shipwright/reminders.jsonl`, append-only, git-ignored, one event per line, resolved by folding events per id (same idea as `triage.jsonl`). Writes take a lock; a second writer waits.
2. A reminder carries: `id` (`rem-<8 hex>`), `title`, `due` (YYYY-MM-DD, strictly validated), `why` (why now), `decided` (what is already decided), `open` (what is still open), `command` (what to run, optional), `links` (list of `{label, kind, ref}` where kind is `campaign`, `triage`, `file` or `url`), `status` (`open`, `done`, `snoozed`), `snoozed_until`, `created_at`, `done_at`.
3. `shared/scripts/tools/reminder_cli.py`: `add`, `list [--json]`, `show <id> [--json]`, `done <id>`, `snooze <id> --until D`. Human output plain; `--json` is the machine contract and is never capped.
4. A secret-shaped value (token, key, password pattern) in any text field is refused at `add` with a plain message. The check reuses the existing secret patterns in the repo; it must not invent a new list.
5. The store path comes from the resolver `shared/scripts/lib/shipwright_paths.py` (it is tool-owned state, not a root file; it lives under `.shipwright/`), and the worktree/main-root rule applies: a reminder written from a worktree lands in the MAIN checkout's store (see memory note "Main-root resolver").
Done when: add/list/show/done/snooze round-trip in a test; a malformed date, an unknown status and a secret-shaped text are each refused with a clear message; two concurrent adds both survive; a reminder written from a worktree appears in the main store; `.shipwright/reminders.jsonl` is git-ignored.

**E1b: the one `due` answer. Medium. `depends_on: E1a`.**
1. `reminder_cli.py due [--json] [--on D]`: returns every open reminder with `due <= D` (default today) PLUS every parked triage entry with `revisitDue` true on D, each in one common shape: `kind` (`reminder` or `triage`), `id`, `title`, `due`, `why`, `decided`, `open`, `command`, `links`. For a triage entry: `title`/`detail`/severity map to the common fields, `why` is the park reason, and `links` carries one `{kind: "triage", ref: <id>}`.
2. Triage entries are read through the existing resolved view (`read_all_items` / `list --json`), never by parsing `triage.jsonl` directly, so the park-expiry rule stays in one place.
3. `--on D` makes the answer testable and lets the WebUI ask "what is due on a given day"; there is no clock inside the logic other than the default.
4. `docs/hooks-and-pipeline.md` gets the artifact-write row for `reminders.jsonl` (who writes it: `reminder_cli.py` only).
5. After merge, ONE reminder is created by explicit operator request: title "R1 starten (root-files-into-config)", due 2026-11-28, with why/decided/open/command/links as in the operator's chat. This step is done by the orchestrator after the merge, in the main checkout, because the store is git-ignored.
Done when: `due --on` returns an expired park and an open reminder in one list, omits a park that has not expired and a reminder that is done or snoozed past the day, and the shape is identical for both kinds; no code path reads `triage.jsonl` except through the existing resolver; the doc row is present.

## 4. Not in this campaign
The alert, the mail, the Settings page, the server timer: all in `reminders-webui`. Auto-creating reminders: later follow-up, operator's call.

## 5. Merge and review
Normal iterate process per unit: architecture review before build for medium, then spec-reviewer, code-reviewer, doubt-reviewer, each spawned with `model=opus` passed explicitly. Merge: automerge on green CI. No admin merge is granted for this campaign; if PR Review blocks, the runner stops and asks. After each merge: `update-marketplace.sh` and `check_plugin_cache_sync.py --strict`.

## 6. Risks
- A second event-log-shaped store: keep it small and reuse the triage store's locking approach rather than a new one.
- The resolver and the main-root rule are easy to bypass with a plain `Path(".shipwright")`; a test must write from a worktree.
- `due` must not change the triage store's behaviour; E1b only reads.
