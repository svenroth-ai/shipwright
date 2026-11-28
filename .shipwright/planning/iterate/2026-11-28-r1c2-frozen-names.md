# Iterate Spec: r1c2-frozen-names

- **Run ID:** iterate-2026-11-28-r1c2-frozen-names
- **Type:** change
- **Complexity:** medium. The classifier said `small` with no flags, but the change touches 69 files across 9 plugins and `shared/`, five hooks (cross_component) and the resolver registry, so the Repo Scout raised it.
- **Status:** implemented

## Goal
This is the fourth R1 PR of the root-files campaign (BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, item 12.10 work list). R1c-1 put the new-then-old lookup into `path()`. This PR makes every reader and writer that still built a moving file's path from a frozen name go through `path()` too. A moving file placed in `.shipwright/config/` (or `.shipwright/runtime/` for the dev-server state) is then found by every Python reader. The `audit_config` (D2) and `dev_server` (D1) registry rows now move like the others.

R1c-2 is split once more (operator instruction 2026-11-28, "just push through": the implementer decides).
- **R1c-2 (this PR)** covers the JOINS: work-list items (a), (b) for every use that joins a root, (c), and the D1/D2 row flips.
- **R1c-3** keeps the remaining frozen names. These are used as git pathspecs, as path-pattern sets (allowlists, bookkeeping lists, sensitive-path regexes, change-type patterns, snapshot sets) and in messages. R1c-3 also takes item (d)'s `rel()`-points-at-the-new-place test and the carrier decision of item (f).

The two halves have different risks. A join decides where a file is READ or WRITTEN. A pathspec or set decides which paths a gate or classifier RECOGNISES, and needs the both-layouts helper `all_known_rels()` and per-commit `rel_at()` reasoning.

## Design
1. **Codemod for constant joins.** An AST codemod rewrote 58 joins `<root> / CONST` into `_sp.path("<key>", <root>)`. It covered every module-level `CONST = <sp>.rel("<moving key>")`, in the defining module and in every module that imports the name (`from m import CONST`). Same key, same root expression. It printed every rewrite (`codemod_r1c2.py`, scratchpad). Four importer modules had no resolver binding in scope (`orchestrator_pkg/config_io.py`, `dev_server/state.py`, `rebuild_adr_collision_baseline.py`, `verifiers/_iterate_run_id.py`). Each gained the import its package already uses (`shipwright_paths` / `lib.shipwright_paths`; one object since R1a).
2. **The planning-dir session config is not the root file.** `shipwright-plan/scripts/lib/config.py` joins `planning_dir / SESSION_CONFIG_NAME`. That is a file of that NAME inside a planning dir, so it now uses `_sp.name("plan_config")` and is not routed.
3. **Key lists.** Lists of root names that were joined in a loop now hold registry keys and resolve each through `path()`: adopt `REQUIRED_CONFIGS` (two modules), `_HONESTY_ARTIFACTS`, `setup_adopt`'s new `_EXISTING_CONFIG_KEYS`, and the shared `lib.config.CONFIG_KEYS` and compliance `collectors._common.CONFIG_KEYS` next to `CONFIG_FILES`. Messages still name `_sp.rel(key)`. The event log entries stay plain root joins, because the event log does not move.
4. **Guarded fallbacks (item a).** The hook and gate fallbacks for a stale shared cache are rewritten from `root / ("<lit>" if _sp is None else _sp.rel(key))` to `root / "<lit>" if _sp is None else _sp.path(key, root)`. The three module constants that held such a fallback name (`session_start_using_shipwright.CONFIG_NAME`, `master_stop_check.CONFIG_NAME`, `security_gate.CONFIG_FILENAME`) are inlined at their one use. The literal stays the LEGACY root name, because a cache older than the resolver predates every move. `test_shipwright_paths_fallbacks.py` recognises the join shape when both sides use the same root (with or without `Path(...)` around it) and still checks that each literal equals `legacy_rel(key)`. The grade plugin's two event-log fallbacks are untouched (the event log stays).
5. **Indirect joins (item c).** The test-gate escape check (`_test_gate_paths._safe_project_file` / `_project_file_or_escape`) gets `path(...).relative_to(root)`, the location in whichever layout. The symlink-escape check then runs on the file that is actually read. `merge_boundary_coverage --target` defaults to `_sp.path("test_results", ".")`, which is still cwd-relative. `compliance_report.py:133` and `fold_events.py` concern the event log only, so they are unchanged.
6. **Row flips (D1, D2).** `audit_config` moves to `.shipwright/config/` and `dev_server` to `.shipwright/runtime/`. Their readers already call `path()` (`audit_detector.load_audit_config`, `dev_server.state`). In an unmigrated repo both resolve to the root as before. `change_type_paths`' `rel("audit_config")` patterns are R1c-3.
7. **Plan-review fixes (opus).** Five more readers/writers that the first guard could not see now resolve through `path()`: `profile_consumer.config_profile` (a parameter DEFAULT `filename=RUN_CONFIG` joined with `os.path.join`; it now takes a registry key and rejects a file name with a clear error; all 9 callers were checked, `setup-design-session` passes `"project_config"`); `anti_ratchet_check` and `group_h` (`root / _bb.BASELINE_FILENAME`, a module attribute; `bloat_baseline._baseline_path` became the public `baseline_path`); `fr_split` (plan keyed by the resolved relative path, so the stale check and the write hit the file that was read); `compliance_input_state.producer_inputs` (the compliance config where it lives). `security_gate.load_threshold` resolves inside its `try` and reads a `LayoutError` (matched by class name, one class per tree) as zero tolerance, so two copies can never let a deploy through the hook's fail-open wrapper. `merge_boundary_coverage --target` resolves after parsing (an explicit `--target` no longer touches the default). `config_io` takes `_sp` from `.constants`.
8. **Guard.** The new `test_shipwright_paths_constant_joins.py` fails on any `<x> / NAME` where NAME is bound to `rel()`/`legacy_rel()` of a MOVING key, in the defining module or in a module that imports it. It also sees a module alias (`root / _bb.NAME`), `/=`, `os.path.join`, `Path(a, b)`, `joinpath`, a binding behind a stale-cache `IfExp` or a `Path()`/`str()` wrapper or `name()`, a binding inside module-level `try`/`if`, and a parameter default that the function joins (a default used only as a message label is allowed). Each shape has a positive control. One allowlisted file: the plan plugin's planning-dir session config. The guard's class-8 rule counts `path()` inside a git-reading function only when it sits in the arguments of a git or blob call; elsewhere in such a function it is the working-tree leg next to a `rel_at()` git read (`ci_supplychain_ack_store._read_legacy`). A positive control pins a `path()`-derived git argument (external plan review). The `rel-join-fallback` allowlist shrinks to the two event-log files. The constants inventory shrinks from 80 to 73 entries and the cap is lowered to match.

## Acceptance Criteria
- [x] AC1: No production module joins a root to a frozen name of a moving file. This holds in the defining module and in importers, and a guard with a positive control pins it.
- [x] AC2: Every rewritten reader or writer finds a moving file in its new place. Config readers, a baseline reader, three path helpers, the dev-server writer, a config writer (no root copy created), the stack-profile reader and the security gate's threshold are driven with the file only in the new place. The test fails on the pre-change code (negative control: all 11 cases of `test_shipwright_paths_moved_layout.py` fail on the pre-change tree, the hook integration case included).
- [x] AC3: Stale-cache fallbacks still name the legacy root file and resolve through `path()` when the resolver is there. They are checked by the fallback scan and by a hidden-resolver run of the session hook.
- [x] AC4: `audit_config` and `dev_server` move (`new_rel` set). An unmigrated repo resolves them at the root as before.
- [x] AC5: Two copies of a routed file stop the reader with `LayoutError("both_copies")`; the security gate reads them as zero tolerance instead (never fails open).
- [x] AC7 (integration): the real SessionStart hook, run as its own process, recognises a project whose run config is only in `.shipwright/config/`.
- [x] AC6: The constants inventory only shrinks (80 to 73), and the unmigrated behaviour is unchanged (full F0 suite).

**Pre-build AC record (Step 2a):** none was written, as in R1a to R1c-1. This is a catalog gap on FR-01.11.

## Spec Impact
- **NONE.** Nothing creates `.shipwright/config/` or `.shipwright/runtime/shipwright_dev_server.json` yet, so every existing project reads and writes exactly the files it did before, with the same result. The new branches only fire in layouts that R3 creates. One cost is not byte-for-byte (doubt review): `path("run_config")` reads the first 2 KiB of the root run config to rule out a pointer stub (R1c-1's lookup), so sites that only checked existence (the SessionStart, UserPromptSubmit and Stop hooks among them) now open the file briefly. On Windows an `os.replace` onto the run config during that read hits a sharing violation, which every run-config writer already retries (`atomic_write.replace_retrying`, its budget exists for exactly this). Accepted; whether to skip the stub check while no new copy exists is R1e's call (it would hide `incomplete_migration`).

## Out of Scope (R1c-3 and later)
- Frozen names used as git pathspecs, path sets, regexes and messages (73 inventory entries remain). R1c-3 decides `all_known_rels()` versus `rel_at()` per use.
- The test that points `rel()` at the new place and runs the basename consumers (12.2, item d).
- Carriers (item f): bash, YAML, prompts.
- Hook-by-hook `LayoutError` handling (R1e). The broad handlers among the rewritten modules are listed in BRIEF 12.12 (c) as an R1e precondition before the next release.
- **Safety window:** the "no release, no R2 dry run, nothing creates the new places" window of BRIEF 12.11 (d) now runs until R1c-3 merges (BRIEF 12.12 (b)).
- A writer with neither copy present writes the root, also for `dev_server` (R1c-1 state table); first creation in the new place is R3's job.

## Affected Boundaries
The read/write location of every moving root file in about 60 modules. Five hooks: `generate_handoff_on_stop`, `session_start_using_shipwright`, `suggest_iterate`, `required_checks_state`, `master_stop_check` (plus `iterate_worktree_gate`). The resolver registry, for the two row flips.

## Confidence Calibration
- **Boundaries touched:** the read/write location of every moving root file behind about 60 modules (all through `path()`); six hooks; the resolver registry (two row flips); the guard and fallback scans.
- **Empirical probes run:**
  1. A usage survey of the 80 inventoried constants, then an AST codemod that printed each of its 58 rewrites.
  2. A negative control: `test_shipwright_paths_moved_layout.py` on the pre-change tree, 11 of 11 cases fail (the hook subprocess case included).
  3. The internal plan review found five readers the first guard could not see (parameter default, module attribute, plan-keyed writes, producer inputs) plus the security-gate fail-open; each was fixed and the guard was extended to the shape, with a positive control.
  4. An audit of broad `except Exception` handlers in the rewritten modules (BRIEF 12.12 (c)).
  5. A full F0 run.
- **Test Completeness Ledger:**

| Behavior | Status | Evidence |
|---|---|---|
| AC1 no root join of a frozen moving name (defining module, importer, module alias, `/=`, `os.path.join`, `Path(a,b)`, `joinpath`, wrappers, IfExp/try/if bindings, joined parameter defaults) | tested | test_shipwright_paths_constant_joins.py (production scan + shape controls + label-default negative case) |
| AC2 readers and writers find the file in the new place | tested | test_shipwright_paths_moved_layout.py (config readers, baseline reader, 3 path helpers, dev-server production writer, config writer creates no root copy, stack profile) |
| AC3 stale-cache fallbacks name the legacy file and resolve through `path()` | tested | test_shipwright_paths_fallbacks.py (join shape scan, hidden-resolver session hook run) |
| AC4 `audit_config` / `dev_server` move; unmigrated resolves at the root | tested | test_shipwright_paths_identity.py::test_known_locations, moved-layout dev-server case |
| AC5 two copies stop a routed reader; the security gate reads them as zero tolerance | tested | ::test_two_copies_stop_a_routed_reader, ::test_the_security_gate_reads_the_new_place_and_never_widens_on_two_copies |
| AC6 inventory 80 -> 73, unmigrated behaviour unchanged | tested | test_shipwright_paths_guard.py (cap 73), full F0 suite |
| AC7 integration: the real SessionStart hook as its own process recognises a moved project | tested | ::test_the_session_start_hook_recognises_a_moved_project (fails on the pre-change hook) |
| safety window: nothing names the new config folder or the D1 dev-server file | tested | test_shipwright_layout.py::test_no_production_code_writes_the_new_place_before_r3 |

- **Confidence-pattern check:**
  - **Depth.** Each case drives the real module function with real files, not a mock of `path()`.
  - **Breadth.** Readers, writers, path helpers, a deploy gate and a hook are each covered; the guard is proven against every join shape it claims.
  - **Integration composition.** The diff touches `hooks/*.py` (cross_component), so the real SessionStart hook runs as a subprocess against the real resolver, and the negative control fails on the old hook.

## End-to-End Verification
- **Surface:** cli
- **Runner:** pytest over the resolver, guard, fallback, moved-layout and layout test files. Evidence: `.shipwright/runs/iterate-2026-11-28-r1c2-frozen-names/surface_verification.json`.

## Internal Plan Review (opus-plan-reviewer)
Severity high (2), medium (5), low (5). Fixed: the security gate let a deploy through on two copies (path() moved into the try, LayoutError = zero tolerance); `profile_consumer.config_profile` (frozen parameter default joined with `os.path.join`); `anti_ratchet_check` and `group_h` (module-attribute joins of the bloat baseline); `fr_split` (plan keyed by the resolved path); `compliance_input_state.producer_inputs`; the `merge_boundary_coverage` default resolved after parsing; the class-8 `path()` exemption scoped to non-git arguments; `config_io` imports `_sp` from `.constants`; the guard extended to every shape named. Recorded for later (BRIEF 12.12): the R1e LayoutError list (rtm_gate_support, events_layout/events_sentinel, audit_detector), the dev-server delete-not-copy recommendation for R3, message sites and `CONFIG_MARKERS` for R1c-3.

## Internal Architecture Review (architecture-internal-reviewer)
Verdict: build it, option 1; the split into joins now and sets/pathspecs in R1c-3 is sound; the D1/D2 flips are safe. Addressed: the safety window now explicitly runs until R1c-3 merges (BRIEF 12.12 (b)); the LayoutError surface in gates is an R1e precondition before the next release, with a named list (12.12 (c)); dev-server "nothing running" for R3 and the dangling-symlink note (12.12 (d)); the class-8 exemption is tied to git arguments, with a control; plan `config.py` is recorded as a deletion candidate.

## Architecture Review
External (`--mode architecture`): GPT approve, no findings; GLM approve, one low (allowlist edits must cite a reason; the one `ALLOWED` entry carries one).

## External Plan Review
GPT revise (3 medium): the class-8 exemption was too broad (FIXED, control added); dev-server first creation with both copies absent (by design: it writes the root until R3, now stated in Out of Scope); a symlinked parent of the new place (recorded for R3). GLM approve: codemod and guard share one static model (answered by the behavioural moved-layout test with its negative control); a `"."` root (path() treats a relative root like an absolute one); the inlined constants had no other users (grep); `relative_to` cannot fail because path() always returns a path under the root.

## External Code Review
GPT revise, GLM approve. Fixed: `config_profile` rejects a file name with a clear error (all 9 callers checked); the security gate matches LayoutError by class name; the dev-server case drives the production writer `_save_state_atomic`. Recorded: local-variable git arguments, unaliased `import pkg.mod`, `from m import *`, loop bindings (guard blind spots, BRIEF 12.12 (c)); `compliance_input_state` on the R1e list. `merge_boundary_coverage`: with neither copy present `path()` returns the root path, so "created if missing" holds; `_baseline_path` had no other users.

## Code Review (Stage 2)
APPROVE, no critical or high. Fixed: `fr_split` resolves each path once. Recorded: dict/tuple-constant joins as a guard blind spot and the CONFIG_FILES/CONFIG_KEYS duplication (R1c-3); readers documented as never raising (gate_policy, phase_invocation_mode, project_facts) and five lower-stakes readers on the R1e list; the leaf-only symlink check in iterate_test_results for R3; the ratchet wording corrected. Accepted as cosmetic: redundant parentheses, `_HONESTY_ARTIFACTS` mixing keys and paths, the dev_server import style.

## Doubt Review (Stage 3)
Four low doubts. Fixed: class-8 sees `subprocess.run(["git", ...path()...])`; the joins guard unwraps `Path()`/`str()`/f-string at the use site; the safety-window pin names the D1 dev-server file. Accepted with rebuttal (Spec Impact): the 2 KiB stub check now opens the root run config at existence-only sites; writers retry the Windows sharing violation.

## Tier-3 PR Review (PR #1128)
BLOCK, fixed in a second commit: the three readers documented as never raising (`gate_policy`, `phase_invocation_mode`, `project_facts`) now catch `LayoutError` by type and return their safe value or a structured error (test with two copies); the security gate catches by type and lets an unrelated error through (test); the handoff assertion pins the exact branch per file. Not changed: committed review records are the pipeline's evidence by design (F6 stages the run directory; `reviews.json` is what F11 and the Tier-3 tier decision read).
