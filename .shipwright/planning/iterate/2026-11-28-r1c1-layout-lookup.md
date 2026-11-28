# Iterate Spec: r1c1-layout-lookup

- **Run ID:** iterate-2026-11-28-r1c1-layout-lookup
- **Type:** change
- **Complexity:** medium (classifier said `large` from the word "migration" and flagged `touches_migrations`, a false positive: no database migration is touched. Repo Scout: one subsystem: the resolver, one new sibling module, two hooks, tests)
- **Status:** implemented

## Goal
Third R1 PR of the root-files campaign (BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, section 5 "R1 split"; R1c was split in two by the operator on 2026-11-28: R1c-1 is the lookup, R1c-2 routes the 80 frozen constants and the indirect joins through it). The resolver's `path()` looks in the new place (`.shipwright/config/`) first and in the old root place second; a file in both places, or a pointer stub without its migrated copy, is a loud error. No repository has a `.shipwright/config/` file or a pointer stub yet, so behaviour only changes once one exists (R3 migrates).

## Design (decisions BRIEF 12.10e asks for)
1. **One lookup, in a sibling module.** `shared/scripts/lib/shipwright_layout.py` (stdlib only) holds `LayoutError` and `locate()`; `shipwright_paths.path()`, `main_path()` and `json_path_or_none()` all call it. The resolver is at its 300-line cap (BRIEF 12.9), so the logic does not go there. The resolver loads the sibling (and `shipwright_pointer`) by FILE from its own directory under a module name that includes that directory, so the plugin cache and the dev tree never share a layout module, and every alias of the resolver gets the same one.
2. **State table** (`new` = `.shipwright/config/<name>`, `root` = the legacy root file; only keys whose registry row `moves`; rows are checked in this order: stub at the new path, root stub verdict, both copies):

| new | root | `path()` returns |
|---|---|---|
| absent | absent | root (writers keep creating the legacy file until R3) |
| absent | present, not a stub | root |
| present | absent | new |
| present | present, not a stub (identical or not) | `LayoutError("both_copies")` naming both paths and the fix |
| present | root is a stub (`run_config` only) | new |
| absent | root is a stub (`run_config` only) | `LayoutError("incomplete_migration")` naming the missing path (BRIEF 14.3) |
| any | root stub `too_new` / `edited` (`run_config` only) | `LayoutError("pointer_too_new")` / `LayoutError("pointer_edited")` (14.1) |
| present and itself carries the signature (every moving key) | any | `LayoutError("stub_at_new_path")` (14.1) |

Files that do not move (`events`, retired rows, `audit_config` and `dev_server` until R1c-2 flips them) resolve to the root as before. Only the root `shipwright_run_config.json` can be a stub (BRIEF 14.1); a stub copied to ANY key's new path is an error (it would otherwise parse as broken JSON and read as defaults). The one recogniser `shipwright_pointer.classify` decides. A large ordinary config is judged on one 2 KiB read: a stub's first line starts (after an optional BOM and ASCII whitespace) with the signature, so a head that starts otherwise settles it, minified one-line JSON included. Only REGULAR files count as present and are read (a directory or FIFO of that name is no copy and never blocks a hook); an unreadable file counts as not a stub. Contents of two copies are never compared. **Identical copies are an error too** (plan and architecture reviews). Accepting them (BRIEF 4.3) would let the first write through `path()` update only the new copy, so the next read would fail anyway. Failing at once, with the fix, is the honest form of BRIEF 14.5's "non-stub root + new copy = loud error". `LayoutError` subclasses `Exception` directly: this codebase catches `OSError`, `ValueError` and `RuntimeError` (lock timeouts) as "missing", "bad JSON" or "retry". The class is per tree, so cross-tree code matches `.code`.
3. **Reads and writes use the same answer.** A writer that calls `path()` writes where the file lives: the root in an unmigrated repo (including "neither exists"), the new place in a migrated one; it refuses on both-copies and incomplete-migration (BRIEF 14.3 "config writes refuse"). Nothing writes the new place before R3 unless a file is already there.
4. **No dual lock in R1** (operator, 2026-11-28, on the advice of all four plan and architecture reviewers). The legacy root lock (`lock_for()`) stays the ONE lock for `run_config` and `ac_registry` in both layouts. It does not depend on where the data lives, so old and new writers keep excluding each other. Before R3 a second lock would protect against no writer that exists, while adding a permanent acquisition order, a doubled worst-case wait and a leak-on-timeout path. Whether and when the lock moves to `.shipwright/locks/` is decided again before R3 (BRIEF 12 item 11). This replaces BRIEF 4.7.2's "dual lock from R1".
5. **`check_file_size`'s dead fallback (BRIEF 12.8) is removed, not revived.** The hook needs `lib.bloat_baseline` at import (module-level constants), and `bloat_baseline` stays strict: the pre-commit anti-ratchet and the CI gate read the baseline through it, and a root-name fallback there would fail open after R3 (BRIEF 4.1). So the hook imports the resolver unguarded, like the eleven other hooks that do (relying on the SessionStart cache heal, BRIEF 12.4), and its `build_config` read goes through `path()`. The strict xfails go with the dead branch.
6. **Sibling loading.** `_sibling()` reuses the module already registered for its directory and registers before exec. It names the module by a CRC of the normalised directory (no `hashlib` on hook start). A missing or broken sibling (a half-copied cache) becomes an `ImportError`, which the guarded hook imports catch. Eight tests that copy the resolver file alone into a fake tree now copy its two siblings too.

## Acceptance Criteria
- [x] AC1: `path()`, `main_path()` and `json_path_or_none()` follow the state table above for every moving key; a test drives every row with real files in a temp directory, plus a write-then-read round trip in both layouts.
- [x] AC2: Each error names the paths involved and the recovery step; the pointer cases use the shared fixture set `shared/testkit/pointer_stub_cases.py` (a stub at the new path is an error, never config).
- [x] AC3: `LayoutError` is not an `OSError`, `ValueError` or `RuntimeError`; no production file names `.shipwright/config` outside the resolver and the stub renderer (the R1c-1-alone invariant below).
- [x] AC4: Every resolver alias and a hand-loaded copy share ONE layout module per tree; another tree has its own; a missing sibling is an `ImportError`.
- [x] AC5: `check_file_size` has no dead resolver fallback left (BRIEF 12.8); the fallback tests have no xfail; every hook that keeps a fallback still imports with the resolver hidden.
- [x] AC6 (integration): the real Stop hook (`generate_handoff_on_stop.main()`) reads each phase's evidence from `.shipwright/config/` when it lives there (no patching), and on divergent copies reports the both-copies error on stderr instead of reading either.
- [x] AC7: An unmigrated repo behaves exactly as before: full suite green; test edits only where a test copies the resolver file alone or pins the removed fallback.

**Pre-build AC record (Step 2a):** none written, as in R1a and R1b. No catalog AC states "Shipwright finds its project files where they live"; the resolver serves dozens of FRs. Recorded as a catalog gap in the F5b event (`catalog_gap_fr: FR-01.11`).

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** Internal path resolution. Behaviour changes only when a `.shipwright/config/` copy or a root pointer stub exists, and neither exists in any current repository (nothing writes them before R3).

## Out of Scope
- The 80 frozen `rel()` constants, second-order constants, the 17 importer modules and the indirect joins (BRIEF 12.10a-d): R1c-2.
- `audit_config` (D2) and `dev_server` (D1) registry flips, the non-Python carriers statement (12.10f): R1c-2.
- `rel_at()` per commit and the gates of 4.1 / 11.7.4 (bloat, review tier, AC baseline): R1d. The hook matrix test (14.6) and WebUI / leadwright: R1e.
- The dual lock (decided again before R3, Design 4).

## R1c-1 alone (release-table row, BRIEF 4.3)
| State | Readers through `path()` | Readers through frozen constants (80, R1c-2) | Writers | Abort |
|---|---|---|---|---|
| R1c-1 merged, R1c-2 not | new-then-old, loud on two copies or an unfinished move | root only | root (through `path()` or constants; legacy root lock) | off |

This state is safe only while no `.shipwright/config/` copy exists anywhere: a copy there would be read by `path()` readers and missed by the frozen ones. Nothing creates one before R3 (pinned by `test_no_production_code_writes_the_new_place_before_r3`). No release and no R2 dry run is cut between R1c-1 and R1c-2.

## Surveys
- **Hooks with the resolver hidden** (every `hooks/*.py`, all five resolver aliases set to `None`): 12 hooks fail at import, all without a resolver fallback; they rely on the SessionStart heal (BRIEF 12.4). They are `aggregate_triage_on_stop`, `anti_ratchet_check`, `audit_compliance_on_stop`, `audit_phase_quality_on_stop`, `bloat_gate_on_stop`, `check_drift`, `check_file_size`, `generate_handoff_on_stop`, `mark_implementation_span`, `track_context_cost`, and iterate's `codex_activation_mint` and `codex_pretooluse_gate`. `check_file_size` was the only one with a (dead) fallback, now removed (Design 5). Every hook that keeps a fallback imports with the resolver hidden (parametrized test).
- **Broad handlers around a lookup:** an AST scan found no `try` whose body calls `path()`, `main_path()` or `json_path_or_none()` directly under an `except Exception`, `RuntimeError` or bare handler. Indirect ones exist: the Stop hook's phase-completion block (fixed and tested here) and `phase_quality/_run_id_resolve.py`, reached from the Stop audit. The full per-hook answer is R1e's hook matrix (BRIEF 14.6).

## Affected Boundaries
- File location of every moving `shipwright_*` file, for every reader and writer that goes through `path()`; lock files unchanged (Design 4). Round-trip: a writer through `path()` and a reader through `path()` meet in both layouts (test).

## Confidence Calibration
- **Boundaries touched:**
  - The file-location contract of every moving `shipwright_*` file behind `path()`, `main_path()` and `json_path_or_none()` (about 100 readers and writers).
  - The by-file sibling load under the resolver's five module names.
- **Empirical probes run:**
  1. A survey of every `hooks/*.py` with all five resolver names hidden: 12 fail without a fallback, and only `check_file_size` had one, a dead one.
  2. An AST scan for broad handlers directly around a lookup: none found.
  3. A negative control on the Stop hook: on the pre-change hook, 4 of 8 integration tests fail (the both-copies report is missing).
  4. A survey of tests that copy the resolver file alone: eight found and fixed.
  5. Byte counting on the large-config read: at most 2048 bytes in all three shapes.
  6. A by-hand check that nothing creates `.shipwright/config/` today. The doubt reviewer did it, and the widened guard now pins it.
  7. A full F0 run.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| AC1 state table rows for every moving key (neither / root only / new only / both copies, identical included) | tested | test_shipwright_layout.py::test_path_follows_the_file, ::test_two_copies_are_a_loud_error_even_when_identical |
| AC1 non-moving keys ignore a new-place copy; only regular files count | tested | ::test_files_that_do_not_move_ignore_a_new_place_copy, ::test_a_directory_or_other_non_file_is_no_copy |
| AC1 main_path / json_path_or_none use the lookup; write-then-read round trip in both layouts | tested | ::test_main_path_and_json_path_or_none_use_the_lookup, ::test_a_writer_and_a_reader_meet_in_both_layouts |
| AC2 root run_config per shared pointer fixture row x new present/absent; stub at the new path for every key; messages name the paths and the fix; stub text never followed | tested | ::test_root_run_config_per_shared_fixture_row, ::test_a_stub_at_the_new_path_is_never_config, ::test_incomplete_migration_names_the_missing_copy_and_the_recovery, ::test_the_stub_text_is_never_followed |
| bounded read of a large root config (three shapes) | tested | ::test_a_large_root_config_is_judged_on_one_short_read |
| AC3 error type; R1c-1-alone invariant (no production file names the folder or asks for the new paths) | tested | ::test_layout_error_is_not_caught_as_missing_file_bad_json_or_lock_timeout, ::test_no_production_code_writes_the_new_place_before_r3 |
| AC4 one layout module per tree, another tree its own, missing sibling = ImportError and no half module | tested | ::test_every_alias_shares_one_layout_module_and_another_tree_has_its_own, ::test_a_missing_sibling_is_an_import_error_the_guarded_hooks_catch, test_shipwright_paths_identity.py |
| AC5 dead check_file_size fallback removed; hooks with a fallback import with the resolver hidden | tested | test_shipwright_paths_fallbacks.py (no xfail), test_shipwright_paths_guard.py |
| AC6 integration: the real Stop hook reads phase evidence from the new place and reports two copies on stderr | tested | test_handoff_stop_reads_new_layout.py (8 cases; 4 fail on the pre-change hook) |
| AC7 unmigrated repo unchanged | tested | full F0 suite |

- **Confidence-pattern check:**
  - **Depth.** Every state-table row is driven with real files, and the pointer rows come from the one shared fixture set.
  - **Breadth.** Every moving key is parametrized, and so are three large-file shapes.
  - **Integration composition.** The diff touches `hooks/*.py` (cross_component). So the real Stop hook `main()` runs against the real lookup with no patching, and the negative control fails on the old hook.

## End-to-End Verification
- **Surface:** cli
- **Runner:** pytest over the layout, Stop-hook integration, pointer and resolver test files. Evidence: `.shipwright/runs/iterate-2026-11-28-r1c1-layout-lookup/surface_verification.json`.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** No redesign is needed, but the plan had footguns:
  - an error type the codebase swallows;
  - an AC6 the hook could not meet;
  - the identical-copies trap;
  - leak and timeout paths in the dual lock.
- **Findings:**

| Finding | Severity | Outcome |
|---|---|---|
| A `RuntimeError` subclass is caught as a lock timeout | high | Fixed: subclass of `Exception`, plus a handler survey |
| The Stop hook swallowed the error | high | Fixed: the hook reports it, and a test checks that |
| Identical copies break after the first write | medium-high | Fixed: identical copies are an error |
| The `_PhaseTasksLock` leak | medium-high | Moot: the dual lock was dropped |
| R1c-1 alone is unsafe if a new-place copy exists | medium | Fixed: invariant, release row, pinning test |
| Full reads and Windows transient errors | medium | Fixed: bounded head; `OSError` counts as not a stub |
| The read of a stub at the new path was not specified | low-medium | Fixed: every key is checked, and the order is written down |
| The sibling loader | medium | Fixed: module reuse, `ImportError`, CRC naming, `.code` matching across trees |
| The `bloat_baseline` literal fallback would fail open | medium | Fixed: the dead hook fallback was removed instead |
| `mint_ac_ids` has no project root | medium | Deferred to BRIEF 12.11b |
| Stale shared cache, doubled waits, creation of `.shipwright/locks` | low | Moot: the dual lock was dropped |
| Line endings (CRLF), FIFOs, lock name | low | Fixed (only regular files count; copies are never compared), or moot |

- **Status:** 9 fixed, 1 deferred, 4 moot

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Build option 1. Fix the identical-copies row, say where the locks are anchored, and keep `path()` (which now does file I/O) away from callers that only need a name.
- **Findings:**

| Finding | Severity | Outcome |
|---|---|---|
| Necessity | low | Accepted |
| Smallest option | low | Accepted. The dual lock is optional before R3; the operator dropped it |
| Identical copies | medium | Fixed: they are an error |
| Which root the locks are anchored to (`main_path`) | medium | Moot: no new lock, and `model_config` has none |
| Name-only callers and cost | medium | Checked. No production `path()` caller uses the result only as a name. The cost is bounded: two stats, plus at most a 2 KiB read for `run_config` |
| Security | low | Fixed: the stub text is never followed (tested) |
| NONE wording | low | Fixed: it now names the pointer stub |

- **Status:** 4 fixed, 1 moot, 2 accepted

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-28-r1c1-layout-lookup/architecture_brief.md`
- **Verdicts:** glm=revise · openai=revise
- **Smallest thing that would do (per reviewers):** option 1's lookup with ONE lock (the legacy root lock) in both layouts, and the lock moved at R4.
- **Findings:**
  - glm/high simpler-alternative: drop the dual lock. Accepted (operator, 2026-11-28).
  - openai/medium: same. Accepted.
  - glm/low existence: the lookup is warranted. Accepted.
- **Reconciliation:** Both reviewers approve the lookup and reject only the second lock. The internal reviewer calls that lock optional before R3. The operator chose to drop it and decide again before R3 (BRIEF 12.11b), which overrides BRIEF 4.7.2's "from R1".

## External Plan Review
- **Verdicts:** glm=approve · openai=revise
- **Findings:**

| Reviewer / severity | Finding | Outcome |
|---|---|---|
| glm/high | Proof of the dual-lock ordering | Moot: the dual lock was dropped |
| glm/medium | Readers that take no lock | Pre-existing; out of scope |
| glm/medium | Time-of-check gap for identical copies | Moot: identical copies are an error |
| glm/medium, openai/high | `mint_ac_ids` compares registry paths | Deferred: BRIEF 12.11b (the lock sits beside the data file) |
| glm/low | Broad `except Exception` in hooks | The Stop hook is fixed; the rest is R1e's |
| glm/low | Fallback allowlist | Confirmed test-only |
| glm/low | Symlinked tree alias | Handled: the CRC is taken of the realpath |
| openai/high | Writers must resolve the path inside the lock | Recorded for R3 (12.11b) |
| openai/medium | Creating the lock directory | Moot |
| openai/medium | AC6 needs the hook edit | Fixed |

## External Code Review
- **Verdicts:** glm=revise · openai=revise
- **Findings:**

| Reviewer / severity | Finding | Outcome |
|---|---|---|
| glm/high, openai/high | The invariant test flags the new module | Fixed: allowlist updated, literal removed from the message, `--untracked` added |
| glm/low, openai/medium | A directory or FIFO counts as present; comparing contents can block | Fixed: only regular files count, and contents are never compared |
| openai/medium | A single-line config is read in full | Fixed: the head rule, plus a byte-counting test |
| glm/low | `check_file_size` swallows `LayoutError` | Recorded for R1e |
| glm/low | Weak round-trip assertion | Fixed |

## Code Review (Stage 2)
- **Reviewer:** code-reviewer (opus).
- **Verdict:** APPROVE. It checked the state table order, the head rule against `classify`, that answers in an unmigrated repo are unchanged, and the sibling loading.
- **Findings (all low):**

| Finding | Outcome |
|---|---|
| `except BaseException` in `_sibling` | Fixed: now `Exception` |
| `check_file_size` swallows `LayoutError` | Recorded for R1e (the hook is at its line cap) |
| `Path.is_file` re-raises EACCES on Python 3.11 | Fixed: `os.path.isfile` |
| The both-copies test could pass through the outer handler | Fixed: "generated at" is asserted |
| The `left` field was not asserted | Fixed |
| The hooks need both siblings synced | Recorded for R1e |

## Doubt Review (Stage 3)
- **Reviewer:** doubt-reviewer (opus).
- **Verdict:** no high or medium doubt. Answers in an unmigrated repo are unchanged for empty, conflicted, non-JSON and BOM configs, for directories, relative roots and hot paths.
- **Doubts:**

| Severity | Doubt | Outcome |
|---|---|---|
| low | `release_paths` left a half-built module when a sibling failed to load | Fixed: the module is removed on failure |
| low | Unbounded read of a blank-led or symlinked large file | Fixed: a blank head counts as not a stub, and the follow-on read is capped at 64 KiB |
| low | The invariant guard was narrower than the invariant | Fixed: every file type under `plugins`, `shared`, `scripts` and `.github`, plus no caller of the new-path helpers |
| low | Windows sharing violations | Resolved by the existing retry, and an `OSError` counts as not a stub. The transient misread is recorded for R3 |
| low | Existence probes over foreign roots after R3 | Recorded for R1e |
| info | `LayoutError` cannot be pickled | Nothing pickles it today |
