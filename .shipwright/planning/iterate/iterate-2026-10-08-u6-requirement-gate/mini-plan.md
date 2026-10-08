# Mini-plan: U6 - requirement gate bypasses (iterate-2026-10-08-u6-requirement-gate)

Campaign `2026-10-07-finalization-claims-hardening`, unit U6. Complexity medium.
FR: FR-01.11 (modify AC03, AC04: fixes are no longer exempt).

## Problem

The requirement gates at event-write time have four bypasses:

1. Bug iterates are exempt from the spec-impact gate (CLI and F11).
2. `spec_impact: none` accepts any free-text justification; nothing countable.
3. `check_fr_existence` allows a declared FR id when specs exist but parse to
   zero requirements (warns only), so a blind parser reads as verified.
4. The spec-impact gate runs only at the `record_event.py` CLI; F5b
   (`finalize_iterate._record_event`, the normal path) skips it.
5. A no-FR `change_type` (docs/tooling/compliance/infra) is self-reported and
   never compared with the diff.

## Approach

- `lib/spec_impact_gate.py` (moved out of `record_event.py`, which is over cap):
  intents feature/change/bug must name FRs or record `spec_impact: none` with a
  justification (`spec_impact_justification` or `none_reason`, parity with
  F11) and `spec_impact_reason_code` from a new closed family
  `spec_impact_none` in `lib/reason_codes.py`. A recorded `none` is answered
  even by intent-less events.
- `lib/fr_gates.run_fr_gates` (the single entry point both write paths already
  call) gains the spec-impact arm and the change_type-diff arm, so F5b runs
  them with no edit to `finalize_iterate.py`.
- Existence: specs found + zero parsed + a declared id -> `fr_gate_specs_unparsed`.
  A collector crash on present specs reports `specs_found=True` (fails closed).
- `lib/change_type_paths.py` (pure): per-change_type glob sets, project-aware.
  Every label covers docs, tests and Shipwright records; docs covers only docs
  and records. Shape detection: Shipwright monorepo (`shared/scripts` +
  `.claude-plugin/marketplace.json`) extends tooling/infra/compliance with
  `plugins/**`, `shared/**`, `scripts/**`. (Rev. after review: the per-project
  `change_type_paths` override key was dropped - see the ADR.)
- `lib/change_type_diff.py`: diff = narrowest merge-base over
  origin/HEAD, origin/main, origin/master, main, master -> working tree, with
  untracked files; `-M` so both sides of a rename are judged; deletions judged.
  Not a git repo -> WARN + allow. git present but no trunk / git failure ->
  `change_type_diff_unavailable` (fail closed). Only the no-FR branch is checked.
- F11 `check_spec_impact_recorded`: stop skipping intent `bug` (one-line edit,
  `iterate_checks.py` does not grow).
- CLI: `--spec-impact-reason-code` (choices = the family).
- Docs: F5b.md, F7.md, path-b/c, F-finalize-bundle.md, guide.md, hooks-and-pipeline.md,
  spec FR-01.11 AC03/AC04.

## Alternative approach considered

A global "no runtime code" rule for every change_type - rejected because in
this monorepo the product is tooling (`shared/scripts/**`, `scripts/**`), so it
would refuse every legitimate tooling change. Re-checking the event at F11 as a
new CLAIM_CHECK - deferred: both write paths now run the same gate, and F11's
existing spec-impact check covers bug iterates.

## Tests

`shared/tests/test_requirement_gate_spec_impact.py`, `..._change_type_diff.py`
(tagged FR-01.11/AC03, AC04): bug refused/accepted, closed code, F5b path, CLI,
zero-parsed specs, collector crash, WebUI and monorepo shapes, mixed diffs,
untracked, committed branch work, rename, unknown paths, config extension,
not-a-repo, no trunk ref. Existing fixtures updated with the reason code.

## Risks

- Every consumer F5b call with `spec_impact: none` now needs the reason code:
  intended (forward-only; old events are not re-gated). Authoring docs updated.
- Consumer repos with a layout neither shape fits: config extension.
