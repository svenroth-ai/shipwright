# Iterate Spec: tag-gate collector gaps (shared lexer, head-config roots, export-ignore)

- **Run ID:** iterate-2026-10-09-tag-gate-collector-gaps
- **Type:** change
- **Complexity:** small (scope dictated by the operator brief; planning-stage reviews not run, disclosed)
- **Status:** built

## Goal
Close the three gaps PR 861 (`iterate-2026-10-08-tag-gate-followup`) listed under Out of Scope: the compliance collector
could not close a wrapped `.each` table that holds a regex literal or JSX text, a test folder named only by the head config,
and files `.gitattributes export-ignore` drops from the archived head.

## Acceptance Criteria
- [x] A wrapped `it.each([...])('title', ...)` whose table holds `/it's/`, `/a(b/` or JSX text with a quote or paren is folded by the
      collector and enumerated as one test; an untagged one added by a diff fails `check_test_tag_binding` with `untagged-added`.
      The collector and the gate use ONE lexer (`lib/ts_lexer.py`, moved from `tools/verifiers/_tag_binding_ts_lex.py`).
- [x] A new test folder named only by the head `traceability.test_roots` (plain, glob, added to or replacing a base config) is seen.
      Measured: already true on `main` (the union floor plus head `configured_test_roots`); pinned by regression tests, no code change.
- [x] A test under a path `.gitattributes` marks `export-ignore` is part of the head (and base) tree the gate scans: the tree is
      materialised from `git ls-tree` + `git cat-file` instead of `git archive`. Regular files, plus a symlink whose relative target is a regular file in the same tree (written as a copy,
      as the old tar extraction did, so a symlinked test cannot hide from the gate); links that leave the tree, directory
      links and submodules stay out.

## Spec Impact
- **Classification:** modify
- **MODIFY:** FR-01.11 AC42 - wrapped case tables and export-ignored folders.

## Out of Scope
Mark reorder digests and the unmeasured quadratic `.each` search (reopen if observed). A `/` after `)` read as division, table
caps (400 lines collector / 20000 chars gate) are unchanged.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `lib/ts_lexer.lex` | `_file_tags._each_end` (collector), `_tag_binding_ts` (gate) | token list + index of the closing bracket |
| `_layer_coverage_regen._archive_tree` | `build_manifest` (collector), rollout gate | directory of tracked regular files |

## Confidence Calibration
- **Boundaries touched:** lexer sharing across plugin/shared; tree materialisation used by the removal, cross-layer, rollout and tag gates.
- **Empirical probes run:** `test_tag_binding_collector_gaps.py` (real git + real collector, 11 cases; 5 failed before the change);
  458 shared tests touching the regen code, full compliance suite (1974 passed), ruff.
- **Test Completeness Ledger:** recorded at F5 (`iterate_latest.test_completeness`).
- **Confidence-pattern check:** each fix has a test that fails on the old behaviour; gap 2 test passes on old code and says so.
