# One assembling event reader with per-file status

Run: `iterate-2026-11-06-events-drop-files-s2-read-events` (campaign `events-drop-files`, unit S2; issue 978).
Binding sources: `.shipwright/planning/campaigns/2026-11-04-events-drop-files-BRIEF.md` and `-DESIGN.md` (section 10 overrides).

## What was decided
- New `lib/events_read.py` is the ONE assembling reader: legacy file in FILE order, then archive and drop files merged by (parsed instant, id). Layout independent (the folders are read whenever they exist); a tree without them reads byte-for-byte as before. `config.read_events_result` returns an `AssembledRead`; the S0 reader in `events_layout.py` is gone (names re-exported).
- Per-file status `ok / corrupt / empty / unreadable` (recovery stays the shared `split_records` path; status means "something is wrong", the records around the damage are still returned). An unreadable LEGACY file keeps raising (never reads as "no events"); a zero-record legacy file is ok, an empty archive/drop is not.
- Duplicates: archive/drop records with the same id and same content (the stamped `run` field is not content) collapse; same id with different content keeps both and lists the id in `duplicate_ids`. Legacy is never deduplicated.
- Absence-gate primitive (KC8): `AssembledRead.absence_blockers(run_key)` / `require_readable_for_absence`. Only a non-ok DROP file named for the run key (normalised with the writer `sanitize_key`, now in `events_read`) or a non-ok drop with an unattributable name blocks; legacy, archive and other runs drops are counted, never block.
- `events_log` gains `event_files()`; `latest_event_dt` / `finalized_run_ids` read archive and drops (unreadable still means "unknown"). Position readers mean "newest by ts, ties the later position": `last_grade_snapshot`, handoff Last Events / Last iterate, dashboard iterate / test-run / build lists (`sorted_by_ts`, `latest_by_ts`). The grade-snapshot dedup in `record_event` treats `skipped_files` like corruption.
- Replay-gate known set tightened 101 -> 85: all 8 S2 entries plus 8 S3/S4 entries that now pass (3 in `test_grade_snapshot_regen` through a layout-agnostic test helper, 5 `test_completion_writers*` through the drop-aware `latest_event_dt`).

## Boundaries (declared, owned by later units)
Renderers on their own read paths (compliance twin / change history / RTM, campaign status, F11 verifiers `read_events_jsonl`, `_reconcile_events`, the `finalize_iterate` prior lookup) are S3/S4 migrations, so KC1 here covers the renderers on the shared contract (session handoff, build dashboard, throughput report, `read_events`, `latest_event_dt`, `finalized_run_ids`). Wiring `require_readable_for_absence` into the real absence gates is S3/S4. S4 must also make drop creation atomic (an empty drop left by a crash would block the gates of its run).

## Architecture Review
Both external reviewers approved over the brief (options A reader module, B sort everything, C each reader opens the folders, D defer); the internal `architecture-internal-reviewer` approved with medium gaps, closed in the code: duplicate rule written down, tie and invalid-ts ordering fixed and tested, a tree without folders reads as before (tested).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| openai high: name the absence-gate callers, KC8 must reach gates | rejected-with-reason: BRIEF S3 (`_reconcile_events`) and S4 (F11 committed check, dedup) own the gates; S2 delivers the contract plus tests |
| openai medium: KC1 covers three renderers, others deferred | accepted: scope stated in this ADR; out-of-order legacy KC1 fixture added |
| both: malformed ts and ties undefined | accepted-and-fixed: unparseable sorts first, ties keep position; `test_ordering_is_deterministic_for_offsets_ties_and_bad_timestamps` |
| openai: recovery must not upgrade a damaged file to ok, key independent of parsing | accepted-and-fixed: key from the file name; tests for unreadable and partial |
| glm: legacy vs archive ordering asymmetry | rejected-with-reason: DESIGN 4.1 fixes legacy file order |
| glm: id collision across sources | accepted-and-fixed: legacy exempt from the duplicate rule, tested |

## Internal review notes
- plan reviewer (opus): key normalisation fails open (fixed with `sanitize_key`), `run` stamp in the duplicate comparison (fixed), empty legacy ok (fixed), symlinked folder (fixed), vanished file race (fixed), KC8 wiring and compliance renderers (declared S3/S4), latency of repeated full reads inside the append lock (deferred to the S8 benchmark), per-file OSError skip in `latest_event_dt` (declined: keeps the documented unreadable-means-unknown behaviour).
- spec-reviewer: round 1 REJECT (ratchet not tightened, position readers partial) fixed; rounds 2 and 3 PASS (the runner guard allows three spawns; the last tiny fail-closed delta is covered by the orchestrator 3f-bis).
- code-reviewer: round 1 bloat (test file 400 lines, split), legacy unreadable behaviour change (restored), dead re-export, docs; round 2 recorded in reviews.json.
- doubt-reviewer: legacy unreadable (fixed), KC8 wiring (rebutted: S3/S4), Build History position reader (fixed), open-time delete race (fixed), grade dedup repo-wide strictness (accepted, fail-safe, dormant), empty-drop atomicity (handed to S4).

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| openai/glm high: KC8 not wired into a production gate | rejected-with-reason: S3/S4 scope (BRIEF), primitive and contract tested |
| glm medium: `events_layout` loses load-context independence | rejected-with-reason: `events_layout` imported `.events_log` relatively before this change; it was package-only already |
| glm low: non-writer-shaped drop names fail open | accepted-and-fixed: such a non-ok drop blocks every run |
| glm low: layout test partly vacuous | accepted: kept as a guard that the layout setting is ignored |

## Confidence Calibration
Boundaries: (1) drop file to reader to renderers: unsplit/split fixture pair, a shuffled legacy variant and a mixed-layout case (legacy newer than a drop), byte-identical renders; (2) damaged files: corrupt, empty, unreadable, vanished, symlinked, hand-named, long and odd run ids. Two consecutive no-finding probes after the last fixes (mixed layout build and iterate tables). Not probed: Linux CI timing of the replay gate with the smaller set; real `ensure_current` on drops (S3).

## Consequences
Nothing changes for consumers (default legacy). Readers now see archive and drop files; the known set shrinks to 85 and the remaining entries belong to S3/S4.
