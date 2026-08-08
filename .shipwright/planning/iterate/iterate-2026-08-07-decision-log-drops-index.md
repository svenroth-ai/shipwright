# Iterate Spec: decision-log-drops-index

- **Run ID:** iterate-2026-08-07-decision-log-drops-index
- **Type:** feature
- **Complexity:** large (Stage 1 keyword estimate; forced continue — see ADR-127 Self-Review section)
- **Status:** implemented

## Goal

Give `.shipwright/agent_docs/decision_log.md` and
`.shipwright/agent_docs/decision-drops/` the same producer treatment the ADR
spec folder's `INDEX.md` already has (ADR-116/ADR-118): pure render + writing
rebuild, a byte-equality drift guard where the artifact is committed, a churn
allowlist entry where a git conflict can genuinely occur, and regeneration
triggered by a change to the source rather than by an unrelated event.

## Acceptance Criteria

- [x] `lib/decision_log_index.py`: pure `render_decision_log_index` + locked
      atomic `rebuild_decision_log_index`, refreshed by both
      `write_decision_log.py` and `aggregate_decisions.py`.
- [x] `.shipwright/agent_docs/decision_log_index.md` committed, registered in
      `churn_merge.CHURN_ALLOWLIST` as `DECISION_LOG_INDEX`, byte-equality
      drift guard in CI (`test_decision_log_index_producers.py`).
- [x] `current-status` (`superseded by ADR-NNN`) derived from a
      `(supersedes ADR-NNN)` title marker, not the sparse `**Status**` field.
- [x] `lib/decision_drops_index.py`: same render/rebuild split for the
      decision-drops directory, refreshed by `write_decision_drop.py` and
      `aggregate_decisions.py`.
- [x] Decision-drops index deliberately carries NO `CHURN_ALLOWLIST` entry and
      NO CI drift guard against a committed copy (the directory is
      gitignored) — documented, not silently omitted.
- [x] `integrate_regenerate.py` refreshes+stages both the ADR index and the
      decision-log index post-merge (shared `_refresh_and_stage_index` helper,
      pre-existing ADR step tokens unchanged).
- [x] `docs/hooks-and-pipeline.md` Merge Reconciliation table + Artifact Write
      Matrix updated (doc-sync registry test `test_churn_merge_doc_sync.py`
      still green, both directions).
- [x] `write_decision_log.py` stays within its frozen bloat-baseline LOC
      ceiling (dead `status` kwarg/flag removed to make room).

## Spec Impact

- **Classification:** none
- **NONE justification:** framework-internal developer tooling (an index
  producer for the framework's own architectural-decision log), not a
  product-facing functional requirement. No FR describes "the framework
  indexes its own decision log" — this is infrastructure the same way
  `lib/adr_index.py` itself was (ADR-116/ADR-118 carry no FR either).

## Out of Scope

- The "context register" (trg-c7ef6eac) that would let decisions be filtered
  by relevance area — a different artifact, not a dependency of this index.
- A general bidirectional obsoletes/obsoleted-by link-graph engine — the
  corpus has exactly one supersession marker today (ADR-307 → ADR-042); the
  regex-match-and-annotate approach scales without a rewrite if more accrue.
- Retitling or renumbering any existing decision-log entry.

## Design Notes

n/a — no UI surface; this is a Python library + CLI + doc change.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `write_decision_log.py` (`append_decision`) | `lib/decision_log_index.py` (`rebuild_decision_log_index` reads `decision_log.md`) | Markdown (`### ADR-NNN: Title` headings) |
| `aggregate_decisions.py` | `lib/decision_log_index.py`, `lib/decision_drops_index.py` | Markdown / JSON drop files |
| `write_decision_drop.py` | `lib/decision_drops_index.py` (`_pending_drops` reads each `*.json`) | JSON (`decision_drop.schema.json`) |
| `integrate_regenerate.regenerate_after_merge` | `lib.decision_log_index.refresh_best_effort` | Markdown (post-merge re-derive) |

`touches_io_boundary` fires (config/JSON producer/consumer pair touched) —
Boundary Probe run below.

## Confidence Calibration

- **Boundaries touched:** the four rows above — two new Markdown-index
  render/parse boundaries and one existing JSON drop-file boundary now also
  read by the new drops index.
- **Empirical probes run:**
  - Ran `rebuild_decision_log_index.py` against THIS repo's real
    `decision_log.md` (328 headings, 1 real supersession marker, 8 verbatim
    quoted duplicates inside a fenced "Imported decisions" block) — found the
    fence-aware parser correctly excludes the 8 duplicates (320 real rows),
    which a naive `^### ADR-` regex would NOT (caught this empirically before
    writing the corresponding test — see `test_every_entry_in_this_repo_is_listed`).
  - Ran the CLI round-trip for the decision-drops index against a real drop
    written by `write_decision_drop.py` from inside this worktree — confirmed
    it resolves to the MAIN repo's `decision-drops/` (not the worktree's,
    which `git worktree remove` would destroy) and the index refreshed there.
  - Ran a real two-commit-diverged `integrate_main.integrate()` (real git,
    `git_origin_repo`/`make_worktree` fixtures) proving
    `regenerate_after_merge` refreshes and stages `decision_log_index.md`
    after a genuine merge commit, and that a monkeypatched refresh failure
    surfaces in `steps`, not only stderr.
  - Verified the two existing monkeypatch targets I initially broke while
    refactoring (`integrate_regenerate.refresh_best_effort` bound name;
    `write_decision_drop.py`'s CLI-only refresh timing) by running the full
    pre-existing ADR-index test suite (116 tests) before and after — both
    regressions were caught this way, not by manual reasoning.
  - Confirmed `write_decision_log.py`'s dead `status` kwarg had zero call
    sites/tests via a repo-wide grep before deleting it.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | `render_decision_log_index` parses `### ADR-NNN: Title` headings, fence-aware | tested | `test_decision_log_index.py::test_headings_inside_a_fenced_code_block_are_ignored` PASSED |
  | 2 | Bare heading with no title still renders | tested | `test_decision_log_index.py::test_a_bare_heading_with_no_title_still_renders` PASSED |
  | 3 | `current-status` derived from `(supersedes ADR-NNN)` marker | tested | `test_decision_log_index.py::test_supersedes_marker_annotates_the_superseded_entry` PASSED |
  | 4 | Supersedes match is case-insensitive | tested | `test_decision_log_index.py::test_supersedes_is_case_insensitive` PASSED |
  | 5 | Title brackets escaped so link label isn't truncated | tested | `test_decision_log_index.py::test_bracket_in_title_is_escaped_so_the_link_label_is_not_truncated` PASSED |
  | 6 | GitHub-heading-anchor slugify matches expected shape | tested | `test_decision_log_index.py::test_slugify_matches_github_heading_anchor_shape` PASSED |
  | 7 | Missing `decision_log.md` → strict no-op | tested | `test_decision_log_index_writing.py::test_missing_decision_log_is_a_strict_noop` PASSED |
  | 8 | Write is atomic (failed replace leaves prior index intact) | tested | `test_decision_log_index_writing.py::test_failed_write_leaves_the_previous_index_intact` PASSED |
  | 9 | Written index is LF-only even on Windows | tested | `test_decision_log_index_writing.py::test_render_is_written_verbatim_lf_even_on_windows` PASSED |
  | 10 | CLI regenerates against a real folder | tested | `test_decision_log_index_writing.py::test_cli_regenerates_the_index` PASSED |
  | 11 | `append_decision()` (direct path) refreshes the index in the same call | tested | `test_decision_log_index_producers.py::test_append_decision_refreshes_the_index` PASSED |
  | 12 | Index refresh at append is best-effort and warns, not raises | tested | `test_decision_log_index_producers.py::test_append_decision_refresh_is_best_effort_and_warns` PASSED |
  | 13 | `aggregate_decisions.py` refreshes with zero drops (fixes the fold-only-refresh defect) | tested | `test_decision_log_index_producers.py::test_aggregate_refreshes_with_zero_drops` PASSED |
  | 14 | `aggregate_decisions.py` dry-run writes nothing | tested | `test_decision_log_index_producers.py::test_aggregate_dry_run_writes_nothing` PASSED |
  | 15 | Committed `decision_log_index.md` in THIS repo is not stale (drift guard) | tested | `test_decision_log_index_producers.py::test_committed_index_is_not_stale` PASSED |
  | 16 | Drift guard actually fails on a stale index (guard is provably not vacuous) | tested | `test_decision_log_index_producers.py::test_drift_guard_actually_fails_on_a_stale_index` PASSED |
  | 17 | Every real decision-log entry (fence-aware) is listed in the committed index | tested | `test_decision_log_index_producers.py::test_every_entry_in_this_repo_is_listed` PASSED |
  | 18 | `DECISION_LOG_INDEX` is registered as resolvable churn | tested | `test_decision_log_index_producers.py::test_the_index_is_registered_as_resolvable_churn` PASSED |
  | 19 | `DECISION_LOG_INDEX` is not a `DERIVED_SNAPSHOTS` member | tested | `test_decision_log_index_producers.py::test_the_index_is_not_a_derived_snapshot` PASSED |
  | 20 | Two-diverged-branch real merge refreshes+stages the index end-to-end (`cross_component` integration) | tested | `test_decision_log_index_churn_integration.py::test_index_refreshes_and_ships_through_a_real_diverged_merge` PASSED |
  | 21 | A failed post-merge refresh is reported in `steps`, not swallowed | tested | `test_decision_log_index_churn_integration.py::test_a_failed_index_refresh_is_reported_not_swallowed` PASSED |
  | 22 | Decision-drops index: no pending drops renders the empty state | tested | `test_decision_drops_index.py::test_no_drops_renders_the_empty_state` PASSED |
  | 23 | A pending drop is listed with its title | tested | `test_decision_drops_index.py::test_a_pending_drop_is_listed` PASSED |
  | 24 | Missing title falls back to a decision snippet | tested | `test_decision_drops_index.py::test_missing_title_falls_back_to_a_decision_snippet` PASSED |
  | 25 | Scaffolding files (`.gitkeep`, `_*.json`) are skipped | tested | `test_decision_drops_index.py::test_scaffolding_files_are_skipped` PASSED |
  | 26 | A malformed drop is skipped, not fatal to the whole render | tested | `test_decision_drops_index.py::test_a_malformed_drop_is_skipped_not_fatal` PASSED |
  | 27 | Missing drops dir → strict no-op | tested | `test_decision_drops_index_producers.py::test_missing_drops_dir_is_a_strict_noop` PASSED |
  | 28 | Drops-index write is atomic | tested | `test_decision_drops_index_producers.py::test_failed_write_leaves_the_previous_index_intact` PASSED |
  | 29 | Drops-index CLI regenerates against a real folder | tested | `test_decision_drops_index_producers.py::test_cli_regenerates_the_index` PASSED |
  | 30 | `write_decision_drop.py`'s CLI refreshes the drops index | tested | `test_decision_drops_index_producers.py::test_write_decision_drop_refreshes_the_drops_index` PASSED |
  | 31 | Drops-index refresh at write is best-effort and warns | tested | `test_decision_drops_index_producers.py::test_write_decision_drop_index_refresh_is_best_effort_and_warns` PASSED |
  | 32 | `aggregate_decisions.py` folding a drop refreshes the drops index back to empty | tested | `test_decision_drops_index_producers.py::test_aggregate_folding_a_drop_refreshes_the_drops_index_to_empty` PASSED |
  | 33 | The drops index carries no `CHURN_ALLOWLIST` entry (deliberate, asserted not just narrated) | tested | `test_decision_drops_index_producers.py::test_the_drops_index_carries_no_churn_allowlist_entry` PASSED |
  | 34 | `docs/hooks-and-pipeline.md` churn table stays in sync both directions | tested | `test_churn_merge_doc_sync.py::test_doc_table_matches_churn_allowlist_both_directions` PASSED (pre-existing test, re-run green after the new entry) |
  | 35 | Full pre-existing ADR-index + decision-log/drop suite has zero regressions | tested | 116 pre-existing tests in `test_adr_index*.py`, `test_write_decision_log.py`, `test_write_decision_drop.py`, `test_aggregate_decisions.py`, `test_decision_drop_ssot.py`, `test_churn_merge_doc_sync.py` — all PASSED |
  | 36 | Supersedes marker matches an unpadded reference (`ADR-42`) against a zero-padded heading (`ADR-042`) | tested | `test_decision_log_index.py::test_supersedes_matches_an_unpadded_reference_to_a_zero_padded_heading` PASSED |
  | 37 | A multi-target marker (`supersedes ADR-042 and ADR-100`) annotates every target | tested | `test_decision_log_index.py::test_supersedes_annotates_every_target_in_a_multi_target_marker` PASSED |
  | 38 | Supersedes marker need not be the last thing in the title | tested | `test_decision_log_index.py::test_supersedes_marker_need_not_be_the_last_thing_in_the_title` PASSED |
  | 39 | `refresh_best_effort` warns (not raises) on an undecodable `decision_log.md` | tested | `test_decision_log_index_producers.py::test_refresh_best_effort_warns_instead_of_raising_on_undecodable_log` PASSED |
  | 40 | Decision-drops index lock is anchored at the resolved drops-dir's own root, not the caller's `project_root` (two worktrees contend on the SAME lock file) | tested | `test_decision_drops_index_producers.py::test_lock_is_anchored_at_the_resolved_drops_dirs_own_root` PASSED |
  | 41 | An embedded newline in a drop's title cannot break its bullet row | tested | `test_decision_drops_index.py::test_an_embedded_newline_in_a_title_cannot_break_the_bullet_row` PASSED |
  | 42 | A mid-loop exception in `aggregate()`'s per-drop architecture-doc step still refreshes the index (via `finally`), not just a clean pass | tested | `test_aggregate_decisions.py::test_a_mid_loop_exception_still_refreshes_the_index` PASSED |
  | 43 | `write_decision_log.py`'s CLI runs with no `PYTHONPATH` set (the invocation shape plan/build/deploy actually use) | tested | `test_write_decision_log_bootstrap.py::test_cli_runs_with_no_pythonpath_set` PASSED (split out of `test_write_decision_log.py` — bloat-gate crossing at 301 lines) |
  | 44 | A `### DR-NNN` entry (shipwright-design's own numbering, sharing the log with ADR-NNN) is indexed alongside ADR entries | tested | `test_decision_log_index.py::test_design_dr_entries_are_indexed_alongside_adr_entries` PASSED |
  | 45 | A DR-NNN and an ADR-NNN sharing digits never collide through the supersession lookup | tested | `test_decision_log_index.py::test_dr_entries_are_never_annotated_as_superseded` PASSED |
  | 46 | `(supersedes ADR-042, see ADR-100)` annotates only the named target, not every ADR the trailing text happens to mention | tested | `test_decision_log_index.py::test_supersedes_does_not_over_derive_from_an_unrelated_adr_mention` PASSED |
  | 47 | A `null` (or non-string) `decision` field in a drop does not crash the title fallback | tested | `test_decision_drops_index.py::test_a_null_decision_with_no_title_does_not_raise` PASSED |
  | 48 | Markdown-active characters in a drop's title cannot become a live link/image or break a code span | tested | `test_decision_drops_index.py::test_markdown_syntax_in_a_title_cannot_become_a_live_link_or_image` PASSED |
  | 49 | An uncommitted local edit to `decision_log.md` at merge time is skipped, not staged as an index describing content no commit contains | tested | `test_decision_log_index_churn_integration.py::test_an_uncommitted_decision_log_skips_the_refresh_instead_of_staging_it` PASSED |
  | 50 | A deleted `decision_log.md` post-merge does not falsely report `-refreshed` for an unchanged, stale committed index | tested | `test_decision_log_index_churn_integration.py::test_a_deleted_decision_log_does_not_falsely_report_a_refresh` PASSED |
  | 51 | `write_decision_log.py` works when imported IN-PROCESS by a test session whose own `lib` package already shadows shared's (ADR-045 collision, distinct from row 43's bare-CLI bootstrap) | tested | `plugins/shipwright-build/tests/test_integration.py::test_setup_and_track_section` + `tests/test_tools.py::test_write_decision_log` + `::test_write_decision_log_creates_dir` — reproduced the CI failure locally before the fix (`load_shared_lib` + relative imports in `decision_log_index.py`/`decision_drops_index.py`), all PASSED after |

  0 untested-testable rows. Rows 36-42 were added after the internal Opus
  architecture review and the external plan/architecture review; rows 43-50
  after the Stage-3 doubt review; row 51 after a real CI failure on the PR
  itself (caught by `plugins/shipwright-build`'s own Required Check, not by
  local `shared/tests`) — see `## Architecture Review` and `## Doubt Review`
  below, and `## Self-Review` in ADR-127, for the full finding list and
  disposition of each.

- **Confidence-pattern check:** asymptote (depth) — yes, one "are you
  confident this doesn't touch decision_log.md's own real-content merge
  conflicts?" question DID produce a subsequent finding this run: the first
  churn-integration test draft assumed two branches could both append to
  `decision_log.md` cleanly, which is false (real content, never
  allowlisted) — redesigned the test around a diverged-but-non-conflicting
  merge instead of asserting a false premise. One further probe (the real
  two-branch `integrate_main.integrate()` run above) confirmed the corrected
  design. Coverage (breadth): every ledger row `tested`, 0 untested-testable.

## Verification (medium+)

- **Surface:** none
- **Justification:** pure Python library/CLI/doc change with no HTTP,
  browser, or CLI-user-facing surface of its own — the framework's dev-loop
  test suite (`shared/tests/`) is the executable surface, and it is exercised
  directly above, not through F0.5's E2E runner.

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-07-decision-log-drops-index/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=revise (not a `reject` from either —
  proceeded per skill, findings integrated below)
- **Smallest thing that would do (per reviewers):** deepseek: as proposed,
  two small indexes, one committed with a CI guard, one local. openai:
  smaller — commit and guard `decision_log_index.md` only; omit
  `decision_drops_index.py` and its writer/aggregate hooks entirely, on the
  grounds that a producer-maintained index for transient, gitignored,
  locally-scoped data is not proportionate to its cost (a second
  render/rebuild contract to explain and keep correct).
- **Findings:**
  - openai (medium, proportionality): the decision-drops index is a second
    standing mechanism for data that is transient and never committed;
    suggested dropping it. **Rejected, with reason recorded:** this artifact
    was named explicitly, by the operator, in the run's own opening brief —
    alongside a measured token cost (202 pending drops = ~4,085 tokens read
    in full) that was the stated reason both artifacts were commissioned
    together, not a self-initiated addition made during design. The
    proportionality concern is not wrong in the abstract, and is recorded
    here rather than dismissed, but overriding an explicit, deliberately
    scoped operator instruction is not this review's role — it is the
    operator's to revisit if they choose. The design does keep the two
    artifacts on separably-removable footing (`decision_drops_index.py` has
    no `CHURN_ALLOWLIST` entry, no CI guard, and is wired at exactly two call
    sites), so dropping it later costs deleting one file and two call sites,
    not unwinding an entangled mechanism.
  - deepseek: no findings; approved as proposed, citing the ADR-index
    precedent for both the committed-index cost/benefit and the
    already-accepted "operator must regenerate on manual edit" trade-off.
- **Reconciliation:** proceeded with both indexes as designed. The mini-plan's
  own rejected alternative (a single shared "index framework" module) was not
  reopened by either reviewer. The internal Opus review (run before this
  external pass, per operator instruction) additionally found and this run
  fixed: a release-commit staging gap that would have left the new committed
  index stale on `main` (changelog `SKILL.md` Step 6 + `compliance-evidence.md`
  updated), a lock-file anchored on the wrong root for the decision-drops
  index (two worktrees would contend on two different locks instead of one —
  fixed in `lib/decision_drops_index.py`), an uncaught `UnicodeDecodeError`
  escaping the fail-soft `refresh_best_effort` contract on both new indexes
  (fixed), and a `(supersedes ADR-NNN)` marker regex that missed unpadded
  digit references and multi-target markers (fixed, `int()`-normalized
  lookup + `finditer` over targets). The external pass's own lower-severity
  findings (a Markdown-newline hazard in rendered drop titles; a mid-loop
  exception in `aggregate()` skipping the index refresh) were fixed the same
  way. All six fixes have dedicated regression tests — ledger rows 36-42.

## Doubt Review (Stage 3)

`doubt-reviewer` ran fresh-context, biased to disprove, against the diff plus
this spec. Advisory-must-address: every doubt gets a disposition below — a
fix with a regression test, or a reasoned rebuttal, never silence.

- **HIGH — `write_decision_log.py` had no `sys.path` bootstrap.** The new
  unconditional `from lib.decision_log_index import refresh_best_effort`
  import turned a previously-conditional bug (only fired with
  `--architecture-impact`, which the lazy `from lib.agent_doc_shape import
  render_canonical_bullet` import also needed) into an unconditional one:
  every plain `append_decision()` call would raise `ModuleNotFoundError` when
  invoked as a bare CLI with no `PYTHONPATH` set — the exact shape
  plan/build/deploy actually use. **FIXED**: added the same
  `_SCRIPTS_ROOT`/`sys.path.insert` bootstrap every sibling tool already
  carries. Reproduced the bug empirically before trusting the fix: stripped
  the bootstrap from a copy, ran `env -u PYTHONPATH uv run python
  write_decision_log.py --project-root ... [args]`, got the exact traceback
  with `decision_log.md` already holding the half-written entry; re-ran with
  the bootstrap restored, exit 0, both files created. Regression test: ledger
  row 43.
- **HIGH — minting `decision_log_index.md` into every adopted downstream repo
  via an unattributed `chore(churn)` commit, and no explicit staging-contract
  update in the plan/build/deploy skills that call `write_decision_log.py`
  directly.** Investigated both halves. (1) The commit attribution: this is
  not a new problem class — the ADR index has minted `INDEX.md` into every
  adopted repo the identical way since ADR-116/ADR-118, via the identical
  `regenerate-followup` `chore(churn)` commit `integrate_regenerate.py`
  already made before this change. The decision-log index rides the same,
  already-accepted mechanism; nothing about this diff makes the attribution
  worse than the precedent it extends. (2) The staging-contract gap: grepped
  `shipwright-plan` and `shipwright-deploy`'s skills for an explicit `git
  add`/`git commit` step around `write_decision_log.py` and found neither
  has one — both rely on the calling phase's own later commit step to sweep
  up whatever `append_decision()` wrote, exactly as they already did for
  `decision_log.md` itself before this change existed. `shipwright-build`
  uses `git add -A`, which sweeps `decision_log_index.md` in alongside
  `decision_log.md` in the same commit — again, no different from how the
  log itself was already staged. **Rebuttal, not a fix**: the index inherits
  whatever staging contract each phase already has for the file it is
  derived from; there is no phase where `decision_log.md` is committed but
  its now-sibling index is not, because both are written by the same
  `append_decision()` call and staged by the same catch-all `git add`. Adding
  a *new*, index-specific staging step to three skills would be solving a
  problem this change does not introduce and the existing contract already
  covers.
- **MEDIUM — DR-NNN completeness gap.** `shipwright-design` writes a second,
  independently-numbered entry class (`### DR-NNN: Title`) into the same
  `decision_log.md`; the index's own acceptance criterion ("every real
  decision-log entry is listed") was silently false for those rows. **FIXED**
  via the kind-aware refactor: `_ENTRY_RE`, `_entries()`,
  `_supersession_map()`, and `render_decision_log_index()` are all now
  `(kind, num)`-keyed rather than assuming ADR-only, so an `ADR-042` and a
  `DR-042` (independent sequences that can share digits) can never collide
  through the shared numeric key, and the supersedes vocabulary stays
  ADR-only (DR entries are never annotated as superseded — that vocabulary
  does not exist for design decisions). Regression tests: ledger rows 44-45.
- **MEDIUM — the two indexes are staged in two separate, non-transactional
  `git add` calls inside `regenerate_after_merge`.** A failure staging the
  decision-log index after the ADR index already staged successfully leaves
  the ADR index committed and the decision-log index rewound/stuck, an
  inconsistent-looking (but each individually correct) partial outcome.
  **Rebuttal**: making this transactional would mean a decision-log-index
  staging failure rolls back an ADR-index staging success that already
  worked — a regression, not a fix, since the ADR index would then go stale
  for a reason entirely unrelated to it. The two indexes are independent
  derivations of independent sources; nothing links their correctness to
  each other, so nothing should link their failure handling either. Each
  call already reports its own structured step token
  (`{label}-refresh-failed` / `{label}-stage-failed` / …), so a partial
  outcome is visible, not silent — see
  `test_a_failed_index_refresh_is_reported_not_swallowed`.
- **MEDIUM — `append_decision()`'s `log_path.write_text(content, ...)` writes
  `decision_log.md` itself with no lock, while the new
  `rebuild_decision_log_index` write is locked.** Genuine race: two
  concurrent `append_decision()` calls (e.g. two parallel build sections
  both landing an ADR at once) can both read the same prior content and one
  write clobbers the other's entry. **Rebuttal, scoped as pre-existing and
  out of scope**: this race exists in `write_decision_log.py` today,
  unrelated to and unintroduced by this change — this iterate adds a lock
  around the *index* it introduces, it does not touch how the *source* file
  it reads from is written. Locking `decision_log.md` itself would need to
  span every writer that touches it (`write_decision_log.py`,
  `aggregate_decisions.py`, and shipwright-design's own DR-NNN append path),
  which is a different, source-level concurrency fix — not a natural
  extension of "give this collection an index" and not something the
  ADR-index precedent (`lib/adr_index.py`) does for the ADR spec folder's own
  writers either. Recorded here as a known pre-existing condition rather
  than silently ignored.
- **LOW — a duplicate ADR number in the log's own history.**
  `_supersession_map`'s `position` dict keeps only the LAST file-order
  position for a number that appears twice (a known historical artifact of
  this specific 328-entry corpus — see `lib/adr_index.py`'s own handling of
  the same fact). **Rebuttal**: already documented in `_supersession_map`'s
  own docstring as an accepted, out-of-scope corpus characteristic; fixing
  entry-numbering hygiene retroactively is explicitly Out of Scope above
  ("Retitling or renumbering any existing decision-log entry").
- **LOW — a comment risked implying `_ENTRY_RE` matches the same heading
  shape `get_next_adr_number`'s numbering regex does.** Checked the current
  comment above `_ENTRY_RE` in `lib/decision_log_index.py`: it already states
  the opposite explicitly ("the two intentionally are not the same regex"),
  naming the concrete difference (anchored + fence-aware + DR-aware vs.
  `get_next_adr_number`'s unanchored, non-fence-aware, numbering-only scan).
  **No change needed** — verified the doubt does not describe the comment's
  current text.
- **LOW — a dishonest `-refreshed` step token when the source is missing but
  a stale tracked index still exists.** `refresh()` on a missing source
  (e.g. `decision_log.md` deleted) returns `None`, the identical shape a
  successful no-warning refresh returns — `_refresh_and_stage_index` could
  not tell the two apart and would append `{label}-refreshed` even though
  nothing was read or written, falsely claiming a stale committed index was
  brought current. **FIXED**: added an explicit `(project_root /
  source).exists()` check before calling `refresh()`; a missing source now
  returns silently (no step token), matching the "nothing to do" semantics
  the function already uses when the resulting path doesn't exist either.
  Regression test: ledger row 50.
