# Iterate spec — Backfill plugin/shared @FR tags + config-aware TT5 gate

- **run_id:** `iterate-2026-07-17-backfill-plugin-fr-tags`
- **Intent:** change (framework traceability retrofit + enforcement-path correctness)
- **Complexity:** medium (history-calibrated; gate change + shared-engine change)
- **Spec Impact:** NONE (FR-gate `change_type: compliance`, mirroring #387) — traceability/
  compliance INFRASTRUCTURE: the TT5 enforcement gate's internal scan-scope changes and
  `@FR` traceability data is added, but **no product FR's observable behaviour** changes and
  no `spec.md` FR row is touched. (The internal gate behaviour does change — hence the full
  review rigor — but for the ADR-059 FR-gate this is the No-FR/compliance branch.)
- **Brief:** `.shipwright/planning/iterate/iterate-backfill-plugin-fr-tags-BRIEF.md` (ordered STEP 1)
- **Data:** campaign `2026-07-15-test-traceability-layers/TT8-coverage-delta.md`

## Goal (plain language)

Plugin and shared tests now carry machine-readable `@FR` tags that say which requirement
each test verifies — the same traceability the product tests already have. And the hard
"did you test the changed requirement at every required layer?" gate is taught to look in
the plugin/shared test folders the project opted into, so a requirement covered only by a
plugin test is no longer wrongly reported as untested.

## Scope

### Task A — write the high-confidence `@FR` tags (data)
Re-run the shared backfill engine (`backfill_test_links`) over the full corpus
(`integration-tests/ + plugins/ + shared/`) and let it auto-write the deterministic,
high-confidence tags into the test files. Expected ≈187 (28× FR-01.06, 7× FR-01.09,
61× FR-01.11, 13× FR-01.13, 78× FR-01.14). The regenerated count is authoritative; any
delta from 187 is documented. **Invariants:** no fixture data file is touched
(byte-stable); after a manifest regen `orphans == []` (D-orphan stays 0 — every tag maps
to an ACTIVE FR).

### Task A-prereq (BLOCKER discovered) — engine can't scan inside the iterate worktree
`backfill_scan.iter_test_files` prunes on `path.parts` (ancestors included). Every iterate
runs in `.worktrees/<slug>/`, and `.worktrees` is a pruned name, so **every** test file is
false-pruned → the engine scans 0 tests in the worktree. Fix: prune on the *in-tree* parts
(`path.relative_to(base).parts`), mirroring the collector's descent-prune intent. Byte-
identical output for a main-root scan (adopt/TT7); fixes the worktree case.

### Task B — decide the 24 low-confidence proposals myself (not a human gate)
Leave untagged when uncertain (untagged is safe; a wrong tag = phantom orphan = group_d
red). Tag only where my own analysis is confident. Document each call in the PR body.

### Task C — thread config into the TT5 enforcing gate
`_layer_coverage_regen._build` hardcodes `test_roots=io.default_test_roots(root)` and passes
no `prune_dirs` → config-blind. Thread `io.configured_test_roots(root)` /
`io.configured_prune_dirs(root)` (mirror `test_links.generate_file`). Base-side asymmetry:
a base commit predating the `traceability` config has no key → `configured_test_roots`
already falls back to `default_test_roots` (verified on the archived base by the new test).

### Marker registration
Register the `covers` pytest marker in the `shipwright-iterate` / `shipwright-test` /
`shipwright-adopt` pyprojects (they receive tags but don't register it; root + compliance
already do). No `--strict-markers`/`filterwarnings=error` today, so this only silences
`PytestUnknownMarkWarning` and future-proofs a strict flip — but it is the correct home.

## Non-goals / explicit exclusions
- Do **not** hand-commit the regenerated `test-traceability.json` (tracked churn artifact;
  regenerates naturally, canon allowlist keeps it green; a hand-commit fans a churn cascade
  across the parallel worktrees). Regenerate only to VERIFY `orphans == []`, then restore.
- STEP 2 (test-rot cleanup) and STEP 3 (FR-unmapped review) are separate, not this iterate.

## Mini-plan + alternative considered
**Chosen:** fix the engine scan (relative-parts prune) → run engine → write tags → thread
config into the gate → add a base/head asymmetry integration test. One atomic F6.

**Alternative (rejected):** run the engine from the main root (no `.worktrees` ancestor) and
copy the writes into the worktree. Rejected: pollutes the `main` working tree (breaks
worktree isolation), and the brief forbids hand-copying — "regenerate, do not hand-copy."

## Affected Boundaries
- `shipwright_compliance_config.json` — `traceability.test_roots` / `exclude_dirs` (consumed
  by the gate now, not just `generate_file`). Read-only consumer; existing fallback semantics.
- Test files under `plugins/*/tests` + `shared/tests` (tag insertions).
- `git archive` base/head trees (the gate resolves config from each side's own tree).

## Outcome (Task A / B)
- **Task A:** the engine (post-scan-fix) auto-wrote **189** deterministic (`unique_commit`)
  tags into **16** files: 108 `shared/tests`, 33 `shipwright-iterate`, 33 `shipwright-test`,
  **15** `shipwright-adopt`. The +2 vs the briefed 187 is entirely **FR-01.13 in
  shipwright-adopt** (13→15 — two adopt tests added since the TT8 snapshot). Verified: **0**
  tags under any `fixtures/` path (byte-stable), all map to ACTIVE FR-01.xx, and a manifest
  regen (config-driven, fixtures excluded) shows **`orphans == []`** (D-orphan = 0). FR
  breakdown: 28× FR-01.06, 7× FR-01.09, 61× FR-01.11, 15× FR-01.13, 78× FR-01.14.
- **Task B (24 low-confidence — all LEFT UNTAGGED, documented):** every one is a multi-FR
  `commit_set` at 0.4 (the introducing commit touched several FRs), i.e. genuinely ambiguous:
  - 10× `integration-tests/test_fr_table_drift_protection.py` (FR-01.10 compliance vs FR-01.13
    adopt) — a **dual-parser** drift test spanning both parsers; no single owner → untagged.
  - 11× `plugins/shipwright-iterate/tests/test_hooks_json_registration.py` (4-way
    run/project/iterate/adopt) — the **cross-plugin phase-router** hook; too diffuse → untagged.
  - 2× `shared/tests/test_hooks_json_quoting.py` (13-way, all plugins) — an **all-plugins**
    hooks-quoting invariant; maps to no single FR → untagged.
  Untagged is the safe default (a wrong tag mis-credits coverage); a human may veto later.

## Design decision (from review) — enforcing gate scans a SUPERSET of generate_file
Task C threads config into the gate, but does NOT purely mirror `generate_file` (which uses
pure REPLACE for the RTM). The **enforcing** gate additionally floors at `default_test_roots`
and re-scans the base manifest's test dirs (`_base_test_dirs` → `extra_roots`, head only).
Rationale: `configured_test_roots` REPLACE-semantics + per-tree config resolution let a config
that narrows (below defaults, or between base and head) starve the **removal** gate → a removed
FR's still-tagged test escapes (false-green). An enforcing gate must be fail-closed: it treats a
`@FR` tag on a removed FR as rot wherever it lives, not only inside the current configured scope.
The RTM stays visibility-only (pure REPLACE); only the gate needs the floor + monotonic re-scan.
Trade-off accepted: a tag deliberately placed outside `traceability.test_roots` is still enforced
by the gate (a dead tag is a dead tag) — the fail-closed posture is correct for an enforcing gate.
**Documented residual (accepted):** a test moved via a NON-git-detected delete+re-add into a new
non-default dir, combined WITH removing its FR AND dropping the config, all in ONE commit, would
still escape (git rename detection covers the detected-move case). This is a quintuple-adversarial
dodge that was 100% invisible pre-Task-C (the gate never scanned plugin dirs at all) and produces a
massive, non-silent diff — consistent with the removal evaluator's existing documented residual
(`_layer_coverage_removal.py`: "a move that ALSO renames the function AND evades git detection").

## Confidence Calibration
- **Boundaries touched:** `shipwright_compliance_config.json` consumer moved into the enforcing
  gate (`_layer_coverage_regen._build`); the `git archive` base/head temp trees; the
  worktree-nested scan root (`backfill_scan.iter_test_files`); 189 `@FR` tag insertions.
- **Empirical probes run:**
  - Engine scanned **0** tests inside `.worktrees/<slug>/` before the prune fix → **7438** after
    (confirmed the ancestor-prune root cause with a direct `path.parts` check).
  - Full-corpus dry-run BEFORE writing: 189 auto-writes, **0** under `/fixtures/`, all
    `unique_commit`, all active FR-01.xx (inspected the report JSON, not trusted).
  - After write: `git status` = only 16 test files + 7 `import pytest`; **0** fixture files;
    189 `@pytest.mark.covers` added; the only deletions are my `backfill_scan` comment edit.
  - Manifest regen → `orphans == 0`, 192 links (189 new + 3 pre-existing); restored (not committed).
  - Both gate-fix regression tests PROVEN load-bearing (temporarily reverted the union and the
    monotonic re-scan → each target test went RED with the exact false-green, then restored).
- **Test Completeness Ledger:**
  | Behaviour | Disposition | Evidence |
  |---|---|---|
  | Engine scans a repo nested under a prune-named ancestor (worktree) | tested | `test_iter_test_files_scans_a_repo_nested_under_a_prune_named_ancestor` |
  | In-tree `node_modules`/`__pycache__` still pruned | tested | same test (asserts no `node_modules`) |
  | Gate sees config-opted plugin-dir coverage (base predates config) | tested | `test_gate_sees_plugin_dir_coverage_when_head_opts_it_in` |
  | Gate misses plugin coverage without config (load-bearing control) | tested | `test_gate_misses_plugin_dir_coverage_without_config_load_bearing` |
  | Union floor: narrowing config can't false-green the removal gate | tested | `test_removal_gate_keeps_default_floor_when_config_narrows` |
  | Monotonic re-scan: head dropping config can't false-green removal | tested | `test_removal_gate_rescans_base_dirs_when_head_drops_the_config` |
  | Rename-target re-scan: a test moved to a NEW dir + FR removed + config dropped can't false-green | tested | `test_removal_gate_follows_a_renamed_test_into_a_new_dir_when_config_drops` |
  | `exclude_dirs` load-bearing: a fixture-path test can't fake a required layer | tested | `test_gate_excludes_fixture_path_so_a_fixture_cannot_fake_a_layer` |
  | 189 tags written / plugin-dir tag round-trips into manifest w/ 0 orphans | tested | existing `test_plugin_dir_tagged_test_round_trips_and_fixtures_are_fenced` + manual regen (orphans==0) |
  | `covers` marker registered so tagged tests don't warn | untestable (`covered-by-existing-test`) | pyproject config; exercised by collecting the tagged suites (all green) |
  | 24 low-confidence left untagged | n/a | no-op (safe default); reasoned in Outcome above |
  0 untested-testable behaviours.
- **Confidence-pattern check:** asymptote (depth) — the two false-green classes the reviews
  surfaced are BOTH closed, each with a revert-proven regression test. Coverage (breadth) —
  worktree-scan, config-opt-in, both narrowing axes, and the round-trip all have tests.
  Integration composition — the base/head `git archive` → collector → gate pipeline is
  exercised on REAL git by `test_layer_coverage_config_scope` + `_gate_integration` (a
  `category:"integration"` proof the pieces compose).
