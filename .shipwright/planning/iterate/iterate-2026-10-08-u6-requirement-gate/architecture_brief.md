# Architecture Brief: requirement gate bypasses (U6)

## The problem

When an iterate finishes it records whether it changed any requirement. Fixes are
exempt from saying so, a "requirements untouched" answer can be any free text,
an iterate that says it is only "tooling" or "docs" is believed without looking
at what it changed, and on the normal finishing path the spec-impact rule is
not applied at all. The result: changes to product behaviour can finish with
no requirement link and no countable reason, and the traceability record says
nothing about them.

## What already exists here

- `lib/fr_gates.run_fr_gates`: one entry point both event-write paths (CLI and
  F5b finalize) call; today it checks classification, FR id existence, and test
  evidence.
- A CLI-only spec-impact gate in `record_event.py` (features/changes only).
- F11 `check_spec_impact_recorded`: post-commit check, skips bug iterates.
- `lib/reason_codes.py`: the shared closed reason-code vocabulary (per family).
- `lib/requirement_impact_git.py`: git-derived changed-path evidence for design
  rounds and build sections (worktree vs HEAD, or a committed range).

## What would newly, permanently exist

A path classification per no-FR label (which globs `docs`, `tooling`,
`compliance`, `infra` may touch), with a detected project shape (Shipwright
monorepo vs generic) and an optional per-project extension key in
`shipwright_run_config.json`. A git diff (fork point to working tree, untracked
included) taken at event-write time whenever the no-FR label is used. One more
closed reason-code family. Kept correct by the framework maintainers; consumer
projects own their extension key.

## Options on the table

- **A:** Check the no-FR label against the diff using per-label, per-shape globs at both write paths; add a closed code for "requirements untouched"; remove the fix exemption; fail closed on unparseable specs.
- **B:** Same, but a single global rule ("a no-FR change may not touch runtime code") instead of per-label globs.
- **C:** Keep the labels self-reported; only add the closed code and remove the fix exemption.
- **D:** Do nothing; rely on the post-merge detective audit.

## Constraints that are not negotiable

The two event-write paths must apply identical gates (ADR-059). `record_event.py`,
`finalize_iterate.py` and `iterate_checks.py` may not grow (bloat caps). The
operator decided to harden the enforcement rather than soften the documentation.
