# Mini-Plan — iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring

## Files to change

| File                                                                                  | Action      | LOC est. |
|---------------------------------------------------------------------------------------|-------------|----------|
| `shared/scripts/test_hygiene.py`                                                  | **new**     | ~150     |
| `shared/scripts/tools/scan_test_hygiene.py`                                           | **new**     | ~80      |
| `shared/tests/test_test_hygiene.py`                                                   | **new**     | ~120     |
| `shared/tests/test_setup_writes_canonical.py`                                         | refactor    | ~30 net (drop inline helpers, add import) |
| `shared/tests/test_path_helpers_template_vitest.py`                                   | refactor    | ~10 net  |
| `shared/tests/test_hook_output_schema_compliance.py`                                  | refactor    | ~8 net   |
| `plugins/shipwright-security/tests/test_oss_backend_smoke.py`                         | refactor    | ~30 net  |
| `shared/tests/test_silent_skip_ci_discipline.py`                                      | edit        | ~40 net (flip-direction drift checks) |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`           | edit        | ~25      |
| `plugins/shipwright-iterate/tests/test_iteration_reviews_section_8.py`                | **new**     | ~80      |

## Work Breakdown (TDD order)

### Phase 1 — RED probes

1. **AC-5 RED:** Write `test_iteration_reviews_section_8.py` first.
   Anchors on `### 8. Test Hygiene Probe` heading inside
   iteration-reviews.md; asserts it contains the CLI snippet
   `uv run shared/scripts/tools/scan_test_hygiene.py --diff` AND the
   "Mandatory at medium+" wording. Will FAIL because section 8 doesn't
   exist yet. Mirror DR-2 pattern from PR #26.

2. **AC-3 RED prep:** Sketch updated `test_silent_skip_ci_discipline.py`
   assertions but don't apply them yet — those need the lib refactor
   (AC-2) to be in place first.

3. **AC-1 RED:** Write `shared/tests/test_test_hygiene.py` with these test
   classes:
   - `TestIsCi` — parametrized: ("true", True), ("True", True), ("TRUE",
     True), ("1", True), ("false", False), ("0", False), ("", False),
     (None, False).
   - `TestImportOrFailInCi` — with `monkeypatch.delenv("CI", raising=False)`
     should raise `pytest.skip.Exception`; with `monkeypatch.setenv("CI", "true")`
     should raise `pytest.fail.Exception` with the plugin name in the
     message.
   - `TestSkipOrFailOnMissingBinary` — analogous, parametrized over
     `shutil.which` mocked to None / "/usr/bin/foo".
   - `TestScanForSilentSkipWithoutCiGuard` — fixture creates a tmp
     test file containing a silent-skip pattern; assert scan returns
     1 finding. Then add the CI-gated branch nearby; assert scan
     returns 0 findings. Plus: allow-silent-skip marker comment
     suppresses the finding.

### Phase 2 — GREEN library + CLI (AC-1)

4. **Implement `shared/scripts/test_hygiene.py`:**
   - `is_ci()` — 1 line.
   - `import_or_fail_in_ci(plugin_name, exc)` — port from
     `test_setup_writes_canonical.py`, drop the iterate-specific
     run-id reference in the failure message (it's a stable lib
     now; the run-id is current-iterate-only context).
   - `skip_or_fail_on_missing_binary(binary, install_hint)` — port
     from `test_oss_backend_smoke.py`.
   - `Finding` dataclass + `scan_for_silent_skip_without_ci_guard(files)`:
     - Parse each `.py` file with `ast` (AST is more robust than regex
       for nested `pytest.skip` / `pytest.mark.skipif` detection).
     - Look for:
       (a) `pytest.skip(...)` calls — flag unless there's an enclosing
       `if is_ci(): pytest.fail(...)` in the same function body
       OR a `pytest.fail(...)` call within ±5 lines before the skip.
       (b) `@pytest.mark.skipif(...)` decorators on test functions
       (always flagged — decorators run at collection time and can't
       be CI-gated structurally; the rule is "convert to body-level
       gate").
     - Skip findings on lines bearing the comment
       `# test-hygiene: allow-silent-skip` (with a rationale on the
       same or previous line).
     - Skip `tests/test_test_hygiene.py` itself (it contains
       deliberate silent-skip fixtures).

5. **Implement `shared/scripts/tools/scan_test_hygiene.py` CLI:**
   - argparse: `--diff` (auto from `git diff --name-only main...HEAD`),
     `--files <path>...` (explicit), `--json` (machine output).
   - Filter to `.py` files matching `test_*.py` or `*_test.py`.
   - Exit 0 if findings empty, exit 1 otherwise.

6. Run `test_test_hygiene.py` — should GREEN now.

### Phase 3 — GREEN refactor (AC-2)

7. For each of the 4 affected test files:
   - Add `from test_hygiene import is_ci, import_or_fail_in_ci`
     (or just `is_ci`, or `is_ci, skip_or_fail_on_missing_binary` per
     file). Path setup: each file already inserts a plugin/repo path
     onto `sys.path` near the top — the `test_hygiene` import
     path is `shared/scripts/test_hygiene.py` which requires
     `shared/scripts/` on the path. The shared/tests/ files run from
     repo root and `shared/scripts/` is on path via project pyproject
     (existing pattern — see `from lib.ci_workflow import ...` in
     `test_ci_workflow_convention.py`).
   - Delete the local `def _ci_truthy(...)` definition.
   - Delete the local `def _import_or_fail_in_ci(...)` or
     `def _skip_or_fail_on_missing_binary(...)` definition where
     applicable.
   - Update call sites: `_ci_truthy()` → `is_ci()`,
     `_import_or_fail_in_ci(...)` → `import_or_fail_in_ci(...)`,
     `_skip_or_fail_on_missing_binary(...)` →
     `skip_or_fail_on_missing_binary(...)`.

8. Run each affected file's tests — should still GREEN.

### Phase 4 — GREEN DR-1 update (AC-3)

9. Update `test_silent_skip_ci_discipline.py`:
   - `_CANONICAL_TRUTHY_RE` (in-source `os.environ.get(...)` expression)
     check is now a NEGATIVE assertion — files should NOT carry the
     expression any more (they import `is_ci`).
   - New `_LIB_IMPORT_RE` — POSITIVE assertion that each affected file
     has `from test_hygiene import` somewhere.
   - `_HELPER_DEF_RE` (`def _ci_truthy(`) — flip to NEGATIVE.
   - Add similar negative regexes for `def _import_or_fail_in_ci(` and
     `def _skip_or_fail_on_missing_binary(`.
   - Keep the brittle-pattern `os.environ.get("CI") == "true"` rejection
     test — still a regression class.
   - Keep `test_vitest_module_pattern_carries_both_ci_branches` — it
     still asserts the module-level fail+skip branches are present
     (they remain, just using `is_ci()` now).

10. Run DR-1 — should GREEN.

### Phase 5 — AC-4 + AC-5 land

11. Edit `iteration-reviews.md`:
    - Update Self-Review intro: "7-point checklist" → "8-point checklist".
    - Add `### 8. Test Hygiene Probe` after item 7 with the CLI snippet,
      Mandatory/Advisory matrix, and skip-rules text from the AC spec.

12. Run `test_iteration_reviews_section_8.py` — should GREEN now.

### Phase 6 — F0/F0.5

13. Full F0 across all affected test files + new test files.
14. F0.5 surface=cli with the runner from spec Verification section.

## Test Strategy

- **Red phase:** AC-5 + AC-1 (test_test_hygiene.py) written first.
  AC-3 RED is delayed until AC-2 lands (the inline-def rejection
  can't be tested while the inline defs still exist).
- **Green phase:** library → CLI → refactor → DR-1 flip → markdown →
  AC-5 probe.
- **Full suite (F0):** all affected files in shared/tests + the two
  plugin test files. Run from repo root for shared/tests, then
  separate session per plugin per ADR-043 conftest-collision.
- **F0.5 (cli surface):** pytest invocations + the new CLI itself
  (smoke run with `--json` flag) as empirical proof of the surface.

## Alternative Considered

- **AC-1 alternative: regex-based scanner instead of AST.** Rejected
  per the ADR-021 + iterate-04 learnings — substring/regex matching
  on a producer-consumer boundary admits false positives. AST gives
  us call-site semantics for free (`pytest.skip` as a `Call` with
  `Attribute(value=Name(id='pytest'), attr='skip')`).

- **AC-1 alternative: include `find no-op test body` rule from
  AC-1 of PR #26.** Rejected here — that's a different rule class
  (greening on `pass` body) and conflating them in the first probe
  release would muddy the failure messages. Tracked as follow-up.

- **AC-2 alternative: keep the inline copies + only centralize the
  static probe.** Rejected — DR-1's whole point in this iterate is
  to enforce centralization. Half-measure would leave the
  duplicate-helper drift surface open.

- **AC-4 alternative: `references/test-hygiene.md` reference doc**
  instead of inlining section 8 into iteration-reviews.md. Rejected
  for the same reason as PR #26's AC-5 — Self-Review is short
  enough that inline keeps the rules in front of the eyes during
  review; a separate ref file invites the rule being skipped.

## Risk

- **AST-walker false positives** on edge-case test files (e.g. a test
  that legitimately calls `pytest.skip` inside an `if not server_running:`
  branch where "server_running" is determined by something CI-aware
  upstream). Mitigation: the `# test-hygiene: allow-silent-skip`
  marker provides an explicit opt-out. If false-positive rate is
  high in practice, tighten the heuristic in a follow-up.
- **CLI path resolution from arbitrary cwd.** The CLI must resolve
  `--diff` against `git diff --name-only main...HEAD` even when
  invoked from a subdirectory. Use `git rev-parse --show-toplevel`
  to anchor the diff. Mitigation: explicit `--files` flag bypasses
  diff entirely.
- **Refactor blast radius.** 4 test files + 1 drift-protection file
  + 1 reference doc + 2 new files + 1 new test file = 9 files touched.
  Mitigation: F0 covers all of them; DR-1's flipped assertions act
  as a structural safety net.
