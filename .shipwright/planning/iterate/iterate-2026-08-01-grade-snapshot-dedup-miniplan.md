# Mini-Plan — iterate-2026-08-01-grade-snapshot-dedup

> **Revised after external plan review (verdict `revise`).** The dedup key changed
> from `(lineage, branch)` to the `lineage` class, because re-measuring with an
> honest attribution guard showed the original key fixed **none** of the measured
> defect. Details and the corrected numbers are in the spec's "Choosing the dedup
> key" section.

## Chosen approach: producer-side dedup on (value + lineage class), under the existing lock

### Steps

1. **`shared/scripts/tools/record_event.py`**
   - Add `last_grade_snapshot(project_root, lineage_class) -> dict | None` beside
     `has_commit` / `has_phase_event`: **reverse-scans the parsed event list** and
     returns the most recent `grade_snapshot` record **of that lineage class**, or
     `None`. Filtering by class inside the scan (rather than comparing classes
     after finding the absolute last snapshot) is what keeps an alternating
     `main`/`branch` sequence deduplicating. It is a full scan of parsed events,
     not a tail read — named and documented as such. Inherits `read_events`'
     corrupt-line policy (recover, warn) rather than inventing a second one.
   - Add a `deduplicate_grade_snapshot: bool = False` parameter to
     `append_event_idempotent` and a branch for it **inside** the existing
     `_FileLock`, alongside `deduplicate_by_commit` and `phase_completed`.
     Default-off, so the CLI replay route and every other caller are unchanged;
     only the compliance emitter opts in. Suppress only when both sides carry a
     resolvable `lineage` (present, not `"unknown"`), the classes are equal, and
     the comparable `(grade, float(score))` pairs are equal. Skip payload:
     `{"reason": "unchanged_grade", "grade": ..., "score": ...}`.
   - Add a private `_comparable_grade(event) -> tuple | None` returning `None`
     unless `grade` is a non-empty `str` and `score` is a non-`bool` `int`/`float`
     that is finite. The comparison must never raise inside the lock: a raise there
     costs the emitter its event (swallowed by `update_compliance`'s best-effort
     wrapper), which is worse than the duplicate being removed. Non-comparable →
     append.
   - Add a private `_lineage_class(event) -> str | None` accepting only the closed
     set `{"main", "branch"}`, so a malformed value cannot match itself.
   - Gate the branch on `deduplicate_grade_snapshot` **and**
     `event.get("type") == "grade_snapshot"`.
   - Update `append_event`'s docstring: it is still the unconditional append, but
     it is no longer what the compliance emitter calls.

2. **`plugins/shipwright-compliance/scripts/lib/_grade_snapshot.py`**
   - Import `append_event_idempotent` instead of `append_event`.
   - Map the skip tuple onto the existing result-dict vocabulary:
     `{"appended": 0, "reason": "unchanged_grade", "grade": ..., "score": ...}` —
     the same shape as the existing `not_gradeable` skip, so `update_compliance`'s
     payload handling needs no change at all. **One canonical reason string**
     shared with the CLI; the emitter does not rename it.
   - Rewrite the AC1 paragraph of the module docstring: state the measurement that
     falsified the old premise, and state the new contract and its key.

2b. **`shared/scripts/lib/config.py`** — correct `read_events`' docstring, which
   still claims it redirects to the canonical main-repo log. `resolve_events_path`
   is a literal per-tree join; the claim is false and it is in the read path this
   dedup depends on.

3. **Contract prose that asserts the old behaviour** (AC6)
   - `shared/scripts/tools/compliance_input_state.py` — two comments claiming
     "appends one `grade_snapshot` event per run by documented contract". Correct
     them, and note that dedup makes the fixpoint argument *stronger*.
   - `plugins/shipwright-compliance/tests/test_grade_snapshot_regen.py` — module
     docstring line "AC1 — one snapshot PER regen, unconditionally".
   - `shared/tests/test_finalize_iterate_idempotency.py` — its prose explains the
     banner-minute split by "each run appends a fresh grade_snapshot"; that reason
     no longer always holds (the `work_completed` append still advances the
     stamp). Correct the explanation; the assertions are unaffected.
   - `docs/hooks-and-pipeline.md` — the artifact-write matrix row for the event log.

4. **Tests** — invert `test_each_regen_appends_another_snapshot` into the AC1/AC2/AC3
   trio, add the lock-invariant and CLI tests, extend the composition test.

### Risks and how each is retired

| Risk | Retirement |
|---|---|
| Dedup hides a real grade regression | Only *strictly consecutive identical* values are suppressed; any change appends. Simulated: every transition survives, including one injected mid-run into 20 identical snapshots. |
| A `lineage`-filtered consumer loses a transition | The comparison requires a matching `lineage` class, so a branch point can never suppress a `main` point. Simulated per-class: value-path identical to raw. |
| A per-*branch* view loses a point | **Accepted, not retired.** Documented in the spec with its rationale — `lineage` is the documented series selector, `branch` is point metadata, and "did this run happen" is answered by `work_completed`. |
| Two concurrent regens both append | Within one checkout: scan and append share one `_FileLock`, inherited from `append_event_idempotent` and pinned by a test. **Across worktrees: not retired** — two trees are two files and two locks. Documented in AC4 instead of being claimed away. |
| A **stale** worktree re-appends a value already merged elsewhere | **Not retired, and the earlier draft's bound was wrong** — this is more common than the concurrent case. Pinned by a test so it is a known limit, not an assumption. Mitigated operationally: worktrees start off a fresh fetch and `ensure_current` refreshes before the arm. |
| Comparison raises inside the lock on malformed durable data | `_comparable_grade` returns `None` instead of raising; non-comparable → append. Flagged independently by **both** reviewers; pinned by a test over null / missing / non-numeric / non-finite scores. |
| Manual replay/backfill silently suppressed | Dedup is **opt-in**; the CLI replay route keeps unconditional append. The falsified premise ("a regen is an explicit act") is false for automatic regens and true for a hand-run replay, so the behaviour is split exactly where the premise splits. |
| Attribution-less records treated as one tree | The guard refuses to compare when either side's `lineage` is absent or `"unknown"`. This is what the first draft got wrong; now pinned by a test. |
| Convergence checker breaks | `change_history.collect_events` filters the type out; dedup makes pass 1 / pass 2 agree *more* readily. |
| A new skip branch changes the result contract for other callers | Enumerated: `append_event_idempotent` has exactly one caller today (the CLI), plus the emitter this iterate adds. |
| CLI replay/backfill blocked | Only suppresses a value identical to the most recent preceding snapshot from the same lineage class — which a backfill would not want either. |

## Alternative considered: leave the producer alone, compact the log periodically

Add a maintenance step (or a git merge driver) that rewrites `shipwright_events.jsonl`
to drop consecutive identical snapshots.

**Rejected.** It requires *destroying appended lines* in a durable audit log, which
is the one outcome `compliance_input_state.py` was explicitly rewritten to prevent
after a rewind guard destroyed a concurrent writer's append. It also fixes the
symptom on a schedule rather than the producer that creates it, so the log is
correct only as often as the compaction runs, and every reader in between still
sees one-third noise. Finally, a rewriting step racing union merges across
worktrees is a genuinely hard concurrency problem, where the chosen approach
inherits a lock discipline that already works.

**A second alternative — keep appending but mark duplicates with a flag** — was
rejected for a simpler reason: it does not reduce the line count at all, which is
the actual complaint.
