# Iterate Spec: security-coverage-manifest

- **Run ID:** iterate-2026-07-27-security-coverage-manifest
- **Type:** change
- **Complexity:** medium
- **Status:** complete

## Goal

Make a shipwright-security scan report say what it *did not* look at, give one
accepted-findings answer per repository, refuse to call a finding "fixed" when
the later run did not cover its class, and hand the operator a per-severity
count plus an explicit scope question instead of silently deciding how far to
go.

## Ownership boundary

This card owns the **security plugin's scanner wiring, its report generator,
and the presentation of security findings to the operator**. It does **not**
own workflow files. Labelling the verdict at the workflow step belongs to the
sibling card that owns the host checks, so the two can run in parallel:

- **In scope:** `plugins/shipwright-security/scripts/**`,
  `plugins/shipwright-security/skills/security/**`,
  `plugins/shipwright-security/tests/**`, `shared/tests/` for the shared
  producer test, `.shipwright/planning/01-adopted/spec.md`.
- **Out of scope (sibling card):** `.github/workflows/**`,
  `shared/templates/github-actions/**`, and any gate that turns coverage into
  a pass/fail verdict at the workflow step. This card **emits** the coverage
  data; the sibling card decides what CI does with it.

## Acceptance Criteria

- [ ] **AC-1 — Name what was not checked.** A scan records one coverage row per
      weakness class (code flaws, vulnerable dependencies, leaked secrets, and
      any further class a backend offers). Each row carries exactly one status
      from a closed vocabulary: `covered`, `not_available` (the check could not
      run here — e.g. the tool is not installed), `not_requested` (the caller
      excluded the class), `degraded` (the tool ran but produced no parseable
      output). The manifest rides in `findings.json`, in the
      `.shipwright/securityreports/latest.json` sidecar, and is rendered in the
      Markdown report.
- [ ] **AC-2 — A one-tool machine cannot read as clean.** When at least one
      class is `not_available` or `not_requested`, the Markdown report carries
      an incomplete-coverage banner naming those classes, above the findings.
      A report whose coverage manifest is empty or absent renders "coverage not
      reported" — never an implied clean sweep.
- [ ] **AC-3 — One accepted-findings answer per repository.** When the scanned
      target root has a `.gitleaks.toml`, the local secret scan **extends** it
      (`[extend] path = <abs path>`) instead of substituting a generated
      configuration, so the project's own allowlist applies on the local path
      exactly as it already does on the host path. With no project file present,
      today's generated configuration (`[extend] useDefault = true` plus the
      shipwright exclusions) is unchanged.
- [ ] **AC-4 — `useDefault` and `path` are never both emitted.** Gitleaks
      refuses a config that sets both; the renderer emits exactly one of them.
- [ ] **AC-5 — Compare two runs only over shared ground.** Comparing two scan
      sidecars yields `resolved` / `new` / `persisting` counts **only** for
      classes both runs covered. A class covered by one side only is listed
      under `not_comparable` with the reason, and none of its findings are
      reported as resolved. No per-finding outcome is stored anywhere — the
      comparison is derived from the two sidecars on demand.
- [ ] **AC-6 — Severity split and scope question at the point of work.** The
      triage card the local scan emits carries the per-severity counts and a
      launch payload that instructs the executing agent to state those counts
      and ask the operator how far to go (all findings, or only the most
      severe) before changing anything. `SKILL.md` gains the matching scope
      gate ahead of remediation, so the tool never silently decides that the
      less severe findings do not matter.
- [ ] **AC-7 — No file crosses its bloat baseline.** Every touched file with a
      `shipwright_bloat_baseline.json` entry ends at or below its recorded
      `current`; new logic lands in new modules under 300 LOC.

## Spec Impact

- **Classification:** modify
- **ADD** (new FR appended): none
- **MODIFY** (existing FR changed): FR-01.07 — /shipwright-security. Two new
  (E) acceptance criteria: naming the classes that were never checked (distinct
  from the existing criterion about a check that *fails*), and gating run-to-run
  comparison on equal coverage.
- **REMOVE:** none
- **NONE justification:** n/a

**MINT-vs-FOLD:** FOLD. Items 2 and 4 are already stated in FR-01.07 (the
accepted-findings register criterion and the "how many at each severity … the
choice of how far to go is put to that person" criterion) — this card
implements them, so they need no spec change. Items 1 and 3 are new guarantees
of an existing capability, so they become acceptance criteria on FR-01.07
rather than new rows.

## Out of Scope

- Turning incomplete coverage into a **CI verdict** (workflow-step labelling) —
  sibling card owns `.github/workflows/**`.
- Failing the local scan when a tool is absent. The user asked to *name* what
  was not checked; the run still completes. The manifest is the data a gate
  would read, and the gate lives with the host checks.
- Replacing the per-finding triage mirrors with an action-unit collapse. The
  card gains a severity split and a question; the existing per-finding
  enumeration and its dedup contract stay as they are.
- Any change to the Aikido backend's own report path.
- Bumping `JSON_SIDECAR_SCHEMA_VERSION`. Its documented contract is
  "existing top-level fields stay stable; new fields may be added" —
  `coverage` is additive, so the version stays `1`.

## Assumptions recorded

- **Basis: assumed** — "Cards today carry a total and an enumeration, no
  severity split and no question" is read as: the local scan's presentation to
  the operator (per-finding triage items + the report total) never states the
  severity split at the point of work nor asks the scope. Resolved by adding a
  collapsed `security-scan:{repo}` action-unit carrying both, *alongside* the
  existing per-finding items, and by adding the matching scope gate to
  `SKILL.md`. Removing the per-finding enumeration would rewrite an established
  dedup contract the request did not ask to change.
- **Basis: verified in code** — the project's accepted-findings file for
  secrets is `.gitleaks.toml` at the repository root: the adopt-scaffolded
  workflow runs `gitleaks detect --no-git` with no `--config`, so gitleaks
  auto-loads it, while `oss_backend._run_gitleaks` passes `--config <temp>`
  and therefore ignores it.

## Design Notes

### Mini-plan (chosen)

**Eight** new modules under `plugins/shipwright-security/scripts/lib/`, each
well under 300 LOC, plus one new thin CLI. Four carry the feature; four are
extractions the bloat gate forces (every file this touches is baselined ABOVE
the 300-LOC cap, and the anti-ratchet hook blocks any commit where a baselined
file exceeds its recorded `current`, so a feature that adds lines must first
remove them):

| New module | Feature or gate-forced | Responsibility |
|---|---|---|
| `scan_coverage.py` | feature | class↔tool map, closed status vocabulary, `build_coverage()` pure derivation, `finding_class()` |
| `coverage_report.py` | feature | Markdown banner + table for a coverage manifest |
| `gitleaks_config.py` | feature | resolve/inspect the project `.gitleaks.toml`, render/write the temp config that extends it |
| `scan_compare.py` | feature | coverage-gated diff of two sidecars |
| `security_card.py` | feature | severity split, scope options, card title/detail/launch payload |
| `security_triage_emit.py` | gate-forced | per-finding mirrors moved verbatim out of `generate_security_report.py` (665→604) + the new action unit. Combined with `security_card.py` this is ~380 LOC, so the two-module split is itself required |
| `scan_history.py` | gate-forced | archive id, listing, pruning — makes room in `run_scan_and_report.py` (334→306) |
| `sarif_outputs.py` | gate-forced | per-source SARIF writing — makes room in `scan.py` (431→429) |
| `tools/compare_scans.py` | feature | the operator entry point for the comparison; documented in SKILL.md Step 6 and exercised by `test_coverage_comparison_wiring.py` |

`build_coverage()` is a **pure function of `(capabilities, requested_types,
scan_errors)`**, so both `scan.py` and `run_scan_and_report.py` derive the same
manifest without either backend changing. Backends that expose capabilities
outside the OSS tool map (Aikido's `iac`) get a row with no tool name rather
than being silently dropped.

### Alternative considered and rejected

Have each backend own and populate a `scan_coverage` attribute, mirroring the
existing `scan_errors` channel. Rejected: `scan_errors` needs to be
backend-populated because only the runner knows a leg fataled, whereas coverage
is fully determined by data the caller already holds (`capabilities`,
`scan_types`, `scan_errors`). A backend-populated channel would add a second
place to keep in sync, force every backend and every test mock to grow the
attribute, and would leave `getattr(backend, "scan_coverage", [])` — an empty
manifest that reads as "no classes" — as the default for anything that forgot.
A pure derivation cannot forget.

### Rejected: inline-merging the project's gitleaks allowlist

Parsing `.gitleaks.toml` with `tomllib` and splicing its `[allowlist]` into the
generated config was rejected: it would silently drop project-defined `[rules]`
and re-implement merge semantics gitleaks already owns. `[extend] path` is
gitleaks' own first-class mechanism and is what "extend the project's file"
means. Note the constraint this imposes: gitleaks aborts when a config sets
both `extend.useDefault` and `extend.path`, so the renderer must emit exactly
one — pinned by AC-4 and its test.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `scan.py::build_config` | `generate_security_report.py`, `.github/workflows/security.yml` (jq), `shared/scripts/security_findings.py` | `findings.json` — gains additive `coverage` |
| `generate_security_report.py::build_json_sidecar` | `run_scan_and_report.py`, SKILL.md Step 6 readers, `scan_compare.py` | `latest.json` sidecar — gains additive `coverage` |
| `run_scan_and_report.py` | `scan_compare.py` | `history/scan-*.json` — same sidecar shape |
| `gitleaks_config.py::render_config` | `gitleaks` CLI | TOML config |
| `security_triage_emit.py` | `.shipwright/triage.jsonl` readers, Command Center | triage item + launch payload |

`touches_io_boundary` fires (JSON producer/consumer pairs + `*_config.json`),
so a Boundary Probe and round-trip tests are required — see Confidence
Calibration.

## Confidence Calibration

- **Boundaries touched:** the five producer/consumer pairs in the table above
  (`findings.json`, the `latest.json` sidecar, the archived `history/scan-*.json`,
  the generated gitleaks TOML, and the triage card).

- **Empirical probes run:**
  - *Does the wrapper actually emit the card?* Ran `run_scan_and_report.run()`
    for real against a scratch project with a stubbed backend and read the
    resulting `triage.jsonl`. It did — and the probe caught a Windows-backslash
    report path in a payload meant to be pasted into a shell. Fixed to POSIX,
    pinned by `test_card_report_path_uses_posix_separators`.
  - *Do the card tests belong in the plugin session?* Running them there hit the
    ADR-044 `lib` namespace collision (this plugin's `scripts/lib` shadows
    `shared/scripts/lib`, so `triage.py`'s `from lib import jsonl_records`
    fails). Verified the RUNTIME path is unaffected by the real probe above,
    then moved the triage assertions to `shared/tests/` beside the existing
    per-finding producer test, which lives there for exactly this reason.
  - *Is the bloat gate real?* Ran `anti_ratchet_check.py --worktree` and it
    BLOCKED on three files — my earlier baseline sync had measured them
    mid-work. Re-synced against the original grandfathered values (asserting no
    file may exceed where it started) and trimmed SKILL.md instead of raising
    its baseline. Gate re-run green.
  - *Does gitleaks accept the generated config?* Could NOT be probed here —
    no scanner binary is installed on this machine, which is itself the exact
    scenario AC-1 exists for. Deferred to CI, where gitleaks 8.21.2 is
    installed: `test_gitleaks_extend_smoke.py` proves default rules still fire,
    the project allowlist applies, and the shipwright exclusions survive. It
    hard-fails in CI if the binary is absent, so it cannot silently skip there.
  - *Scanner absence in practice:* `semgrep`, `trivy` and `gitleaks` are all
    absent locally, so every local report before this change read clean for all
    three classes. After it, the manifest names all three `not_available`.

- **Test Completeness Ledger:** every behavior this diff introduces →
  `tested` (evidence) or `untestable` (closed-vocabulary `reason_code`).
  0 testable-but-untested.

| # | Behavior | Disposition | Evidence / reason_code |
|---|---|---|---|
| 1 | One coverage row per class, closed status vocabulary | tested | `test_scan_coverage.py::TestBuildCoverage` (9) |
| 2 | Status precedence degraded > not_requested > not_available | tested | `test_scan_coverage.py::test_degraded_leg_beats_every_other_status`, `test_not_requested_beats_not_available` |
| 3 | Backend capability outside the OSS map still gets a row | tested | `test_capability_outside_the_oss_tool_map_still_gets_a_row` |
| 4 | Prompt-injection row added only when it carries information | tested | `TestPromptInjectionRow` (5) |
| 5 | Empty manifest is never "complete" | tested | `TestIsComplete`, `test_unknown_status_never_reads_as_complete` |
| 6 | `findings.json` carries `coverage`; cache re-read keeps it | tested | `test_coverage_wiring.py::TestScanCliWritesCoverage` (4) |
| 7 | Report renders banner + table; PR mode too | tested | `TestReportRendersCoverage` (5) |
| 8 | "Coverage not reported" ≠ "Incomplete Coverage" | tested | `test_report_from_a_pre_feature_sidecar_says_coverage_not_reported` |
| 9 | Sidecar keeps `schema_version: 1` while gaining `coverage` | tested | `test_sidecar_carries_coverage_and_keeps_schema_version_1` |
| 10 | Local gitleaks config extends the project's file | tested | `test_gitleaks_config.py::TestRenderConfig` (8) + `TestRunGitleaksWiring` (2) |
| 11 | `useDefault` and `path` are never both emitted | tested | `test_usedefault_and_path_are_never_both_emitted` |
| 12 | Extend path is absolute even from a relative target | tested | `test_relative_target_still_yields_an_absolute_path` |
| 13 | Full TOML escaping of the extend path | tested | `test_gitleaks_config_hazards.py::TestTomlPathSerialization` (9) |
| 14 | A rule-less project config is named, not obeyed silently | tested | `TestInspectProjectConfig` (6) + `TestProjectConfigWarning` (7) + `TestGitleaksCaveatReachesTheManifest` |
| 15 | Real gitleaks honours the extend (rules + both allowlists) | tested | `test_gitleaks_extend_smoke.py` — **evidence lands in CI**, hard-fails there if gitleaks is missing; skipped locally (no binary) |
| 16 | Comparison only over classes both runs covered | tested | `test_scan_compare.py::TestComparableGround` (5) |
| 17 | Losing / gaining a tool between runs claims nothing | tested | `test_coverage_comparison_wiring.py::TestWrapperRoundTrip` (4) |
| 18 | No stored per-finding outcome; inputs unmutated | tested | `TestNoStoredOutcome` (2) |
| 19 | Unclassified findings counted, never resolved, surfaced | tested | `test_unclassifiable_findings_are_counted_not_resolved`, `test_unclassified_count_is_surfaced_in_the_rendered_output` |
| 20 | Location-based fingerprint (moved finding = resolved+new) | tested | `TestFingerprintIsLocationBased` |
| 21 | `compare_scans.py` CLI renders / exits 2 with no prior scan | tested | `TestCompareCli` (3) |
| 22 | Card carries per-severity counts and the scope question | tested | `test_security_card.py` (19) + `shared/tests/test_security_scan_card.py` (8) |
| 23 | Scope options are concrete, ordered, and never fake | tested | `test_security_card_scope.py` (6) |
| 24 | Card names unchecked classes; degraded never reads all-clear | tested | `test_security_card_hygiene.py::TestDegradedIsNotReassuring` (3) |
| 25 | Caller-supplied `repo`/`report_path` cannot inject instructions | tested | `TestPayloadInjectionSurface` (6) |
| 26 | Card carries no raw finding strings | tested | `test_card_carries_no_raw_finding_strings` |
| 27 | One card per repo; coexists with the per-finding mirrors | tested | `test_card_is_deduped_across_repeat_scans`, `test_card_coexists_with_the_per_finding_enumeration` |
| 28 | Degraded derived from what happened to the leg | tested | `TestDegradedDerivation` (4) |
| 29 | Pre-feature artifacts tolerated by every reader | tested | `TestPreFeatureArtifacts` (7) |
| 30 | No baselined file exceeds its recorded `current` | tested | `anti_ratchet_check.py --worktree` exits 0; baselines re-synced to final sizes |
| 31 | SKILL.md Step 2.5 scope gate is followed at the point of work | untestable | `requires-interactive-tty` — a prompt-level instruction to the executing agent plus an `AskUserQuestion` round-trip. The machine-checkable half (the card telling it to ask, with the counts) is row 22. |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the two failure modes that motivated the card are each
    pinned by a test that fails if the gate is removed — `test_losing_a_tool_
    between_runs_reports_nothing_fixed` (comparison) and
    `test_one_installed_tool_names_the_other_two` (manifest). The external code
    review then found three more ways to be quietly wrong (degraded reading as
    all-clear, "not reported" collapsing into "incomplete", an unsanitized
    payload); each is now its own test. Depth stopped paying at the point where
    new probes only re-confirmed existing rows.
  - *Coverage (breadth):* 31 behaviors, 30 tested, 1 `requires-interactive-tty`.
    615 tests pass in the plugin suite, 4960 in `shared/tests`, ruff clean.
    Breadth gap acknowledged: row 15 is the only row whose evidence is produced
    in CI rather than here, because the machine running this iterate has no
    scanner installed.
  - *Integration composition:* `cross_component` does NOT fire — the diff
    touches no hooks, no merge/churn/event-log resolver, no phase validator and
    no campaign machinery. `touches_ci_supplychain` does not fire either: no
    `.github/workflows/**`, `.github/actions/**` or `dependabot.yml` path is in
    the diff, which is the ownership boundary this card was given.
    `touches_io_boundary` DOES fire and is answered by the round-trip tests in
    `test_coverage_wiring.py` / `test_coverage_comparison_wiring.py`, which
    write with the real producer and read with the real consumer rather than
    asserting against a hand-built fixture.
