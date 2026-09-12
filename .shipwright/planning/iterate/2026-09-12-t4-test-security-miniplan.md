# Mini-Plan: t4 - test-security (FR-01.06 + FR-01.07 AC backfill)

- **Run ID:** iterate-2026-09-12-t4-test-security
- **Campaign:** req3-05-test-backfill-mono, sub-iterate t4
- **Type:** change (test backfill via `@pytest.mark.covers`, no production-behavior change)
- **Complexity:** small (Stage 1 `classify_complexity.py`). Step 3.4 diff-driven
  re-check: `effective_complexity=small`, `upgraded=false`, `risk_flags=[]`,
  `plan_review_required=true` (merge-base diff is 195 LOC, over the 100-LOC
  threshold).

## Cited seam (binding, not re-decided)

Per the campaign header's binding-seam rule, this unit cites
`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md` (t0)'s row for
this cluster rather than re-deciding it:

> `FR-01.06 | /shipwright-test | 18 / 18 | plugins/shipwright-test/tests |
> test_test_runner.py, test_smoke_test.py, test_playwright_runner.py,
> test_journey_coverage.py, test_boundary_coverage_report.py (already the
> plugin's densest suite — attach beside it) | none yet | t4`
>
> `FR-01.07 | /shipwright-security | 18 / 14 | plugins/shipwright-security/tests;
> shared/tests for the shared scan-card/coverage surface (Finding 1) |
> test_generate_security_report.py, test_gitleaks_*, test_coverage_*; shared:
> test_security_scan_card.py | shared/tests/test_security_scan_card.py ->
> AC04, AC08, AC11; plugins/shipwright-security/tests/test_gitleaks_extend_smoke.py
> -> AC06 | t4`

**Root count — 3, waived** (`.shipwright/planning/iterate/2026-09-11-req3-05-seam-survey.md`,
"Per-unit ADR-044 root count" table + "Flagged deviation" section): the
campaign owner (Sven) ruled 2026-09-12 that option (a) — accept the deviation,
the roots are forced by where the behavior lives, not chosen — applies to t4
(and t5/t8/t9) exactly as already accepted for t1. Roots touched:
`plugins/shipwright-test/tests`, `plugins/shipwright-security/tests`,
`shared/tests` — one `pytest` invocation per root (ADR-044 governs pytest
*processes*, not roots per unit), one `--junitxml` per root, results merged by
hand afterward. In this unit's execution, `shared/tests` was touched only to
upgrade ONE already-existing bare tag (`test_test_checks_accepted_baseline.py`,
which already carried `FR-01.06` tags before this unit ran) — no new test file
was added to `shared/tests`.

## Re-derived work list (not copied from the spec)

`shipwright_ac_coverage_baseline.json` -> `unbound` at branch point (fresh
`origin/main`): 18 ACs start with `FR-01.06/` (AC01-AC18, all of them) and 14
start with `FR-01.07/` (AC01,02,03,05,07,09,10,12,13,14,15,16,17,18 — AC04,
AC06, AC08, AC11 already bound per the seam survey's own precedent column) —
32 ACs total, matching the spec's stated count going in.

## Approach

Precedent-first: for every AC, first checked whether an EXISTING test in the
assigned root already exercises the exact behavior the AC describes (most of
FR-01.06's honesty/retry/coverage mechanics and FR-01.07's degraded-scan /
comparison / config-extension mechanics were already covered by real,
executing tests — just under a bare `FR-01.xx` tag, or untagged). Where that
was true, the SAME test function was upgraded to the qualified
`FR-xx.yy/ACnn` tag — no new test, no new file. Where no existing test proved
an AC's specific claim, a new test function was added to the SAME file already
covering that production module (never a new file), invoking the real
production entry point (subprocess CLI for `test_runner.py` /
`prompt_injection_scan.py`; direct function call for `normalize_gitleaks`,
`scan.parse_scan_types`) rather than re-implementing any logic.

**Seven ACs are left unbound with a recorded reason** — five in FR-01.06, two
in FR-01.07. Every one of them was checked against a concrete production
module or reference doc before being declared unprovable; none is a
convenience skip. Full per-AC reasoning is in the table below; the pattern in
every case is the same class already established in this campaign's own
Exception 1 (Preview) and Exception 7/8 (t3, FR-01.03/FR-01.04): the AC
describes agent-executed SKILL.md prose or a conjunctive claim whose second
clause has no code artifact a deterministic test can invoke and assert on.

## Per-AC seam mapping (executed)

### FR-01.06 (/shipwright-test)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | test | `test_test_runner.py::test_run_tests_failing` — a real subprocess command's real exit code is reported, not an assumed one |
| AC02 | **not bound — recorded reason** | Conjunctive AC: "every layer carries an explicit outcome ... and a skip with no reason given stops the phase from being called complete." The first clause (explicit outcome + stated reason) has a real seam (`test_runner.py --skip-if-missing`, used for AC04 below); the second clause ("stops the phase from being called complete") is pure SKILL.md prose (`references/completion-gate.md`) — no module reads `shipwright_test_results.json` and refuses to mark the phase complete on an unreasoned skip. Per this campaign's own Exception 7/8 precedent ("a partially-provable clause does not make the whole AC provable"), not bound. |
| AC03 | shared | `test_test_checks_accepted_baseline.py::test_an_empty_run_is_still_never_a_pass` — `check_test_results_file_fresh` rejects `total=0` as an ERROR, matching the AC's exact wording ("a record showing nothing executed is never accepted as a passing one") |
| AC04 | test | `test_test_runner.py::test_skip_if_missing_records_not_run_with_a_reason_never_a_pass` (new) — `--skip-if-missing` records `skipped: True` + a `skip_reason` string, `passed=0/total=0`, never a bare pass |
| AC05 | **not bound — recorded reason** | No code seam anywhere refuses an out-of-pipeline result and re-runs it. Confirmed by reading `shared/scripts/tools/stamp_test_results.py`'s own docstring: "Nothing here enforces the stamp... A gate that refuses an unstamped or mismatched record belongs to sibling card `trg-12b4cf3f`" — i.e. the gate this AC describes is explicitly future work, not yet built, campaign-wide (not scoped to this unit to build). |
| AC06 | test | `test_playwright_runner_flaky.py::test_a_legacy_multi_attempt_pass_is_not_silently_a_first_time_pass` — already annotated in its own docstring "Losing the retry here would lose exactly the signal AC6 asks for" |
| AC07 | **not bound — recorded reason** | "Runnable tests are written from journeys instead of skipping the whole layer" describes E2E spec GENERATION (step-2.5), which is agent-authored content creation from `claude-plan-e2e.md` — no generator script exists (`grep` for a spec-generation module in `plugins/shipwright-test/scripts` finds none); `journey_coverage.py` (the seam AC08 binds to) only *reports* coverage of specs that already exist, it does not generate them. |
| AC08 | test | `test_journey_coverage.py::test_greenfield_gaps_block` + `::test_brownfield_gaps_do_not_block_and_leave_a_follow_up` — per-journey report, greenfield blocks, brownfield follows up |
| AC09 | test | `test_warning_followups.py::test_the_same_failure_across_two_commits_stays_one_follow_up` — idempotent across commits, so a long-standing failure stays one visible tracked item rather than silently vanishing or re-appearing as "new" |
| AC10 | test | `test_warning_followups.py::test_the_returned_summary_names_accepted_and_genuine_separately` + `::test_the_summary_says_when_the_accepted_list_could_not_be_read` — known/genuine split, and an unreadable list "excuses nothing... and says so" |
| AC11 | test | `test_playwright_runner_flaky.py::test_retries_no_longer_inflate_the_total` — two tests / four attempts still count as `total=2`, each test counted once |
| AC12 | **not bound — recorded reason** | Conjunctive AC (same class as t3's Exception 7, FR-01.04/AC10): "each screen compared to mockup, divergence named" IS provable (`design_fidelity_check.py`'s `status: needs_review` per screen), but "a screen that matched before and diverges now is reported as a regression, distinct from one never checked" is agent-executed triage (`step-3.7-design-fidelity.md`'s Resolved/Regression/Persistent/Unchecked buckets) — no module implements or reads a prior-run comparison for this. A partially-provable clause does not make the whole AC provable. |
| AC13 | test | `test_warning_followups.py::test_a_failing_consistency_category_leaves_a_follow_up` — "spacing"/"colors" inconsistent while "typography" consistent, reported as the outlier categories |
| AC14 | test | `test_performance_check_integration.py::test_block_gate_fails_when_lighthouse_below_budget` + `::test_warn_gate_succeeds_even_on_lighthouse_failure` — real subprocess CLI, budget exceeded by how much (score/LCP), gate=block stops + files triage, gate=warn continues |
| AC15 | test | `test_boundary_coverage_report.py::test_round_trip_detection_heuristic` — a declared producer/consumer pair reported as apparently covered when a test mentions the producer |
| AC16 | test | `test_boundary_coverage_report.py::test_drift_signal_fires_when_io_commit_lacks_section` — an IO-touching commit with no declared boundary is flagged as a missed declaration |
| AC17 | test | `test_boundary_coverage_report.py::test_merge_into_creates_key_in_existing_file` — the coverage report becomes part of the durable `shipwright_test_results.json` record the audit-evidence phase reads |
| AC18 | **not bound — recorded reason** | "A green test run is never mistaken for a security clearance" is a policy/documentation guarantee (Step 4 of `SKILL.md` is explicitly a no-op; `step-5-report-results.md` prints `Security: {via /shipwright-security | not run}` as prose) with no executable behavior to probe — same class as this campaign's Exception 1, Preview AC09. |

### FR-01.07 (/shipwright-security)

| AC | Root | Test file :: function |
|---|---|---|
| AC01 | security | `test_scan_cli.py::test_the_scan_examines_every_named_risk_category` (new; strengthened after external plan review, openai, medium) — drives the real `scan.main()` end to end with a fake backend reporting one finding of each of the three infrastructure categories, and asserts the WRITTEN report carries all three `type`s (not merely that the alias parser recognizes their names), plus `prompt_injection_scan.scan_hooks_json` flagging a hostile hooks file for the fourth (instruction-hijacking) category |
| AC02 | security | `test_normalizers.py::test_every_normalizer_produces_the_same_required_shape` (new) — semgrep/trivy/gitleaks findings all carry the same required key set |
| AC03 | security | `test_scan_cli_degraded.py::test_degraded_returns_2_and_writes_marker` — a check that could not run (`degraded`) returns exit 2, never a clean 0 |
| AC05 | security | `test_scan_compare.py::test_class_not_covered_by_the_later_scan_is_not_resolved` — a finding is only "fixed" for a class both scans examined; otherwise the comparison names the class "not comparable" |
| AC07 | security | `test_scan_cli.py::test_no_scanner_available_stops_with_setup_instructions_not_a_clean_result` (new) — exit 2, no findings file written, stderr carries install instructions (Semgrep/Trivy/Gitleaks) |
| AC09 | security | `test_normalizers.py::test_remediation_hint_says_the_credential_must_be_rotated` (new) — every gitleaks finding's `remediation_hint` says "rotate the credential", not merely "remove" |
| AC10 | security | `test_security_card.py::test_title_leads_with_the_severity_split_not_a_bare_total` — the card's title leads with "N critical, M below", never a bare "passed" |
| AC12 | security | `test_run_scan_and_report.py::test_appends_shipwright_entry_when_gitignore_exists_without_it` — detailed reports land under `.shipwright/securityreports/`, which is added to `.gitignore` — the findings do not travel with the code |
| AC13 | **not bound — recorded reason** | "'Fixed' only if the project's tests passed after the fix" is agent-executed remediation-loop prose (`references/remediation-loop.md`, steps 4-5: "Run tests... If tests pass -> mark as fixed"); `finding_classify.classify_finding` only buckets remediation DIFFICULTY (auto-fixable/agent-fixable/needs-review), it does not gate a "fixed" status on a subsequent test run — no module implements that gate. |
| AC14 | **not bound — recorded reason** | "The report carries the person's decision (fix/decline/defer) and the reason they gave" describes a human-recorded decision. `suppression-syntax.md` references "the accepted-risk register" carrying "a recorded decision and a rule-specific statement", but no module in `plugins/shipwright-security/scripts` parses or validates that register's decision/reason fields (searched `finding_classify.py`, `semgrep_tailoring.py`, `gitleaks_config.py`, `review_record_tier.py` — none implement it); recording the decision is itself agent/operator-executed, not a code path this test suite can invoke. |
| AC15 | security | `test_run_scan_and_report.py::test_writes_latest_md_and_latest_json` — the scan's own raw JSON output is durably written, unsummarized, at the path the audit-evidence phase reads |
| AC16 | security | `test_gitleaks_config.py::test_project_config_is_extended_by_absolute_path` — the project's own `.gitleaks.toml` (its accepted-findings register, kept with the project) is extended, not silently replaced |
| AC17 | security | `test_scan_cli.py::test_writes_default_sarif_files_on_clean_scan` — SARIF 2.1.0 files are written for every scanner source, the format GitHub's code-scanning security surface expects |
| AC18 | security | `test_finalize_security_compliance.py::test_finalize_skips_in_standalone_mode` — a repository without `shipwright_project_config.json` (not framework-managed) gets no compliance-snapshot commit at all; git HEAD is asserted unchanged, not merely a returned flag |

## No new test harness

No new pytest fixture pattern, mocking approach, or test-double strategy was
introduced. No new test FILES were created — every new test function was
added to a file already covering that exact production module, alongside its
existing sibling tests, using the same subprocess/direct-call idiom that file
already established.

## Verification performed

1. `uv run pytest plugins/shipwright-test/tests -q --junitxml=<scratch>/t4-shipwright-test.xml`
   — full green run (244 passed) of the FR-01.06 root.
2. `uv run pytest plugins/shipwright-security/tests -q --junitxml=<scratch>/t4-shipwright-security.xml`
   — full green run (1031 passed, 7 skipped) of the FR-01.07 root.
3. `uv run pytest shared/tests -q --junitxml=<scratch>/t4-shared.xml` — full
   green run of the third (waived) root (10622 passed, 32 skipped, 20
   deselected). One `pytest` process, one `--junitxml`, per root — ADR-044.
4. `uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py
   --project-root . --phase build --run-id iterate-2026-09-12-t4-test-security`
   — regenerated `.shipwright/compliance/test-traceability.json` from the live
   tree before touching the baseline.
5. `uv run shared/scripts/tools/check_ac_coverage_ratchet.py --project-root .
   --write` -> `unbound_count: 152` (from 177) — 25 FR-01.06/FR-01.07 entries
   resolved, 7 excepted with recorded reason (FR-01.06/AC02, AC05, AC07, AC12,
   AC18; FR-01.07/AC13, AC14). Verified directly (not by count math alone):
   ```
   FR-01.06 remaining unbound: AC02, AC05, AC07, AC12, AC18
   FR-01.07 remaining unbound: AC13, AC14
   ```
   read back from the regenerated `shipwright_ac_coverage_baseline.json`
   itself, confirming exactly the seven exceptions named above and no other
   FR-01.06/FR-01.07 entry — including confirming `FR-01.06/AC03` (the one
   edit in the waived third root, `shared/tests`) is no longer in that list.
   The four FR-01.07 ACs already bound before this unit (AC04, AC06, AC08,
   AC11, per the seam survey's precedent column) were never in `unbound` at
   any point in this run and are unaffected; their existing tests
   (`shared/tests/test_security_scan_card.py`,
   `plugins/shipwright-security/tests/test_gitleaks_extend_smoke.py`) ran
   green inside the full-root runs above (step 2, step 3).
6. `uvx ruff@0.15.15 check plugins/shipwright-test/tests
   plugins/shipwright-security/tests` — clean.
7. `git checkout -- .shipwright/compliance/{change-history.md,ci-security.json,
   dashboard.md,sbom.md,test-evidence.md,test-traceability.json,
   traceability-matrix.md} shipwright_compliance_config.json` — reverted the
   compliance-report regen sweep (step 4) after it had done its one job
   (feeding step 5's baseline write a fresh manifest), per t1/t2/t3 precedent.
   Verified via `git status --short` afterward: only
   `shipwright_ac_coverage_baseline.json` remained modified from that sweep
   (plus this mini-plan and the run's own `risk_recheck.json`, both genuine
   output of this unit).
8. Downstream-consumer check (external plan review, glm, low): `grep -rln
   "pytest.mark.covers\|fr_tag_grammar" shared/scripts/tools/verifiers
   shared/scripts/lib plugins/shipwright-compliance/scripts` — every consumer
   of `@covers` tags routes through `fr_tag_grammar.parse_python`, the same
   reader P3.2 already made backward-compatible ("a bare `FR-01.11` stays
   valid") for exactly this upgrade direction (bare -> qualified). No
   downstream tool special-cases a bare tag differently in a way this sweep
   could regress.

## External-Plan-Review-Findings (Step 3.5)

Both reviewers (glm via openrouter, openai via codex) reviewed the mini-plan
against the spec twice (before and after the AC01 strengthening below).

| # | Reviewer | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | openai | high/medium | Verification commands did not name `--junitxml` per ADR-044 | accepted-and-fixed — re-ran all three roots with `--junitxml=<scratch>/...`, results unchanged (244 / 1031+7skip / 10622+32skip); see "Verification performed" above. |
| 2 | openai | medium | FR-01.07/AC01 proved only the alias parser + hooks detector, not that the real scan chain reports breadth across all three infrastructure categories | accepted-and-fixed — `test_the_scan_examines_every_named_risk_category` now drives `scan.main()` end-to-end with a fake backend returning one finding per category and asserts the written report's `type`s cover all three, before the separate prompt-injection assertion. |
| 3 | openai, glm | medium/low | The seven exceptions' reasons are prose-only in this mini-plan; confirm they read back as reasoned exceptions in the regenerated baseline, not merely absent entries | accepted-and-fixed — see "Verification performed" step 5's explicit read-back of the seven remaining `FR-01.06`/`FR-01.07` unbound ids. The baseline schema itself (schema_version 1) has no per-entry reason field — same documented, campaign-wide gap t0's seam survey (Finding 5) and t3's mini-plan already recorded; not scoped to this unit to fix. |
| 4 | glm | medium | FR-01.06/AC02's completion-gate clause and AC12's regression-tracking clause might be provable with a cheap probe against `check_test_results_file_fresh` / `design_fidelity_check.py` | rejected-with-reason, after actually running the suggested probe — `check_test_results_file_fresh` (`shared/scripts/tools/verifiers/test_checks.py`) reads only `data.get("unit")`'s `total`/`passed`/`failed`/`skipped` counts; it has no per-layer "skip reason" field and no notion of overall phase completion. `design_fidelity_check.py` (read in full) computes purely from the current mockup + implementation on every call; it reads no prior-run artifact (`grep` for "design-fidelity-report"/"prior"/"previous" inside the module returns nothing) — there is no state for a second invocation to compare against. Both probes confirm, rather than merely assume, the original unbind reasoning. |
| 5 | glm | low | Confirm nothing downstream special-cases a bare `FR-xx.yy` tag in a way the bare->qualified upgrade could break | accepted-and-fixed — see "Verification performed" step 8. |
| 6 | openai | medium | `.gitignore` idempotency edge cases (duplicate/negated rules, already-tracked report dir) are not covered by the AC12 binding | acknowledged, out of scope for this AC's actual claim — AC12's text is "detailed findings stay in a place that does not travel with the code", proven by the bound test's core guarantee (a fresh `.gitignore` gains the entry). The bound test file (`test_run_scan_and_report.py::TestGitignoreBestEffort`) already has SEPARATE, pre-existing tests for exactly the edge cases named (`test_does_not_duplicate_when_shipwright_entry_already_present`, `test_does_not_double_write_when_legacy_entry_present`) — not new work this unit needs to add, and not part of what AC12 itself asserts. |
| 7 | openai | medium | Independently assert each risk category rather than one combined AC01 test, so a partial failure can't mask a missing category | rejected-with-reason — the strengthened test (finding #2 above) already asserts `types_examined == {"sast", "sca", "secret_detection"}` as a set-equality check: a missing OR an extra category both fail the assertion distinctly and are named in the failure diff; splitting into three tests would not add signal, only ceremony, for a single CLI invocation's output. |

## Self-Review

1. **Spec Compliance** — pass. Every bound AC's test asserts the exact
   behavior `spec.md`'s FR-01.06/FR-01.07 text describes (checked AC-by-AC
   against the literal wording, not the module's own docstrings). Every
   unbound AC has a reason grounded in a specific, quoted absence in the
   production code or reference doc, not a convenience skip.
2. **Error Handling** — pass. The new/strengthened tests exercise real error
   paths: a degraded scanner (exit 2), no backend configured (exit 2, setup
   instructions), a directory that cannot be reached (`--skip-if-missing`,
   `skip_reason` recorded), a malformed accepted-baseline file (still an
   error, not silently excused).
3. **Security Basics** — pass. No secrets introduced. Fixture "secrets"
   (`sk-...`, `_SECRET` dict literals) are pre-existing synthetic fixture data
   this unit did not add; `test_remediation_hint_says_the_credential_must_be_rotated`
   reads the SAME pre-existing `sample_gitleaks_output` fixture, adding no new
   fixture content.
4. **Test Quality** — pass. For every binding, the mini-plan's per-AC table
   states the specific mechanism the test exercises (real subprocess CLI,
   direct call to the actual production function) — the standing question
   asked before binding each one was "would this test fail if the production
   code broke in the way this AC describes", per this unit's own operating
   instructions; the seven unbound ACs are exactly the cases where that
   question's honest answer was no.
5. **Performance Basics** — pass. All new tests use `tmp_path`/subprocess with
   short timeouts (30s), no unbounded loops, no new fixtures larger than the
   existing ones in the same file.
6. **Naming & Structure** — pass. New test names follow each file's existing
   convention (`test_<behavior_in_plain_english>`); no new test file was
   created (see "No new test harness" above).
7. **Affected Boundaries (ADR-024)** — pass, none applicable. This unit adds
   test assertions and `@pytest.mark.covers` tags only; it introduces no new
   producer/consumer of a serialized format. Step 3.4's diff-driven re-check
   independently confirms this: `risk_flags: []`, `touches_io_boundary` not
   set.

## Internal Review Cascade (Step 3.7.1)

Diff size (195 LOC, working-tree vs branch point) is over the 100-LOC
threshold, so the cascade is triggered. `spec-reviewer` / `code-reviewer` /
`doubt-reviewer` are delegated to the orchestrator — this runner has no Agent
tool (SKILL.md contract). Recorded `not_run` with disposition
`delegated_to_orchestrator: runner has no Agent tool; cascade runs at
campaign-mode.md 3f-bis before merge` for `code` and `doubt`; `spec` recorded
`not_run` with `Stage-1 spec-review is run by the orchestrator, not this
sub-iterate runner (no Agent tool available here)`.

## External-Code-Review-Findings (Step 3.7.2)

Diff reviewed: full working-tree diff vs `HEAD` (no interim commit exists yet
for this run), via `review_scratch.py resolve` + `trap ... EXIT` cleanup, per
contract. Both providers returned `SHIPWRIGHT_VERDICT: revise`.

| # | Reviewer(s) | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | glm | medium | The seven excepted ACs' "recorded reason" lives only in this mini-plan's prose, not in any machine-readable field of `shipwright_ac_coverage_baseline.json` — a future consumer of the baseline alone can't distinguish "convenience skip" from "documented exception". | rejected-with-reason — documented, campaign-wide, pre-existing schema gap, not scoped to this unit: `shipwright_ac_coverage_baseline.json` (schema_version 1) is by its own `$comment` a flat grandfather `unbound` list with no per-entry reason field for ANY exception in this campaign. t0's seam survey (Finding 5), t2's mini-plan, and t3's mini-plan (Step 3.5 disposition #4, Step 3.7 disposition #5) already raised and dispositioned this identical concern the same way. A schema change is cross-cutting and out of scope for a test-binding unit. |
| 2 | glm | medium | `test_no_scanner_available_stops_with_setup_instructions_not_a_clean_result` assumes stderr is a JSON payload with `error.alternatives`, and worries `import json` may be missing from the file (the reviewer only sees the diff hunk, not the full file). | rejected-with-reason, empirically verified — `import json` is present at module scope (line 5, pre-existing); re-ran the test in isolation (`pytest tests/test_scan_cli.py -k test_no_scanner_available...`) and it passes, confirming `scan.main()` does emit the assumed JSON shape on stderr. A reviewer given only a diff hunk cannot see this; the production behavior is unchanged by this unit. |
| 3 | glm | low | `patch("scan.get_backend", ..., create=True)` will silently fabricate the attribute if `scan.get_backend` doesn't exist, masking a moved seam. | rejected-with-reason — this is the file's own established pattern, not a deviation introduced by this unit: every sibling `FakeBackend` test in `test_scan_cli.py` (`TestMainE2E`, `TestSarifDir`, etc. — 9 other call sites) already patches `scan.get_backend` with `create=True`. Matching file convention is correct; changing only the new test would be inconsistent, not safer. |
| 4 | glm | low | `test_every_normalizer_produces_the_same_required_shape`'s required-key set is the test's own invention, not derived from a shared schema the report writer consumes. | acknowledged, no change — accurate but out of scope: no shared schema constant exists to derive from (adding one would be new production code, not a test backfill). The test still proves the three normalizers currently agree, which is what AC02 claims. |
| 5 | glm | low | `test_skip_if_missing_records_not_run_with_a_reason_never_a_pass` asserts the literal string `"no tests/integration/ directory"`, brittle to a wording-only change. | acknowledged, no change — the behavioral assertions (`skipped`, `passed=0`, `total=0`) are the real proof; the string match is intentionally exact to also prove the reason names *which* directory, not just that a reason exists. |
| 6 | openai | medium | `FakeBackend.scan()` ignored `scan_types` and always returned findings for all three categories, so the AC01 test would still pass if `scan.main()` regressed to request only a subset by default. | accepted-and-fixed — `FakeBackend.scan()` now filters returned findings by the requested `scan_types` (defaulting to its `capabilities` when `None`); manually verified a narrowed request (`["sast"]`) now returns only the `sast` finding, so `types_examined == {"sast","sca","secret_detection"}` would fail under the regression the reviewer described. `plugins/shipwright-security/tests/test_scan_cli.py`. |
| 7 | openai | medium | AC12's tagged test only asserts a `.gitignore` line was appended, not that Git actually ignores the report path — a negating rule or an already-tracked report would still let the finding travel with the code. | accepted-and-fixed — `test_appends_shipwright_entry_when_gitignore_exists_without_it` now `git init`s a real repo, runs the real scan, and asserts `git check-ignore -q` on the actual written report path returns 0 — proving AC12's literal claim ("findings ... stay in a place that does not travel with the code") with real Git semantics instead of a string match. Probed separately (scratch, not committed): confirmed `git check-ignore` correctly reports "not ignored" (exit 1) for an already-tracked file, so this mechanism is the right one to catch that failure mode too, though a dedicated already-tracked fixture is not added here (new scope beyond AC12's default-path claim). `plugins/shipwright-security/tests/test_run_scan_and_report.py`. |

Re-ran both full roots after applying fixes 6 and 7: `plugins/shipwright-security/tests`
— 1031 passed, 7 skipped (unchanged pass count; fixes strengthen assertions,
add no new tests). Ruff clean on both edited files.

## Bloat baseline (F6 pre-commit hook)

The pre-commit anti-ratchet hook blocked the first commit attempt: 4 files
crossed their `grandfathered` (`state: grandfathered`, `adr: null`) LOC
baseline as a direct result of the new AC-proving tests and docstrings added
in this unit — each file was measured EXACTLY at its baseline `current`
before this unit's edits (confirmed via `git show HEAD:<path> | wc -l`), so
every added line is this unit's own legitimate growth, not pre-existing debt
resurfacing. Bumped `current` for all four (no ADR needed — that gate applies
to `state: exception` entries, not `grandfathered`; precedent: t1's PR #730
bumped a `grandfathered`-adjacent `exception` entry the same way for the same
reason, tag-driven test growth):

| File | Before | After |
|---|---|---|
| `plugins/shipwright-security/tests/test_finalize_security_compliance.py` | 340 | 345 |
| `plugins/shipwright-security/tests/test_run_scan_and_report.py` | 361 | 384 |
| `plugins/shipwright-security/tests/test_scan_cli.py` | 380 | 474 |
| `plugins/shipwright-test/tests/test_warning_followups.py` | 390 | 392 |
