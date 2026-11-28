# Iterate Spec: r1b-path-joins

- **Run ID:** iterate-2026-11-27-r1b-path-joins
- **Type:** change
- **Complexity:** medium (98 call sites in 67 shared and plugin files, mechanical; one new guard rule)
- **Status:** implemented

## Goal
Second of five R1 PRs of the root-files campaign (BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, section 5 "R1 split", section 12 item 1). Every filesystem join `<root> / _sp.rel(key)` becomes `_sp.path(key, <root>)`, so R1c can put the new-then-old lookup inside `path()` and every one of these readers follows it. Direct joins only: indirect ones (a helper that joins, a constant joined later, a local variable) are listed for R1c in BRIEF 12 item 10. A guard forbids new direct joins. No production behaviour changes: `path(key, root)` is `Path(root) / rel(key)` today.

## Acceptance Criteria
- [x] AC1: No production Python file (outside tests and the resolver) joins a path with `<x> / _sp.rel(...)`; every former join calls `_sp.path(key, <x>)` with the same key and the same root expression (`Path(x)` wrappers dropped, `path()` wraps the root itself).
- [x] AC2: The guard (`shared/tests/test_shipwright_paths_guard.py` via `_shipwright_paths_scan.py`) fails on a new direct join on `rel()`/`name()`/`legacy_rel()`: `/`, `/=`, `.joinpath`, `os.path.join`, `str.join` of a tuple, `Path(root, rel)`, `Path(rel)` wrappers, also through `shipwright_paths.rel`; the guarded fallback shape is a separate rule allowed only in 7 named files, so a plain join there still fails; a positive control proves each shape is detected.
- [x] AC3: Module-level constants bound to `_sp.rel(...)` (BRIEF 12.1: frozen at import, joined elsewhere as `root / CONST`) are inventoried by the guard as a closed list; a new one fails the guard with a message pointing at `path()`. The existing ones are R1c's work (they must follow the lookup too) and are named in BRIEF 12.
- [x] AC4: The full suite stays green with no test edits beyond the guard; the hook fallbacks of shape `"<literal>" if _sp is None else _sp.rel(key)` stay as they are (pinned by R1a's fallback test).

**Pre-build AC record (Step 2a):** none written. `ac_decision.py` refuses `exempt` because 67 production files change, and `unchanged` needs a catalog AC whose promise the touched code keeps; no catalog AC states "Shipwright finds its project files where they live" (the readers serve dozens of FRs). Recorded as a catalog gap in the F5b event (`catalog_gap_fr: FR-01.11`), the same warning class R1a carried; every rewritten call returns the same path.

## Spec Impact
- **Classification:** none
- **ADD:** none · **MODIFY:** none · **REMOVE:** none
- **NONE justification:** Internal refactor; every rewritten expression returns an equal `Path` today.

## Out of Scope
- The module-level `_sp.rel` constants and their `root / CONST` joins (R1c, together with the lookup).
- Hook fallbacks `"<literal>" if _sp is None else _sp.rel(key)` (R1a pinned them; R1c changes them with `rel()`).
- Basename uses of `rel()` in pattern lists and git pathspecs (`change_type_paths`, `artifact_migrations`): not filesystem joins.
- New-then-old lookup, both-copies error, dual lock (R1c); silent-failure gates (R1d); hook matrix (R1e).

## Test-runner config (incidental)
`shipwright_test_config.json` `suite.xdist` gains `"shipwright-changelog": 8`. The changelog unit (810 tests, golden scenarios with real git runs) no longer fits the 1800 s F0 unit timeout serially on this host: three F0 runs of this iterate timed out on it with no test failure (none of its files is touched here). Run alone under `-n 4`: 808 passed, 2 skipped in 24 min, so the unit is xdist-safe; under full-fleet load 4 workers still timed out, hence 8. Config only, no test or gate weakened.

## Affected Boundaries
None: no serialized format, no file location changes.

## Confidence Calibration
- **Boundaries touched:** none serialized; the call contract `path(key, root)` (root may be a str, a `Path`, never wrapped by the caller) now carries 98 readers.
- **Empirical probes run:** (1) survey of every join's left side before the edit (89 names, 9 `Path(x)`), no test replaces `_sp`; (2) line-by-line equivalence of the 98 rewritten lines against the old ones (only redundant parentheses differ); (3) negative control: the new rule over the OLD versions of the changed files flags exactly 98; (4) `git log -L` on `path()`: one version since R0b, always `Path(root) / rel(key)`, so a stale shared cache behaves the same; (5) a regex parenthesis cleanup broke 3 call sites, caught by ruff, repaired and re-checked; (6) full F0 suite green before the review fixes (18/18 units), re-run on the final tree.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| AC1 no direct join left in production; all 98 equivalent | tested | test_python_goes_through_the_resolver (rel-join rule, no allowlist) + full suite |
| AC2 each direct join shape detected (`/`, `/=`, joinpath incl. receiver, os.path/"/"/os.sep join, `Path(root, rel)`, `Path(*[...])`, wrappers, either side, name/legacy_rel) | tested | test_scanner_catches_each_reference_shape (rel-join rows) |
| AC2 only the exact fallback shape is exempt, plain join in an allowed file fails | tested | test_a_plain_join_in_a_fallback_file_is_not_allowed, unrelated-conditional row |
| AC2 no false positive on message/pathspec joins, lambdas, basename comparison | tested | test_scanner_ignores_prose_docstrings_and_resolver_calls |
| AC3 closed per-binding inventory, cap, stale entries | tested | test_no_new_rel_constants, rel-constant rows |
| AC4 fallbacks untouched, hook fallback tests unchanged | tested | test_shipwright_paths_fallbacks.py (unedited) |
| str-root contract the dropped wrappers rely on | tested | test_path_accepts_a_str_root |
| integration: the Stop hook (real `main()`, run config, resolver) reads each phase's evidence where `path()` points, not the old root location | tested | test_handoff_stop_follows_resolver.py (4 phases; fails on the pre-R1b hook) |

- **Confidence-pattern check:** depth - the equivalence claim is checked per line and by the full suite, the guard by positive and negative controls; breadth - every shape the reviews named is either a control or a written blind spot (BRIEF 12.10d); integration composition - the diff touches `hooks/generate_handoff_on_stop.py` (cross_component), so a real-scenario test drives the hook's `main()` with `path()` pointing into a subfolder (R1c's shape) and proves all four rewritten reads follow it.

## End-to-End Verification
- **Surface:** cli
- **Runner:** pytest over the five resolver/guard test files (112 tests, exit 0) - `.shipwright/runs/iterate-2026-11-27-r1b-path-joins/surface_verification.json`

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** The rewrite is mechanically sound (same key and root at every site); gaps were joins through a helper or variable, guard shapes the scan missed, a file-wide allowlist, and an inventory that caps definitions, not uses.
- **Findings:** completeness/medium indirect joins (`_test_gate_paths` helper fed `rel("test_results")`, cwd-relative CLI default, loop and pathspec joins) - deferred to R1c with the exact sites (BRIEF 12 item 10c; the helper is a symlink-escape check whose combination with the lookup R1c must decide); architecture/medium guard false negatives - fixed (`Path(root, rel)`, `Path(rel)` wrappers either side, tuple/list/starred arguments, `/=`), f-strings / `+` / aliased receivers / local variables recorded as blind spots (BRIEF 12.10d); architecture/medium file-wide allowlist - fixed (`rel-join-fallback` rule, plain `rel-join` has no allowlist, test pins it); architecture/medium inventory caps definitions not uses - fixed by stating R1c's work list is every use (12.10b) and a hand-lowered count cap; completeness/low constant blind spots - fixed (`legacy_rel`/`path`/`main_path`, tuple targets), class bodies and default args recorded in the docstring (none exist); architecture/low equivalence - confirmed line by line (98/98), mock roots left to the full suite; architecture/low redundant parentheses - fixed (19 sites; a first regex pass broke 3 call sites, caught by ruff and re-checked).
- **Known limitations:** indirect joins (12.10c), shape-scan blind spots (12.10d)
- **Status:** 6 fixed, 1 deferred

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Build option 2: the smallest change that lets R1c's lookup reach readers that build the path themselves.
- **Findings:** necessity/low - accepted; smallest-option/low - accepted (option 2); complexity-cost/medium `path()` serves reads and writes - deferred to R1c as a design decision (12.10e); completeness/medium `main_path()`/`lock_for()`/`json_path_or_none()` join themselves, constants and fallbacks stay outside - deferred (12.10e, Goal now says "direct joins only"); completeness/low guard blind spots - recorded (12.10d); security/low - none.
- **Known limitations:** see BRIEF 12 item 10
- **Status:** 0 fixed, 3 deferred to R1c (written down)

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-11-27-r1b-path-joins/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (option 2).
- **Findings:** glm/low the guard outlives the campaign - accepted, the inventory part is campaign-scoped (closed list, cap lowered to zero by R1c); glm/low inventory as machinery - accepted (a JSON list plus one test, no new runtime code). openai: none.
- **Reconciliation:** Option 1 (flip `rel()`) breaks unmigrated repos (12.1), option 3 (lazy) mixes the mechanical edit into R1c's behaviour change; both reviewers chose option 2 independently.

## External Plan Review
- **Verdicts:** glm=approve · openai=revise
- **Findings:** glm/medium + openai/medium file-wide fallback allowlist - fixed (own rule, plain join fails in those files); glm/low str-typed roots - checked (a `str / str` join would have raised before; every root is a `Path` or wrapped); glm/low `name()`/`legacy_rel()` joins - checked (0 in production; scan of the old tree flags exactly the 98); glm/low multi-argument `rel()` - checked (codemod asserts one positional argument); openai/medium reconcile scanner with the codemod - done (old tree 98, new tree 0 plain + 8 fallback); openai/low runtime root types - checked (no `PurePath`/custom roots at the 98 sites; full suite).

## External Code Review
- **Verdicts:** openai=revise · glm=approve
- **Findings:** openai/medium any conditional counted as the fallback - fixed (exact `"<lit>" if _sp is None else _sp.rel(...)` match; an unrelated conditional is `rel-join`, control added); openai/medium `Path(rel).joinpath(...)` missed - fixed (receiver checked, control added); openai/low no direct `legacy_rel()` join control - fixed; glm/low allowlist test only checked the dict - fixed (end-to-end: a plain join in an allowed file is reported, the fallback in the same file is not); glm/low `rel(...) / x` and `Path(rel, "sub") / x` missed - fixed (either side of `/`, wrappers with any argument); glm/low attribute-access receivers - recorded (BRIEF 12.10d).

## Code Review (Stage 2)
- **Reviewer:** code-reviewer (opus). All 98 rewritten sites equivalent (same key and root; `None` root raises `TypeError` in both forms); the 3 parenthesis repairs read correctly.
- **Findings:** low `join` too broad (message / `shlex` pathspec joins) - fixed (only `os.path`/`posixpath`/`ntpath`/`"/"`/`os.sep` joins; negative controls); low bare-name `rel` imported from the resolver - recorded as a blind spot (BRIEF 12.10d); low inventory compared names not bindings - fixed (per-binding `Counter`, swap with an edited fixture stated in the docstring); low lambda calling `path()` counted as frozen - fixed (lambda bodies skipped, negative control).

## Doubt Review (Stage 3)
- **Reviewer:** doubt-reviewer (opus). No incorrect rewrite found; receivers are uniformly `_sp`.
- **Doubts:** medium dropped `Path(x)` wrappers rely on `path()` wrapping a str root - resolved: `path()` has returned `Path(root) / rel(key)` since R0b (`git log -L`, one version), now pinned by `test_path_accepts_a_str_root` (also `main_path`); low `Path(*[root, rel])` missed - fixed (Starred counts as a join, control added), `with_name`, `%`-format and bare/aliased `join` added to the blind spots (12.10d); medium R1c work list incomplete - fixed: the 17 modules importing an inventoried name are listed (12.10b), second-order constants named, and the non-Python carriers get their own item (12.10f).
