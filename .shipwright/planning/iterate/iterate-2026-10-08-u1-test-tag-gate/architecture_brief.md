# Architecture Brief: test-tag gate at finalization

## The problem
Tests added to the monorepo almost never name the requirement they prove (6% tagged overall; 11 of the last 45 test-changing PRs added any tag). Nothing at finalization requires it: the only existing tagging rule fires when a brand-new acceptance criterion has no test, so a test added under an unchanged criterion always ships untagged, and the requirement-to-test traceability the framework advertises keeps eroding by ~30 untagged tests a day.

## What already exists here
- The compliance plugin's traceability collector, which regenerates a requirement-to-test manifest (tagged links, untagged tests, malformed tags, orphan tags) from any git tree.
- `regenerate_base_head`, used by the existing removal and cross-layer coverage gates at finalization, which builds that manifest for the merge-base and the head commit.
- A git-blob reader and a base-manifest shape validator that fail closed.
- A registry of finalization claim checks plus a per-test exemption record in the iterate entry with a closed reason-code vocabulary.

## What would newly, permanently exist
One more finalization gate in the registry, run on every iterate at every complexity: it compares the base and head manifests and stops the run when the diff adds or edits a test that names no requirement, unless that one test carries a recorded exemption whose code the gate can verify against the code. The collector learns three tag placements it does not see today (wrapped multi-line Playwright declarations, class-level and module-level pytest marks). Kept correct by its own tests and the registry's both-directions meta-test.

## Options on the table
- **A:** a hard finalization gate over regenerated base/head manifests, diff-only, per-test exemptions.
- **B:** the same comparison as an advisory warning only.
- **C:** a repo-wide baseline file of allowed untagged tests, ratcheted down over time.
- **D:** only change the authoring instructions (tell the agent to tag tests), no gate.
- **E:** do nothing.

## Constraints that are not negotiable
The operator decided on 2026-10-07: hard STOP at every complexity from day one, diff-only, no baseline file. Existing untagged tests must not be touched. The finalization verifier file is at its size cap.
