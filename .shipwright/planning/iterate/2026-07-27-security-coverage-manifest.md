# Iterate Spec: security-coverage-manifest

- **Run ID:** iterate-2026-07-27-security-coverage-manifest
- **Type:** change
- **Complexity:** medium
- **Status:** complete

## Goal

Make a shipwright-security scan record what it did **not** look at, so a machine
with one scanner installed can no longer produce a report that reads clean for
every class of weakness.

## Ownership boundary

This card owns the **security plugin's scanner wiring and its report generator**.
It does **not** own workflow files: turning incomplete coverage into a pass/fail
verdict at the workflow step belongs to the card that owns the host checks, so
the two can run in parallel. This card **emits** the coverage data; that one
decides what CI does with it.

**Split note.** This started as a four-item card. The PR-Review gate fails closed
on a diff over 200,000 chars, and the four items together measured 288,963 — 1.44x
the cap — so it was split rather than overriding a security gate. This is part 1.
Part 2 (`iterate/security-scope-and-parity`, built after this merges) carries the three items that *consume*
the manifest: one accepted-findings answer per repository, comparison only over
shared ground, and the operator's severity split + scope question. Part 2 is
stacked on this one — every one of its items reads the coverage rows — so it lands
after this merges.

## Acceptance Criteria

- [x] **AC-1 — Name what was not checked.** A scan records one coverage row per
      weakness class (code flaws, vulnerable dependencies, leaked secrets, and any
      further class a backend offers). Each row carries exactly one status from a
      closed vocabulary: `covered`, `degraded` (the tool ran but its result cannot
      be trusted), `not_requested` (the caller excluded the class),
      `not_available` (the check could not run here). The manifest rides in
      `findings.json`, in the `.shipwright/securityreports/latest.json` sidecar,
      and is rendered in the Markdown report.
- [x] **AC-2 — A one-tool machine cannot read as clean.** When at least one class
      is `not_available` or `not_requested`, the report carries an
      incomplete-coverage banner naming those classes. A report whose manifest is
      empty or absent renders "Coverage not reported" — a state deliberately
      distinct from "Incomplete Coverage", and never an implied clean sweep.
- [x] **AC-3 — The manifest is untrusted on the way back in.** `--input` and
      `--input-from-cache` read it from a caller-supplied file, so it is
      normalized where it enters (non-dict rows dropped, control characters
      flattened, values capped) and flattened where it renders. Every sanitized
      status is inside the closed vocabulary; an unrecognized one coerces to
      `degraded` with the original preserved in `detail`, so an invalid status is
      never laundered into a fresh artifact.
- [x] **AC-4 — Coverage claims only what actually happened.** `degraded` is
      derived from what became of the leg (a valid zero-finding report stays
      `covered`; exit-0-with-unparseable-output does not). The prompt-injection
      row reads `covered` only when its output was actually read, never from the
      mere presence of `--prompt-risks`. `--input`'s manifest is authoritative
      including its absence — it never inherits the local config's coverage.
- [x] **AC-5 — No file crosses its bloat baseline.** Every touched file with a
      `shipwright_bloat_baseline.json` entry ends at or below its recorded
      `current`; new logic lands in new modules under 300 LOC.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.07 — /shipwright-security. One new (E) acceptance criterion:
  naming the classes that were never checked. This is distinct from the existing
  criterion about a check that *fails* — a crashing tool already records a
  `scan_errors` marker and fails the run; a tool that was never installed
  produced no leg at all and was invisible.
- **ADD / REMOVE:** none.

**MINT-vs-FOLD:** FOLD. A new guarantee of an existing capability becomes an
acceptance criterion on FR-01.07, not a new row.

## Out of Scope

- Turning incomplete coverage into a **CI verdict** — the sibling host-checks
  card owns `.github/workflows/**`.
- Failing the local scan when a tool is absent. The ask was to *name* what was
  not checked; the run still completes. The manifest is the data a gate would
  read, and that gate lives with the host checks.
- The three consumers of the manifest (accepted-findings parity, coverage-gated
  comparison, the operator's scope question) — part 2.
- Bumping `JSON_SIDECAR_SCHEMA_VERSION`. Its documented contract is "existing
  top-level fields stay stable; new fields may be added", so `coverage` is
  additive and the version stays `1`.

## Design Notes

Six new modules under `plugins/shipwright-security/scripts/lib/`, each well under
300 LOC. Three carry the feature; three are extractions the bloat gate forces —
every file this touches is baselined ABOVE the 300-LOC cap, and the anti-ratchet
hook blocks any commit where a baselined file exceeds its recorded `current`, so
a feature that adds lines must first remove them.

| New module | Feature or gate-forced | Responsibility |
|---|---|---|
| `scan_coverage.py` | feature | class↔tool map, closed status vocabulary, `build_coverage()` pure derivation, `finding_class()` |
| `coverage_sanitize.py` | feature | the untrusted-input boundary for a file-sourced manifest |
| `coverage_report.py` | feature | Markdown banner + per-class table |
| `security_triage_emit.py` | gate-forced | per-finding mirrors moved verbatim out of `generate_security_report.py` (665→647) |
| `scan_history.py` | gate-forced | archive id, listing, pruning — makes room in `run_scan_and_report.py` (334→300) |
| `sarif_outputs.py` | gate-forced | per-source SARIF writing — makes room in `scan.py` (431→425) |

### The derivation, and why it is not a channel

`build_coverage()` is a **pure function of `(capabilities, scan_types,
scan_errors)`** — all data the caller already holds — so both `scan.py` and
`run_scan_and_report.py` derive the same manifest without any backend changing.

**Alternative rejected:** have each backend own and populate a `scan_coverage`
attribute, mirroring the existing `scan_errors` channel. `scan_errors` has to be
backend-populated because only the runner knows a leg fataled, whereas coverage is
fully determined by data the caller already has. A channel adds a second place to
keep in sync, forces every backend and test mock to grow the attribute, and leaves
an empty manifest — which reads as reassuring — as the default for anything that
forgot. A derivation cannot forget.

### Where "not reported" differs from "incomplete"

Nothing synthesizes a row onto an empty manifest just to have one. Appending a
`not_requested` prompt-injection row to an absent manifest would convert *we do
not know what was checked* into *we know, and one class is outstanding* — a claim
about classes nobody measured. A `covered` row is different: the prompt scan
genuinely ran, so recording it adds knowledge rather than manufacturing it.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `scan.py::build_config` | `generate_security_report.py`, `.github/workflows/security.yml` (jq), `shared/scripts/security_findings.py` | `findings.json` — gains additive `coverage` |
| `generate_security_report.py::build_json_sidecar` | `run_scan_and_report.py`, SKILL.md Step 6 readers | `latest.json` sidecar — gains additive `coverage` |
| `run_scan_and_report.py` | the archived-sidecar readers | `history/scan-*.json` — same shape |
| `scan.py --input-from-cache` | `scan.py` (re-emit) | the manifest round-trip |

`touches_io_boundary` fires (JSON producer/consumer pairs + `*_config.json`), so
round-trip tests are mandatory — see Confidence Calibration.

## Confidence Calibration

- **Boundaries touched:** the four producer/consumer pairs above.

- **Empirical probes run:**
  - *Scanner absence in practice:* `semgrep`, `trivy` and `gitleaks` are all
    absent on this machine, so every local report before this change read clean
    for all three classes. After it, the manifest names all three
    `not_available`. The motivating bug is reproducible here by doing nothing.
  - *Is the bloat gate real?* Ran `anti_ratchet_check.py --worktree`; it BLOCKED
    on files my earlier mid-work baseline sync had under-recorded. Re-synced
    against the ORIGINAL grandfathered values with an assert that no file may
    exceed where it started, and trimmed prose instead of raising a baseline.
  - *Does the split hold?* Measured the reviewable diff with the gate's own
    `filter_generated_paths`: 115,001 chars against the 200,000 cap (0.58x), so
    this half will not truncate the review that the four-item version did.

- **Test Completeness Ledger:** every behavior this diff introduces →
  `tested` (evidence) or `untestable` (closed-vocabulary `reason_code`).
  0 testable-but-untested. Machine-readable form in
  `shipwright_test_results.json.iterate_latest.test_completeness`.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the motivating failure is pinned by a test that fails if
    the derivation is removed (`test_one_installed_tool_names_the_other_two`). An
    external code review then found four further ways to be quietly wrong —
    `--input` inheriting the local config's coverage, the prompt row trusting a
    flag instead of a parsed file, a manifest treated as trusted on the way back
    in, and an out-of-vocabulary status re-emitted into a fresh artifact. Each is
    now its own test.
  - *Coverage (breadth):* 549 tests pass in the plugin suite (+45 new); F0 green across all
    18 units; ruff clean.
  - *Integration composition:* `cross_component` does NOT fire — no hooks, no
    merge/churn/event-log resolver, no phase validator, no campaign machinery.
    `touches_ci_supplychain` does not fire either: no `.github/workflows/**`,
    `.github/actions/**` or `dependabot.yml` path is in the diff, which is the
    ownership boundary this card was given. `touches_io_boundary` DOES fire and is
    answered by round-trip tests that write with the real producer and read with
    the real consumer rather than asserting against a hand-built fixture.
