# Iterate Spec: events-context-backfill-keys

- **Run ID:** iterate-2026-08-07-events-context-backfill-keys
- **Type:** change
- **Complexity:** medium
- **Status:** implemented

## Goal

`.shipwright/runtime/events-context-index.json` (815 entries) is the disposable
index `event_context_query.py` scores to build "relevance-bounded event
context" for Repo Scout. Its selection keys are mostly empty
(`area_ids` 23%, `changed_files` 23%, `affected_frs` 13%, `commit` 9%,
`supersedes_event_id` 4%), so nothing can be ranked by relevance today. Make
`commit`, `changed_files`, and `area_ids` deterministically recoverable from
git plus the area catalogue wherever the underlying data still exists, and
record — per entry AND in an envelope summary — which keys are `derived`
(computed), `declared` (present on the event itself, incl. the legal
no-FR `change_type` branch), or `unavailable` (no recoverable source).

**Correction to the originating brief, made during Repo Scout** (read
`shared/scripts/lib/event_context_index.py` in full before writing this
spec — see review discipline): two of the brief's stated mechanisms do not
match the code, and this spec follows the code, not the brief:

1. **There is no separate "LLM extraction" path.** `extraction.confidence`
   (`event_context_index.py:133-137`) is one deterministic ternary —
   `"high" if paths else "low"` — not an LLM output. There is nothing to
   "drop... beside the deterministic one" because there was never a second
   path. The corrected scope: retire the crude `extraction` block in favor
   of the richer per-field `provenance` block this spec adds, so there is
   exactly one signal instead of two that could quietly disagree.
2. **There is no ADR obsoletes/obsoleted-by graph** ("RFC-index pattern").
   Grepped the whole repo — zero hits. The real convention is `Status:` /
   `Supersedes:` bullets in `.shipwright/agent_docs/decision_log.md`
   (confirmed: 328 `### ADR-NNN:` headers, 16 `Status:` lines — the brief's
   "328 ADRs, 16 Status fields" number is correct, it's the mechanism that
   was wrong), parsed by `shared/scripts/lib/adr_headers.py`. There is no
   function that projects "the current live ADR" from a supersession chain,
   and ADRs supersede ADRs, not individual events — mapping one onto the
   other is a real design problem, not a lookup. `supersedes_event_id`
   stays `declared`-or-`unavailable` in this change; deriving it from ADR
   `Supersedes:` chains is left for a follow-up once `ADR:` commit trailers
   (this spec, item below) give it real data to derive from.

Everything else in the originating brief matches the code and is in scope
unchanged: `commit`/`changed_files` are read verbatim off the event JSON
(`event.get("commit") or event.get("commit_sha")`,
`event.get("changed_files")`) rather than reconstructed, `area_ids` is
already a pure function of `changed_files` via the existing
`area_catalog.match_area` (nothing to change there once `changed_files` is
backfilled), and `affected_frs` already reads correctly from the event log
with `change_type` as the legal declared-absence branch.

## Acceptance Criteria

- [x] `build_index()` backfills `commit` and `changed_files` for any event
      whose JSON record has them empty but whose entry-level `run_id` (the
      existing `event.get("run_id") or event.get("adr_id")` fallback,
      unchanged) matches a `Run-ID:` trailer on a commit reachable from a
      resolved base ref — resolved via TWO `git log` walks total (not one
      subprocess call per event): one for sha→body (trailer extraction),
      one for sha→changed-files (`--name-only`, no body ambiguity). Base ref
      resolution: `origin/HEAD` → `origin/main` → `origin/master` → local
      `HEAD`, first that resolves; record which one won in `coverage`.
      Legacy events whose `run_id` is actually an `ADR-NNN`-shaped `adr_id`
      (pre-2026-05-16, per `fr_change_history.py`'s documented history) will
      not match a `Run-ID:` trailer and correctly resolve `unavailable` —
      no separate `adr_id`-keyed lookup is built; there is exactly one join
      key (`entry.run_id` ↔ `Run-ID:` trailer), not two.
- [x] `area_ids` is recomputed from the (possibly backfilled) `changed_files`
      via the existing `match_area` — no new area-matching logic.
- [x] Every entry carries a `provenance` object with one of
      `derived` / `declared` / `unavailable` for each of `commit`,
      `changed_files`, `area_ids`, `affected_frs`, `supersedes_event_id`.
      The old `extraction` block is removed (superseded by `provenance`).
- [x] `build_index()`'s payload carries a `coverage` envelope: per-key
      `{derived, declared, unavailable}` counts across all entries.
- [x] Running `build_index()` twice against the same event log + git state
      produces byte-identical output **when the git commit-map scan
      completes without timeout** (existing determinism contract in
      `test_rebuild_is_byte_deterministic_and_cache_is_disposable`,
      extended to cover the new fields) — the fixture-repo test scope is
      always well within the timeout, so this is the tested path; a
      real-world timeout is a recorded, visible degradation
      (`coverage.commit_map.status`), not silently-nondeterministic output,
      per external review finding (openai #2).
- [x] `INDEX_SCHEMA_VERSION` bumped 1→2; `load_or_rebuild_index`'s
      `required` key-set includes `provenance` so a stale cached index is
      rejected and rebuilt rather than silently read as complete.
- [x] A new shared, Run-ID-scoped module (`shared/scripts/lib/commit_trailers.py`,
      public surface `resolve_base_ref()` + `build_run_id_commit_map()`)
      resolves the join used above, mirroring the existing loose-match
      convention (`plugins/shipwright-compliance/scripts/audit/git_log_scan.py`'s
      `commit_run_id`, NOT imported across the plugin boundary — this
      module is shared/lib-owned since `event_context_index.py` is a
      shared producer). **No `ADR:`/`Area:`/`FR:` trailer reading, no
      `area_catalog.py match` subcommand, no `F6.md` change** — cut after
      the architecture review (see `## Architecture Review` below): none of
      the three would be consumed by anything this change builds, `Area:`
      would only duplicate what `match_area` already derives from
      `changed_files`, and `FR:` would duplicate `affected_frs`/`change_type`,
      which the F5b FR-gate already enforces from a single source of truth.
- [x] `integration-tests/test_event_context_workflow.py`'s six-surface
      invocation-text assertion still passes unmodified (no producer
      contract text changes needed — same CLI entry points).
- [x] Field-level provenance rule (external review openai #4, pinned by
      tests): `commit` is `derived` on any valid sha match (merge-only
      matches excluded per above); `changed_files` is `derived` whenever a
      matching commit was found — including the rare true-empty-diff case,
      which is a genuine computed fact, not "unavailable"; `area_ids` is
      `derived` whenever `changed_files` is non-empty, even when zero areas
      match (a computed empty result), and `unavailable` only when
      `changed_files` itself is empty/unavailable.

## Spec Impact

- **Classification:** none
- **NONE justification:** internal framework/infra change to the iterate
  skill's own event-context tooling; no entry in `shipwright_sync_config.json`
  maps `shared/scripts/lib/event_context_index.py` or its siblings to a
  project FR. `change_type: internal-tooling` branch applies at F5b/F11
  (ADR-059 no-FR branch).

## Out of Scope

- **`ADR:`/`Area:`/`FR:` commit trailers — cut after architecture review**
  (see `## Architecture Review`). The originating brief asked for these;
  both external architecture reviewers, and the internal Opus arbitration
  that resolved their split verdict, found none of the three would be
  consumed by anything this change builds — `Area:` would only duplicate
  `match_area`'s existing derivation from `changed_files`, `FR:` would
  duplicate `affected_frs`/`change_type` which the F5b FR-gate already
  enforces from one source of truth, and `ADR:` names a use
  (`supersedes_event_id` graph derivation) this spec already put out of
  scope for lack of a reliable event↔ADR mapping. A standing authoring
  convention with no reader is exactly the kind of scope this project's own
  YAGNI rule exists to catch; add it in a later change if and when
  something is built that actually reads it back.
- Deriving `supersedes_event_id` from the ADR `Supersedes:` graph (no
  reliable event↔ADR mapping exists yet, and the `ADR:` trailer that would
  have seeded it is cut — see above).
- A one-off migration script. `build_index()` already rebuilds the full
  index from `shipwright_events.jsonl` on every cache-invalidating change
  (disposable-by-design); the backfill logic lives in the ongoing producer,
  not a separate pass.
- Any change to `event_context_query.py`'s scoring/selection algorithm —
  this run only makes the keys it reads non-empty; ranking quality is a
  separate, later change once the keys exist (this is explicitly the
  precondition work, per the brief's own framing).
- Rewriting `plugins/shipwright-compliance/scripts/audit/git_log_scan.py`'s
  existing `commit_run_id` — left as-is; the new shared trailer reader is a
  separate module to avoid a cross-plugin import into `shared/scripts/lib/`.

## Design Notes

n/a — no UI surface (Python library + CLI + one skill-reference doc change).

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `event_context_index.build_index()` | `event_context_query.query_events()` | JSON (`events-context-index.json`) |
| `git log` (commit bodies, `Run-ID:` line) | `commit_trailers.py` reader | text (loose trailer-line match) |

`touches_io_boundary`-equivalent risk applies (JSON producer/consumer pair
above) even though the literal file-path pattern (`*_config.json`/
`*_state.json`) doesn't match `events-context-index.json` — treating this as
if the flag fired: Boundary Probe sub-step required in Build.

## Confidence Calibration

- **Boundaries touched:** `event_context_index.build_index()` (JSON
  producer) ↔ `event_context_query.query_events()` (consumer);
  `git log` commit bodies ↔ `commit_trailers.py` (reader).
- **Empirical probes run:**
  - Real fixture git repos (`git init` + real commits, not mocked
    subprocess output) for every backfill scenario — merge-commit
    exclusion, duplicate-Run-ID union, the 50-file cap, no-match,
    no-repo/no-base-ref. A mocked `git log` return value would not have
    caught the `%x00` token-alignment bug class the two-call split was
    designed to avoid.
  - Boundary Probe: `build_index()` → JSON write → `load_or_rebuild_index()`
    → read via the CACHE path (not a rebuild) → `provenance`/`coverage`
    compared dict-identical to what was written
    (`test_boundary_probe_provenance_and_coverage_survive_the_json_round_trip`).
  - Verified `area_ids` against the REAL `match_area` output for a real
    seeded catalog (`["src"]`), not just checked that a provenance label was
    one of two acceptable values — the first draft of that test only
    asserted `in ("derived", "unavailable")`, which would have passed even
    if area matching silently broke; tightened after noticing this while
    writing this section.
  - Ran the full `shared/scripts/tests` root (406 passed, no regressions),
    `integration-tests/test_event_context_workflow.py` (2 passed, six-surface
    invocation-text contract intact), `uvx ruff@0.15.15 check` (clean), and
    `scan_test_hygiene.py --diff` (no findings).
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Empty commit/changed_files backfilled from git via Run-ID trailer match | tested | `test_git_backfill_populates_commit_and_changed_files_with_derived_provenance` PASSED |
  | 2 | Declared commit/changed_files are never overwritten by backfill | tested | `test_declared_commit_and_changed_files_are_untouched_by_backfill` PASSED |
  | 3 | No matching commit → `unavailable` (not a silent empty-but-derived) | tested | `test_no_matching_commit_resolves_unavailable_provenance` PASSED |
  | 4 | Merge-only Run-ID match → `unavailable`, never `derived` with an empty file list | tested | `test_merge_only_match_resolves_unavailable_not_derived` PASSED |
  | 5 | Duplicate Run-ID across commits: union `changed_files`, newest commit's sha wins | tested | `test_duplicate_run_id_unions_files_newest_sha_wins` PASSED |
  | 6 | `changed_files` capped at 50 with `changed_files_truncated: true` | tested | `test_changed_files_capped_and_truncation_flagged` PASSED |
  | 7 | `area_ids` derived correctly from backfilled `changed_files` via existing `match_area` | tested | `test_git_backfill_populates_commit_and_changed_files_with_derived_provenance` (tightened to assert the real `["src"]` value) PASSED |
  | 8 | Backfilled paths route through the same `normalize_path` pipeline as declared paths (no second unguarded inlet) | tested | `test_backfilled_paths_flow_through_the_same_normalize_path_pipeline` PASSED |
  | 9 | `provenance` object present (5 keys); `extraction` block removed | tested | asserted across all backfill tests (`"extraction" not in entry`) PASSED |
  | 10 | `coverage` envelope: per-field derived/declared/unavailable counts, commit-map scan status | tested | `test_coverage_envelope_present_with_per_field_counts` PASSED |
  | 11 | `affected_frs` provenance: `declared` via non-empty list OR legal `change_type`; `unavailable` otherwise | tested | same test, exact counts asserted (2 declared, 1 unavailable) PASSED |
  | 12 | `supersedes_event_id` provenance: `declared` when `amends`/`amended_event_id`/`supersedes` present, `unavailable` otherwise | tested | same test, extended with a positive case PASSED |
  | 13 | Stale v1-shaped cache (no `provenance`/`coverage`) is rejected and rebuilt, never silently read as complete | tested | `test_stale_v1_cache_shape_is_rejected_and_rebuilt` PASSED |
  | 14 | `resolve_base_ref` falls back to local `HEAD` when no `origin` remote is configured | tested | `test_resolve_base_ref_falls_back_to_head_with_no_origin` PASSED |
  | 15 | `resolve_base_ref` returns `None` for a non-git directory (fail-soft, not a crash) | tested | `test_resolve_base_ref_none_for_non_repo` PASSED |
  | 16 | `build_run_id_commit_map` returns `status: "no-repo"` gracefully (not an exception) when `base_ref` is `None` | tested | `test_build_map_no_repo_status` PASSED |
  | 17 | A commit with no `Run-ID:` trailer is simply absent from the map (not an error) | tested | `test_commit_without_trailer_is_absent_from_map` PASSED |
  | 18 | Existing determinism contract (`build_index()` twice → byte-identical) still holds with the new fields | tested | `test_rebuild_is_byte_deterministic_and_cache_is_disposable` (unmodified, still green) PASSED |
  | 19 | Existing cross-phase six-surface producer-invocation contract untouched | tested | `integration-tests/test_event_context_workflow.py::test_all_phase_surfaces_invoke_one_catalog_producer` PASSED |
  | 20 | A commit landing after `build_index()` ran, with no new event appended, invalidates the cache on the next read (code-review finding) | tested | `test_new_commit_landing_after_index_build_triggers_rebuild_not_stale_cache` PASSED |
  | 21 | The 50-file truncation cap keeps source paths over dot-prefixed bookkeeping paths (code-review finding — alphabetical sort was systematically biased) | tested | `test_truncation_prefers_source_paths_over_dot_prefixed_bookkeeping` PASSED |
  | 22 | `resolve_base_ref` pins an immutable sha before either `git log` walk | tested | `test_base_ref_is_pinned_to_a_sha_before_scanning` PASSED |
  | 23 | `git revert --no-edit`'s default message carries no trailer (empirical baseline for the revert-hijack question) | tested | `test_default_git_revert_carries_no_trailer_so_original_run_id_wins` PASSED |
  | 24 | A revert-subject commit carrying its OWN legitimate Run-ID recovers normally (external-review finding — an earlier broader exclusion was removed) | tested | `test_revert_subject_commit_with_its_own_run_id_recovers_normally` PASSED |
  | 25 | The `git log --grep` prefilter matches case-insensitively, same as the `(?i)` Python regex (external-review finding) | tested | `test_lowercase_trailer_matches_the_case_insensitive_git_grep_prefilter` PASSED |
  | 26 | An empty-diff matched commit resolves `changed_files: derived` with `[]`, not `unavailable` (external-review finding) | tested | `test_empty_diff_backfilled_commit_is_derived_not_unavailable` PASSED |
  | 27 | Changed files matching zero catalog areas resolve `area_ids: derived` with `[]`, not `unavailable` (external-review finding) | tested | `test_changed_files_matching_zero_catalog_areas_is_derived_not_unavailable` PASSED |

  0 untested-testable rows; every AC in this spec has at least one row above.
- **Confidence-pattern check:** Asymptote (depth) — the first draft of the
  `area_ids` assertion in AC/row 7 was a loose "one of two acceptable
  labels" check that would not have caught a real regression in
  `match_area`'s call; caught and tightened while writing this section, one
  more probe run after the fix (all 8 tests in that file re-ran green).
  Coverage (breadth) — every row above is `tested`, 0 `untestable`, so the
  ledger's "testable ⇒ tested" bar is met without needing the closed-vocab
  `reason_code` escape hatch. `cross_component` machinery is not touched by
  this diff (`event_context_index.py`/`commit_trailers.py` do not match
  `CROSS_COMPONENT_FILE_PATTERNS` in `risk_detectors.py` — verified by
  reading the pattern list, not assumed), so Integration Coverage does not
  apply.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-events-context-backfill-keys/architecture_brief.md`
- **Verdicts:** deepseek=**reject** · openai=**revise**
- **Smallest thing that would do (per reviewers):** openai — keep the
  git-history recovery (only path that fixes the 815 existing entries) but
  drop the `ADR:`/`Area:`/`FR:` trailer convention entirely, since nothing
  in this change reads them back. deepseek — drop the git-history recovery
  altogether; instead capture `changed_files` at event-creation time so
  only *future* events are populated, accepting the 815 existing entries
  stay sparse indefinitely.
- **Findings:**
  - openai: the trailer convention (reader module, `area_catalog.py match`
    subcommand, `F6.md` footer change) is a new standing authoring
    convention with zero consumers in this change — **accepted, cut** (see
    Out of Scope).
  - deepseek: a write-side fix at event-creation time is simpler and lower
    risk than history reconstruction — **rejected, with reason.** Verified
    against the actual F5b/F6 phase ordering (not assumed): `F5b.md`
    already lists `changed_files` among the `--event-extras-json` fields a
    `work_completed` event can carry — the write side isn't missing, it's
    non-compliant, so "add it at write time" re-specifies an existing
    mechanism rather than proposing a new one. Worse, F5b runs BEFORE F6
    (the commit), so a `git diff` at event-creation time would read the
    *dirty working tree*, not a commit — including the ten-plus derived
    snapshots F6.md deliberately excludes from every commit, which would
    make most events match the same handful of areas and destroy the
    ranking discrimination the index exists for. And `commit` is
    unobtainable write-side by construction: `F5b.md` documents
    `commit=""` as deliberate, with the `Run-ID:` commit footer as the
    designed linkage — which is exactly the join this plan implements, not
    a mechanism competing with an existing one.
  - deepseek's "the problem decays naturally" claim does not hold on this
    codebase either: `shipwright_events.jsonl` is append-only and
    `build_index()` rebuilds from the *whole* log every time — nothing ages
    out, so the 815 sparse entries are permanent, not a transient cohort
    future events would dilute away.
- **Reconciliation:** operator delegated the split verdict to an internal
  Opus arbitration pass (agent a90fcb42ce311e6cc) rather than choosing
  directly. Adopted openai's revise, cut deeper than openai asked: the
  entire `ADR:`/`Area:`/`FR:` trailer surface is removed (not just narrowed)
  — `commit_trailers.py` keeps only `resolve_base_ref()` +
  `build_run_id_commit_map()`, Run-ID-scoped; no `area_catalog.py match`
  subcommand; no `F6.md` change. The git-history backfill (both log calls,
  all internal-review findings B1/B2/S1-S5 attached to them) is unchanged —
  it is the only proposal on the table that actually fixes the 815 entries
  the originating brief complained about.
