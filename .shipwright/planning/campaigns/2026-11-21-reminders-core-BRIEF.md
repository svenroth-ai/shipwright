# Campaign brief: reminders, part 1 of 2 (`reminders-core`, repo `shipwright`)

Date: 2026-11-21 · Status: rev 2 (operator-approved in chat, plan review applied), nothing built · Part 2 is `reminders-webui` (repo `shipwright-webui`), created only after this campaign has merged.
Branch strategy: `serial`. Units: E1a, then E1b (`depends_on` E1a). The operator starts the campaign from the WebUI, not autonomously from chat.

## 0. Goal
Shipwright can hold reminders with real context, and one call returns everything that is due: the reminders themselves AND the parked triage entries whose revisit day has come. The WebUI (part 2) shows the alert and sends mail from that one call. This campaign builds no UI, no mail and no hook.

## 1. What exists today (verified 2026-11-21, rev 2 corrects rev 1)
- No reminder STORE, mail, SMTP or scheduler anywhere in `shipwright` or `shipwright-webui`. (`shared/scripts/hooks/plugin_sync_reminder_on_stop.py` is an unrelated Stop-hook nudge; avoid a name clash.)
- A parked triage entry is status `snoozed` with `revisitAt`; it counts as open again from that day by DERIVATION at read time (`lib/triage_defer.py`, field `revisitDue`, `resolve_revisit`). `triage list --json` is never capped.
- The triage store lives in `shared/scripts/triage.py` (not in `triage_cli.py`); its lock is `lib/file_lock.FileLock`. Many producers write it. The WebUI writes it through its own TypeScript implementation with `proper-lockfile`, which does NOT coordinate with the Python lock. Consequence for this feature: the WebUI must never write `reminders.jsonl` directly; it may only call `reminder_cli.py`.

## 2. Operator decisions (2026-11-21)
1. Reminders are created ONLY when the operator asks ("make me a reminder"). No campaign, hook or tool creates one on its own. Auto-creation is a later follow-up.
2. No SessionStart hook. If the WebUI server is not running there is no reminder; accepted.
3. No secrets in any reminder text, ever (see E1a.4).
4. Parked triage entries are NOT copied into the reminder store; `due` merges both sources in one answer.
5. The store is git-ignored and local; losing it to `git clean -fdx` or a re-clone is accepted.

## 3. Units

Shared design rules for both units (from the plan review, so nobody builds a second mechanism):
- **Reuse:** locking = `lib/file_lock.FileLock`; tolerant reading = `lib/jsonl_records.read_jsonl_records`; append = copy triage's handling of a file without a trailing newline (`triage.py` append helper, `jsonl_records.ends_without_newline`).
- **Layout (300-line limit per file):** `shared/scripts/lib/reminder_store.py` (path, append, fold, validation), `lib/reminder_secrets.py` (the secret check), `lib/reminder_due.py` (the merge), `shared/scripts/tools/reminder_cli.py` (thin verbs; accept `--project-root` before or after the verb like `triage_cli.py`). Tests under `shared/tests/` (one test root); concurrency and worktree tests use a real `git init` + `git worktree add` and two processes, not threads.
- **Path:** a module constant `.shipwright/reminders.jsonl`, resolved at the MAIN root with `lib/repo_root.resolve_main_repo_root`, falling back to the given project root when it returns `None` (precedent: `lib/quarantine_log.py`). NOT a `shipwright_paths.py` row: that registry is for the root `shipwright_*` files, its guard pins the exact name set, and a new row would be moved by the root-files campaign's R3.

**E1a: the reminder store and its CLI. Medium.**
1. Store: append-only JSONL, two event types: `add` (carries all fields) and `status` (`done`, `snoozed`, `open` with `snoozed_until`). Fold rule: last valid event per id wins, in file order (single file, so no triage-style union sort). A new id's uniqueness is checked while holding the lock.
2. Fields: `id` (`rem-<8 hex>`), `title`, `due` (YYYY-MM-DD, strict), `why`, `decided`, `open`, `command` (optional), `links` (list of `{label, kind, ref}`, kind in `campaign`, `triage`, `file`, `url`), `status` (`open`, `done`, `snoozed`), `snoozed_until`, `created_at`, `done_at`.
3. CLI verbs: `add`, `list [--json]`, `show <id> [--json]`, `done <id>`, `snooze <id> --until D`. `--json` is the machine contract and never capped. A `done` reminder cannot be snoozed (refused); `--until` must be after today (UTC).
4. **Secret check** (`lib/reminder_secrets.py`): refuses at `add` and at every status event that carries text. It covers EVERY text field including `command` and `links[].label` / `links[].ref`. Source: reuse the one pattern set that has no URL rule (`lib/main_health_diagnosis.py`) by promoting it to a single public `contains_secret()` that its current caller also uses (no fifth private copy), plus a URL-credentials check (`user:pass@`, `?token=`, `&key=`). Test fixtures build secret-shaped strings from fragments (precedent `test_backfill_engine_units.py`) so scanners do not trip on them.
5. Docs in the same diff: the Artifact Write Matrix row in `docs/hooks-and-pipeline.md` (writer: `reminder_cli.py` only; explicit note that the WebUI must call the CLI), and the `docs/guide.md` Appendix B command row if the repo's rule applies. Spec bookkeeping: decide at planning whether this adds a new FR (per `shared/fr-authoring.md`) or is `tooling` with a stated reason; record it, do not leave it to F5b.
6. Optional: an explicit `.shipwright/reminders.jsonl` line in `.gitignore` AND `shared/templates/shipwright-gitignore.template` (they must stay congruent; `test_gitignore_template_congruent.py`). It is already covered by `/.shipwright/*`; add only to pin the intent.
Done when: add/list/show/done/snooze round-trip in a test; a malformed date, an unknown status, a `done` snooze, a past `--until` and a secret-shaped text in each text field (including a URL with credentials) are each refused with a plain message; two concurrent processes adding both survive with distinct ids; a reminder written from a worktree lands in the main store; the doc row is present.

**E1b: the one `due` answer. Medium. `depends_on: E1a`.**
1. `reminder_cli.py due [--json] [--on D]`. "Today" is the UTC calendar day, from the same helper triage uses (`triage_defer.utc_date(now_utc())`), so a reminder and a park due the same day flip at the same moment. `--on D` becomes `datetime.combine(D, time.min, tzinfo=timezone.utc)` for triage, because `triage.read_all_items` takes an aware datetime.
2. Effective state, defined like triage's `resolve_revisit`: an `open` reminder is due when `due <= D`; a `snoozed` reminder is due when `snoozed_until <= D` and its effective `due` is `snoozed_until`; `done` is never due.
3. Triage side: call `triage.read_all_items` directly (no subprocess) and select items with `revisitDue == True` (they resolve to status `triage`). Which root is read, and the cross-worktree merge it does, are stated in the output (`on`, and a `source_root` note) because the answer differs between the main checkout and a worktree. A park made with `snooze` and no date never appears; an expired park appears every day until acted on (part 2 must suppress repeat mails).
4. **Output contract, versioned:** `{contractVersion: 1, on: "YYYY-MM-DD", items: [...]}`; every item has the same fixed field set, `null` where empty: `kind` (`reminder`|`triage`), `id`, `title`, `due`, `why`, `decided`, `open`, `command`, `links`, `severity`. Mapping for a triage item: `due` = `revisitAt`; `why` = `statusReason`; `decided` = `null`; `open` = the item's `detail`; `command` = `null`; `severity` = its severity; `links` = one `{kind: "triage", ref: <id>}`. The text fields of triage items are passed through the secret redaction at output time because part 2 mails this output off the machine. A pinned-shape test and a "Cross-repo contract" note naming the WebUI as consumer are required (`test_cross_repo_contract_documented.py` pattern).
5. After merge, ONE reminder is created by explicit operator request, by the orchestrator in the main checkout (the store is git-ignored): "R1 starten (root-files-into-config)", due 2026-11-28, with why/decided/open/command/links as agreed in chat.
Done when: `due --on` returns an expired park and an open reminder in one list with the identical item shape; omits a park that has not expired, a `done` reminder and a snooze not yet ended; includes a snooze that has ended with `due = snoozed_until`; a reminder and a park due the same UTC day appear together; no code reads `triage.jsonl` except through `read_all_items`; the contract shape is pinned and documented.

## 4. Not in this campaign
The alert, the mail, the Settings page, the server timer, repeat-mail suppression: all in `reminders-webui`. Auto-creating reminders: later follow-up, operator's call.

## 5. Merge and review
Normal iterate process per unit: architecture review before build for medium, then spec-reviewer, code-reviewer, doubt-reviewer, each spawned with `model=opus` passed explicitly. Merge: automerge on green CI. No admin merge is granted for this campaign; if PR Review blocks, the runner stops and asks. After each merge: `update-marketplace.sh` and `check_plugin_cache_sync.py --strict`.

## 6. Risks
- A second event-log-shaped store: it must reuse `FileLock` and the tolerant reader, not copy them.
- Bypassing the main-root rule with a plain `Path(".shipwright")`: a test must write from a worktree.
- `due` must not change triage behaviour; E1b only reads.
- The 300-line limit: the planned file split above is mandatory, not optional.
- The secret check refusing harmless text: scoped to the one pattern set plus URL credentials, with a clear message so the operator can reword.

## 7. Plan review record
Round 1 (2026-11-21, `opus-plan-reviewer`, read-only, against the real code): 2 blocking (wrong resolver; false claim about the triage writer), 9 should-fix, 4 nits. All applied in this revision. Not verified by the reviewer: that the WebUI client has no reminder code (checked only the server dir), and whether the classifier blocks secret-shaped fixtures.
