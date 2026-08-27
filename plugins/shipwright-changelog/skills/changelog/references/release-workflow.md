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


## GitHub Release publishing (Step 7)

Every tag `/shipwright-changelog` pushed was, until this change, a bare
tag — clicking it on GitHub showed only the one-line tag-annotation
commit message, never the change content. `CHANGELOG.md` already carries
the real, structured release notes; this step surfaces them where a
reader (someone deciding whether to upgrade, a contributor scanning what
shipped) actually looks, without requiring them to open the repository.

**Why condense instead of publishing the section verbatim.** A real
version section can run 400+ lines of dense, multi-sentence bullets
(v0.32.0's is 454 lines) — unreadable as a release page, and the reason
this feature exists at all rather than a one-line `gh release create
--notes-from-tag`. An architecture-review pass independently proposed the
verbatim alternative and was declined for exactly this reason — see the
iterate spec `iterate-2026-08-26-changelog-release-notes.md`'s
`## Architecture Review` section for the full reconciliation.

**Why the LLM's role is bounded to judgment, never to safety or shape.**
Compressing a dense multi-sentence bullet into one clear sentence, and
classifying "breaking" vs. merely "changed", are judgment calls a
mechanical script cannot make well — a naive first-sentence truncation or
keyword regex reliably keeps the least informative clause. But nothing
about whether the result is SAFE or SHAPED correctly to publish depends on
judgment, so none of that is delegated to the model:
- the condensation call (`condense_release_notes.py`) is a single,
  tool-less LLM completion — no Agent-tool spawn, no function/tool
  definitions passed — so a prompt-injected CHANGELOG bullet (drop files
  can originate in an external contributor's PR) can influence only the
  *text* returned, never take an action;
- the trailing links (CHANGELOG reference, compare URL) are computed
  mechanically from the resolved version and are never trusted to model
  output;
- `validate_release_notes.py` is a deterministic gate the condensed text
  must pass before anything is published — fixed heading vocabulary, a
  hard size cap, `@mentions`/`#NNN` neutralized, images/autolinks/bare
  URLs/raw HTML rejected outright, links restricted to this repo's own
  host — and it returns the CANONICAL SANITIZED body; the caller publishes
  exactly what this function returns, never the model's raw reply.

This is the standard shape for any LLM output reaching a public surface —
generate, then gate — the same pattern as a lint/test gate in front of
generated code, not a novel mechanism invented for this feature.

**Why forward-only.** The 40+ tags already pushed before this change are
explicitly out of scope (operator decision) — no backfill. A release
created going forward with `gh release create --verify-tag` also refuses
to auto-create a tag at the branch tip if `git push --tags` silently
failed, so a release page can never point at a commit the pushed tag
doesn't actually name.

**Why failure here never blocks the changelog phase.** The pushed tag is
the release's source of truth; the release page is a best-effort
convenience layered on top of it. Every stage — extraction, condensation,
validation, publishing — reports a distinct, never-swallowed status
(`ok` / `exists` / `skipped: <reason>` / `failed: <reason>`) in the Step 7
summary banner, but none of them halts the phase. Because a silently
skipped or failed release note could otherwise rot unnoticed for months,
the NEXT release's setup step advisory-checks (never blocks) whether the
immediately preceding tag has a release, and prints a notice if not — so
the gap surfaces once, at the next release, instead of never.


