# Mini-Plan — iterate-2026-05-11-test-hygiene-and-skill-rules

## Files to change

| File                                                                                  | Action      | LOC est. |
|---------------------------------------------------------------------------------------|-------------|----------|
| `shared/tests/test_dev_server_multiservice.py`                                        | edit        | ~3       |
| `shared/tests/test_setup_writes_canonical.py`                                         | edit (7×)   | ~30      |
| `shared/tests/test_path_helpers_template_vitest.py`                                   | edit (2×)   | ~15      |
| `shared/tests/test_hook_output_schema_compliance.py`                                  | edit (1×)   | ~10      |
| `plugins/shipwright-security/tests/test_oss_backend_smoke.py`                         | edit (3×)   | ~25      |
| `shared/tests/test_ci_template_registry_completeness.py`                              | **new**     | ~60      |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md`                                  | edit (Step 6) | ~40    |
| `.shipwright/planning/iterate/2026-05-11-test-hygiene-and-skill-rules.md`             | this spec   | —        |

## Work Breakdown (TDD order — Red first, then Green)

1. **AC-4 RED → GREEN** (smallest, no deps): write
   `test_ci_template_registry_completeness.py` first. The test will FAIL
   if any orphan template exists today (must verify all 3 templates have
   registry entries). If GREEN immediately, that confirms registry is
   currently in sync — still a useful drift guard for the future.
   Verify by adding a temporary orphan file → test RED → remove → GREEN.

2. **AC-1**: One-line edit — annotate the no-op test with `@pytest.mark.skip`.
   Run pytest, verify it shows as skipped (not passed). No new test
   needed: AC-1 is removing a false-positive, not adding coverage.

3. **AC-3** (six sites, mechanical): for each `@pytest.mark.skipif(...)`
   that gates on `shutil.which(X) is None`:
   - Remove the `@pytest.mark.skipif` decorator
   - Add a body-start check:
     ```python
     if shutil.which(X) is None:
         if os.environ.get("CI") == "true":
             pytest.fail(f"{X} not on PATH in CI — install via {hint}")
         pytest.skip(f"{X} not on PATH (local dev)")
     ```
   - For module-level skip (vitest `if shutil.which("npx") is None:`):
     same pattern but at module level with `allow_module_level=True` on
     the skip. For npm install failure (line 99): convert to fail in CI
     (it should not skip ever; npm install failures are real errors).
   - Add a small unit test verifying the CI=true path raises Failed.
     We can use `monkeypatch.setenv("CI", "true")` + `pytest.raises`.
     Land this verifier in `shared/tests/test_silent_skip_ci_discipline.py`
     (new — short, ~40 LOC).

4. **AC-2** (seven sites in `test_setup_writes_canonical.py`):
   pattern is identical to AC-3 but with `ImportError`/`ModuleNotFoundError`
   instead of missing-binary. Build a small helper at the top of the file:
   ```python
   def _import_or_fail_in_ci(skip_reason: str, fail_hint: str) -> None:
       if os.environ.get("CI") == "true":
           pytest.fail(fail_hint)
       pytest.skip(skip_reason)
   ```
   Replace each existing `pytest.skip(f"cross-plugin sys.path pollution: {exc}")`
   with a call to this helper. Sites:
   - Line 70-71 (artifact_writer.write_spec)
   - Line 95-96 (config_writer.write_project_config)
   - Line 123-124 (campaign_init.init_campaign)
   - Line 221-222 (data_collector.collect_requirements)
   - Line 329-330 (artifact_writer.write_agent_docs)
   - Line 401-404 (importorskip → manual + helper)
   - Line 416-417 (inner pytest.skip)
   Hint text directs operator to run `cd plugins/<plugin> && uv run pytest tests/`.
   Reuse the verifier from AC-3 (extend its parametrization) to assert
   the CI=true branch raises.

5. **AC-5** (SKILL.md Step 6 update): insert three new sub-bullets after
   the existing "No tests that always pass regardless of implementation"
   bullet in `2. RED — Write failing tests first`:
   - Test-Update-Klausel
   - Registry-driven SSoT meta-test rule
   - Silent-skip CI-discipline rule
   Cross-reference: AC-4's test file as canonical example for the
   registry rule; ADR (this run) for the CI-discipline rule.
   **Drift-protection meta-test:** add a probe in
   `plugins/shipwright-iterate/tests/test_skill_step_6_rules_present.py`
   (new, ~30 LOC) — asserts the three sub-bullets appear in SKILL.md
   under Step 6. Mirrors the pattern from ADR-021 (decision_log probe).

6. **AC-6**: NOT IN SCOPE THIS ITERATE. Confirm deferral in ADR.

## Test Strategy

- **Red phase:** AC-4 + AC-3-verifier + AC-2-verifier + AC-5-probe written
  to fail before implementation. AC-1's "RED" state is the current no-op
  test green-passing; "GREEN" is the new skipped status.
- **Green phase:** edits land, all new + existing tests pass.
- **Full suite (F0):** `cd plugins/<each>` runs because of `conftest.py`
  collision (ADR-043 learning). For the shared tests, single `pytest`
  invocation at repo root. Use the wrapper script pattern.
- **F0.5 (cli surface):** the changed test files themselves are the
  surface — running them under `CI=true` empirically proves the
  hard-fail branch fires (in addition to the unit-level verifier).
  We'll run the affected test files twice: once unset CI (skip),
  once CI=true (fail) — capture both outputs in `surface_verification.json`.

## Alternative Considered

- **AC-2 approach (a)** — fix the sys.path setup. Rejected: requires
  rewriting `_add_plugin_to_path` to namespace-isolate each plugin via
  `importlib.machinery.PathFinder` or per-test `sys.modules` snapshot/restore.
  High risk of breaking other test files in the same pytest session;
  the cross-plugin `lib`/`tools` namespace collision is structural
  (every plugin defines its own `lib/` package). Approach (b) is
  cheaper AND provides a louder failure signal in CI, which is what
  the AC is really after.

- **AC-3 alternative: blanket-fail all six sites** (no CI gate).
  Rejected: would break local-dev workflows on machines without all
  scanners installed. The `CI=true` gate matches Shipwright's existing
  pattern in `tests/test_hooks_json_registration.py` (see ADR-030)
  where pre-push tests gate on cache state.

- **AC-5 alternative: write the rules in a new
  `references/test-hygiene.md`** and link from SKILL.md Step 6 instead
  of inlining the bullets. Rejected: Step 6 is short enough that a
  three-bullet inline addition keeps the rules in front of the eyes
  during build; a separate ref file invites the rules being skipped.

## Risk

- **AC-2 helper placement.** `_import_or_fail_in_ci` lives in the test
  file (not shared lib) — by design, AC-6 (the shared helper) is
  deferred. Acceptable since the helper is 3 lines.
- **AC-5 probe pattern fragility.** Asserting bullets exist in
  SKILL.md by substring match could be brittle (white-space changes,
  punctuation). Solution: anchor probe on a normalized phrase, not
  the full bullet text. Same trade-off as the ADR-021 decision_log
  probe.
- **F0 full suite cost.** Each `plugins/<X>/tests/` run is its own
  pytest session — wall-clock will be longer than usual. Mitigation:
  run the affected plugin pytest sessions, not every plugin.
