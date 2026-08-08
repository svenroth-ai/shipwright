# Backfill events-context-index selection keys from git history (Run-ID trailer only)

**Run ID:** iterate-2026-08-07-events-context-backfill-keys
**Spec:** `.shipwright/planning/iterate/2026-08-07-events-context-backfill-keys.md`

## Context

`.shipwright/runtime/events-context-index.json` — the index
`event_context_query.py` scores to build relevance-bounded event context for
Repo Scout — had mostly-empty selection keys (`area_ids` 23%, `changed_files`
23%, `affected_frs` 13%, `commit` 9%, `supersedes` 4% across 815 entries),
making relevance ranking mostly a no-op. The originating brief attributed this
to a stale "LLM extraction" path; that path does not exist — it is one
deterministic ternary. The brief also asked for `ADR:`/`Area:`/`FR:` commit
trailers alongside `Run-ID:`, modeled on a supposed ADR obsoletes/obsoleted-by
graph; no such graph exists (real convention is `Status:`/`Supersedes:` prose
in `decision_log.md`). Both premises were corrected in the spec's Goal section
before build.

## Decision

Backfill `commit`/`changed_files` from git history via the existing `Run-ID:`
commit trailer only (single join key: `entry.run_id` ↔ `Run-ID:`), using
exactly two `git log` walks per index build (sha→body, sha→changed-files) —
never one subprocess call per event. Recompute `area_ids` from the backfilled
`changed_files` via the existing `match_area` (no new matching logic). Replace
the unused `extraction` block with a 5-key `provenance` object
(`derived`/`declared`/`unavailable` per field) and a `coverage` envelope
(per-field counts + commit-map scan status). Bump `INDEX_SCHEMA_VERSION` 1→2.
Cache validity in `load_or_rebuild_index` now also re-resolves the base-ref
sha and rebuilds on a mismatch — the event-log fingerprint alone could not
detect a commit landing after a build with no new event appended (F5b writes
`work_completed` before F6 creates the commit).

## Consequences

`event_context_query.py`'s relevance ranking now has real signal to score
against for any event whose run_id resolves to a reachable commit. No
authoring-convention surface was added (`ADR:`/`Area:`/`FR:` trailers): commit
messages are unchanged, so this ships with zero migration and zero new
discipline asked of future commits. A shallow clone or a commit outside the
resolved base ref's history still resolves `unavailable`, visibly, via
`coverage.commit_map.status`.

## Rationale

The originating brief's stated cause (an "LLM extraction" path) does not
exist in the codebase — verified by an Explore agent before writing the spec,
not assumed. Given that, the actual gap is structural: most events are
written with `commit=""` by design (the worktree flow links via the F6
commit's `Run-ID:` trailer instead), and nothing ever read that trailer back
into the index. Two independent external LLM reviewers (openai, deepseek)
split on the original architecture-review brief (revise vs reject); the
delegated internal Opus arbitration (agentId a90fcb42ce311e6cc) read
`F5b.md` directly and found the "write side is simply missing the data"
premise the reject verdict rested on was disproven by the code itself — commit
is deliberately empty at write time — so a write-side fix could not close the
gap, only a read-side recovery could. It also found zero in-repo consumer for
`ADR:`/`Area:`/`FR:` trailers, so the smallest change that closes the actual
gap is Run-ID-scoped recovery only.

## Rejected Alternatives

1. **Write-side fix (stamp `commit`/`changed_files` at event-write time).**
   Rejected — disproven by `F5b.md`: the commit does not exist yet when the
   `work_completed` event is written (F5b precedes F6), so there is nothing to
   stamp. This was deepseek's original `reject` position; the internal Opus
   arbitration read the actual write-order code and found it unfixable as
   proposed.
2. **`ADR:`/`Area:`/`FR:` trailers alongside `Run-ID:`.** Rejected by both
   external architecture reviewers and the internal Opus arbitration — zero
   in-repo consumer for any of the three; `Area:` would only duplicate
   `match_area`'s existing derivation, `FR:` would duplicate
   `affected_frs`/`change_type` (already enforced by the F5b FR gate), and
   `ADR:` names a use (`supersedes_event_id` graph derivation) this spec
   already excludes for lack of a reliable event↔ADR mapping.
3. **Deriving `supersedes_event_id` from an ADR obsoletes/obsoleted-by
   graph.** Rejected — no such graph exists in this repo; the real convention
   (`Status:`/`Supersedes:` prose in `decision_log.md`) has no reliable
   event↔ADR mapping to derive from.
4. **A one-off migration script over the 815 existing entries.** Rejected —
   `build_index()` already rebuilds the full index from
   `shipwright_events.jsonl` on every cache-invalidating change
   (disposable-by-design); a separate migration pass would be redundant with
   the producer itself.

## Review Cascade Summary

Internal `spec-reviewer` PASS (9/9 ACs). Internal `code-reviewer`: 10 findings
(4 medium fixed — cache-validity re-pin, truncation-cap dot-path bias,
`--grep` history-scan filter, stale doc cell; 6 low — 4 fixed, 2 accepted with
documented reasoning). `doubt-reviewer` not_applicable (no migrations/async/
cross-plugin/irreversible-ops surface). External code-review cascade: openai
`revise` (3 findings, all fixed — an over-broad revert-subject exclusion
introduced by the internal review round removed again, a case-sensitivity gap
between the git-side `--grep` prefilter and the `(?i)` Python regex closed,
two provenance edge cases test-pinned), deepseek `approve` with zero findings.
Full findings tables: mini-plan `## Review Cascade` section.
