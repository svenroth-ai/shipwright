# Iterate — FR-existence gate

**Run ID:** `iterate-2026-07-18-fr-existence-gate`
**Type:** CHANGE · **Complexity:** medium
**Triage:** `trg-8deb2213` · **Campaign anchor:** `trg-16d79da2` (S0)
**Spec:** `Spec/design/2026-07-18-requirements-catalog-campaign-SPEC.md` §4 (S0)

## Goal

The finalization FR-gate accepts requirement ids that do not exist. It checks only
that the declared list is non-empty (`is_non_empty_fr_list` — "a list with ≥1
non-empty-string element"). Whether a declared requirement *exists* is verified only
by detective check D2 — MEDIUM severity, non-blocking, post-merge, behind a
`spec_updated` watermark.

An iterate can therefore declare `--affected-frs FR-99.99` and the gate passes. This
is a false green in the most load-bearing gate of the finalization chain, and it is
why dangling references to non-existent requirement ids are present in the repo today.

## Acceptance Criteria

- **AC1** — Declaring an `affected_frs` id that exists in no spec fails the gate with
  an actionable error naming the offending id(s).
- **AC2** — The same rule applies to `new_frs`: a minted requirement that never
  reached a spec is a defect, not a special case.
- **AC3** — Declaring known ids passes unchanged; the no-FR `change_type` branch is
  untouched; the existing BP-1 behaviour-affecting rule is untouched.
- **AC4** — Both write paths enforce it: `record_event.main` (CLI) and
  `finalize_iterate._record_event` (worktree F5b). No bypass.
- **AC5** — **Graduated failure, so a customer repo is never bricked:**
  - planning directory absent → cannot validate → allow, emit a warning
  - planning present, requirements parse, id unknown → **HARD FAIL**
  - planning present, zero requirements parsed → allow + warn loudly (a legitimately
    empty new project must not be blocked, but the blind-scanner case must be visible)
- **AC6** — The rule lives in `fr_classification` as a **pure** predicate taking the
  known-id set as a parameter. That module is deliberately stdlib-only and
  self-contained so the compliance plugin can load it pollution-free
  (`fr_classification.py:17-19`); collection stays at the call sites.

## Out of Scope

- Repairing the existing dangling references (reported, not auto-fixed — separate item).
- Anything else in the Requirements-Catalog campaign (S1–S8).
- Changing what counts as a requirement or how specs are discovered — S2/S3 own that.

## Design Notes

**Why the predicate is pure.** `fr_classification` is imported by the compliance
plugin through `audit_adapters.load_shared_lib` specifically to avoid binding `lib` in
`sys.modules` (ADR-044 discipline — see the memory of the lib-collision incident).
Importing `drift_parsers` there would re-introduce exactly that coupling. So:

- `fr_classification.unknown_fr_ids(declared, known) -> list[str]` — pure, stdlib only
- `record_event` / `finalize_iterate` collect the known set and call it

**Why `new_frs` is validated too.** At F5b the spec edit has already happened during
build, so a minted row must be on disk. If it is not, the iterate minted a requirement
that exists only in the event log — precisely the drift this campaign exists to end.

**Why AC5 is graduated rather than fail-closed.** Fail-open on *unavailable* is not the
same as fail-open on *unknown*. A repo with no planning directory has nothing to check
against; blocking it would make the gate un-adoptable. A repo whose specs parse to zero
requirements is the dangerous case (it reads as "nothing to audit"), so it warns loudly
rather than passing silently — the same distinction the campaign spec draws in §6.1.

## Affected Boundaries

- `shared/scripts/lib/fr_classification.py` — new pure predicate (stdlib-only invariant)
- `shared/scripts/tools/record_event.py` — CLI write path
- `shared/scripts/tools/finalize_iterate.py` — worktree F5b write path
- Consumers of the gate's error vocabulary (a new `error` value is added)

## Confidence Calibration

- **Boundaries touched:** the two event write paths and the shared classification
  predicate; the spec-discovery boundary is read-only here.

- **Empirical probes run:**
  - Scanned the real `shipwright_events.jsonl`: **326** iterate `work_completed`
    events, **0** declared ids the new gate would reject. The gate is a pure
    tightening with no false-positive surface in this repo.
  - Corrected a claim from the scouting round: the known dangling references
    (`FR-03.01`, `FR-04.02`, `FR-99.99`) live in iterate-spec prose and fixtures,
    **not** in the event log. The write path was already clean — the gate closes
    an open door nobody had yet walked through.
  - Reproduced the `integration-tests` collection error against **unmodified
    main**: identical failure, so it is pre-existing sys.path pollution from
    running both test trees in one pytest invocation, not caused by this change.
  - Ran the suites separately: shared **4310 passed / 0 failed**, integration
    **234 passed**. Lint `All checks passed!`.

- **Test Completeness Ledger:** 8 behaviors, 0 untested-testable.
  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Unknown `affected_frs` id blocked | tested | `test_unknown_affected_fr_is_blocked` |
  | 2 | Unknown `new_frs` id blocked | tested | `test_unknown_new_fr_is_blocked` |
  | 3 | Error names every offender, blames no known id | tested | `test_error_names_every_offending_id` |
  | 4 | Known ids pass; no-FR branch untouched | tested | `test_known_ids_pass`, `test_no_fr_change_type_branch_untouched` |
  | 5 | Absent planning dir does not block | tested | `test_absent_planning_dir_does_not_block` |
  | 6 | Zero parsed requirements warns but does not block | tested | `test_zero_parsed_requirements_does_not_block`, `test_spec_present_but_unparseable_is_found_with_no_ids` |
  | 7 | Both write paths actually invoke the gates | tested | `test_finalize_path_runs_both_gates`, `test_cli_path_runs_the_existence_gate` |
  | 8 | One entry point applies BOTH gates | tested | `test_combined_entry_point_applies_both_gates` |

- **Confidence-pattern check:**
  - *Depth (asymptote):* the pure predicate is exhaustively covered (order,
    trimming, blanks, non-strings, duplicates, empty known set) — further cases
    stopped yielding new information.
  - *Breadth (coverage):* the failure mode I feared most was **dead capital** —
    a gate defined but never wired, with every unit test still green. Behaviors 7
    and 8 exist specifically to make that impossible, and they earned their keep:
    a missing `run_fr_gates` re-export broke 16 finalize tests, which is exactly
    the signal that would otherwise have been silent.
  - *Search completeness:* one real miss. A grep for `record_event._CHANGE_TYPE_VALUES`
    missed the drift test that imports the module as `re_mod`, so I deleted a
    re-export that was in use. Caught by the full suite, not the targeted subset;
    fixed by restoring the re-export rather than adapting the test.
