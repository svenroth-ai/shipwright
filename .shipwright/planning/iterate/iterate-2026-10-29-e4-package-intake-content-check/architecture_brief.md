# Architecture Brief: Brief-package intake content check and kit-token warning

## The problem
A Brief package is approved by a person and accepted at intake, but its brief.md is only content-checked later in the Project phase, so a thin brief (42 empty dimensions in the last end-to-end run) is found about 70 minutes into a run. Separately, the package's visual guidelines are free prose and nothing tells the person, before the run, that they lack the colour and size tokens the design kit needs.

## What already exists here
- brief_project_mode.py already holds the content check (check_capabilities), run only by `apply` in the Project phase.
- brief_dir_intake.intake_dir is the single intake path (used by brief_intake.py and write_run_config.py).
- The design plugin's check_brand_tokens.py holds the kit contrast rules (CONTRAST_PAIRS) and tokens-contract.md is the contract.

## What would newly, permanently exist
One small shared module (brief_intake_checks.py) that intake calls: it asks the existing content check for issues and the existing kit checker for token warnings. No new rule set, no new gate in the pipeline, nothing written to disk.

## Options on the table
- **A:** intake calls the existing content check (in its own interpreter) and the existing kit checker (found next to shared); content issues refuse intake, token findings are advisory warnings in the intake result.
- **B:** only document in the run skill that the agent should run the Project content check and the kit checker by hand before continuing.
- **C:** move the content-check and contrast code into shared libraries so intake imports them directly.
- **D:** do nothing; keep finding both in later phases.

## Constraints that are not negotiable
Token findings must not block a run. No second copy of the content rules or the contrast rules.
