# Mini-plan: R1c-3 — sets, pathspecs and messages recognise a moving file in either place

Run: `iterate-2026-11-28-r1c3-name-sets`. Campaign BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, item 12.12 (a).

## Goal
After R1c-2 every reader and writer finds a moving file through `path()`. What still RECOGNISES a moving
file by its root name are path sets, allowlists, regexes, git pathspecs and messages. After R3 a file at
`.shipwright/config/<name>` would be missed by them (e.g. a `test_results` copy not seen as a derived
snapshot, a `security_config` copy outside the sensitive-path regex). R1c-3 makes each recognise both places
and ends the safety window of 12.12 (b).

## Inventory (fixture `shared/tests/fixtures/shipwright_paths_rel_constants.json`, 73 entries)
Use sites: scratchpad `r1c3_uses.txt` (regenerate with `r1c3_uses.py`).

1. **Recognisers -> both places** (`_sp.known_rels(key)` / `_sp.all_known_rels(...)`):
   - resolver: `snapshot_paths()` and `run_written_paths()` emit new AND legacy (docstring already promises
     it) -> `DERIVED_SNAPSHOTS`, `RESTORABLE_SNAPSHOTS` follow.
   - `change_type_paths` `_BOOKKEEPING/_COMPLIANCE/_INFRA/_TOOLING`; `review_diff_threshold.UNCOUNTED_FILES`;
     `section_file_list.FRAMEWORK_BOOKKEEPING`; `compliance_input_state.PRODUCER_STATE`;
     `get_phase_context.PHASE_OWN/PREREQ_ARTIFACTS`; `artifact_migrations.ALLOWLIST`;
     `gitignore_selfheal.MANAGED_MARKER_PATHS` (check what it lists); design/plan `*_ALLOWED_PREFIXES`;
     `pr_review_skip_safety._SKIP_REVIEW_CANONICAL_BASENAME_PATHS`; `review_record_tier.SENSITIVE_PATH_RE`;
     `setup_adopt._EXISTING_ARTIFACT_CANDIDATES`; `project_root.CONFIG_MARKERS`;
     `churn_merge.TEST_RESULTS` membership in `resolve_churn_conflicts` / `compliance_refresh` keys.
   - `lib.config.CONFIG_FILES` and `collectors._common.CONFIG_FILES`: derive the names from `CONFIG_KEYS`
     (one source), shown repo-relative via the resolved path.
2. **Labels / messages -> `_sp.name(key)`** (a file name, never joined): `CONFIG_NAME` (run, build,
   changelog, test, iterate...), `RESULTS_NAME/FILENAME/REL`, `BASELINE_NAME`, `REGISTER_NAME`,
   `KNOWN_FAILURES_NAME`, `SYNC_CONFIG`, `_CONFIG_FILENAME`, `profile_consumer.RUN_CONFIG` (origin label),
   `ac_mode.CONFIG_FILE` (source label), argparse help texts. Message sites that print a location report the
   resolved path (`record_inherited_baseline` `written:`).
3. **Dead constants -> delete** (only `__all__`/definition): verify test imports first.
4. **Stays**: the event log (`EVENT_FILE`, `EVENTS_LOG`, `EVENT_LOG_NAME`, `UNION_PATHS`) — `events` does not move.

## Tests
- `rel()`-moved test (12.2 / item 10 (d)): patch the resolver so every moving key's `rel()`/`name()` differs
  and assert no recogniser set still holds only the legacy name; a direct test per recogniser that a path
  under `.shipwright/config/` (or `.shipwright/runtime/`) is recognised.
- Inventory fixture shrinks to the event-log entries; cap lowered.

## Out of scope
R1d (per-commit `rel_at`), R1e (LayoutError per module), R3 (the move).

## Revisions after review (2026-11-28)
- **Skip-safety stays at the root** (internal architecture review). It loosens the required review gate, so it
  follows the file and is not widened before R3. Item 1's `pr_review_skip_safety` entry is withdrawn. R3 switches it.
- **change_type_paths: `_AS_ROOT`** (internal plan review). The blanket `.shipwright/**` bookkeeping would cover a
  moved baseline or risk register for every no-FR label. A moving root file in either place is now judged as the
  root file it is.
- **Design and plan boundary prefixes**: recorded as an R3 obligation. The `.shipwright/` prefix already allows the
  new place, and both gate files sit at the 300-line cap.
- **Tests**: the "rel()-moved" patch test became an AST net over production code, with a positive control, plus a
  direct behaviour test per recogniser. The behaviour tests fail on the old tree (9 of 10 at the time of the
  negative control). Patching `rel()` at import time would have to reload about 20 modules across plugin roots that
  cannot share one pytest process (ADR-044).
- **Dead constants** (item 3): not deleted. The two left (`RUN_CONFIG_REL_PATH`, `ADVISORY_CONFIG_FILE`) are
  `name()` labels now and cannot name a place. `churn_merge.TEST_RESULTS` is used by many tests.
