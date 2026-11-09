# Per-run drop files for shared append records (issue 978) — design v4 (closed end-to-end plan)

Status: DESIGN v6 = v4 body + section 10 amendments (round-5 review and empirical spike). Section 10 overrides on conflict.
Operator requirement: ONE closed plan that works as a whole (end state + migration + rollback), no salami slicing. Details that
are only implementation (exact names, thresholds) are decided inside the individual iterates; everything that decides
WHETHER the whole thing works is decided here.

## 1. Problem (measured)
- Reporter (private repo, squash, linear history, auto-merge): 7 merges / 6 PRs in 2 days. On GitHub's check (no `merge=union`):
  `shipwright_events.jsonl` 7/7, `conventions.md` 6/7, `architecture.md` 1/7, `triage.jsonl` 0/7. Auto-merge then stalls and
  merging `main` in by hand stales head-bound evidence.
- Own repo: 38 % of PRs see a sibling merge while open. `ensure_current` (F11) covers only the time before arming.
- Experiments (`git --attr-source=<empty tree> merge-tree`): same-file appends conflict 100 %; files unique per branch never conflict.
- Stopgaps that change the PR head (rebase bot, re-run ensure_current, merge queue) stale evidence or use the same server check.
  A stopgap question to the reporter is posted on #978 (answer pending); it does not replace the fix.
- Stop-tracking-the-log alternative is rejected (2026-05-29 decision: untracked main-tree events were wiped once; F11 requires the
  event in the committed blob; WebUI rebuilds campaigns from `origin/main`).

## 2. Reviewer findings and how v3 closes them
| Finding (round) | v3 answer |
|---|---|
| Per-event files are finer than needed; 70x slower read; fold/cache/collision machinery (arch v2) | **One file per run** (section 4.1). File count ~ number of runs; run-scoped reads open exactly one file. |
| Removing the lock re-opens the F14 duplicate race (plan v2) | Same-run writers share one file and keep the existing untracked `_FileLock` + in-lock dedup. Different runs never share dedup keys except `grade_snapshot` (accepted). |
| Tracking rule would ignore the folder in consumer repos and destroy drops (plan v2) | **No template change.** The folder line is mirrored only in projects where `git check-ignore shipwright_events.jsonl` is already true (self-heal, conditional). |
| Mixed-version promise unimplementable for installed plugins (plan v2) | Two groups, section 6: post-change plugins fail closed via a layout sentinel; pre-change plugins are bounded by design (they only ever write legacy, which new readers still read) plus an optional CI check. Bound stated honestly. |
| Fold has no actor/cadence outside our repo; two folds collide on one archive (plan v2) | Archive = **one file per fold** (`shipwright_events.archive/<fold-id>.jsonl`), dedup by id on read; fold is idempotent, may run from any iterate, time-based (drops older than 14 d), threshold-triggered warning. |
| Guard misses literal-path classifiers (plan v2: ~10 modules) | Guard is **reference-based**: every occurrence of the literal, `EVENT_FILE` or `resolve_events_path` in non-test code must sit on an allow-list tagged reader / classifier / writer / marker; classifiers must list the drop dir. |
| Prompt guard too narrow (plan v2) | Extended to `plugins/**`, `shared/prompts`, `shared/templates`, `docs/`, agent-docs templates. |
| Bullet drops have no folder, folder reader, WebUI reader (both) | Bullets use the **existing decision-drop store** (new kind), folded by `aggregate_decisions` at release; pending ones are read at context load (row B2, cap 20) and by the WebUI docs reader (section 4.3). |
| Layout flag becomes a permanent second mode (arch v2) | Flag is a **dated transition switch** (section 6); removed in the final step once all in-repo consumers are on the reader. |
| Position-dependent readers / read order (both) | Legacy file keeps FILE order; archive + drops sorted `(ts, id)` and appended after; amendments: last in that order wins. Position readers moved to "latest by ts" helpers first. |
| Event ids 8 hex, "first wins" drops legit events (plan v2) | New ids 16 hex; duplicate id with different content keeps both and flags it; identical content dedups. |
| Rollback only to post-S2 code (plan v2) | Two rollbacks named: emergency fold (to archive, layout flag back to legacy, post-change readers) and full fold into the legacy file (one-time, conflict-accepting, for pre-change readers). Both rehearsed before the flip. |
| Append-only integrity rule lost; back-dated events; path traversal (arch v2) | New CI/F11 check: a PR may only ADD files, or append to the file whose key equals its own run id; delete/modify of any other drop only in a fold commit; keys validated against `[A-Za-z0-9._-]{1,80}`. |
| Main-tree events outside PRs (arch v2) | Written to `shipwright_events.d/_main--<session8>.jsonl`; committed by the existing F7b `chore(events)` seal exactly as today's legacy append. |
| Kill criterion 6 untestable (F0 timing varies 4x) | Replaced by a fixed-repeat microbenchmark of `read_events` and one hook (section 8). |
| Stop-guard claim overstated (plan v2) | Correct: `next_phase_hint` is a hint, not a gate. Real gates: F11 events check, phase-quality, compliance, WebUI campaign state. |

## 3. Scope (decided)
IN: events; `conventions.md` and `architecture.md` bullets. OUT: `triage.jsonl` (0/7), stays `merge=union`. The "one triage item
per branch" acceptance criterion is removed.

## 4. End-state design
### 4.1 Events (v4: file identity decided)
- **Path:** `shipwright_events.d/<key>--<wt8>--<nonce8>.jsonl`.
  `wt8` = first 8 hex of sha256 of the realpath of the writing worktree's git dir (the worktree's OWN identity; never the session
  pointer, never an env var). `key` precedence (v5; one function shared by writers and the replay splitter): (1) an explicit run id from the caller
  (`finalize_iterate`, `record_event --run-id`, `SHIPWRIGHT_RUN_ID`), (2) the per-unit worktree's own identity, (3) `_branch-<slug>`, (4) `_detached-<wt8>`
  when HEAD is detached, `_main` only for main-tree writers. The chosen key is STAMPED into each event (`run` field) so the run-scoped read
  and the splitter never have to guess. Events that gates look up (`work_completed`, gate-checked `phase_*`) never take a `_branch-` key
  (they carry an explicit run id). The run-scoped read is by stamped `run` field across all drop files of the run key, plus the legacy file and
  archive filtered by run/adr id; the `_branch-` mapping is dropped from the definition. `nonce8` is random, fixed at file creation.
  The whole name is validated against `[A-Za-z0-9._-]{1,120}` before it becomes a path.
- **v5 rule, purely local, no refs or fetch: rotate on commit.** A writer appends only to a drop that is NOT in HEAD's tree (untracked
  or newly staged). Every commit closes the file; the next write starts a NEW file with a fresh nonce. This works detached, offline,
  stacked and after a squash merge (where the merge-base never moves past the merged PR), and committed drops are immutable by
  construction. A file is created only on its first complete write, atomically and under the lock (no empty files).
  (Superseded v4 wording "absent from the merge-base tree" was wrong under squash merges and needed a fresh origin ref.) The same run id in two worktrees
  (retry) therefore never shares a name. The existing untracked `_FileLock` + in-lock dedup applies to the branch's own open file,
  so same-run Stop-hook fan-out stays serialized.
- **Integrity rule (CI + F11):** relative to the merge-base a PR may only ADD files under the drops folder (and append to those it
  added itself); any modify or delete of a file that exists at the merge-base fails, except in a fold commit (recognised by: every
  deleted id appears in an added archive file). This also removes fold modify/delete conflicts.
- **Reading (`read_events(root)`):** legacy file in FILE order, then archive files and drops merged and sorted by parsed instant
  then id. Amendments: last in that order wins; amendments carry an explicit target id. The result carries PER-FILE STATUS (ok,
  corrupt, empty, unreadable) so every caller keeps its own policy: gates that look for an event's ABSENCE treat any non-ok file as
  failure, batch readers (compliance, dashboards) skip and report a count, `finalized_run_ids` keeps returning "unknown" on unreadable.
- **Run-scoped read** = all files whose key is the run id, plus the branch-slug files of the run's branch, plus the legacy file and
  archive filtered by run id/adr id. The 20 ms budget is set against THIS definition.
- **Writers:** `record_event` and every duplicate `EVENT_FILE` user (six constants plus `verifiers/common.read_events_jsonl`) go
  through one writer module. New event ids are 16 hex; identical id + identical content dedups, identical id + different content
  keeps both and flags it.
- **Lock (v5):** taken per (worktree git dir, key) in an untracked location OUTSIDE the tracked folder, BEFORE choosing or creating the
  file; dedup runs over the run-scoped set (resumed runs included). The write path (12 writers) is part of the microbenchmark.
- **Corrupt or empty drop that reached main (v5):** absence gates fail on non-ok files only within the RUN-SCOPED set. The integrity rule has a
  legal `quarantine` exception: move the raw bytes to `shipwright_events.quarantine/` in one commit, recognised by matching content hashes.
- **Committed-ness (v5):** F6 stages only drops whose KEY is its own run id or branch slug AND that are untracked or added-in-branch (never
  by `wt8`: the shared campaign worktree has one `wt8` for orchestrator and all sub-iterates). Bullet file names carry the run key too.
  With rotate-on-commit no dirty tracked drop can exist across a branch hop. (Decision-drop lesson: not a folder-level add.) F11 `_event_committed_in_head` decides tracked-ness via `check-ignore` on the
  folder and lists the run's files in the HEAD tree; an unstaged drop FAILS the check (never `None`/pass). F7b
  (`commit_event_followup`) is generalized to seal untracked `_main--*` files (porcelain status, folder-scoped add and commit), because
  today's `git diff --quiet` and hard-coded path would never commit them.
### 4.2 Fold (release housekeeping, not a daily actor)
Idempotent tool: moves drops whose events are older than 14 days (by event `ts`, not mtime) and whose PR is merged into
`shipwright_events.archive/<fold-id>.jsonl`, deleting them in the same commit. Two concurrent folds produce two archive files (dedup
by id on read) and delete/delete on the same drops (clean). Because PRs never modify a file that exists on main (4.1), a fold cannot
create a modify/delete conflict. Warning, not block, above the measured threshold.
### 4.3 Bullets (v4: hidden from old consumers, own fold and gates)
- Stored as `.md` files in `.shipwright/agent_docs/decision-drops/bullets/<target>--<wt8>--<nonce8>.md` (subfolder AND non-`.json`
  suffix): the non-recursive `*.json` globs of `aggregate_decisions._snapshot_drops`, `architecture_doc.scan_drops` and the WebUI
  decision-drops reader cannot see them, so old consumers never turn bullets into ADRs. Same one-branch/one-file/ADD-only rules as 4.1.
- Fold: only at release (one actor, via `aggregate_decisions`), into the curated sections of `conventions.md`/`architecture.md`;
  a separate `fold_bullets` tool can also run as its own small PR. Order with the ADR fold is fixed (bullets first, so the
  architecture fallback bullet is not duplicated). Context load shows the 20 newest pending bullets plus a line "N more pending", and a
  warning above 40. `agent_doc_budget`, `agent_doc_shape`, `architecture_doc`, `check_architecture_documented` and the WebUI docs
  reader read folded + pending. The mtime-based `check_conventions_reviewed` warning is adapted.
### 4.4 Readers and classifiers
All ~23 Python readers, the five duplicate path constants, the compliance twin and the WebUI readers (incl. the `git show
origin/main:` reader, which switches to `ls-tree` + `cat-file --batch`) use `read_events`. Literal-path classifiers get the
drop dirs added: `change_type_paths`, `review_diff_threshold`, `section_file_list`, `churn_merge`, `project_root`, `gitignore_selfheal`,
`gitattributes_union`, `worktree_isolation`, security `pr_review_*`, adopt `validate_adoption`. Agent prompts: `F6.md` stages only this
worktree's own files (`wt8` token, see 4.1); F5b/F11/SKILL.md and the 27 prompt/doc files updated.

## 5. Why this works as a whole (the argument, then the proof obligations)
Conflict-freedom comes from construction (unique file per run). Visibility comes from one reader. Safety during migration comes from
ordering (readers everywhere before any writer switches), from keeping the legacy file readable forever, and from two named
rollbacks that are rehearsed. Anything that cannot be proven here is turned into a gate in section 8 that blocks the flip.

## 6. Migration order and the flip
1. WebUI reader (own repo, merged AND released; minimum WebUI version recorded) + Python `read_events` + position-reader fixes + replay tests. Writers unchanged.
2. Migrate all readers/classifiers/prompts; reference-based guards live; layout sentinel in plugins (supported-layouts constant); release-evidence
   producers (compliance, changelog evidence) check the sentinel and REFUSE to run on a repo with drops they do not understand.
3. Bullet drops (writers + readers + WebUI + fold + gates). Bullets are invisible to old consumers by construction (4.3), so they need no flag.
4. Emergency fold and full fold tools; integration test; rehearsals on a copy of our real repo history and on a fixture.
5. **Flip, dogfood first:** this repo sets `events_layout: drops` in `shipwright_sync_config.json`, runs two weeks; the reporter pilots next with the
   consumer CI check ON by default (it fails PRs that append to the legacy file once the flag is on).
6. Stop branching on the flag (drops become the only layout for new repos). **The `events_layout` key is NEVER removed from existing repos**: a
   plugin from steps 2-5 reads "absent = legacy" and would otherwise silently write legacy again. `init`/`adopt` WRITE `events_layout` explicitly and "absent = legacy"
   stays forever; "a drops folder exists" is only a refuse-to-write guard. The consumer CI check judges the flag at the PR's MERGE-BASE (not
   head), so PRs in flight at the flip are not failed; tracked-ness is probed with a representative FILE path (`shipwright_events.d/x.jsonl`),
   and the self-heal adds a re-include when the legacy file is tracked but `*.jsonl` is ignored. Step 6 is gated on the sentinel being in every supported plugin line AND the
   minimum WebUI version, not on the calendar. If the planned date passes without the gate, nothing breaks: readers keep working, a loud
   warning plus a tracked issue appears.
Mixed versions: (a) plugins from step 2 on read drops and refuse to write or produce evidence for a layout they do not support (fail closed,
"update the plugin"); (b) older plugins keep writing the legacy file, which every reader still reads, and cannot see bullets (4.3); the only
unmitigated case is an old READER on a repo that already has drops. Its damage is bounded: gates see a run as missing, derived renders miss
runs and self-heal on the next new-plugin iterate; release evidence is covered by (a) when produced by a post-change plugin. It exists only
between the flip and the last teammate updating, so the flip is a team-announced event.

## 7. Cost to keep and what it forecloses
Keep: one reader contract in Python and TypeScript, guards with allow-lists, fold housekeeping, two layouts until step 6.
Forecloses: reading the log as one plain file via `git show`/grep/jq by outside tools; any meaning in file order beyond the legacy file.

## 8. Kill criteria and proof obligations (blocking the flip)
1. Replay: the new reader on the UNSPLIT legacy file is the baseline; the same log split by a splitter that follows the 4.1 key rule must
   render byte-identically in every renderer (compliance change history, RTM, throughput report, session handoff, build dashboard, grade
   counters, campaign status in Python AND the WebUI node script, `finalized_run_ids`, `latest_event_dt`).
2. Reference-based guards green (readers, classifiers, prompts across plugins/, shared/prompts, shared/templates, docs/) with no unclassified occurrence.
3. Integration test (bare origin + clone + worktrees, real `record_event`, `merge-tree` without union): all pairs clean; squash sequence; OLD-writer
   branch appending to legacy; fold racing an open PR; campaign wave (N worktrees sharing one session id, hooks writing); retried unit with the same
   run id; TWO run ids in ONE shared worktree with leftover drops and post-F6 writes before a hop (F6 stages only its own key's added files);
   continue-after-squash-merge and stacked-base branches; mid-run flip (CI judged at merge-base); corrupt drop on main repaired by quarantine; F6 forgets to stage -> F11 FAILS; F7b seals a new
   `_main--` file; mid-run flip and mid-run rollback; both rollbacks; old-plugin `aggregate_decisions` and old WebUI against bullet drops;
   `events_layout` absent after step 6; mixed-version fail-closed incl. release-evidence refusal; fault injection (corrupt, empty, duplicate id, future ts).
4. Concurrency: 12 parallel Stop-hook writers per run -> no duplicate `phase_completed`; `work_completed` idempotent across a resumed run's files.
5. Microbenchmark, fixed repeats, run on Windows locally AND the Linux CI runner: run-scoped read <= 20 ms; whole-log read <= 0.3 s at 300 files;
   `_main--` files are bounded by the fold.
6. Integrity check blocks modify/delete of any file existing at the merge-base, a path-traversal key, and a forged-run-id append.
7. Bullets: two branches adding bullets are clean under `merge-tree`; an old-plugin changelog run leaves bullets untouched; budget/shape checks identical
   on pending vs folded render; ADR-vs-bullet fold order covered; cap overflow warns.
8. Gates that look for an event's absence fail on any non-ok file status (never pass silently).
Any red item blocks the next step; before step 5 the whole thing can be abandoned at zero cost to consumers, because writers are untouched.

## 9. Open decisions (recommendations)
Archive per fold (recommended, done). Flip dogfood-first (recommended, done). Pilot repo for the reporter after our two weeks.


## 10. v6 amendments (override anything above that conflicts) — round-5 review + empirical spike

### 10.1 Spike result (throwaway prototype, never merged; real record_event, real ensure_current, bare origin, 3 worktrees)
- Legacy baseline reproduces #978: `merge-tree` without union CONFLICTS on all 3 pairs; `ensure_current` is ok (local union).
- Drops layout: `merge-tree` without union is CLEAN on all 3 pairs (the core claim holds). After 2 squash merges, a real `ensure_current`
  on the third branch integrates and the branch sees all three runs' drops, AFTER fixing two product spots the spike hit by running it:
  (1) `change_type_paths` rejected `work_completed` ("change_type does not cover shipwright_events.d/...") — the classifier must list the folder;
  (2) `resolve_churn_conflicts._reconcile_events` reported "work_completed absent - the merge dropped it" (events_invalid, exit 4) on every
  behind-main refresh — it validates the legacy file only. Both were predicted by reviewers; now observed.
- Also observed: the `.lock` file lands INSIDE the drops folder (the lock must live outside, untracked).
- F11 `_event_committed_in_head` on a correctly committed drop returns False (it looks only at the legacy file): F11 would FAIL every
  correctly finalized run until migrated.
- Existing-test inventory: 3075 event-related shared tests pass on legacy; with the drops layout 53 fail, in 18 files (finalize_iterate,
  grade_snapshot_dedup, attach_commit_to_event, record_event, finalize_bundle, iterate_tests_block, finalize_event_self_id,
  events_newline_integrity, compliance_refresh_real_producer, iterate_ledger_anchor (event_at anchor), finalize_campaign_status (campaign
  status stays `pending`), compliance_input_state, ...). Most assert on the legacy file path directly (test side); the product-side hits are
  campaign-status regeneration, the ledger event anchor, compliance input state, attach_commit, finalize_iterate. This list is a LOWER bound
  and becomes the S2/S3 work list; running the same test selection under `SHIPWRIGHT_EVENTS_LAYOUT=drops` is a standing gate.

### 10.2 Decisions closing the round-5 blockers
- **N1 guard:** the reference-based guard tracks the literal AND every module-level alias bound to it (`EVENT_FILE`, `EVENTS_LOG`,
  `EVENT_LOG_NAME`, `resolve_events_path`) with all imports and uses. Named migration lines: `_reconcile_events` (validate legacy deduped +
  drops, run-scoped lookup of the run's `work_completed`), `regenerate_campaign_statuses`, `compliance_input_state`, the
  `event_context_index` fingerprint, `gitattributes_union`, plan/design phase gates (`PLAN_ALLOWED_PREFIXES`, `DESIGN_ALLOWED_PREFIXES`).
  The integration test gets a real `ensure_current.py` case on a behind-main branch carrying its own drop, plus campaign-status regeneration.
- **Events after F6:** writers append only to UNTRACKED files whose name carries their own key AND their own `wt8` (drop "newly staged").
  `ensure_current` gets an ABSORB step for drops, mirroring `_absorb_dirty_triage_log`: before the merge it commits all untracked drops
  of this worktree's `wt8`, after validation, folder-scoped. F11 runs ensure_current before the committed-check, so absorbed files count.
  F11's "unstaged drop fails" applies after the absorb and only to the run's gate events. Events after push or arming are best-effort.
  `attach_commit_to_event` becomes an `event_amended {commit}` written to a new drop (a closed file is never edited).
- **Corrupt files:** every file is read record by record with today's `split_records` recovery; status means "remainder present", not
  "file unusable". Only a non-ok DROP file whose key is the run's key blocks an absence gate; the legacy file and the archive keep today's
  tolerant behaviour (count reported, never block). Quarantine only for files with zero recoverable records, and only for files non-ok at the
  merge-base (re-checked by the CI checker). A fold requires every deleted event to appear byte-identical (or with an equal per-event hash)
  in an added archive file.
- **Keys:** an explicit run id (including `--adr-id` on `work_completed`) always wins, also in the main tree; F7b seals every untracked
  drop whose `wt8` is the main git dir's. The replay splitter assigns keys from content only (adr_id, else session, else `_legacy`) and
  stamps `run` the same way; replay proves equal renders, not fidelity to the live key rule. Stale sentences (wt8 staging in 4.4, branch-slug
  files in the run-scoped read, `_main--<session8>` in section 2) are void: 4.1 and this section rule.
- **Dedup scope:** `phase_completed` and by-commit dedup read the whole log (read-only) while holding the own-key lock; the remaining race
  between different keys is accepted. Added kill case: a re-run of `plan` with a fresh `SHIPWRIGHT_RUN_ID` must not duplicate `phase_completed`.
- **Follow-ups for the iterates:** line-hash consumers (`event_context_index`, `dedup_event_lines`) exclude the stamped `run` field in
  the byte-identity comparison; the rotation probe uses `ls-tree`/`cat-file` or a HEAD-sha marker, never `git status`; `validate_event_log`
  and `commit_event_followup` hard-coded paths; Windows path length (key cap 80); `integrate_merge` validates drops brought in by a merge;
  prompt_injection_scan on bullet `.md`; a plugin from before this campaign on a drops repo does NOT fail: it writes silently to the legacy `shipwright_events.jsonl` (tested with v0.34.0, 2026-11-07), so the flip announcement must say: update every machine BEFORE switching.

### 10.3 Campaign shape (every iterate carries its own control: kill criteria, guards, full review cascade)
- **S0** harness: the spike's bare-origin integration harness promoted to a test (legacy baseline vs drops, real `ensure_current`/`record_event`)
  plus the standing replay gate (event-related shared tests under `SHIPWRIGHT_EVENTS_LAYOUT=drops`).
- **S1** WebUI reader (own repo). **S2** `read_events` contract, per-file status, position-reader fixes. **S3** migrate all Python
  readers, aliases and classifiers, plus the guards. **S4** prompts/docs/F6/F5b/F11/F7b, `ensure_current` absorb, attach_commit as amendment.
- **S5** bullets in `decision-drops/bullets/` with fold and gates. **S6** fold, quarantine, emergency fold, full fold, integrity check.
- **S7** mixed-version sentinel, release-evidence refusal, consumer CI check. **S8** full integration, microbenchmark, rehearsals on a copy
  of real history. **S9** flip (dogfood two weeks), then reporter pilot, then stop branching on the flag (the key is never removed).
- Readers strictly before writers; the writer flip is the only step with consumer impact and is gated on S8 green.
