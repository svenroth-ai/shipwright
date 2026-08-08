# Mini-Plan: index-readers-adr-lock

- **Run ID:** iterate-2026-08-08-index-readers-adr-lock
- **Revised after the operator's final design decision** (see the iterate
  spec's `### Architecture Review` — the allocator/lock/watermark design from
  the internal-Opus-reviewed draft is superseded; new ADR spec files are
  named `<run_id_sanitized>-<slug>.md` instead, needing no allocator).

## Files to create/modify

**Defect 1 (edit, 4 files + 1 new test):**
1. `plugins/shipwright-iterate/skills/iterate/references/context-loading.md` — edit item 4
2. `plugins/shipwright-build/skills/build/references/first-actions.md` — edit line 63
3. `plugins/shipwright-plan/skills/plan/references/first-actions.md` — edit line 103
4. `plugins/shipwright-project/skills/project/references/step-1-interview.md` — edit line 16
5. `shared/tests/test_mandated_reader_index_first.py` — new: permanent regression guard for AC1/AC1b

**Defect 2 (new + edit — pruned to the final design):**
6. `plugins/shipwright-iterate/skills/iterate/references/F3.md` — edit: naming
   instruction and worked example switch from `<NNN>-<slug>.md` to
   `<run_id_sanitized>-<slug>.md`; the worked `# ` heading no longer claims a
   numeric `ADR-NNN`.
7. `shared/scripts/lib/adr_index.py` — add a public `parse_adr_number()`
   wrapper around the existing `_ADR_FILENAME_RE` match (pure refactor,
   shared by the renderer and the new drift guard so they cannot disagree —
   Opus finding 7, still applicable to the drift guard alone).
8. `shared/tests/test_adr_index_no_duplicate_numbers.py` — new: anti-ratchet
   drift guard against *new* numeric-prefix collisions (backsliding guard,
   not an allocator guard), baseline regenerated from the tree, not
   hand-transcribed (Opus finding 1).
9. `shipwright_adr_collision_baseline.json` (project root) — new: baseline
   data file, written by a regeneration command (mirrors
   `shipwright_bloat_baseline.json`'s shape/idiom) — **not** hand-typed
   numbers. (Moved here from `shared/scripts/lib/` during code review —
   item 18 below.)
10. `shared/scripts/tools/rebuild_adr_collision_baseline.py` — new: the
    documented regen command for #9, so the next parallel-merge collision (if
    anyone reverts to hand-guessing a number) has a considered "did the
    baseline grow" decision instead of a silent guard update (Opus finding 1).
11. `.shipwright/planning/iterate/iterate-2026-08-08-index-readers-adr-lock-adr-collision-report.md` — new: the collision report (Opus finding 6 — filed under `.shipwright/planning/iterate/`, not `.shipwright/planning/adr/`, which would render it into the committed INDEX.md as a pseudo-entry).
12. `docs/hooks-and-pipeline.md` — check context-loading matrix / F3 row for needed updates (naming-convention wording only — no new command, no new hook).
13. `docs/guide.md` — Appendix B / Chapter 4 DID need edits after all (three prose mentions of the old `<NNN>-<slug>.md` convention at lines ~1856/2323/2353) — the "likely no change needed" note above assumed no *new command*, but the *existing* naming-convention prose still had to be kept honest.
14. `plugins/shipwright-iterate/skills/iterate/references/{F2,F6,F-finalize-bundle}.md` + `.shipwright/planning/adr/_template-bloat-exception.md` — found during a repo-wide sweep for stale `<NNN>-<slug>.md` mentions in LIVE (non-historical) files; same naming-convention wording fix.
15. `plugins/shipwright-compliance/scripts/audit/group_f.py` — the F4/F6/F7 detective-audit finding messages advised refactoring bloated ADRs into `<NNN>-<slug>.md`; a user acting on that advice today would recreate the exact defect this run retires. Updated the advisory text; existing `test_audit_groups_c_f.py` suite (18 tests) re-run green — no behavior change, only the message string.
16. `shared/scripts/tools/write_decision_log.py`, `shared/scripts/tools/write_decision_drop.py`, `shared/schemas/decision_drop.schema.json`, `plugins/shipwright-iterate/agents/sub-iterate-runner.md`, `plugins/shipwright-build/agents/code-reviewer.md` — spec-reviewer (Stage 1, model=opus) caught these on its first pass: the `--spec-ref` CLI help text, an `ADR_SPEC_FOLDER_HINT` constant baked into the field-overflow error message, the schema's own `description` fields, and an `adr:` example line duplicated verbatim in two agent files all still advertised `<NNN>-<slug>.md`. Fixed; `shared/tests` subset (`adr or decision_log or decision_drop`, 259 tests) re-run green.
17. `shared/scripts/lib/adr_index.py::_entries()` — spec-reviewer's second finding: AC5 claims `_entries()` and the drift guard "share one `parse_adr_number()` helper," but `_entries()` still called `_ADR_FILENAME_RE.match()` directly. Wired it to call `parse_adr_number()` for real. First attempt introduced a regression (used the int form for the rendered label, silently dropping zero-padding — "ADR-90" instead of "ADR-090"), caught by `test_adr_index_writing.py::test_cli_regenerates_the_index` failing; fixed by keeping `match.group('num')` (the zero-padded string) for the label and the int only for the sort key / branch decision.

18. **Code-review round (Stage 2, model=opus).** Found 19 issues (6 medium, 13 low) after spec-reviewer's PASS. Fixed the 6 medium + most low: moved `adr_collision_baseline.json` from `shared/scripts/lib/` to project-root `shipwright_adr_collision_baseline.json` (portability — the old location baked in a monorepo-only path, contradicting the tool's own stated bloat-baseline-mirroring rationale); fixed `load()`'s docstring (it claimed fail-open, the actual — and correct — behavior is fail-closed); added a shared `unpinned_collisions()` helper so the subset-rule logic isn't re-typed across 3 tests; rewrote a vacuous shrink-test that degenerated to `{}` before ever exercising the subset rule; added in-process (not subprocess — a documented diff-coverage landmine) CLI coverage for `rebuild_adr_collision_baseline.py`; corrected `sub-iterate-runner.md`/`code-reviewer.md`'s `adr:` field example, which had ALREADY been wrong before this run (path-style, when real `shipwright_bloat_baseline.json` entries are all `"ADR-NNN"`-style) — my first pass had mechanically preserved that pre-existing error rather than questioning it. Declined 3 low findings with reasoning (double-regex-match "readability" nit would undo the spec-reviewer's AC5 requirement; a shared-walker extraction would push `adr_index.py` over its exact 300-line bloat cap; a proposed `docs/hooks-and-pipeline.md` matrix row would contradict the sibling `shipwright_bloat_baseline.json`'s own established precedent of having none). Re-verification requested from code-reviewer.

## Work breakdown

1. **Defect 1, readers (files 1-4)** — apply the index-first wording (drafted during Repo Scout, corrected per review finding 11 to name an explicit fallback for "index has no matching entry") to each of the four mandated-reader instructions.
2. **Defect 1, regression guard (file 5)** — TDD: write this test FIRST. Asserts each of the four files (a) references `decision_log_index.md` and (b) contains no "read...completely" / "ALL...decisions" phrasing bound to `decision_log.md`. Confirms red before step 1's edits, green after.
3. **Defect 2, `parse_adr_number()` (file 7)** — extract/export the existing `_ADR_FILENAME_RE` match logic as a public function so the renderer (`_entries()`) and the new drift guard (step 5) provably agree on what counts as a collision (3-4 digit, `_template-*` skip, etc.). Refactor `_entries()` to call it — no behavior change, existing `test_adr_index*.py` suite is the regression guard for this step.
4. **Defect 2, baseline regen + drift guard (files 8-10)** — write `rebuild_adr_collision_baseline.py` first (scans `.shipwright/planning/adr/*.md`, groups by number via `parse_adr_number()`, writes `adr_collision_baseline.json`), run it to produce the real baseline (measured 15 files/6 numbers at Repo Scout — re-measure at build time since more may have merged since), then write `test_adr_index_no_duplicate_numbers.py`: for every PINNED number, `actual_files ⊆ pinned_files`; for every unpinned number, at most one file (subset rule, not count/equality, so a legitimate rename-away never false-positives and a swap never false-negatives).
5. **Defect 2, report (file 11)** — per-number citation counts (`grep -rc "ADR-<NNN>\b"` excluding the colliding files' own self-references) + proposed resolution, left to the operator. Also states the accepted consequence (spec-folder filename and `decision_log.md` number are formally independent identities; cite by slug/run_id, not bare number).
6. **Defect 2, wire-in (file 6)** — update F3.md's "write the ADR spec file BEFORE running the command" step to use `<run_id_sanitized>-<slug>.md` and update the worked example.
7. **Docs sync (files 12-13)** — `hooks-and-pipeline.md` context-loading/F3 rows (naming convention only); `guide.md` check only — expect no change (no new command shipped).
8. **F0-F12 finalization** — full test suite, F0.5 CLI surface verification, review cascade (model=opus), **`bash scripts/update-marketplace.sh` + `check_plugin_cache_sync.py --strict` after push** (plugin-side files: the four skill readers + F3.md), PR + automerge.

## Test strategy

- New regression guard for AC1/AC1b (permanent, closes the gap Opus review finding 8 identified).
- New anti-ratchet drift-guard test for AC5, baseline regenerated not hand-typed (finding 1), subset rule (finding 7).
- No allocator tests — nothing to allocate under the final design.
- Existing `test_decision_log_index_producers.py::test_committed_index_is_not_stale` and `test_adr_index*.py` suites must stay green — the `parse_adr_number()` extraction (step 3) is a pure refactor of already-tested logic.
- No E2E surface (framework prose + Python tooling, no browser/server) — `surface: cli`, consistent with `shipwright_test_results.json`'s standing e2e/smoke `n/a` precedent for this repo.

## Superseded designs (kept for provenance, not implemented)

**Round 1 — claim-time allocator.** Dedicated lock + self-healing
cross-worktree watermark + idempotent CLI. Internal Opus review fixed 11 real
bugs in this design (self-deadlock from lock reuse, watermark durability,
silent degradation, path-traversal via the slug). Then both external
reviewers rejected/revise'd the approach itself on proportionality grounds —
see the iterate spec's `### Architecture Review`.

**Round 2 — merge-time blocking check** (both external reviewers'
recommendation). No new runtime mechanism; add a CI/F11 gate that blocks a
merge on a guessed-number collision. Superseded by the operator's own
question during the architecture-review stop: presented with this as one of
three options, the operator asked why the file needs a number at branch time
at all, which led to the final design (no number, no gate needed for new
files either).

Both rounds' full reasoning is preserved in the iterate spec's `## Design
Notes` and `### Architecture Review` sections rather than deleted, since the
rejection reasoning is what prevents this problem from being re-litigated the
same way twice.
