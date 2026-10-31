# Architecture brief: independent AI gap check (baseline-package P4)

Need: a change records "no requirement affected" about itself, and that is wrong on a noticeable share of changes. A second opinion from a model that is not Claude should be visible in the PR, without ever holding it.

Options:
1. One advisory call to a non-Claude model through the existing external-review route, a PR-body block, a warning-only record check.
2. Do nothing new: rely on the P1 declaration and the existing reviewers.
3. Make the verdict a blocking F11 check or a required PR check.
4. Run the check as a separate service or a new provider client.

Constraint: nothing may newly block a PR; no new provider client; the check must degrade to a visible note when it cannot run.
