Goal: Before the commit, a model that is not Claude checks the change's own account of its effect on the requirements against the diff and the catalog, and the pull request shows one advisory block with the verdict and whether a catalog gap exists.
Reason: A change that says no requirement was affected is wrong on a noticeable share of changes, and the author cannot be the only judge of it; the check must inform and never hold the change.
Reference: baseline-package campaign, unit P4; mini-plan.md in this directory
Affected ACs: FR-01.11.AC49
Catalog gap: FR-01.11
