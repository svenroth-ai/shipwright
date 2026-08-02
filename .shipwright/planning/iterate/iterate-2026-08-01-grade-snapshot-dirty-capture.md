# Iterate — capture dirtiness before the producer writes, not after

- **Run ID:** `iterate-2026-08-01-grade-snapshot-dirty-capture`
- **Status:** implemented
- **Intent:** CHANGE (Path B)
- **Complexity:** medium (Stage 1 `small` from a history fall-through; Stage 2 upgraded on positive evidence — see below)
- **Risk flags:** `touches_io_boundary` (self-raised)
- **Card:** `trg-f5ae5371` — split out of anchor `trg-ac4fc684`, which superseded
  `trg-4bbbd233` after PR #490 delivered four of six parts.
- **Spec Impact:** NONE (a field is added to a durable event; no FR behavior changes)

## The defect, precisely

`grade_snapshot` events carry `lineage` / `branch` / `base` so a consumer can tell
which tree a Control Grade was measured on. What they cannot tell is whether that
tree held **uncommitted tracked changes** at measurement time — i.e. whether `base` honestly
names the thing that was graded, or whether the grade describes a state no commit
names.

The obvious fix — measure `git status` when the snapshot is emitted — is the one
that was **built and withdrawn before commit after two review rounds**. It fails
for a measured reason:

> Every automatic producer writes **tracked** files before the snapshot is emitted,
> so a dirtiness measurement at emit time reads `true` on a pristine tree.

Four cases were evidenced (`update_compliance`, the run orchestrator,
`finalize_iterate`, the sbom/test-evidence emitters); one was reproduced
end-to-end with `dirty=true` and **zero uncommitted source**.

The chain is verifiable in this tree today:

| Step | Writes | Tracked? |
|---|---|---|
| `finalize_iterate.finalize()` Step 1 → `_record_event` | `shipwright_events.jsonl` | yes |
| Step 2 → `_update_compliance` (subprocess) | 6 generators: rtm, test-evidence, test-links, change-history, dashboard, sbom | yes |
| … then `emit_grade_snapshot` measures | — | — |

By the time the emitter could ask git, the producer has dirtied the tree with its
own output.

**Why an exclusion list was rejected in review.** Hanging one off
`DERIVED_SNAPSHOTS` is structurally wrong: that register deliberately keeps the
event log and `triage.jsonl` **out**, and the two registers answer different
questions. It is also unbounded — it would have to enumerate every output of every
producer, forever.

**The real distinction.** A producer's own writes are the *output* of the
measurement, not its *input*. The question `dirty` answers is about the tree the
grade was computed from, which is settled **before the producer runs**. So the
capture belongs at the producer's entry, and the value is passed through — not
re-derived later and then corrected by subtraction.

## Approach

Reuse the existing seam rather than rebuild it, per the card:

- `source_state.py` already models a **run-id-primary** stamp with a three-valued
  `dirty` (`True` / `False` / `None` = "git could not answer").
- `source_state_git.resolve_git_state` already solved the sibling
  path-relativisation problem (`git status` prints repo-root-relative paths, so an
  exclusion computed against a subdirectory `--project-root` silently misses).

New leaf `shared/scripts/source_state_capture.py`:

- `capture_dirty(project_root, run_id)` — **first capture for a run wins.** If a
  capture already exists for `run_id`, return it; otherwise measure now via
  `resolve_git_state` and record it.
- **Transport: the environment**, not a file. `capture_dirty` writes
  `SHIPWRIGHT_SOURCE_DIRTY` (`"1"` / `"0"`) and `SHIPWRIGHT_SOURCE_DIRTY_RUN` into
  `os.environ`; `subprocess.run` inherits the parent environment by default, so a
  producer needs one line at its entry and no `env=` plumbing at the spawn site.
  The value is honoured only when the recorded run id matches the reader's.
  *A run-scoped JSON store was planned and dropped after external review — see
  `iterate-2026-08-01-grade-snapshot-dirty-capture/external-plan-review.md`.*
- No run id, or a mismatched one → measure now and return. Correct for a standalone
  CLI producer, which has written nothing yet.

Wiring (only the evidenced entry points; everything else degrades honestly):

1. `finalize_iterate.finalize()` — capture at entry, **before** Step 1's event write.
   The one spawning parent that writes tracked files before the regen.
2. `update_compliance.main()` — capture at entry, before the first generator; new
   optional `--run-id`, falling back to `SHIPWRIGHT_RUN_ID` (explicit wins). When
   `finalize_iterate` already captured, this is a read, not a measurement. Since
   `emit_grade_snapshot` has exactly **one** caller, this entry point covers every
   automatic emission.
3. `grade_snapshot_shape.apply_grade_snapshot(..., dirty=...)` — stamps `dirty`
   when known, **omits** it when not (matching `lineage_fields`: absent means the
   event predates the field).
4. `dirty` joins `ATTRIBUTION_KEYS`, so `event_amended --fields` cannot assert it.
   Same rule, same reason as `lineage`: an amendment that could set `dirty: false`
   would launder a work-in-progress measurement into a clean one.

## Acceptance Criteria

- **AC1** — `capture_dirty` measures at most once per run id: a second call after
  the tree has been dirtied returns the **first** value, not a fresh measurement.
- **AC2** — The capture round-trips through the environment, including across a
  real subprocess boundary, and is honoured only when the recorded run id matches
  the reader's.
- **AC3** — Without a run id, `capture_dirty` measures now and records nothing that
  a later run could mistake for its own.
- **AC4** — A malformed environment value (anything but `"1"` / `"0"`) reads as
  **unknown**. The run marker and the value are separate facts: the marker means
  *this run was captured*, the value is *the answer*. So a malformed-or-absent value
  under a **matching** marker is a recorded unknown and is **not** re-measured —
  re-measuring is exactly what would let a producer's own writes turn an honest
  unknown into a false `true`. A fresh measurement happens only when there is no
  matching marker. Nothing in the capture path raises into the producer.
- **AC5** — `apply_grade_snapshot` stamps `dirty` when known and omits the key
  entirely when unknown; the score/grade validation order is unchanged.
- **AC6** — `event_amended --fields` refuses `dirty` alongside `lineage`/`branch`/`base`.
- **AC7** — End-to-end: a compliance regen on a **pristine** tree emits
  `dirty: false` (the reproduced defect emitted `true`), and a regen in a worktree
  holding uncommitted source emits `dirty: true`.
- **AC8** — `docs/hooks-and-pipeline.md` carries the consumer contract for the new
  field and the capture-before-write rule.

## Affected Boundaries

- `shipwright_events.jsonl` — durable, git-tracked, append-only, union-merged, read
  cross-repo by the WebUI Ship's-Log. A wire-shape addition (optional boolean;
  historical events lack the key).
- **`SHIPWRIGHT_SOURCE_DIRTY` / `SHIPWRIGHT_SOURCE_DIRTY_RUN`** — a new environment
  producer/consumer pair spanning a process boundary. This is what raises
  `touches_io_boundary` (`parse_env` is an anchored keyword in the taxonomy), and it
  is what the round-trip test and Boundary Probe are owed for.
- The `finalize_iterate` → `update_compliance` subprocess argv contract (`--run-id`).

## Out of scope, with the reason

- **`stamp_test_results.py` (the F5 `source_state` stamp).** A prior review logged
  *"at F5 `dirty` is `true` on essentially every run"* and closed it by disclosing
  it in `F5.md`. That is **not this defect**: at F5 the iterate's source changes
  genuinely *are* uncommitted, so `true` is honest there, merely uninformative.
  This card is about `true` with **zero** uncommitted source. Left alone
  deliberately.
- **The orchestrator's sibling-process residual.** The env transport reaches
  descendants of the capturer. In a pipeline run the phase's own bookkeeping write
  (`record_event.py`, a *sibling* subprocess of the later compliance regen) can
  still leave one tracked append the emitter counts as tree dirt. It is not the
  reproduced case, and the two mechanisms that would close it both fail: capturing
  at pipeline-run start is stale by the time a later phase legitimately edits
  source, and a durable store was rejected above. Named here rather than papered
  over; filed as **`trg-709828ad`**. Bounded: `true` is the conservative direction,
  so a consumer excluding dirty points loses a point rather than trusting a false
  one.
- **`trg-4f3ee56b`** — grade_snapshot emission *volume* (83% of lines carry nothing
  new). The sibling half of the same split anchor; its own card, its own run.
- **The WebUI consumer change** (`shipwright-webui`, `run-data-join.ts`) — a
  different repo, so it cannot be part of a monorepo iterate.

## Confidence Calibration

- **Boundaries touched:**
  - `shipwright_events.jsonl` — durable, git-tracked, append-only, union-merged,
    read cross-repo. Wire-shape addition (optional boolean).
  - `SHIPWRIGHT_SOURCE_DIRTY` / `_RUN` / `_ROOT` — new environment producer/consumer
    pair spanning a process boundary (`touches_io_boundary`).
  - `finalize_iterate` → `update_compliance` subprocess argv (`--run-id`).
  - `resolve_churn_conflicts.regenerate_tracked_snapshots` → same subprocess.
  - `sys.path` front-insert inside the compliance plugin (ADR-045 namespace hazard).

- **Empirical probes run:**
  1. **Reproduced the defect against the old code path.** Built a pristine repo with
     `dashboard.md` / `events.jsonl` tracked, replayed the real producer write
     order, confirmed zero uncommitted *source*, then called `resolve_git_state`:
     **`dirty=True`** — the withdrawn implementation, reproduced.
  2. **Same fixture through the new path:** **`dirty=False`**. And with a genuine
     source edit: **`dirty=True`** — so the fix does not blanket-report clean.
  3. **Producer inventory measured, not assumed.** `emit_grade_snapshot` has exactly
     **one** caller (`update_compliance.py:222`); **no hook or shell script**
     invokes `update_compliance` (grepped `hooks.json`, `*.sh`, every `hooks/`
     package). That is what retired the run-scoped JSON store as YAGNI, and it is
     what makes the child-entry capture cover every automatic emission.
  4. **Spawning parents audited one by one.** Only `finalize_iterate` and
     `resolve_churn_conflicts` write tracked files before spawning;
     `finalize_security_compliance` writes nothing first. Stage 2 found the
     `resolve_churn_conflicts` case, which falsified the first inventory — fixed.
  5. **Subprocess inheritance exercised for real**, with no `env=` argument, plus a
     negative control proving the child reports `True` when the capture is absent.
  6. **`grep '"dirty"' shipwright_events.jsonl` → zero matches**: the reserved key
     collides with no existing event, so no amendment flow breaks.
  7. **Anti-ratchet run against staged content** (`anti_ratchet_check.py`, exit 0)
     after bumping three already-`exception` entries.

- **Test Completeness Ledger:** every behavior this diff introduces or changes.
  **0 testable-but-untested.**

  | # | Behavior | Status | Evidence |
  |---|---|---|---|
  | 1 | First capture wins; a later ask after the producer wrote returns the first value | `tested` | `test_second_call_after_producer_wrote_returns_the_first_value` |
  | 2 | A genuinely dirty tree still captures `True` | `tested` | `test_a_genuinely_dirty_tree_still_captures_true` |
  | 3 | Untracked files are not dirt | `tested` | `test_untracked_files_are_not_dirt` |
  | 4 | Capture round-trips through the environment | `tested` | `TestRoundTrip::test_capture_is_readable_back`, `test_true_round_trips_as_true` |
  | 5 | A real subprocess inherits it with no `env=` | `tested` | `test_child_process_inherits_the_capture` + negative control `test_child_without_the_capture_does_measure` |
  | 6 | A foreign run's capture is not inherited | `tested` | `test_a_different_run_does_not_read_this_capture`, `test_a_different_run_re_measures_rather_than_inheriting` |
  | 7 | Same run, **different tree** re-measures (doubt D1) | `tested` | `TestBoundToATreeAsWellAsARun::test_same_run_different_tree_is_re_measured` |
  | 8 | The tree binding does not defeat legitimate inheritance | `tested` | `test_same_run_same_tree_still_inherits` |
  | 9 | No run id → measure now, record nothing | `tested` | `TestWithoutRunId` (4 cases, incl. `{run_id}` placeholder) |
  | 10 | Malformed value under a matching marker is a recorded unknown, not re-measured | `tested` | `test_a_malformed_flag_under_a_matching_marker_is_not_re_measured` (4 params) |
  | 11 | Malformed value with **no** marker does measure | `tested` | `test_a_malformed_flag_under_NO_marker_does_measure` |
  | 12 | Unresolvable git records the unknown; a stale flag is cleared | `tested` | `test_unresolvable_git_records_the_unknown`, `test_a_stale_flag_is_cleared_when_the_new_capture_is_unknown` |
  | 13 | Never raises into a producer on a nonsense root | `tested` | `test_a_nonsense_project_root_never_raises` (3 params) |
  | 14 | `apply_grade_snapshot` stamps a bool, omits when unknown, drops a non-bool | `tested` | `TestDirtyIsSuppliedNotMeasured` (10 cases) |
  | 15 | `dirty` refused as an amendment, at function and CLI level | `tested` | `test_dirty_is_refused_as_an_amendment`; `test_an_amendment_cannot_overlay_attribution[dirty]` |
  | 16 | Refusal list cannot drift behind what reaches the log | `tested` | `test_attribution_keys_cover_everything_derived_from_the_tree` |
  | 17 | **End-to-end:** pristine tree → `dirty: false`, non-vacuously (asserts the producer really dirtied the tree) | `tested` (**integration**) | `test_pristine_tree_emits_dirty_false` |
  | 18 | **End-to-end:** genuine uncommitted source → `dirty: true` | `tested` (**integration**) | `test_genuinely_uncommitted_source_emits_dirty_true` |
  | 19 | A parent's earlier capture is inherited by the regen | `tested` (**integration**) | `test_a_parents_earlier_capture_wins` |
  | 20 | Explicit `--run-id` beats ambient `SHIPWRIGHT_RUN_ID`; env is the fallback | `tested` | `test_an_explicit_run_id_beats_the_environment`, `test_run_id_falls_back_to_the_environment` |
  | 21 | No git → field omitted rather than guessed | `tested` (**integration**) | `test_no_git_omits_the_field_rather_than_guessing` |
  | 22 | `finalize_iterate` captures **before** Step 1 writes | `tested` | `test_capture_happens_before_step_1_writes` (spy on the first writer) |
  | 23 | `--run-id` reaches the real subprocess argv, and is omitted when absent | `tested` | `test_the_subprocess_argv_actually_carries_run_id`, `test_no_run_id_means_no_flag` |
  | 24 | Historical events without the field still parse | `untestable` — `covered-by-existing-test` | `TestAdditiveConsumer::test_change_history_collector_ignores_grade_snapshot` already pins that a consumer skips the type; and `grep` measured zero existing `"dirty"` keys |
  | 25 | Environment reads/writes fail soft and never escape into a producer | `tested` | `test_environment_transport_failure_never_reaches_the_producer` (read, write, and delete failures) |
  | 26 | Reusing one run id across tree A/B/A preserves each tree's own first capture | `tested` | `test_each_tree_keeps_its_first_capture_when_the_process_returns_to_it` |
  | 27 | Repository root and a subdirectory identify the same canonical worktree | `tested` | `test_repo_root_is_the_same_from_a_subdirectory`, `test_a_subdirectory_inherits_the_same_worktree_capture` |
  | 28 | A matching run marker without a root binding is incomplete and re-measured | `tested` | `test_matching_run_without_a_root_is_re_measured` |
  | 29 | Explicit empty `--run-id ""` does not fall back to an ambient run id | `tested` | `test_an_explicit_empty_run_id_does_not_adopt_the_environment` |
  | 30 | An unknown or non-boolean supplied value removes any stale `dirty` key | `tested` | `test_explicit_unknown_removes_a_stale_value`, `test_a_non_bool_never_reaches_the_durable_log` |
  | 31 | The consumer docs do not claim that `dirty: false` identifies the exact graded commit | `untestable` — prose contract | Reviewed `docs/hooks-and-pipeline.md`: clean means no tracked working-tree delta at capture time; commit identity remains a separate claim |

- **Confidence-pattern check:**
  - **Asymptote (depth).** The claim is an *ordering* claim, so depth means testing
    order, not values. Pinned at three levels: the unit (`capture_dirty` after a
    tracked write), the producer (`finalize_iterate` spy on its first writer), and
    the real `update_compliance` loop end to end. The end-to-end test carries an
    explicit non-vacuity assertion, so it cannot pass by the tree simply staying
    clean.
  - **Coverage (breadth).** Both directions are covered — `false` on a pristine tree
    *and* `true` on a genuinely edited one — because a fix that always answered
    "clean" would pass a one-sided test while being strictly worse than the bug.
    Degradation is covered in the safe direction: unknown ⇒ omitted, never `false`.
  - **Integration composition.** `cross_component` was **not** raised (no path
    matches `CROSS_COMPONENT_FILE_PATTERNS`), but the change is a contract between
    two processes, so three `category:"integration"` behaviors (17–19, 21) exercise
    the composition through the real loop rather than a mock.
  - **What is NOT claimed.** `dirty` is producer-supplied, so it is *not*
    tamper-evidence: exporting the capture variables asserts it directly (doubt D3,
    disclosed in `docs/hooks-and-pipeline.md`). And the sibling-process residual
    (`trg-709828ad`) is open — both biases point at `true`, the conservative
    direction.
