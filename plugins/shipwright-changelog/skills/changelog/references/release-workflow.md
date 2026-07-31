# Release workflow — the parts that are rationale, not instruction

Reference for **Step 7** of `/shipwright-changelog`. Moved out of `SKILL.md` when
the compliance-evidence step was added (iterate-2026-07-31-derived-docs-at-release):
the skill is an index of what to DO, and this is the reasoning behind it.

## Parallel iterate handling

- Multiple open PRs against the same default branch: rebase per PR is expected — no skill-logic change required.
- `gh pr merge --merge` vs `--squash`: the default stays `--merge`; `--squash` is optional for parallel-iterate PRs when linear history matters.
- Tag creation is single-writer (only the release-iterate tags a version) — no concurrency change needed.
- Conventional-Commit sort is deterministic: merge order does not affect changelog ordering.
- **`CHANGELOG.md [Unreleased]` is a merge hotspot.** Every iterate F4 appends to `[Unreleased]`. Two parallel iterates conflict on merge — the second PR rebases and resolves the bullet merge manually. Structural fix tracked as a `CHANGELOG-unreleased.d/` drop pattern bundled with the iterate_history file-per-iterate refactor.
- Full parallel-iterate conventions live in `/shipwright-iterate` B1a.


## Why the phase-completion canon stops at C3

Iterate 12.4 wires the changelog plugin into the Minimum Phase
Completion Canon at C1/C2/C3 only. **C4 is skipped by policy** —
release tagging is process management, not an architectural decision.
**C5 is not applicable** — this plugin IS the one that writes
`[Unreleased]` prepends; appending to `[Unreleased]` after a release
would pollute the next version.


