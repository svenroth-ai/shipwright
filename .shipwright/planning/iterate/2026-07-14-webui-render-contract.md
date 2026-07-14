# Iterate: Cross-repo output contract — the Command Center renders grade + adopt

- **Run ID:** `iterate-2026-07-14-webui-render-contract`
- **Intent:** CHANGE (Path B)
- **Complexity:** medium
- **Triage anchor:** `trg-46a8de1f` (this repo) · `trg-3edbc478` (shipwright-webui)
- **Spec Impact:** **ADD** — new `FR-01.15` (cross-repo output contract)
- **Consumer spec:** `C:/01_Development/shipwright-webui/.shipwright/planning/iterate/campaigns/webui-wow-usability-2026-07-10/sub-iterates/A08-intent-wizard.md`

## Problem

The Command Center WebUI (sub-iterate A08, "intent wizard") now renders two of this
repo's output artifacts **natively, field-for-field**:

1. **`shipwright-grade`** — the `ReportModel` / `DimensionView` graph
   (`plugins/shipwright-grade/scripts/lib/report_model.py`), reachable as
   `grade.py --format json` (`dataclasses.asdict(model)`). The WebUI's *"Grade your
   repo"* screen renders this model so the screen and the downloadable HTML report
   cannot tell different stories.
2. **`shipwright-adopt`** — `.shipwright/adopt/snapshot.json`
   (`plugins/shipwright-adopt/scripts/tools/analyze_codebase.py`). The WebUI's adopt
   screen shows *"what's already here"* from it before anything is written.

That turns both from "our own output format" into a **cross-repo contract** — and
**nothing in this repo says so**. A field renamed or dropped here does not fail
loudly in the WebUI: it renders a half-empty card, or worse, a plausible-but-wrong
one. Nobody working in this repo currently has a reason to know the WebUI is watching.

The grade SKILL.md already claims `--format json` emits a *"stable schema"* — an
unbacked promise: nothing pins it and nothing detects a break.

## Why a bare version constant is not enough

A `schema_version` that a developer must remember to bump reproduces the exact
failure it is meant to fix: the person renaming a field is by assumption the person
who does not know the WebUI exists. The constant would sit at `"1.0"` while the shape
moved underneath it, and the WebUI would confidently render a broken card — a
*worse* outcome than no version at all, because the version asserts trustworthiness.

**Therefore the version is only load-bearing if something forces the bump.** The
contract tests are the deliverable; the version field is what they protect.

## Approach

**Declare + version + enforce**, per producer:

1. **Declare** the contract where the person about to break it will actually look:
   the module docstring of the producer, and the SKILL.md of the owning plugin.
2. **Version** each payload with a `schema_version` (`major.minor`) so the consumer
   can detect a shape it does not understand:
   - **major** — breaking (a field **removed**, **renamed**, or **retyped**). The
     WebUI must **refuse to render** and say "report shape not recognised".
   - **minor** — additive (a new field). The WebUI keeps rendering and ignores it.
3. **Enforce** with a contract test per producer whose pin is **one `CONTRACT` object
   holding the version and the shape together**. The test diffs the pin against the
   live payload, **derives the bump that diff requires, and asserts the version
   actually performed it**. A developer who legitimately changes the shape cannot green
   the test by editing the pinned graph alone — the pinned version sits in the same
   object and the derived-bump check fails until it moves. That is the whole point:
   **turn a feat of memory into a mechanism.**

The bump rule is what makes the version honest: an additive change must NOT force a
WebUI release (or people would stop bumping), and a breaking change MUST.

## Scope decisions (confirmed with Sven, 2026-07-14)

- **Guard strength: enforced by test**, not documented-only. A doc note relies on the
  developer reading it first — the assumption that already failed here.
- **Both producers get the marker.** The triage names `ReportModel` explicitly, but
  the adopt snapshot carries the identical risk (the WebUI's adopt screen reads it the
  same way). Versioning only one leaves the adopt screen with the silent-drift hole
  this iterate exists to close.

## Out of scope (filed, not fixed)

- `/shipwright-grade` **has no FR** in `spec.md` (the table stops at FR-01.14) — a
  pre-existing gap from the grade campaign. Filed as triage; backfilling it is not
  this iterate's job.
- The WebUI half (payload-shape validation + the honest "report shape not recognised"
  state) is **already specified** by A08 AC and is built in that repo.

## Affected Boundaries

| Boundary | Producer | Consumer | Contract |
|---|---|---|---|
| `grade.py --format json` | `report_model.build_report_model` → `asdict` | Command Center *Grade* screen; `--format html/markdown/terminal` renderers | `ReportModel` + `DimensionView` + `DimensionProvenance` field graph |
| `.shipwright/adopt/snapshot.json` | `analyze_codebase.analyze` | Command Center *Adopt* screen; `generate_adoption_artifacts.py`, `validate_adoption.py`, `ci_workflow_scaffolder.py` | top-level key set |

`touches_io_boundary` — both are serialized producer/consumer boundaries → Boundary
Probe + round-trip verification required.

## Acceptance Criteria

- **AC1** — `grade.py <repo> --format json` emits a `schema_version` field
  (`major.minor`); the value is the single `report_model.SCHEMA_VERSION` constant. The
  terminal / markdown / html renders are **byte-unchanged** (the field is machine
  metadata, not a human-facing row).
- **AC2** — `.shipwright/adopt/snapshot.json` carries a `schema_version` from the
  single `analyze_codebase.SNAPSHOT_SCHEMA_VERSION` constant, as an additive key. Every
  existing in-repo reader keeps working, and a snapshot written *without* the key
  (an older adopt) is still readable — no reader may require it.
- **AC3** — a **contract test per producer** pins **one `CONTRACT` object carrying the
  version *and* the shape together** — for grade, `{"schema_version": ..., "ReportModel":
  {field: type}, "DimensionView": {...}, "DimensionProvenance": {...}}`; for adopt,
  `{"schema_version": ..., "snapshot": [top-level keys]}`. The version lives **inside
  the pin, not beside it**: it is the baseline the bump-check compares against, so
  without it "did you bump?" has nothing to answer against. The only way to green the
  test after a shape change is to edit the pin — with the version line under your cursor.
  The failure message names the Command Center as the consumer, classifies the diff
  (added / removed / retyped), and states the bump that is due.
- **AC4** — the gate **computes the due bump from its own classification and asserts it
  was performed** — memory is not a mechanism. Removed/renamed/retyped ⇒ **major**;
  purely additive ⇒ **minor**; unchanged ⇒ none. The rule is
  `performed >= required` (major > minor > none), **not** equality:
  - bundling an additive field into an already-breaking release must not fail;
  - **an unchanged shape with a deliberate major bump must be allowed** — see AC4a.
  A shape change with no bump fails. Both directions are covered by exercising the
  classifier against synthetic drifted shapes (breaking-with-minor-bump ⇒ fail;
  additive-with-no-bump ⇒ fail; pinned shape ⇒ pass).
- **AC4a** *(known limit, documented not hidden)* — the gate is **structurally blind to
  a semantic break with an identical field graph**: if `DimensionView.status` gained a
  fourth value beyond `ok|gap|n/a`, every field name and type would be unchanged while
  the WebUI's rendering broke. The `performed >= required` rule keeps the manual major
  bump available as the escape hatch for that class, and the limit is stated in the
  producer docstring + SKILL.md rather than papered over. Where the value domain is
  cheaply enumerable (the `status` vocabulary), pin it too.
- **AC5** — both SKILL.md files carry a **Cross-repo contract** section naming the
  consumer, the load-bearing fields, and the "a change here requires a WebUI change"
  rule. A drift test asserts the section is still present in both (it is the artifact
  a future refactor would silently delete).
- **AC6** — the grade SKILL.md's target-resolution behaviour (local path **or** remote
  → shallow clone into a purged tempdir; `--no-clone` opts out) is stated as part of the
  contract, because the WebUI surfaces the clone step and its network cost explicitly.
- **AC7** — the unbacked *"stable schema"* claim on `--format json` is replaced by a
  claim the version + gate actually back.
- **AC8** — full grade + adopt suites stay green; `uvx ruff@0.15.15 check .` clean.

## Review findings folded in (external + internal)

The plan survived, the *implementation* did not — three rounds of review moved it:

1. **GPT-5.6-terra-pro (plan review): the mutable pin cannot enforce a bump.** Edit the
   pin to match the rename and the diff empties, so the required bump becomes `none`.
   *Editing the pin erases the evidence.* → the baseline moved to `origin/main`.
2. **Both external models: a top-level-only pin is a false sense of security**, and
   pinning Python annotations is brittle. → the skeleton became the recursive **JSON wire
   shape**, which fixes depth and annotation-churn in one move.
3. **Internal code review: the `nullable` sidecar was never diffed.** `flatten` walks an
   array by its first element, so `{"nullable": [a, b, c]}` collapsed to ONE leaf and
   adding a path produced an empty diff — a container becoming nullable read as *"no bump
   required"* while the consumer dereferenced null. → nullability moved **into** the
   skeleton (`object|null`), where retype ⇒ major already applies. The sidecar is gone.
4. **Internal code review: the status probe was self-referential** (it drove the test
   fixture's own re-implementation of the rule, so it agreed with itself). → it now drives
   the **real engine's** `DimensionResult.status` via `engine_bridge`.
5. Also closed: fixture **deletion** (freeze-loop now reads what `origin/main` published,
   not the working tree), **bootstrap disarm** (renaming `CONTRACTS_DIR` silently skipped
   the gate — now cross-checked against `any_published_contract`), and `profile.source`
   (only appears under `--profile-hint`, so a third fixture arm observes it).

## Bug found while building the contract (in scope, fixed)

`git_analyzer.analyze_git` — **`major_refactor_commits` was always `[]`, for every repo.**
`git log --format=… --numstat` prints a **blank line between the header and the numstat
block**; the parser treated that blank as *end of commit* and reset `current = None`
before a single numstat line was read, so `files_changed` never rose above 0 and the
`>= 5` threshold was unreachable. Fixed (the blank is a separator; the next header flushes
the previous commit). Fixing it was *required*, not optional: pinning a permanently-empty
field into a published contract would have the WebUI render an always-empty "major
refactors" — the exact plausible-but-wrong card this iterate exists to prevent. The header
separator also moved to `0x1F`, because a subject containing `|` shifted date and author.

## Confidence Calibration

- **Boundaries touched:** `grade.py --format json` (`ReportModel` → `asdict` → wire);
  `.shipwright/adopt/snapshot.json` (`analyze()` → file); the `origin/main` git baseline
  read by both gates; `git log --numstat` parsing.
- **Empirical probes run:**
  - *Does `schema_version` actually reach the wire?* Ran `grade.py <fixture> --format json`
    end-to-end and asserted the field in the real stdout — not just on the dataclass.
    (Also caught: with network off the CLI emits `network_enrichments: []`, an empty
    instance of a pinned array, which the first conformance check wrongly rejected.)
  - *Is the `nullable` sidecar actually diffed?* Flattened `{"nullable": [a,b,c]}` →
    **one** leaf. Confirmed the reviewer's claim rather than trusting the argument.
  - *Is `major_refactor_commits` really dead?* Dumped raw `git log --numstat` and read the
    blank line after the header. Confirmed structurally unreachable, not merely untriggered.
  - *Does `.strip()` eat the `0x1F` sentinel?* Yes — `"\x1f".isspace()` is `True` in
    Python. Caught by the suite going red; header detection now runs before stripping.
  - *Is the contract-engine ≤300 LOC cap real?* Read `bloat_baseline`: `current <= limit`
    skips, so exactly 300 is legal. Split anyway once the module needed to grow.
- **Test Completeness Ledger** — every behavior this diff introduces; **0 testable-but-untested**:

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Grade JSON carries `schema_version` | tested | `test_schema_version_reaches_the_json_output`; real CLI in `test_the_real_cli_conforms_to_the_pin` |
  | 2 | Adopt snapshot carries `schema_version` | tested | `test_schema_version_is_written_into_the_snapshot` |
  | 3 | A shape change with no bump FAILS | tested | `TestRequireBump`, `TestEndToEndGate` |
  | 4 | Breaking (removed/retyped) ⇒ major; additive ⇒ minor | tested | `TestDiffAndRequiredBump` |
  | 5 | `performed >= required`, not equality (bundling + semantic escape hatch) | tested | `test_additive_change_may_be_bundled_into_a_major_release`, `test_unchanged_shape_may_take_a_deliberate_major_bump` |
  | 6 | Versions compare numerically (`1.10` > `1.2`) | tested | `test_versions_compare_numerically_not_lexically` |
  | 7 | **Editing a published fixture is caught** (the whole design) | tested | `test_editing_a_published_fixture_is_caught` |
  | 8 | **Deleting** a published fixture is caught | tested | `test_deleting_a_published_fixture_is_caught` |
  | 9 | Bootstrap stand-down cannot be abused by renaming the dir | tested | `test_a_renamed_contracts_dir_does_not_look_like_a_bootstrap` |
  | 10 | **A container becoming nullable ⇒ major** | tested | `TestNullabilityIsBreaking` (4 cases) |
  | 11 | Weak pins rejected: empty arrays, null-only leaves | tested | `test_the_pin_has_no_unpinned_arrays`, `test_the_pin_has_no_null_only_leaves` |
  | 12 | The pin describes the **serialized artifact**, not just the dataclass | tested | `TestRealCliConformance` |
  | 13 | `status` vocabulary probed against the **real engine** | tested | `test_the_real_engine_only_ever_emits_the_pinned_vocabulary` |
  | 14 | Both SKILLs state the contract, with substance | tested | `test_cross_repo_contract_documented.py` (21 cases) |
  | 15 | `schema_version` is additive — old snapshots stay readable | tested | `TestBackwardCompatibility` |
  | 16 | `major_refactor_commits` is detected at all (bug fix) | tested | `test_a_refactor_touching_many_files_is_detected` |
  | 17 | A `\|` in a commit subject does not shift date/author | tested | `test_a_pipe_in_the_subject_does_not_shift_the_other_fields` |
  | 18 | Terminal / markdown / HTML renders are byte-unchanged by the new field | untestable → `covered-by-existing-test` | `test_render_snapshots.py` goldens pass unchanged |

- **Confidence-pattern check:**
  - *Asymptote (depth).* The two claims the whole deliverable rests on were **probed, not
    argued**: that the pin cannot be edited to hide a break (`test_editing_a_published_
    fixture_is_caught`), and that nullability is not silently permitted. The second only
    surfaced because a reviewer disbelieved the design and I went and flattened the list
    instead of defending it.
  - *Coverage (breadth).* Both producers; both gates; the algebra; the git baseline; the
    docs; the consumer-visible value domain; backward compatibility.
  - *Integration composition.* `cross_component` does **not** fire (no hook, phase
    validator, merge/churn resolver or campaign file in the diff — verified against
    `CROSS_COMPONENT_FILE_PATTERNS`). A real-git integration test exists anyway
    (`test_contract_gate_git.py`), because the gate's enforcement lives precisely in the
    *composition* of the algebra with git — unit-testing the algebra alone would have left
    the enforcing half unverified, and a gate that no-ops is a false green.
  - *Known limit, stated not hidden.* A value-domain break with an identical field graph is
    invisible to the structural gate. `status` is pinned against the real engine; other
    vocabularies are not. `performed >= required` keeps the manual major bump available for
    that class. Narrowing nullability (`object|null` → `object`) reads as a conservative
    **false major** — safe, and recorded in the test name rather than papered over.
