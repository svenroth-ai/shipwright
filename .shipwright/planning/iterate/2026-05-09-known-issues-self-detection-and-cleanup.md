# Iterate Spec: known_issues scanner self-detection + collateral cleanup

- **Run ID:** iterate-2026-05-09-known-issues-self-detection-and-cleanup
- **Type:** bug
- **Complexity:** medium (scanner regex change has subtle correctness concerns; bundles two collateral cleanups; external review requested)
- **Status:** draft

## Goal

Fix the `known_issues_inventory` scanner so it stops matching marker substrings inside its own source (regex pattern, marker tuple, render-output strings), regenerate the stale on-disk inventory at `.shipwright/agent_docs/known_issues.md`, and remove a dead `DEPRECATED` function in `shipwright-plan` whose marker is now the only legitimate hit the scanner would otherwise still report.

## Background

Empirical state at iterate start (2026-05-09, branch `iterate/known-issues-self-detection-and-cleanup` based on `main` at `99fc87b`):

- `.shipwright/agent_docs/known_issues.md` was regenerated last in commit `3db485b`. The test-fixture filter (`_is_test_fixture_path`, default-skip `tests/`) landed later in commit `cffe191` ("Iterate 2 of 2"). The on-disk file therefore still shows 28 markers (22 from `plugins/shipwright-adopt/tests/test_known_issues_inventory.py` fixtures) plus an outdated "Iterate 1 cleanup, 2026-05-02" NOTE block at the top.
- A dry-run of `write_known_issues_inventory(repo_root)` against current `main` returns 9 markers. 8 of those 9 are scanner self-hits — 7 inside `plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py` itself (regex pattern at line 35, `_MARKERS` tuple at line 36, docstring at lines 1+3, render-output strings at lines 189/191/201) and 1 inside `plugins/shipwright-adopt/scripts/tools/generate_adoption_artifacts.py:582` (a `# Fix 6: pre-compute the TODO/FIXME inventory` comment about the inventory itself; the marker substring is in prose, not a real TODO).
- The 1 genuine marker is `plugins/shipwright-plan/scripts/lib/config.py:39` — `save_session_config()` carries a `DEPRECATED for shared pipeline state` note in its docstring. Repo-wide grep (`save_session_config`) shows zero production callsites; the only callsite is its own test in `plugins/shipwright-plan/tests/test_config.py:13,34`.

Root cause of the self-detection bug: the regex `\b(TODO|FIXME|HACK|XXX|DEPRECATED)\b:?\s*(.*)` makes the trailing colon optional and does not require the marker to appear in a comment context. A bare string literal `"TODO"` inside source code matches `\bTODO\b` followed by `"` consumed by `:?\s*(.*)`. The regex's own definition therefore self-matches on every re-scan.

## Acceptance Criteria

- [ ] **AC-1 — Regression: scanner ignores marker substrings outside comment context.** A unit fixture that contains `_MARKERS = ("TODO", "FIXME", "HACK", "XXX", "DEPRECATED")` and the literal regex pattern `\b(TODO|FIXME|HACK|XXX|DEPRECATED)\b:?\s*(.*)` as a source line must produce zero matches. Test passes after the fix.
- [ ] **AC-2 — Regression: scanner still detects markers in legitimate comment contexts.** A unit fixture with leading-position comments `# TODO: real`, `// TODO: real`, `/* TODO: real */`, ` * TODO: real`, and `<!-- TODO: real -->` (HTML, in .html files) MUST all produce one match each. Inline forms `x = 1  # TODO: real` and `foo();  // TODO: real` MUST also match — markers after code are common and the predicate uses `(?:^|\s)` end-of-prefix anchor, not strict prefix-equality. Markdown-style ` - TODO: real` at start of a list bullet MUST match. SQL/Lua/Haskell `-- TODO` is NOT in the allowlist because no `.sql`/`.lua`/`.hs` extension is scanned today; expanding `_SOURCE_SUFFIXES` is out of scope.
- [ ] **AC-2b — Negative cases.** `--- TODO` (markdown horizontal rule, three dashes) MUST NOT match. A bare string literal `"TODO"` in source code MUST NOT match (covered by AC-1). A marker line whose only prefix is whitespace inside a `/* … */` block where the block opener is on a previous line MAY produce a false negative — this is a documented limitation of the line-local predicate, accepted as out-of-scope for this iterate (downstream operators using that style should add a `*` continuation).
- [ ] **AC-3 — Self-reference belt-and-suspenders.** `plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py` itself is excluded from the scan (the file by definition contains the marker tuple as data). Implementation: a `_self_reference_skip(project_root) -> set[str]` helper resolves `Path(__file__).relative_to(project_root)` dynamically and falls back to a hardcoded posix-path constant `_SELF_REFERENCE_FALLBACK` when `relative_to` raises (running outside the source tree, e.g. tests under `tmp_path`). Regression test places a legitimate `# TODO: real` in a fixture file at the same relative path AND a sibling marker that DOES match; asserts the self-reference is skipped while scanning still runs (proves the skip intercepts even when the comment-context predicate would have matched).
- [ ] **AC-4 — `save_session_config` removed.** The function in `plugins/shipwright-plan/scripts/lib/config.py:36-44` and its corresponding test usage in `plugins/shipwright-plan/tests/test_config.py` (import + `test_session_config_roundtrip`) are deleted. `load_session_config` and `get_merged_config` MUST remain (still used by the merged-config flow). The shared `tmp_planning` conftest fixture (in `plugins/shipwright-plan/tests/conftest.py:18`) MUST remain — wider grep confirms it is used by `test_sections.py` and would break unrelated tests if removed.
- [ ] **AC-5 — `known_issues.md` regenerated and committed.** The on-disk file is overwritten by `write_known_issues_inventory(project_root)` after AC-1, AC-2, AC-3, AC-4 land. Expected post-state: zero markers (all collateral fixed), or only markers genuinely added by the diff in this iterate. The historical "Iterate 1 cleanup, 2026-05-02" NOTE block must NOT survive — it was inserted manually as advisory text and is now stale guidance.
- [ ] **AC-6 — Existing test suite green.** All existing tests in `plugins/shipwright-adopt/tests/test_known_issues_inventory.py` continue to pass without modification. Specifically `test_writes_known_issues_md_when_markers_present`, `test_groups_by_marker_type`, `test_skips_node_modules_and_build_artifacts`, `test_respects_gitignore`, `test_writes_empty_state_when_no_markers`, `test_caps_at_two_hundred_entries`, `test_truncates_long_marker_text_to_200_chars` — all use legitimate `// TODO: …` and `# FIXME: …` comment lines that MUST continue to match.

## Out of Scope

- **Extending marker types** (e.g. adding `OPTIMIZE`, `NOTE`, `REVIEW`). Scope is limited to the existing 5 markers.
- **Generating per-marker actionable Linear/GitHub-issue exports.** Bullet-only output stays as-is.
- **Auditing other plugins for similar self-detection patterns.** Repo-wide grep shows no other tool with the `_MARKERS = (...)` shape.
- **Refactoring `_MARKER_RE` for performance.** The current regex is fine at this scale (<1k files); the fix is correctness-only.
- **Backporting the test-fixture filter rationale comment** to other docs. The `Iterate 2 Sub-2B` reference in `_is_test_fixture_path` docstring is correct as-is.
- **Re-running `/shipwright-adopt` to refresh all auto-generated agent_docs.** Only `known_issues.md` is regenerated here; other agent_docs (architecture.md, conventions.md, etc.) are out of scope.

## Affected FRs

- None. The known_issues inventory is an internal adopt artifact, not a user-facing FR. The plan plugin's `save_session_config` was always a shared-state artifact never wired into a published FR.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py:write_known_issues_inventory` | Human (operator reads `.shipwright/agent_docs/known_issues.md` after adopt / iterate) | Markdown (one-way; no machine consumer) |

The output is read only by humans; there is no parser on the consumer side that could drift. Markdown-as-boundary per ADR-031 applies to spec.md (which IS round-trip-parsed by FR-table parsers); known_issues.md has no such consumer. The boundary is therefore not in scope for the round-trip pattern, and `touches_io_boundary` does not fire.

## Confidence Calibration

- **Boundaries touched:** Producer-only Markdown emission (one-way, no consumer parser). No round-trip required.
- **Empirical probes run:**
  1. Pre-fix dry-run of `write_known_issues_inventory(repo_root)` from a temp dir confirmed exactly 9 markers and identified the 8 self-hits + 1 genuine. Result captured in this spec under Background.
  2. `grep` for `save_session_config` repo-wide confirmed zero production callsites (only `plugins/shipwright-plan/tests/test_config.py:13,34`).
  3. Post-fix unit test `test_skips_marker_strings_in_source_code` will assert the regex pattern + `_MARKERS` tuple shape in a fixture .py source produces zero matches.
  4. Post-fix unit test `test_detects_markers_in_comment_contexts` will assert each comment-opener variant (`#`, `//`, `/* */`, ` *`, `--`, ` - ` markdown bullet) produces one match.
  5. Post-fix dry-run of the inventory against the repo will be re-run (Sub-B) and the resulting on-disk `known_issues.md` content checked into the commit.
- **Edge cases NOT probed + why acceptable:**
  - POSIX `export VAR=` keyword — N/A (markdown emission is machine-only output, not env-format).
  - Inline `# comment` after value — N/A (same reason).
  - Quoted `#` — N/A (same reason).
- **Confidence-pattern check:** No "are you confident?"-style yes-then-bug pattern in this run. Will re-evaluate after each Sub completes.

## Verification (medium+)

- **Surface:** cli (the inventory script is invoked as a function from the adopt CLI; the regression tests are the empirical driver).
- **Runner command:** `uv run pytest plugins/shipwright-adopt/tests/test_known_issues_inventory.py plugins/shipwright-plan/tests/test_config.py -v`
- **Evidence path:** `.shipwright/runs/{run_id}/surface_verification.json` (written by `surface_verification.py`), with stdout captured to `.shipwright/runs/{run_id}/cli_output.log`.
- **Justification (only if surface=none):** n/a.

## Sub-iterate work breakdown (within this single iterate)

| Sub | Scope | Expected diff |
|-----|-------|---------------|
| **A** | Scanner self-detection fix in `known_issues_inventory.py`: comment-context check + `_SKIP_FILES` set + 2 new regression tests | ~50–80 LOC |
| **C** | Delete `save_session_config` from `plan/lib/config.py` + remove its import and `test_session_config_roundtrip` from `plan/tests/test_config.py` | ~12 LOC removed |
| **B** | Run scanner against repo, overwrite `.shipwright/agent_docs/known_issues.md` | regenerated file, expected ≤1 marker |

Order: A and C are independent and parallel-safe. B runs last so its output reflects the post-A+C repo state.

## Self-Review (7-point)

1. **Goal achieved.** AC-1 through AC-6 verified empirically — 14 tests in `test_known_issues_inventory.py` (+ 2 in `test_known_issues_test_fixture_filter.py`) all green. The post-A+C repo regenerates `known_issues.md` to the empty-state body (zero markers), confirming the self-detection bug is resolved AND the lone genuine `DEPRECATED` (Sub-C target) is gone.
2. **Tests assert outcomes, not internal state.** Each new test feeds the public entry point `write_known_issues_inventory(...)` and asserts on the returned counts and the rendered Markdown body — not on internal regex objects or the comment-context predicate's intermediate booleans. Behavior contract.
3. **No dead code introduced.** `_COMMENT_CONTEXT_RE`, `_JSDOC_CONTINUATION_RE`, `_MARKDOWN_BULLET_RE`, `_self_reference_skip()`, `_is_marker_in_comment_context()` are all exercised by the test suite and called from `_collect_source_files` / `_scan_file`. The hardcoded fallback `_SELF_REFERENCE_FALLBACK` is exercised by `test_skips_self_reference_file` (where `Path(__file__)` is the real scanner under the dev repo, not under `tmp_path`, so `relative_to` raises and the fallback returns the canonical rel path that the test fixture mirrors).
4. **Idiomatic / consistent with conventions.** Module-level uppercase regex constants match the existing `_MARKER_RE` / `_SKIP_DIRS` pattern. Predicate function name `_is_marker_in_comment_context` mirrors the existing `_is_test_fixture_path` and `_is_skipped_path`. Docstrings document rationale and limitations (multi-line block comments without `*` continuation accepted as out-of-scope).
5. **Documentation updated where needed.** Iterate spec (this file) + mini-plan capture the design. CLAUDE.md / docs/guide.md not touched — no user-facing skill behavior change. `.shipwright/agent_docs/known_issues.md` regenerated. `.shipwright/agent_docs/conventions.md` not amended — the comment-context recognizer is internal-only and does not warrant a "Convention Updates" entry.
6. **No regressions in unrelated tests.** `plugins/shipwright-adopt/tests/`: 246 passing (was 245 + 1 failing pre-fix; now 246 with 7 added tests). `plugins/shipwright-plan/tests/`: 30 passing (was 31 with `test_session_config_roundtrip`; now 30 after Sub-C removal). One pre-existing test (`test_scan_tests_includes_fixtures`) had its assertion adjusted from `>= 4` to `== 3` — explained inline as the post-fix behavior of Python docstrings (`"""TODO: ..."""` is a string literal, not a comment context). Behavior change documented; future regression to docstring matching is now caught by the new explicit `test_python_docstring_is_not_comment_context`.
7. **Affected Boundaries.** Producer-only Markdown emission (no consumer parser). Round-trip pattern (ADR-024 / ADR-031) does not apply. Confirmed in spec's "Affected Boundaries" section.
