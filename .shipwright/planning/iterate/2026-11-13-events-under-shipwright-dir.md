# Iterate: event folders move under `.shipwright/events/`

- **Run ID:** iterate-2026-11-13-events-under-shipwright-dir
- **Intent:** CHANGE (location of an existing artifact; behaviour of the event log is unchanged)
- **Complexity:** large by keyword, force-continued by the operator ("scope exceeded iterate threshold, user chose to continue"): full test suites and the full review cascade are mandatory.

## Request

The per-run event folders of the drops layout sat at the repo root next to config files. They belong under `.shipwright/`
with the other artifacts Shipwright produces. Decided by the operator: layout "variant 1" (bundled folder), and a HARD
ABORT for a project that still has the old root folder (no compatibility reader).

| Before | After |
|---|---|
| `shipwright_events.d/` | `.shipwright/events/drops/` |
| `shipwright_events.archive/` | `.shipwright/events/archive/` |
| `shipwright_events.quarantine/` | `.shipwright/events/quarantine/` |

Out of scope: the root config files (`shipwright_*_config.json` etc.) and the legacy single file `shipwright_events.jsonl`
with its `.lock` (a possible second step). The advisory lock stays at the root, outside the tracked folder.

## Design

- **One definition.** `lib/events_log.py` (`DROPS_DIR`, `ARCHIVE_DIR`, `QUARANTINE_DIR`) is the source; every other module
  that spelled the name now carries the new path (68 files: libs, verifiers, plugin checks, adopt seeder, grade routing,
  classifiers, skills, docs, tests).
- **Hard abort.** `lib/events_sentinel.py`: `old_event_folders` detects an old root folder (a real directory only);
  `require_writable_layout` raises `UnsupportedEventsLayout` and `evidence_refusal` answers `refused_events_folder_moved`,
  both with the exact `git mv` commands. The integrity check flags an add at an old name. No reader reads the old folder.
- **Migration tool.** `tools/migrate_events_folder.py` (`git mv` per file, never overwrites, re-runnable, `--dry-run`).
  The integrity check recognises exactly that move (deleted old file + identical blob added under the matching new folder).
- **Integrity library.** It assumed the folder was the FIRST path segment; the folder is now the first three
  (`.shipwright/events/<kind>`). Without the change `foreign_key` and the other checks passed silently over the new path.
- **gitignore.** `/.shipwright/*` ignores `.shipwright/events` itself. The canonical block (template + this repo) gets
  `!/.shipwright/events/`; the self-heal re-includes the parent chain before the folder lines (git cannot re-include a file
  whose parent directory is excluded).
- **Directory creation.** Writers/fold/adopt create the folder with `parents=True` (`.shipwright/events/` may not exist yet).

## Spec Impact
- **Classification:** none
- **NONE justification:** the event log's behaviour and its requirements are unchanged; only where its folders live moves.
  Pre-build AC record: one `unchanged` item on FR-01.11.AC01 listing the observable files of the diff.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib/events_write.py`, `lib/events_layout.py`, adopt `event_seeder.py`, `tools/fold_events.py` | `lib/events_read.py`, compliance readers, grade, **WebUI `event-log-assemble.ts` / `event-log-files.ts` (other repo)** | JSONL files in `.shipwright/events/{drops,archive,quarantine}/` |
| `shared/templates/shipwright-gitignore.template` | `gitignore_selfheal` / `gitignore_canon` of every managed repo | gitignore rules |

**Cross-repo consumer:** the Shipwright WebUI hardcodes the old folder names in `server/src/core/event-log-assemble.ts`
(`DROPS_DIR`, `ARCHIVE_DIR`) and reads them in `event-log-files.ts`, `mission-context/ref-event-log.ts`. It must move to the new
paths in its own PR (new path first, old path as fallback), or the Command Center stops showing the events of a drops repo. That PR must land BEFORE or together with this merge (resolves the earlier "last step" wording; external plan review, both legs).

## Confidence Calibration
- **Boundaries touched:** event folders (JSONL), gitignore canon, integrity check over git diffs, WebUI reader (other repo).
- **Empirical probes run:** `git check-ignore` on `.shipwright/events/drops/x.jsonl` showed the whitelist gap before the fix
  (ignored by `/.shipwright/*`) and no match after; the foreign-key integrity test failed on the first pass (nested path) and
  passes after the fix; the move tested through a real `git mv` PR branch (accepted) and the three negative shapes (plain
  delete, new file at the old name, move plus edit: all flagged).
- **Test Completeness Ledger:** see F5 record; new tests in `shared/tests/test_events_folder_move.py` (22), the existing
  event suites (shared, integration, plugins) re-run on the new paths.
- **Confidence-pattern check:** the full shared, integration, scripts and every plugin test root ran; composition proven by
  the existing integration suites on the new location (`cross_component` machinery: `events_log`, `churn_merge`,
  `gitattributes_union`).

## Local projects
Checked before touching anything: `leadwright`, `shipwright-webui`, `aiportal` run the legacy single file and have no event
folder (nothing to move). Only this repo is on `drops`; after merge its main checkout moves with `git pull` plus the tool
for untracked leftovers.

## Internal Architecture Review
Fresh-context reviewer (opus), over the architecture brief and this spec only. Verdict: no objection to building bundled layout + hard abort now (cheapest point; hard abort is the safe policy for writers). Findings and what was done:

| Finding | Severity | Disposition |
|---|---|---|
| Fail-open hook callers could swallow the abort | high | Verified: the writer CLI exits 1 with `unsupported_events_layout` and the fix in the message; `finalize_iterate` re-raises it; an iterate that loses its event fails the F11 committed-event check. Added a test through the real `record_event.py` CLI. Hook-side fail-open wrappers are the existing contract of the layout sentinel and stay as is. |
| Readers/grade/fold see a missing folder as "no events" | high | Fixed for the shared reader: an old root folder is reported as an unreadable drop with no key, so every absence gate fails closed and batch readers count it (`events_read`, `events_log.old_root_folders`). Grade falls back to its heuristic grade for a repo without a readable log (its documented path), not to a zero. |
| gitignore whitelist missing silently drops events | high | Canonical block + self-heal fixed (parent chain). A repo that is not healed still fails loudly: `git add` skips the ignored drop, so the F11 committed-event check refuses the run. No extra per-write probe added. |
| WebUI shows empty history until it follows | medium | Accepted; WebUI PR planned as the last step, to read the new path first and then the old one. |
| Old-plugin skew / branches recreating the old folder | medium | Abort message now names an outdated plugin as the likely cause; the migration tool refuses and moves nothing while any file name exists in both places (it reports them), and otherwise moves every file; plugin-cache sync is part of the rollout. |
| Whitelist re-includes quarantine; gitattributes keyed on old names | medium | Checked: all three folders were tracked before (never ignored at the root); `.gitattributes` has no rule for the folders, only for `shipwright_events.jsonl`. Unchanged. |
| Move exception could smuggle a deletion | low | Same filename, matching kind folder and identical blob are required; added negative tests for a cross-kind move and a rename. |
| Permanent code for a one-time move | low | Removal point recorded in the migration doc. |

## Internal Plan Review
Reviewer: opus-plan-reviewer, over this spec and the built diff. Dispositions:

| Finding | Severity | Disposition |
|---|---|---|
| An OLD plugin meets the NEW layout unguarded (the declared layout value is unchanged, so the old sentinel accepts it, finds no folder, and writes a new drop at the old root) | high | Accepted as designed, recorded here: the split is caught loudly and afterwards, not prevented. The new plugin's writer aborts at the next write, readers report the old folder as an unreadable keyless drop (absence gates fail closed), the iterate F11 integrity check flags the add at the old name (no CI workflow runs that check: a direct push to main is not checked), and the migration tool moves the stragglers (it refuses, moving nothing, only while a name exists in both places). Bumping the declared layout value would force every adopter repo to edit its config for a one-person population, against the operator's "hard abort, keep it simple". Rollout order: plugin-cache sync (`update-marketplace.sh`) right after the merge, before sessions work on the moved main. |
| Symlink guards check only the leaf now that the path is nested | medium | Fixed: `events_log.real_event_dir` (no symlink at any level) used by `event_files`, the open-drop counter and `old_root_folders`; grade has its own `real_dir` (routing, authoritative). Tests with a symlinked `.shipwright` and `.shipwright/events`. |
| Self-heal cannot heal a repo that ignores `.shipwright` wholesale and keeps appending dead rules | medium | Fixed: the heal probes the healed rules in a throw-away repo and writes nothing when they cannot take effect; the F11 committed-event check still fails the run loudly. |
| Archive classified as drop under a relative root | low | Fixed (`path.parent == root / ARCHIVE_DIR`), regression test for both root spellings. |
| Integrity message wrong for D/M entries; gitignore re-includes more than the check accepts | low | Message made neutral. The re-include stays at `.shipwright/events/` (it matches the canonical-block shape). |
| In-flight branches/worktrees; OS junk keeps an emptied old folder alive | medium | Migration doc says: merge main, then run the tool. A folder holding only OS junk (`.DS_Store`, `Thumbs.db`, `desktop.ini`) no longer counts as an old event folder. |
| WebUI as the last step leaves the Command Center empty meanwhile; vendored gates may hardcode the names | medium | WebUI change to land first or together, reading the new path and falling back to the old one. Its vendored code was searched: only `server/src/core/event-log-assemble.ts`, `event-log-files.ts`, `mission-context/ref-event-log.ts` and tests name the folders. |
| Name copies in five places; `project_root` markers | low | Guard test added that the copies in the sentinel, the adopt seeder and grade match `events_log`. A repo whose only marker is the old folder is vanishingly unlikely (a drops repo also has a sync config). |
