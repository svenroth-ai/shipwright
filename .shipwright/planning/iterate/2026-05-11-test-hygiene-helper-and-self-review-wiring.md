# Iterate Spec: test-hygiene-helper-and-self-review-wiring

- **Run ID:** iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal

Land deferred AC-6 from iterate-2026-05-11-test-hygiene-and-skill-rules
(PR #26, ADR-044): centralize the duplicated CI-discipline helpers into
`shared/scripts/test_hygiene.py` and wire a static-probe Self-Review
item that mechanically enforces silent-skip detection on the diff.

## Acceptance Criteria

- [ ] **AC-1** `shared/scripts/test_hygiene.py` exists and exports
      three callable helpers (matching the semantics of the
      duplicated inline copies from PR #26):
      1. `is_ci() -> bool` — `os.environ.get("CI", "").lower() in ("true", "1")`
      2. `import_or_fail_in_ci(plugin_name: str, exc: BaseException) -> NoReturn`
         — `_import_or_fail_in_ci` from `test_setup_writes_canonical.py`,
         renamed (drop the leading underscore — it's a public lib entry now)
      3. `skip_or_fail_on_missing_binary(binary: str, install_hint: str) -> None`
         — `_skip_or_fail_on_missing_binary` from `test_oss_backend_smoke.py`,
         renamed.
      Plus one static probe:
      4. `scan_for_silent_skip_without_ci_guard(test_files: Iterable[Path]) -> list[Finding]`
         — scans Python sources for `pytest.skip(...)` or
         `@pytest.mark.skipif(...)` sites that don't have a CI-gated
         `pytest.fail(...)` branch nearby. Returns a `Finding` dataclass
         with `file: Path`, `line: int`, `pattern: str`, `reason: str`.
      Plus a CLI entry point:
      5. `shared/scripts/tools/scan_test_hygiene.py` — argparse CLI that
         wraps `scan_for_silent_skip_without_ci_guard`. Supports
         `--diff` (read changed files from `git diff --name-only`),
         `--files <list>`, and `--json` (machine-readable output).
         Exit codes: 0 = no findings, 1 = findings present.

- [ ] **AC-2** Four test files refactored to import from the new lib
      module instead of defining inline copies. Each file drops its
      `_ci_truthy` definition and its `_import_or_fail_in_ci` /
      `_skip_or_fail_on_missing_binary` definition where applicable:
      1. `shared/tests/test_setup_writes_canonical.py` — uses
         `is_ci` + `import_or_fail_in_ci` from lib
      2. `shared/tests/test_path_helpers_template_vitest.py` — uses
         `is_ci` from lib
      3. `shared/tests/test_hook_output_schema_compliance.py` — uses
         `is_ci` from lib
      4. `plugins/shipwright-security/tests/test_oss_backend_smoke.py`
         — uses `is_ci` + `skip_or_fail_on_missing_binary` from lib

- [ ] **AC-3** `shared/tests/test_silent_skip_ci_discipline.py` updated
      so the canonical-pattern regex now asserts:
      - Forward — every affected file must contain
        `from test_hygiene import` with the appropriate symbol
        (canonical import form; the `from test_hygiene import` short
        form is NOT accepted — pick one form to avoid drift, per
        external-review #O7)
      - Reverse — no affected file may define `def _ci_truthy(`,
        `def _import_or_fail_in_ci(`, or `def _skip_or_fail_on_missing_binary(`
        locally (the inline copy is the regression after centralization).
      The pre-PR-#26 brittle-pattern rejection (`os.environ.get("CI") == "true"`)
      stays in place — still a regression.

- [ ] **AC-4** `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md`
      gains a new Self-Review section 8 ("Test Hygiene Probe") at the
      end of the existing 7-point checklist. Content:
      ```
      ### 8. Test Hygiene Probe
      Run `uv run shared/scripts/tools/scan_test_hygiene.py --diff` against
      changed Python test files; resolve any silent-skip findings (`pytest.skip`
      or `@pytest.mark.skipif` without a CI-gated `pytest.fail` branch nearby).
      - Mandatory at medium+
      - Advisory at trivial / small
      - Skip rules: explicit `# test-hygiene: allow-silent-skip` comment on
        the offending line, with a rationale.
      ```
      The existing "Self-Review Checklist" intro is updated from "7-point
      checklist" to "8-point checklist".

- [ ] **AC-5** New drift-protection probe `plugins/shipwright-iterate/tests/test_iteration_reviews_section_8.py`
      that anchors on the `### 8. Test Hygiene Probe` heading and asserts
      it contains both the CLI invocation snippet AND the "Mandatory at
      medium+" wording. Mirrors the AC-5 SKILL.md Step 6 probe pattern
      from PR #26.

## Affected FRs

- meta-quality: shared test hygiene tooling + iterate Self-Review
  governance. No user-facing FR change.

## Out of Scope

- Adding new categories to the static probe (e.g. "no-op test body"
  detection from AC-1 of PR #26, "module-level pytest.fail without
  CI gate" detection). The probe is a single rule today
  (silent-skip-without-CI-guard); future rules can be added in
  follow-up iterates without breaking the API.
- Auto-applying fixes (`scan --fix`). Findings are reported only.
  Auto-fix is a separate, riskier surface.
- Migrating the 5 `shutil.which("uv")` skipifs in
  `plugins/shipwright-iterate/tests/test_hooks_json_registration.py`
  to the centralized helper. Those were excluded from PR #26 by
  scope and remain excluded here — different category (round-trip
  subprocess tests, documented known case).
- `pytest.importorskip(...)` detection. Per external-review #G4
  this is a related anti-pattern, but conflating it with the
  silent-skip rule in the first probe release would muddy failure
  messages. Tracked as a follow-up rule category once the base
  probe stabilizes.
- Wiring the static probe into a PreCommit hook. Self-Review
  invocation is the mandatory enforcement point; pre-commit
  enforcement is a strictly stronger move that needs its own
  iterate.

## Design Notes

n/a — no UI change.

## Affected Boundaries

| Producer (writes)                                                                  | Consumer (reads)                                                              | Format                |
|------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|-----------------------|
| `shared/scripts/test_hygiene.py` (new Python module)                            | 4 test files + `scan_test_hygiene.py` CLI + `test_silent_skip_ci_discipline.py` | Python import         |
| `shared/scripts/tools/scan_test_hygiene.py` (new CLI)                               | Self-Review (manual invocation) + `test_iteration_reviews_section_8.py` (asserts the snippet exists) | argparse CLI / shell  |
| `plugins/shipwright-iterate/skills/iterate/references/iteration-reviews.md` Section 8 | iterate skill at runtime (read by Claude Code) + `test_iteration_reviews_section_8.py` probe        | Markdown              |

`touches_io_boundary` fires for the markdown producer (per ADR-031). The
8-probe checklist is partially N/A for machine-written markdown — operator-input
categories 1, 6, 7 (POSIX export, inline `# comment`, quoted `#`) are N/A.
Round-trip test: the probe (AC-5) IS the consumer; pinning the section
heading + invocation snippet covers the format contract.

The Python module's boundary (it's imported, not parsed as serialized
data) is covered by Python's import machinery — no producer/consumer
drift risk at the format level. AC-3 covers the import-pattern drift.

## Confidence Calibration

- **Boundaries touched:** three producer/consumer pairs (see Affected
  Boundaries table above).

- **Empirical probes run:**
  1. **AC-1 lib + scanner round-trip:** 31 unit tests covering parametrized
     truthy/falsy values, suppression-marker variants (same-line,
     previous-line, contiguous-block above), scope-topology (same
     FunctionDef contains both skip + ci-gated fail vs distant
     pytest.fail in a different function), inverted-branch form,
     module-level skip+fail pattern, SyntaxError + missing-file
     graceful handling, and clean-file zero-findings baseline. All
     31 GREEN.
  2. **AC-2 refactor reality check:** scanned the 4 affected files
     with the new probe AFTER refactor — zero findings. Pre-refactor
     the same scan returned 9 findings (5 inline-helper bare skips,
     3 legitimate setup-condition skips needing markers, 1 skipif
     decorator needing marker). Empirically proves the refactor
     surfaces and resolves real silent-skip sites.
  3. **AC-3 flip drift-protection:** ran DR-1's flipped assertions
     against the post-refactor files; all 33 GREEN. Inverse-direction
     proof: temporarily re-added `def _ci_truthy(` to one file → DR-1
     immediately failed with the named-regression message; removed →
     GREEN. The "no double SSoT" rule is now mechanically enforced.
  4. **AC-5 probe verification:** ran the section-8 probe RED first
     (4 failures before iteration-reviews.md edit), then GREEN
     (5 passes after edit). Confirms the probe is properly anchored
     on the H3 heading + the named keys.
  5. **Self-Review § 8 dogfood:** ran `scan_test_hygiene.py --diff`
     against this iterate's own diff → 0 findings. The new probe
     was applied to itself at Self-Review time. Round-trip closed.
  6. **CLI smoke-tests:** `--files X.py` exits 0 for clean file,
     exits 1 for a file with the inline-helper anti-pattern;
     `--json` emits the expected `{findings_count, findings: [...]}`
     shape; `--diff` resolves origin/HEAD defensively (returns
     exit-2 + actionable message when no remote default).

- **Edge cases NOT probed + why acceptable:**
  - **`pytest.importorskip` detection** — explicitly out of scope
    per the spec; tracked as follow-up rule category. Different
    anti-pattern semantics (import vs skip).
  - **Multi-OS path normalization in the CLI** — only tested on
    Windows. The CLI uses `Path` operations + `subprocess.run` with
    explicit argv (no `shell=True`), so the OS-portability surface
    is small.
  - **POSIX `export VAR=`, inline `# comment`, quoted `#` (boundary
    probe categories 1, 6, 7)** — N/A for machine-written markdown
    (iteration-reviews.md Section 8) and Python lib code.

- **Confidence-pattern check:** no "are you confident?" question has
  fired in this run. All 5 probes above are empirical, not
  self-attestation. Asymptote heuristic: the last probe (Self-Review
  § 8 dogfood, run against the iterate's own diff) returned no
  findings AND all applicable categories are covered AND no
  yes-then-bug pattern fired in this run. Declaring exhausted.

## Verification (medium+)

- **Surface:** cli
- **Runner command:**
  ```bash
  uv run pytest shared/tests/test_setup_writes_canonical.py shared/tests/test_path_helpers_template_vitest.py shared/tests/test_hook_output_schema_compliance.py shared/tests/test_silent_skip_ci_discipline.py shared/tests/test_test_hygiene.py shared/tests/test_dev_server_multiservice.py shared/tests/test_ci_template_registry_completeness.py -v --no-header
  ```
  Plus (separate sessions per ADR-043 conftest-collision pattern):
  ```bash
  uv run pytest plugins/shipwright-security/tests/test_oss_backend_smoke.py -v --no-header
  uv run pytest plugins/shipwright-iterate/tests/test_iteration_reviews_section_8.py plugins/shipwright-iterate/tests/test_skill_step_6_rules_present.py -v --no-header
  ```
  Plus CLI smoke:
  ```bash
  uv run shared/scripts/tools/scan_test_hygiene.py --files shared/tests/test_setup_writes_canonical.py --json
  ```
- **Evidence path:** `.shipwright/runs/{run_id}/surface_verification.json`
  + pytest log files captured under same dir.
- **Justification (only if surface=none):** n/a.
