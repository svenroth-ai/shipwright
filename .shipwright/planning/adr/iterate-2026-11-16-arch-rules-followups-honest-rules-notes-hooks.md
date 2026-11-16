# Honest rule wording, reviewer notes kept, hooks never bypassed

Run: iterate-2026-11-16-arch-rules-followups (follow-ups of the profile-architecture-rules campaign). No FR is minted; criteria AC38 to AC40 sit under FR-01.01.

- Rendered rules: a rule with a linter fragment no longer reads "checked by the linter". It reads that the fragment comes with the scaffold template and is enforced only where the project's linter config carries it. Marker and block format are unchanged; this repository's own block has no linter rule, so it is byte-identical.
- Reviewer notes: the code reviewer's optional top-level `notes` string is stored as `reviewer_notes` on the code row of the review record, bounded to 1000 characters, only for a completed code-reviewer pass. It is never a finding, so it is never counted and never reaches the autonomous fix loop. The schema change is one additive optional string; older records stay valid.
- Runner contract: the sub-iterate runner states that git hooks are never bypassed (no skipping flag, no hooks-path override, no environment variable). Added in place on an existing line because the file is at its bloat baseline. The orchestrator's campaign-mode text was left to another run.
- Rejected: a new top-level reviewer field on findings (notes would be counted); validating notes content (free text by design).
