# Iterate Spec: test-hygiene-and-skill-rules

- **Run ID:** iterate-2026-05-11-test-hygiene-and-skill-rules
- **Type:** change (mixed bug + change; primary = change)
- **Complexity:** medium
- **Status:** draft

## Goal

Stop tests from "greening" through silent skips that hide real failure
modes — both in `pytest`-on-binary-missing patterns and in the no-op
test for `_wait_for_service`. Codify the rules in the iterate SKILL.md
so future iterates don't re-introduce the same anti-patterns.

## Acceptance Criteria

- [ ] **AC-1** `test_wait_for_service_port_held_by_external_process_no_pid`
      in `shared/tests/test_dev_server_multiservice.py` is annotated with
      `@pytest.mark.skip(reason="covered by test_start_port_busy_no_state_errors_no_kill")`.
      It no longer green-passes a `pass` body that asserts nothing.

- [ ] **AC-2** `shared/tests/test_setup_writes_canonical.py` converts every
      `pytest.skip(f"cross-plugin sys.path pollution: {exc}")` site (5 sites)
      AND the inner `pytest.skip("compliance plugin not importable in this test session")`
      site (1 site) AND the `pytest.importorskip("scripts.lib.compliance_report")`
      site (1 site) to `pytest.fail(<actionable hint>)` **when `os.environ.get("CI") == "true"`**.
      Local dev (`CI` unset / "false") keeps the skip so single-plugin
      pytest sessions don't blow up. CI hard-fails with a hint that
      directs the operator to run the test under its plugin's pytest
      session, not from `shared/tests/`.
      
      *Approach (b) chosen* over a sys.path rewrite — the cross-plugin
      `lib`/`tools` namespace collision is unfixable at sys.path level
      without runtime module isolation.

- [ ] **AC-3** Six silent-skip-on-missing-binary sites add a CI-discipline
      gate: `if os.environ.get("CI") == "true": pytest.fail(<install hint>)`.
      Local: skip as today; CI: hard-fail with install hint pointing to
      the relevant `setup-*` action or `winget`/`brew` command. Sites:
      1. `shared/tests/test_path_helpers_template_vitest.py:31`
         (npx — install via `actions/setup-node@v4`)
      2. `shared/tests/test_path_helpers_template_vitest.py:99`
         (npm install failure — should not skip in CI, real failure)
      3. `plugins/shipwright-security/tests/test_oss_backend_smoke.py:135`
         (semgrep — install via `pip install semgrep`)
      4. `plugins/shipwright-security/tests/test_oss_backend_smoke.py:171`
         (gitleaks — install via `gitleaks/gitleaks-action@v2`)
      5. `plugins/shipwright-security/tests/test_oss_backend_smoke.py:204`
         (trivy — install via `aquasecurity/trivy-action@master`)
      6. `shared/tests/test_hook_output_schema_compliance.py:367`
         (uv — install via `astral-sh/setup-uv@v3`)

      `@pytest.mark.skipif` decorators are converted to manual
      `if not shutil.which(...)` inside the test body (the AC-3 gate
      can't sit on `skipif` because the decorator runs at collection
      time before any branching). The decorator is removed and the
      check is moved into the function body, gated by CI.

- [ ] **AC-4** New test `shared/tests/test_ci_template_registry_completeness.py`
      asserts: for every `shared/templates/github-actions/ci-*.yml.template`
      file on disk, there is a matching `TEMPLATE_BY_PROFILE` value
      pointing at it. The existing forward test (every TEMPLATE_BY_PROFILE
      value exists on disk) lives in `test_ci_workflow_convention.py`;
      this is the reverse — no orphan templates.

- [ ] **AC-5** `plugins/shipwright-iterate/skills/iterate/SKILL.md`
      Step 6 (Build TDD) gains three explicit rules:
      1. **Test-Update-Klausel** — when changing test infrastructure
         (skips, hygiene, conventions), the iterate MUST update the
         skill's reference rules to match, not just the test.
      2. **Registry-driven SSoT meta-test rule** — when a registry
         (dict, list) in `shared/scripts/lib/*` maps to files on disk,
         both forward (registry → disk) AND reverse (disk → registry)
         drift tests MUST exist. Reference AC-4 as canonical example.
      3. **Silent-skip CI-discipline rule** — `pytest.skip(...)` on
         missing-binary / missing-import paths MUST hard-fail in CI
         (gated by `os.environ.get("CI") == "true"`) with an
         actionable install hint. Local dev keeps the skip.

- [ ] **AC-6** *Deferred to follow-up iterate.* `shared/scripts/lib/test_hygiene.py`
      static probe helper. Tracked in the ADR's Consequences section.

### Drift-protection tests (explicit, added per external review #O1)

- [ ] **DR-1** `shared/tests/test_silent_skip_ci_discipline.py` — verifies the
      `_ci_truthy()` helper + the CI-gate branching logic. Unit-level
      tests (no subprocess) using `monkeypatch.setenv("CI", ...)`. Pins
      that `"true"`, `"1"`, `"True"` all activate the CI branch, and
      that unset / `"false"` / `"0"` don't.
- [ ] **DR-2** `plugins/shipwright-iterate/tests/test_skill_step_6_rules_present.py`
      — verifies that SKILL.md Step 6 contains the three named rule
      anchors (`Test-Update-Klausel`, `Registry-driven SSoT`,
      `Silent-skip CI-discipline`). Probe is anchored on Step 6
      heading first, then searches the section body — avoids the
      false-positive class flagged in ADR-025.

### CI-gate convention

The CI gate uses `os.environ.get("CI", "").lower() in ("true", "1")`
across all sites (normalized per external-review #O3 + #G4). The
canonical helper signature is `_ci_truthy() -> bool`. Each affected
test file defines its own 3-line copy; centralization is deferred
with AC-6.

## Affected FRs

- meta-quality: shared test hygiene + iterate SKILL governance.
  No user-facing FR change. The `python-plugin-monorepo` profile spec
  does not list test-discipline rules as FRs.

## Out of Scope

- Refactoring `_add_plugin_to_path` to use `importlib.machinery.PathFinder`
  for true per-plugin module isolation (would be approach (a) for AC-2;
  rejected).
- Wiring the `test_hygiene.py` helper into Step 7 (Self-Review) as a
  mandatory checklist item (deferred with AC-6).
- Adding the same CI-discipline gate to the **5** other
  `shutil.which("uv") is None` skipif sites in
  `plugins/shipwright-iterate/tests/test_hooks_json_registration.py`
  — those are a different category (round-trip subprocess tests,
  not "missing binary" pattern; uv being absent on Windows CI
  Python jobs is a documented known case there). Tracked as
  follow-up if needed.
- Touching `shared/tests/tools/test_validate_deploy_profile.py:332`
  (also a `shutil.which("uv")` skip) — same rationale.

## Design Notes

n/a — no UI change.

## Affected Boundaries

| Producer (writes)                                                        | Consumer (reads)                                                       | Format               |
|--------------------------------------------------------------------------|------------------------------------------------------------------------|----------------------|
| `shared/scripts/lib/ci_workflow.py:TEMPLATE_BY_PROFILE`                  | `shared/tests/test_ci_template_registry_completeness.py` (new) + `ci_workflow_scaffolder.py` + existing `test_ci_workflow_convention.py` | Python dict          |
| `shared/templates/github-actions/ci-*.yml.template` (files on disk)      | same registry test (reverse) + adopt scaffolder                        | Filesystem directory |
| pytest test files (skip markers)                                         | CI runner (`CI=true` env)                                              | OS environment       |
| `plugins/shipwright-iterate/skills/iterate/SKILL.md` Step 6 (markdown)   | iterate skill at runtime (read by Claude Code)                         | Markdown             |

`touches_io_boundary` fires for the markdown SKILL.md producer (per
ADR-031: markdown is a producer/consumer boundary). The 8-probe checklist
is partially N/A for machine-written markdown (operator-input categories
1, 6, 7 — POSIX export, inline `# comment`, quoted `#` — are N/A).
Round-trip test for SKILL.md changes: the Phase Matrix and Override
Classes table reference Step 6, so a structural change there requires
matrix consistency.

## Confidence Calibration

- **Boundaries touched:** four producer/consumer pairs (see Affected
  Boundaries table above).

- **Empirical probes run:**
  1. **AC-4 reverse-drift probe:** added temporary
     `ci-orphan-test.yml.template` to `shared/templates/github-actions/`,
     ran `test_every_ci_template_on_disk_has_registry_entry` → FAILED
     with named-orphan message; removed file, re-ran → PASSED.
     Confirms the test actually catches orphans (not vacuously
     passing). Output captured in run log.
  2. **AC-2 + AC-3 CI-gate round-trip:** ran
     `test_setup_writes_canonical.py::test_compliance_generators_*`
     with `CI=true` → hard-FAILED with "cross-plugin sys.path
     pollution" + plugin-session hint. Same test without CI →
     SKIPPED with same hint as skip-reason. Both branches
     empirically verified — not just "I read the diff".
  3. **DR-1 drift-protection:** the brittle-pattern regex
     `os.environ.get("CI") == "true"` was tested by introducing it
     temporarily into one of the affected files (in scratch). The
     test caught it. Then removed.
  4. **DR-2 anchor probe:** ran with rule anchors absent (SKILL.md
     unchanged) → 4 FAILED (the three anchor parametrized tests +
     the "not in unrelated sections" test). After SKILL.md edit
     → 6 passed. Confirms the probe is properly anchored.
  5. **AC-1 skip-marker round-trip:** ran the no-op test under
     `pytest -v` after `@pytest.mark.skip` was added. Output shows
     `SKIPPED` (not `PASSED`). Greening on no-op stopped.

- **Edge cases NOT probed + why acceptable:**
  - **Module-level `pytest.fail()` in CI=true mode for
    `test_path_helpers_template_vitest.py`** — not exercised live
    (would require CI=true npx-absent simulation). Pytest's
    `pytest.fail` raises `_pytest.outcomes.Failed`; at module level
    pytest catches this and converts to a collection error, which
    is documented in the pytest source even if not in the public
    docs. The risk class is low because (a) the message will appear
    in CI output regardless of how pytest renders the collection
    failure, and (b) DR-1 already verifies the canonical pattern
    string is present in the file.
  - **Cross-OS path normalization in AC-4 glob** — only tested on
    Windows host. The test uses `Path.glob("ci-*.yml.template")` +
    `Path.as_posix()` on both sides of comparison, so path
    separators are normalized identically.
  - **POSIX `export VAR=`, inline `# comment`, quoted `#`
    (boundary-probe categories 1, 6, 7)** — N/A for machine-written
    markdown (SKILL.md) and Python dict (`TEMPLATE_BY_PROFILE`).
    Markdown is not operator-edited as env; the dict is Python code.

- **Confidence-pattern check:** no "are you confident?" question has
  fired in this run. The session has used empirical probes
  throughout (5 probes above + the RED→GREEN TDD cycle for each AC).
  Asymptote heuristic: the last probe (DR-2 anchor probe) returned
  no findings AND all applicable categories from
  `references/boundary-probes.md` are covered AND no
  yes-then-bug pattern fired. Declaring exhausted.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  ```bash
  uv run pytest shared/tests/test_dev_server_multiservice.py::test_wait_for_service_port_held_by_external_process_no_pid shared/tests/test_setup_writes_canonical.py shared/tests/test_path_helpers_template_vitest.py shared/tests/test_hook_output_schema_compliance.py shared/tests/test_ci_template_registry_completeness.py shared/tests/test_ci_workflow_convention.py -v --no-header
  ```
  Plus (separate pytest session to avoid `conftest.py` collision — see
  ADR-043 learnings):
  ```bash
  cd plugins/shipwright-security && uv run pytest tests/test_oss_backend_smoke.py -v --no-header
  ```
- **Evidence path:** `.shipwright/runs/{run_id}/surface_verification.json`
  + pytest log files captured under same dir.
- **Justification (only if surface=none):** n/a.
