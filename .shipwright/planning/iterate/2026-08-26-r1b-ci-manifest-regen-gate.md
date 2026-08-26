# Iterate Spec: r1b-ci-manifest-regen-gate

- **Run ID:** iterate-2026-08-26-r1b-ci-manifest-regen-gate
- **Type:** feature
- **Complexity:** medium
- **Status:** implemented

## Goal

Close the second half of SPEC D8 (`Spec/design/2026-07-22-req3-campaign-SPEC.md`
§4 P0a / §5 P3.0, campaign `req3-04-ac-identity-mono`, REQ3.04b /
`trg-8d6b49d9`): CI regenerates `.shipwright/compliance/test-traceability.json`
from a real, full test run and reports when the committed manifest has drifted
from what the tree's tests actually prove — first as a visible, non-blocking CI
annotation, hardening to a hard gate only after several consecutive green PRs.
Precondition (REQ3.04a, `trg-a8f4b029`) is merged (PR #648/#649/#650) and its
required measurement (`iterate-2026-08-25-r1a-evidence-staging-multiroot.md`)
answered the two open questions this unit needs: which manifest fields are
reproducible across independent regens (Q1), and how marker selection / OS /
interpreter affect manifest content (Q2).

## Acceptance Criteria

- [x] AC1: A new comparison tool (`shared/scripts/tools/compare_traceability_manifest.py`)
  compares two `test-traceability.json` documents in TWO tiers, not one flat
  diff (revised after Internal Plan Review — see below):
  - **Structural tier (enforced):** every top-level key except `generated_at`
    and `source_commit`, and every per-requirement field EXCEPT the entire
    nested `tests` map AND `coverage` — `id`, `spec_path`, `title`, `priority`,
    `status`, `required_layers`, `required_layers_source`, plus `orphans`/
    `invalid_tags`/`invalid_layers`/`untagged_tests`/`schema_version`/
    `collector_version`/`spec_hash`. **`tests` is excluded WHOLESALE from this
    tier — not just its `status`/`.executed` leaves** (External Review, both
    reviewers independently: comparing the map with only those two leaves
    dropped still compares its KEY SET, so a test id present on only one
    platform is a structural key mismatch and re-introduces the exact
    false-positive AC1 exists to prevent — the tests map belongs to the
    execution tier ENTIRELY, never the structural one). **`coverage` is
    excluded for the same reason, verified empirically against the real
    computation** (`_test_links_requirements.py::_cov_status`:
    `passing = any(l["status"]=="enabled" and l["executed"]=="pass" for l in
    links)`) — it is a pure function of `tests` + `required_layers`, so it
    inherits the identical platform-dependence; leaving it in the structural
    tier would silently reopen the same bug one level up, at exactly the kind
    of aggregate cell SPEC P0a's own AC names ("Mindestens eine Coverage-Zelle
    liest `ok`"). No separate execution-tier logic is needed for `coverage`
    itself — since it derives entirely from `tests` + the (structural, always
    compared) `required_layers`, the tests-level execution-tier report below
    already explains any `coverage` difference an operator would want to
    understand. These are the fields R1a's Q1 actually measured as
    reproducible; a mismatch here is always a `--check` failure.
  - **Execution tier (reported, not gating during this iterate):** compare
    over the INTERSECTION of test ids present in both manifests' `tests`
    maps — `status`/`executed` must agree for each shared id; a real mismatch
    here (a test the committed manifest claims passed but the fresh run shows
    otherwise) is exactly what SPEC P0a's AC exists to catch. A test id
    present in only ONE manifest is reported separately as a
    platform-selection difference (Windows-local F0 vs Linux-CI collect/skip
    differently — real, per R1a's Q2 and confirmed by 34
    `skipif(...win32...)` occurrences across 8+ files in this repo) and never
    counted as drift, by construction (it is never compared structurally at
    all, per the fix above — not merely excluded from the exit-code
    decision). Both sub-cases are printed, clearly labeled, but the tool's
    exit code during this iterate is driven by the structural tier only — the
    execution tier is genuinely new empirical data (no prior measurement
    covers it; R1a's Q1 ran with `evidence={}` on both sides) and its
    behavior across real CI runs is exactly what the advisory period is for.
    Refining/hardening the execution tier is out of scope for this unit.
  - **Exit-code contract (External Review, deepseek):** `0` = no structural
    drift, `1` = structural drift found (the advisory case — CI treats this
    as non-blocking), `2` = usage/runtime error (malformed input, a missing
    required field, a crash) — CI must NOT swallow `2` the way it swallows
    `1`; a broken comparator must fail the step for real, not read as a
    silent clean pass.
  - Pinned by a unit test (`shared/scripts/tools/tests/
    test_compare_traceability_manifest.py`) that explicitly covers: a shared
    test id with differing `status`; a shared id with differing `executed`;
    a one-sided id on either side (never gating); and a malformed/missing-field
    manifest failing loudly with exit `2`, never reading as a clean `0`
    (External Review, openai — the earlier test list didn't cover any of
    these, including the one case this whole unit exists to catch).
- [x] AC2: `run_test_suite.py` (F0's suite runner) retains each unit's OWN
  JUnit report on a green run — not only on failure as today — under a stable,
  per-run location (mirroring the existing failed-attempt diagnostics location
  pattern), alongside a small side-manifest recording each unit's
  `(unit_id, base, report_path)` triple. The base comes from `plan_root()`,
  **extracted during Build** into `shared/scripts/lib/suite_root_plan.py`
  (`RootPlan`/`plan_root`/`plan_all_roots`, pure — no subprocess, no I/O
  beyond `Path.relative_to`) — a genuinely shared module both this file's
  retention code AND ci.yml's AC4 step import, rather than each re-deriving
  the same rule. `run_full_suite_evidence.py` now imports and re-exports the
  same three names, verified byte-for-byte behavior-preserving (its own
  17-test suite, unchanged, still green; a new direct-import test,
  `shared/tests/test_suite_root_plan.py`, pins the module's standalone
  importability and that the re-export is a real alias — `is`, not a copy).
  **Not** a fresh derivation from `discover_test_roots`, which returns a bare
  path set with no base logic at all (Internal Plan Review corrected this).
  F0's own unit discovery (`suite_units.discover_units`) is a
  THIRD, independently-hardcoded list; a parity test (mirroring the existing
  `test_f0_ci_parity.py`) asserts it matches `discover_test_roots` so a future
  new root can't silently diverge between the two. Retry/race rule: the
  authoritative attempt's report (the serial retry's, when one ran) supersedes
  the initial parallel attempt's, and the side-manifest records that attempt's
  OUTCOME (pass/test_failure/infra) alongside the report path — not just that
  a file exists (External Review, both reviewers: a fully-reported but red
  run must be distinguishable from a green one). No second full pytest pass is
  introduced anywhere in the local iterate flow — the reports F0 already
  produces are what gets staged. Reports and the side-manifest are written to
  a per-run TEMPORARY subdirectory and atomically published (renamed into
  place) only once every unit has a final outcome recorded (External Review,
  openai — an interrupted or concurrent F0 run must never leave a
  partially-written side-manifest readable by a staging call, and pruning must
  never delete a run still being written). Retained run directories are
  pruned to the last N=5 PUBLISHED (not in-progress) runs so local disk usage
  does not grow unbounded.
- [x] AC3: A new script (`shared/scripts/tools/stage_f0_evidence.py`) reads
  that side-manifest and stages every retained report via
  `evidence_drop.stage_reports` (the R1a multi-report API, one call, exact
  bases) — no report is re-generated, only relocated/staged. `--run-id` and
  `--head-commit` are REQUIRED (no defaults) so a wrong/missing value fails
  loud instead of silently degrading the F11 cross-layer gate to `MISSING`
  everywhere (`_layer_coverage_evidence.fresh_evidence` trusts staged evidence
  only when provenance matches). The script refuses to stage unless the side-
  manifest shows EVERY discovered unit has a report AND every recorded outcome
  is `pass` (External Review, both reviewers — AC2 already says "on a green
  run"; this enforces it rather than only checking report-presence, which
  would let a fully-reported red run stage as if it were complete evidence).
  Before staging, the side-manifest itself is validated: unique unit ids
  (**not** unique bases — the `shared/tests`/`shared/scripts/tests`/
  `shared/scripts/tools/tests`/`integration-tests` units all legitimately
  share `base=""` in every healthy run, since `base_for_root` only returns a
  non-empty base for a `plugins/<name>/tests` root; requiring unique bases
  would make this script refuse every real F0 run it will ever see —
  corrected during Step 8 re-review after the External-Code-Review-Findings
  table's rejected-with-reason #2/#6 pointed out this text still promised a
  validation the code correctly does not perform), and every `report_path`
  resolves to an existing regular file beneath the expected run directory —
  no path traversal, no unexpected entries (External Review, openai). This is
  the ONLY staging call for a run that went
  through F0 — F5.md documents it as replacing (not adding to) the existing
  generic multi-`--junit` staging example for that case, since
  `evidence_drop.stage_reports` clears the evidence dir first and two staging
  calls in one run would race. `test_links.generate_file()` run immediately
  after produces a manifest whose evidence is backed by the SAME full-suite
  run F0 already performed.
- [x] AC4: `.github/workflows/ci.yml`'s three existing pytest invocations
  (plugin loop, shared-tier loop, integration-tests step) each pass
  `--junit-xml` to a scratch path named by the SAME filename convention
  `plan_root()` produces (recovered by a small Python helper at staging time —
  no hand-maintained base-to-path mapping in YAML). A new step, placed at the
  END of the `python-checks` job (after "Sweep delivery surface (gate)", so a
  step that intentionally mutates the tracked manifest and the evidence dir
  cannot affect any other gate) does, in order: (a) recover the base for every
  staged report from its filename and assert that set equals EXACTLY the
  expected full root/base set from the same shared planner AC2 uses — missing,
  duplicate, or unexpected entries fail the step (External Review, both
  reviewers — nothing today verifies the three existing pytest steps
  collectively cover every root; a silently-dropped root would either read as
  false structural drift or get masked as a "platform-selection difference"
  it is not); (b)-(e) are one call to a new script,
  `shared/scripts/tools/ci_manifest_drift_check.py` — `git show
  HEAD:.shipwright/compliance/test-traceability.json` to a scratch path (the
  committed baseline, captured before it gets overwritten), stage the CI
  run's JUnit reports, call `test_links.generate_file()` (regenerates the
  TRACKED file in place — it has no scratch-output parameter, confirmed
  against the real signature; the working tree is intentionally left dirty,
  harmless since nothing runs after it), then call
  `compare_traceability_manifest`'s comparison functions directly (same
  process, no subprocess) and return its identical 3-way exit code (0/1/2).
  ci.yml's step wraps THAT single tool call with an `if`-scoped bash branch —
  exit `1` (structural drift) prints `::warning::` and the step exits `0`;
  exit `2` (a broken regen, a bad manifest, a genuine tool error) is
  re-raised as the step's own exit code, never swallowed.
  **Verified empirically against `check_ci_gate_coverage.py`'s actual
  `is_loose()` (not assumed): this `if`-scoped form is correctly NOT
  recognized as a loose gate** — `_PIPE_SUPPRESS` only matches a suppression
  token on the SAME line as a `GATE_COMMANDS` substring, and this step's
  `exit 0` sits on its own line inside an `if` block, never on the line that
  invokes the tool. That is exactly why the if-scoped form was chosen over a
  trailing `|| true`/`|| exit 0` on the command line — the latter WOULD
  register as a loose gate needing an allowlist entry, but it would also
  swallow exit code 2 right along with exit code 1, silently hiding the one
  failure class this design exists to keep loud. **No
  `LOOSE_GATE_ALLOWLIST` entry is added**: `stale_allowlist_entries()` fails
  the guard on an entry that matches no step `is_loose()` actually flags, so
  adding one here — for a step the guard correctly does not consider a gate
  — would itself break `check_ci_gate_coverage.py`. The advisory design and
  its hardening trigger are instead documented directly in the ci.yml step's
  own comment. Structural-tier drift prints a `::warning::`-annotated diff;
  execution-tier differences print separately labeled, informational output.
  The hardening condition (N=5 consecutive green PRs, confirmed with the
  operator) AND the hardening prerequisite Internal Plan Review flagged —
  before this becomes a real block, the comparator must run from the PR's
  BASE revision (mirroring the existing "Repair-PR safety (gate)" `git show
  <base>:...` pattern, ci.yml:253-282) so a branch cannot silence its own
  drift finding by editing the tool that judges it — are recorded in that
  same comment, not built in this iterate, only documented as a
  precondition for the follow-up that hardens it.
- [x] AC5: `plugins/shipwright-iterate/skills/iterate/references/F0.md` and
  `F5.md` are updated to describe the new retention/staging path (AC2/AC3),
  and `docs/hooks-and-pipeline.md` is updated per CLAUDE.md's rule (a phase
  validator / between-phase action changed).
- [x] AC6: `Spec/design/2026-07-22-req3-campaign-SPEC.md` §4 P0a gains a short
  note recording that the AC ("Mindestens eine Coverage-Zelle liest `ok`")
  from this unit is CI-enforced only as an advisory annotation for now, per
  the split decision recorded in the campaign brief (§7, H1/H2) and E2.

## Spec Impact

- **Classification:** modify
- **MODIFY:** FR-01.10 (`/shipwright-compliance`) — its existing AC ("Given an
  evidence document, when it no longer matches the state it was produced
  from... then it is reported as no longer valid") already claims this
  behavior in prose; this iterate is the first mechanical enforcement of it
  for the traceability manifest specifically, in CI. Append one AC line
  naming the CI-regenerate-and-compare check, advisory-first.
- **ADD:** none
- **REMOVE:** none

## Out of Scope

- Hardening the CI check from advisory to a hard, blocking gate — deferred
  until several consecutive green PRs are observed with the check live (per
  the brief and SPEC E2's asymmetric-policy reasoning). This iterate only
  builds the advisory mechanism and registers it in the loose-gate allowlist.
- Any AC-identity / AC-ID minting mechanism (Welle 2 / P3.1+, campaign
  `req3-04-ac-identity-mono`, tracked separately as REQ3.04c).
- Widening `evidence_drop`/`test_links` to any repo other than this monorepo
  — `run_full_suite_evidence.py`/`stage_f0_evidence.py` stay explicitly
  monorepo-scoped tools (F5.md already documents this boundary for
  `run_full_suite_evidence.py`; the new tool follows the same convention).
- Changing the `test-traceability.json` schema itself (frozen,
  `additionalProperties: false` — SPEC names P3.2 as the only place allowed
  to touch it).

## Design Notes

n/a — no UI surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `run_test_suite.py` (F0 unit reports, retained) | `stage_f0_evidence.py` | JSON side-manifest + JUnit XML |
| `.github/workflows/ci.yml` pytest steps (`--junit-xml`) | new CI step (stage + regen + compare) | JUnit XML |
| `compare_traceability_manifest.py` | CI step / operator console | JSON diff report |

`touches_io_boundary` is in scope: the side-manifest and JUnit staging paths
are new producer/consumer pairs. Boundary Probe sub-step applies during Build.

## Confidence Calibration

Mandatory (medium+, `touches_io_boundary` also fires — extensive `json.dump`/
`json.load` across the new tools). Four probes, asymptote reached at round 4
(round 4 found nothing, closing the loop opened by rounds 1-2).

1. **Probe:** Do the three new CLI tools (`stage_f0_evidence.py`,
   `ci_junit_plan.py`, `ci_manifest_drift_check.py`) actually run as real
   standalone `uv run` invocations, not merely under pytest's own
   collection-time sys.path side effect? **Finding: bug.** All three had a
   broken `from lib import ...` / `from lib.X import ...` that resolved only
   because pytest auto-inserts `shared/scripts` onto `sys.path` when
   collecting a test file under `shared/scripts/tools/tests/` — invisible to
   every passing unit test, fatal (`ModuleNotFoundError`) as a real CLI call.
   Fixed by consistently importing via `scripts.lib.*`/`scripts.tools.*` from
   one `shared/` sys.path root. Re-verified as real CLI invocations after the
   fix.
2. **Probe (mandatory — round 1 found a bug):** With the sys.path fix in
   place, does the *pre-existing* test suite still pass when `run_test_suite.py`
   actually runs, for real, on this repo's own tree — exercising AC2's new
   `Retention` import for real rather than through an isolated unit test?
   **Finding: bug.** `test_f0_cli_diff_coverage_e2e.py`'s synthetic-repo
   fixture (`_RUNNER_FILES`, a hand-enumerated file list) predates this
   iterate and did not carry the two files AC2 added a dependency on
   (`suite_retention.py`, `suite_root_plan.py`) — a real regression this
   iterate's own change caused in an unrelated, already-existing test, caught
   only by actually driving the real suite rather than trusting the isolated
   unit-test run. Fixed by adding both to the fixture list; re-verified green.
3. **Probe (mandatory — round 2 found a bug):** Does manifest regeneration
   correctly reach the plugin's real collector code (not a `scripts.lib`
   binding already cached from this process's own earlier import — the
   ADR-045 collision class) when driven for real against this repo's actual
   `.shipwright/compliance` state, and does the comparator correctly classify
   the result as advisory structural drift rather than false-blocking or
   silently passing? **Finding: no bug.** Ran the full chain for real: F0
   GREEN (18/18 units, 4.4 min, 87% diff-coverage) → `stage_f0_evidence.py`
   staged all 18 retained reports in one call → the plugin's real
   `test_links.generate_file()` regenerated the tracked manifest via the
   subprocess-isolated path → `compare_traceability_manifest.py` correctly
   returned exit 1 (real, legitimate structural drift — a stale committed
   `spec_hash` and newly-added test ids, not a false positive) — never a
   silent exit 0, never an unhandled exit 2.
4. **Probe (asymptote check, since round 3 found nothing):** Do all four
   consumers of `ci_junit_plan.py plan`'s `plan.json` — the three `jq`
   lookups in `ci.yml` and `ci_manifest_drift_check.py`'s `stage_ci_reports`
   — read the exact field names the producer (`write_plan`) writes, so a
   future shape change cannot silently diverge one consumer from the rest?
   **Finding: no bug.** Grepped all four sites: every one reads exactly
   `rel_root`/`base`/`junit_out`, matching `write_plan`'s output byte-for-byte.
   Two consecutive no-findings (rounds 3-4) — asymptote reached.

Condition 3 (drift-protection when N>1 consumers exist) is separately covered
for `plan_root`/`base_for_root` (F0 retention, `ci_junit_plan.py`, and
`run_full_suite_evidence.py` all consume it): `test_suite_root_plan.py`'s
`test_run_full_suite_evidence_re_exports_the_same_function_object` asserts
`is`-identity, not merely equal behavior, between the shared function and the
re-export — the two call sites cannot silently diverge.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** high
- **Summary:** The plan's central claim is half right — F0 genuinely runs all
  18 roots with CI's marker expression and 3.11 pin, and genuinely discards
  the JUnit reports — but F0 runs on Windows while CI runs on Linux, so the
  original AC1 (blanket structural-equality except two fields) would
  re-introduce H2 exactly. Also found: `generate_file()` has no scratch-output
  parameter and the manifest is a TRACKED file (CI regen dirties the tree by
  design, not a bug); an AC4/mini-plan contradiction that would have failed
  `check_ci_gate_coverage.py`'s reverse-drift check; and several
  correctness/integrity gaps in the retention/staging design (base derivation,
  retry semantics, dual evidence-clear, run_id contract).
- **Findings:**
  1. HIGH/completeness — OS divergence breaks the AC1 exclusion set (fix: split
     structural vs. execution comparison tiers)
  2. HIGH/completeness — `generate_file()` has no scratch-path param; tracked
     file (fix: capture committed baseline via `git show` before regen,
     document the intentional dirty tree, move step to end of job)
  3. HIGH/completeness — Q1 never measured execution-derived fields (fix:
     treat live CI runs during advisory period as the real measurement;
     execution tier reported, not gating, in this iterate)
  4. HIGH/architecture — AC4 vs. mini-plan step 6 allowlist contradiction (fix:
     `|| true` scoped to only the compare command, correctly registers as loose)
  5. HIGH/architecture — unconditional exit 0 would swallow real breakage (fix:
     fail-closed on infra, advisory only on the compare tool's own verdict)
  6. MEDIUM/architecture — AC2's base-derivation claim was wrong; a third
     hand-maintained root list (fix: reuse `plan_root()`, add parity test)
  7. MEDIUM/architecture — CI YAML would hand-maintain a base mapping (fix:
     filename convention + Python helper, no YAML literals)
  8. MEDIUM/completeness — retry/race retention semantics undefined, and a
     false "no regression" test claim (fix: explicit supersede rule, corrected
     test description)
  9. MEDIUM/architecture — two producers both clear the evidence dir first;
     no gating on a complete F0 run (fix: exactly one staging call per run,
     refuse to stage an incomplete side-manifest)
  10. MEDIUM/completeness — `run_id`/`head_commit` silently degrade the F11
      gate if wrong (fix: required args, no defaults, freshness test)
  11. MEDIUM/security — a branch can silence its own drift finding (fix:
      documented as an explicit hardening-day prerequisite, not built now)
  12. LOW/performance — step placement mid-gate-chain (fix: move to end of job)
  13. LOW/performance — cost-figure inconsistency, `~1.9 min` vs.
      `run_full_suite_evidence.py`'s docstring claim of `20-60 min` (verified:
      the two tools use different execution strategies — F0 runs the pool in
      parallel, `run_full_suite_evidence.py` drives one root at a time,
      serially, per its own R1a design; both figures are independently
      correct for their respective tool, and the discrepancy strengthens
      rather than weakens the case for AC2/AC3 — the rejected alternative
      really does cost an order of magnitude more, not the same)
  14. LOW/performance — unbounded local artifact growth (fix: prune to the
      last N=5 run directories)
- **Known limitations:** none disclosed — every finding was fixed and
  integrated into the ACs above and the mini-plan.
- **Status:** 14 fixed

## External-Code-Review-Findings (Step 8, `--mode code` against the merge-base diff)

Branch A ran; `openai` returned 6 findings (all `severity: medium` except one
`high`), `deepseek` was `degraded` (empty reply — recorded as `unavailable`,
not treated as a second opinion). Verdict: `revise`. Disposition per finding:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | high | `Spec/design/2026-07-22-req3-campaign-SPEC.md` missing from the diff — AC6 not implemented | **rejected-with-reason.** `Spec/` is gitignored (`.gitignore:123`), so an AC6 edit there is *structurally invisible* to any diff-based reviewer — it cannot appear in `git diff` no matter how it was made. Confirmed independently by `spec-reviewer` (Stage 1), which read the file directly in the main tree (`Spec/design/2026-07-22-req3-campaign-SPEC.md:208-217`) and verified the note is present. Not a gap; a known blind spot of the review method itself. |
| 2 | medium | `stage_f0_evidence.py` should reject duplicate `base` values across units, not just duplicate `unit_id` | **rejected-with-reason, code unchanged — but AC3's TEXT was wrong and is now fixed.** By design, the three `shared/` units and the `integration-tests` unit ALL legitimately share `base=""` (`base_for_root` returns `""` for every non-plugin root) — that is not a corrupted manifest, it is the normal, expected shape for every real retained run this repo ever produces. Requiring unique bases would make `stage_f0_evidence.py` refuse every healthy run. `unit_id` uniqueness (already enforced) is the correct integrity check; `base` uniqueness is not a property this data has. `spec-reviewer`'s re-review (Step 8) caught that AC3's own prose still promised "unique unit ids and bases" — the code was right and the SPEC was outrun by it; AC3 above is corrected to say so explicitly, rather than leaving that contradiction standing next to this table's explanation. |
| 3 | medium | `compare_traceability_manifest.py`: malformed `tests` shapes (`null`, non-list layer, a record with no `id`) reach `execution_report()` uncaught and crash with Python's default exit 1, not the documented `EXIT_ERROR=2` | **accepted-and-fixed.** Verified the exact crash empirically before fixing. Added `_validate_tests_shape()` to `_validate()` (checks `tests` is an object, each layer a list, each record an object with `id`) and three regression tests (`test_null_tests_field_exits_2_not_an_unhandled_crash`, `test_non_list_layer_in_tests_exits_2`, `test_test_record_missing_id_exits_2`). |
| 4 | medium | `ci_manifest_drift_check.py`: a malformed `plan.json` (non-list, or an entry missing `base`/`junit_out`) reaches `stage_ci_reports()`'s dict indexing uncaught, and `run()` only catches `DriftCheckError` | **accepted-and-fixed.** Added explicit shape validation in `stage_ci_reports()` (list check, then per-entry field check) raising `DriftCheckError` with the offending index, plus two regression tests. |
| 5 | medium | AC2's `discover_units` vs `discover_test_roots` parity test is missing | **accepted-and-fixed.** Same finding as `spec-reviewer`'s Stage-1 REJECT (see below) — new file `shared/scripts/tools/tests/test_f0_unit_root_parity.py`, both directions, run for real against this repo's own 18 roots. |
| 6 | medium | Same duplicate-base claim as #2, framed as a missing test | **rejected-with-reason.** Same reasoning as #2 — the implementation is correct as written; a test asserting duplicate-base rejection would itself be wrong. |

**Cross-validation note:** finding #5 (parity test) was independently raised by
both `spec-reviewer` (Stage 1, as a REJECT — see the Review Cascade section
below) and the external `openai` reviewer, from reading the same diff two
different ways. That agreement is itself evidence the gap was real, not a
reviewer artifact — unlike #1, #2, #6, each of which the diff or the design
itself directly refutes.

## Internal Code-Review Findings (Stage 2, `code-reviewer`)

Verdict: `REVISE` (one medium, three low — all non-blocking per the reviewer's
own assessment). Disposition per finding:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | medium | `stage_f0_evidence.py`'s `load_and_validate_manifest()` checked each unit entry for `unit_id`/`outcome` but not `base`, while `main()` later indexes `e["base"]` unguarded — a manifest entry missing `base` crashed with an uncaught `KeyError` (exit 1), not the tool's own documented exit-2 refusal contract. The identical malformed-input class as the two accepted-and-fixed external findings (#3/#4 above) on this same iterate, on a third tool. | **accepted-and-fixed.** Added `"base" not in entry` to the malformed-unit-entry check, updated the module docstring to name `base` among the fields validated up front, and added `test_an_entry_missing_base_is_refused`. |
| 2 | low | `ci_manifest_drift_check.py` imported `compare_traceability_manifest` twice under two different module identities — once via `scripts.tools.compare_traceability_manifest` (through the `_SHARED_ROOT` sys.path insert, the form its own test suite patches) and once as a bare `compare_traceability_manifest` via a second `sys.path.insert(0, .../tools)` — the ADR-044/045 dual-binding class this repo documents explicitly. | **accepted-and-fixed.** Replaced the second insert + bare import with `from scripts.tools import compare_traceability_manifest as _compare_mod`, resolving through the existing `_SHARED_ROOT` path — one module identity, one fewer global `sys.path` mutation. |
| 3 | low | `.github/workflows/ci.yml`'s three `jq` lookups for `--junit-xml` don't assert a match — a root absent from `plan.json` silently produces an empty flag value rather than failing at the point of the mistake. Relatedly, `ci_junit_plan.py`'s own lookup/verify indexes `e['rel_root']`/`e['junit_out']` without the shape validation its sibling `ci_manifest_drift_check.stage_ci_reports` applies to the same `plan.json`. | **acknowledged, deferred — non-blocking.** The end-of-job "Verify test-root JUnit coverage (gate)" step already catches a missing report and fails closed (exit 2); the gap is failure-message locality, not a missed-drift risk. Left as-is rather than adding assertions to three already-passing CI steps for a failure mode the existing gate already prevents from going unnoticed. |
| 4 | low | `run_test_suite.py`'s per-attempt report path (`<tmp>/p|s/u{idx}/r.xml`) is reconstructed at three call sites instead of one shared helper — a future rename inside `_exec` would silently degrade retained units to `report_path: null`. | **acknowledged, deferred — non-blocking.** A boy-scout dedup with no behavior change; left for a future touch of that file rather than widening this diff's surface for a cosmetic reducibility fix. |

## Doubt-Reviewer Findings (Stage 3, advisory-must-address)

Triggered by cross-plugin imports + subprocess isolation
(`ci_manifest_drift_check.py`'s regen subprocess into `shipwright-compliance`).
Fresh-context, disprove-biased pass. Could NOT disprove the headline claim —
the subprocess isolation genuinely closes the ADR-044/045 dual-binding gap
(attacked via module-cache leakage, child `sys.path` ordering, and
namespace-package merging; settled by `shipwright-compliance`'s `scripts.lib`
being a REGULAR package, so first-match-in-`__path__` resolution favors
`plugin_root` at position 0 regardless), and confirmed the Stage-2 single-
module-identity fix is correct. Four doubts survived the attempt:

| # | Severity | Doubt | Disposition |
|---|---|---|---|
| 1 | high | `run()` caught only `DriftCheckError`; an unanticipated exception (e.g. an `OSError` from `evidence_drop.stage_reports`, or a JSON `null` for `plan.json`'s `junit_out` crashing `Path(None).is_file()`) escaped uncaught and exited with Python's bare default — `1` — which ALIASES with `EXIT_STRUCTURAL_DRIFT`, so ci.yml's advisory wrapper would silently swallow a real infra failure as reported drift. | **fixed.** Added a catch-all `except Exception` in `run()` returning `EXIT_ERROR`, and tightened `stage_ci_reports`'s plan-entry validation to require `base`/`junit_out` be strings (not merely present), closing the specific `null` crash path named. Two regression tests added: `test_a_null_junit_out_raises_driftcheckerror_not_a_bare_typeerror`, `test_an_unanticipated_exception_exits_error_not_the_bare_default`. |
| 2 | medium | The new "Verify test-root JUnit coverage (gate)" step is an unacknowledged HARD gate whose expected set (`discover_test_roots`) is not proven to match its producers (ci.yml's own shell-loop predicates: `pyproject.toml && tests/` for plugins, a hardcoded 3-dir list for shared, an existence guard for integration-tests). A future test root matching `discover_test_roots` but none of those predicates would be planned but never run, and would hard-red an unrelated PR at `verify`. | **reasoned rebuttal, no code change.** This is deliberate, not hidden: `docs/hooks-and-pipeline.md`'s "Merge gates in this repo's own CI" table already documents this step as the 4th hard gate, distinct from the advisory drift check the "never blocking merges" framing describes — the two are different steps with different contracts, and this doubt does not contradict that framing, it sharpens a separate, already-hard gate's own failure mode. The failure is loud, self-describing (`verify` names the missing root), and fail-closed — the property the External Review explicitly asked for at AC4. Extending AC2's parity test to also assert against ci.yml's shell predicates would require parsing YAML shell fragments as data, a materially larger and more fragile addition than this iterate's scope; accepted as a known gap for a future iterate rather than solved here. |
| 3 | medium | `ci_manifest_drift_check.py` mutates the LIVE tree (clears `.shipwright/compliance/evidence/`, overwrites the tracked manifest) with no CI-only guard, and its scratch dir `.ci-junit/` was not gitignored — a local run (e.g. "verify the producer," a documented anti-pattern in this repo) plants files at repo root that a routine `git add -A` would sweep in. | **partially fixed.** Added `/.ci-junit/` to `.gitignore` (zero-risk, closes the accidental-commit half). Declined a CI-only runtime guard: the tool already requires `--run-id`/`--head-commit` with no defaults specifically so a wrong/missing value degrades loudly rather than silently (see the module docstring), and the recovery path for a mistaken local run is real — `git checkout` restores the tracked manifest, `stage_f0_evidence.py` restages evidence from the retained F0 run (AC2/AC3's own reason for existing, and a direct answer to the Architecture Review's "drop AC2/AC3" finding below). |
| 4 | low | `Retention`'s pruning only walks `published/`; a `pending/` dir from an interrupted F0 run (Ctrl-C mid-suite) is never pruned, so orphaned pending dirs accumulate unboundedly in the durable main-tree store. | **reasoned rebuttal, no code change.** Accepted as a known, narrow gap rather than fixed here: an interrupted local run is rare relative to normal F0 completion, each orphan is small (at most one project's worth of JUnit XML + a manifest), and this repo's own memory of "never delete local state" makes an automated age-based prune a design decision bigger than this doubt's severity warrants — worth a dedicated small iterate, not a rider on this one. |

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-26-r1b-ci-manifest-regen-gate/architecture_brief.md`
- **Verdicts:** deepseek=revise · openai=revise
- **Smallest thing that would do (per reviewers):** AC1 (comparator) + AC4 (CI
  stage/regen/compare step) only — drop AC2/AC3 (F0 report retention +
  `stage_f0_evidence.py`) entirely; CI's own three existing pytest
  invocations already produce everything the CI check needs directly.
- **Findings:** Both reviewers, independently, category `simpler-alternative`
  (openai: medium, deepseek: high) — the F0 retention/staging apparatus (side-
  manifest, atomic publish/prune, `stage_f0_evidence.py`, the parity test) has
  no consumer in the CI drift check; it is a standing local mechanism the CI
  gate never reads.
- **Reconciliation:** Correct and not in dispute — AC4 does not consume AC2/AC3
  and would work standalone. But that was never AC2/AC3's purpose. Per the
  brief template's own rule, the brief deliberately omits why alternatives
  were rejected, so neither reviewer saw the reason AC2/AC3 exists: the
  operator explicitly asked, in this iterate's own Interview (before the
  mini-plan was written), for finalize to stop discarding the full-suite
  evidence F0 already produces on every run — a separate, already-approved
  gap, orthogonal to whether the CI check needs it. Presented this finding
  back to the operator (naming that F0 already runs the tests either way and
  the added cost is a new script + tests, not new test-running time): decision
  is to keep both in this iterate, matching the earlier approval. AC2/AC3
  stay as specified. If AC2/AC3 turn out blocked or materially harder than
  scoped during Build, AC4 can still ship alone — the reviewers' point stands
  as a fallback, not a directive.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run shared/scripts/tools/compare_traceability_manifest.py --check --committed <a> --regenerated <b>` (finalized during Build) plus `uv run shared/scripts/tools/run_test_suite.py --project-root . --run-id {run_id}` then `uv run shared/scripts/tools/stage_f0_evidence.py --project-root . --run-id {run_id} --head-commit <sha>` proving AC2/AC3 end-to-end on this repo's own tree.
- **Evidence path:** `.shipwright/compliance/evidence/` (existing convention) + test output.

**F0 full-suite run caught one real gate failure the cascade did not:**
`shared/tests/test_artifact_path_canon.py::test_no_legacy_artifact_paths[compliance-migrated]` —
`ci_manifest_drift_check.py`'s `TRACKED_MANIFEST_REL = Path(".shipwright") / "compliance" / ...`
used `Path(".shipwright")` as a constructor call rather than the canon-lint's
recognized `<expr> / ".shipwright" / "compliance"` chained-division form, so
the literal `"compliance"` segment read as an unmigrated legacy path
reference. Fixed by rewriting as `Path(".") / ".shipwright" / "compliance" /
"test-traceability.json"` — `pathlib` collapses the leading `.` at
construction time (verified: `.as_posix()` output is byte-identical, no
behavior change), and the chain now matches the canonical form every other
`.shipwright/compliance` reference in this repo already uses. Zero logic
change; confirmed via the full drift-check test suite (12/12) plus the
canon-lint test itself, both green after the fix.
