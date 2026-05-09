# Mini-Plan: known_issues scanner self-detection + cleanup

- **Run ID:** iterate-2026-05-09-known-issues-self-detection-and-cleanup
- **Spec:** `.shipwright/planning/iterate/2026-05-09-known-issues-self-detection-and-cleanup.md`

## Files to change

### Sub-A — Scanner self-detection fix

- `plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py`
  - Replace `_MARKER_RE` with a context-aware match. Concrete approach:
    - Keep `_MARKER_RE` but add a per-line context predicate `_is_marker_in_comment_context(line, match_start)` that walks back from `match_start` through the prefix and returns True only when the prefix matches one of:
      - `#\s*` — Python / shell / Ruby line comment
      - `//\s*` — JS / TS / Java / Go / Rust line comment
      - `/\*+\s*` — C-style block-comment opener
      - `\s*\*\s*` — JSDoc / Javadoc continuation line
      - `--\s*` — SQL / Lua / Haskell line comment
      - `^\s*-+\s*` — Markdown list bullet
      - `^\s*#+\s*` — Markdown heading
      - `<!--\s*` — HTML / Markdown comment
    - This is a positive-allowlist of recognised comment forms. Anything else (a bare string literal, regex literal, tuple element) returns False.
  - Add `_SKIP_FILES = frozenset({"plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py"})` (relative-path keyed). Skip in `_collect_source_files` after `_is_test_fixture_path`.
  - The existing `_is_skipped_path` (directory-level) and `_is_test_fixture_path` (test-shape) stay unchanged.
- `plugins/shipwright-adopt/tests/test_known_issues_inventory.py`
  - Add `test_skips_marker_strings_in_source_code(tmp_path)` — fixture writes a `.py` file containing `_MARKERS = ("TODO", "FIXME", "HACK", "XXX", "DEPRECATED")` and the regex pattern as raw string literals; assert `inv["total"] == 0`.
  - Add `test_detects_markers_in_comment_contexts(tmp_path)` — fixture writes 6 different files exercising `#`, `//`, `/*`, ` *`, `--`, ` - ` (markdown bullet); assert each contributes one marker to the total.
  - Add `test_skips_self_reference_file(tmp_path)` — fixture writes a file at `plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py` (relative path mirroring the real one) containing `# TODO: real`; assert it's skipped via `_SKIP_FILES`. Test relies on the relative-path keying, so the fixture must build the directory tree under tmp_path.

### Sub-C — Remove dead `save_session_config`

- `plugins/shipwright-plan/scripts/lib/config.py`: delete lines 36–44 (the `save_session_config` function).
- `plugins/shipwright-plan/tests/test_config.py`:
  - Remove `save_session_config` from the import block (line 13).
  - Remove `test_session_config_roundtrip` (lines 33–36).
- The `tmp_planning` fixture used by `test_session_config_roundtrip` may have other consumers — check. If unused after removal, also remove the fixture; if still used, leave as-is.

### Sub-B — Regenerate `known_issues.md`

- `.shipwright/agent_docs/known_issues.md`: overwrite via `write_known_issues_inventory(repo_root)`. Expected post-state: `**No TODO / FIXME / HACK / XXX / DEPRECATED markers found in the source.**` empty-state body (zero markers), since A removes all 8 self-hits and C removes the lone genuine DEPRECATED hit.
- Do NOT preserve the manually-added "Iterate 1 cleanup, 2026-05-02" NOTE block — the auto-generated empty-state template is the new canonical content.

## Test strategy

1. **Red phase (Sub-A):** Add the 3 new test cases (`test_skips_marker_strings_in_source_code`, `test_detects_markers_in_comment_contexts`, `test_skips_self_reference_file`). Run the test file — the new tests MUST fail (because the comment-context check + `_SKIP_FILES` are not yet implemented). The 7 existing tests MUST still pass (regression check at red phase too).
2. **Green phase (Sub-A):** Implement `_is_marker_in_comment_context` and `_SKIP_FILES`. Run the test file — all 10 tests pass.
3. **Sub-C:** Delete function + test. Run `plugins/shipwright-plan/tests/test_config.py` — 5 tests pass (was 6, now 5).
4. **Sub-B:** Run a one-shot regeneration script (in-memory invocation of `write_known_issues_inventory`); verify output matches expectations; commit the resulting file.
5. **F0 fresh run:** `uv run pytest plugins/shipwright-adopt/tests/ plugins/shipwright-plan/tests/ -v` — all green.
6. **F0.5 surface verification:** `uv run pytest plugins/shipwright-adopt/tests/test_known_issues_inventory.py plugins/shipwright-plan/tests/test_config.py -v` driven through `surface_verification.py --surface cli`. tests_run > 0, exit 0.

## Alternative considered

**Option B — Tighten the regex itself instead of adding a context predicate.** Make `_MARKER_RE` require the colon (`(?::\s+|\s)` instead of `:?\s*`) so `"TODO"` (with quote suffix) doesn't match. Rejected because: (1) many legitimate comments use `# TODO ` without the colon, and `test_writes_known_issues_md_when_markers_present` would fail without changes — but the existing test fixtures all happen to use `:`, so requiring the colon would be a behavior regression for repos that use the no-colon idiom. (2) The user-edited test fixture `# HACK: temporary workaround for upstream bug` would still match a tuple element `"HACK:"` if any code carried that literal. (3) Comment-context is the structurally correct fix; regex tightening is cosmetic.

**Option C — Heuristic: skip lines containing `=` or `re.compile(`.** Rejected as too brittle. The right shape is "is this a comment line" not "does this line look like assignment".

## Risks

- **Comment-context regex over-tightening.** A novel comment style not in the allowlist (e.g. `;` for Lisp / Clojure, `'` for VBA) would silently produce false negatives. Acceptable today: Shipwright's source-suffix list (`_SOURCE_SUFFIXES`) does not include those languages, so they cannot reach the predicate. If new suffixes are added later, the allowlist must be extended in the same diff.
- **`_SKIP_FILES` relative-path drift.** If `known_issues_inventory.py` is moved to a different path, the skip set silently stops applying. Mitigation: add a one-line assertion in the test that the skip-file path actually exists in the repo (catches refactors that don't update the constant).
- **`save_session_config` removal blast radius.** Mitigated by the empirical grep run before edit. Belt-and-suspenders: re-run the grep just before the delete, fail loudly if any callsite exists outside the test file.
