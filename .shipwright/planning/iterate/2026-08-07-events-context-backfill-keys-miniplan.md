# Mini-Plan: events-context-backfill-keys

- **Run ID:** iterate-2026-08-07-events-context-backfill-keys
- **Spec:** `.shipwright/planning/iterate/2026-08-07-events-context-backfill-keys.md`

## 1. Files to create/modify

**Trimmed after architecture review — see spec `## Architecture Review`.**
`ADR:`/`Area:`/`FR:` trailers, the `area_catalog.py match` subcommand, and
the `F6.md` change are all cut (zero consumers in this change). Rows below
reflect the trimmed scope.

| File | Change |
|---|---|
| `shared/scripts/lib/commit_trailers.py` | new — Run-ID-scoped: `parse_trailers(body)` (internal, `Run-ID:` only), `resolve_base_ref(repo_root)`, `build_run_id_commit_map(repo_root, base_ref)`: two `git log` calls over `base_ref` returning `{run_id: {"sha": ..., "changed_files": [...]}}` |
| `shared/scripts/lib/event_context_index.py` | edit — `_event_entry` backfills `commit`/`changed_files` from the commit map when empty; adds `provenance` per entry; removes `extraction`; `build_index` adds envelope `coverage`; `INDEX_SCHEMA_VERSION` 1→2 |
| `shared/scripts/lib/area_catalog.py` | no change — `match_area`/`normalize_path` reused as-is |
| `shared/scripts/tests/test_event_context.py` | edit — extend determinism/hostile-input tests for `provenance`+`coverage`; add backfill-from-git test (fixture repo with a real commit + Run-ID trailer) |
| `shared/scripts/tests/test_commit_trailers.py` | new — unit tests for the trailer/commit-map reader against a fixture git repo |
| `integration-tests/test_event_context_workflow.py` | read-only check — confirm still green, no edit expected (CLI entry points unchanged) |

## 2. Work breakdown

1. **`commit_trailers.py`: Run-ID-scoped trailer reader + commit map**
   (trimmed to `Run-ID:` only after architecture review — no `ADR:`/`Area:`/
   `FR:` reading; see spec `## Architecture Review`). Write tests first
   (fixture: `tmp_path` git repo, 2-3 commits with `Run-ID:` trailers, one
   without any trailer, **one duplicate Run-ID across two commits, one
   merge commit carrying a Run-ID trailer, one commit body containing raw
   NUL/control bytes crafted to look like a delimiter**).
   Implement `resolve_base_ref(repo_root) -> str | None` (`origin/HEAD` →
   `origin/main` → `origin/master` → local `HEAD`, first that resolves via
   `git rev-parse --verify`, soft-fail `None`), and
   `build_run_id_commit_map(repo_root, base_ref)`. **No generic
   `parse_trailers(body) -> dict`** — actual implementation applies the
   `Run-ID:` regex directly via an internal `_parse_bodies` (sha→body only,
   no trailer-dict abstraction), which is already the narrow, Run-ID-scoped
   surface the second external-review round (below) asked for; this line
   corrects stale aspirational text from before implementation. **Two git calls, not one combined call** (external review
   openai #5 — a single `--name-only --pretty=format:...B...` call has no
   safe way to bound where a hostile commit body ends and the file list
   begins):
   - Call A (sha→body, for trailer extraction): `git -c core.quotepath=false
     log <base_ref> --no-merges --pretty=format:%H%x00%B%x00` — split on
     `\x00`, and validate every candidate sha token against
     `^[0-9a-f]{40}$` before trusting the body that follows it; a token
     that fails the check is a resync point, not a crash (bounds the blast
     radius of a crafted NUL/x00 in a commit body to one skipped record).
   - Call B (sha→changed-files, for the file map): `git -c
     core.quotepath=false log <base_ref> --no-merges --no-renames
     --name-only --pretty=format:%x00%H` — no body/user-text is present in
     this call's format at all (only the sha and git's own newline-listed
     filenames, which cannot contain NUL), so there is no delimiter-safety
     question here to begin with.
   - Both calls: `encoding="utf-8", errors="replace"` matching
     `git_log_scan.py`'s subprocess contract, `timeout=60`.
   - **Merge commits are excluded from the map entirely** (`--no-merges`) —
     `--name-only` emits no diff for a multi-parent commit, so a Run-ID
     trailer that only lands on a merge must resolve `unavailable`, never
     `derived` with an empty file list (that would be worse than the status
     quo: a confidently-wrong "derived" label). Squash-merge commits (the
     normal PR-merge shape here) have one parent and are unaffected.
   - **Duplicate Run-ID across commits** (the normal case here — repair
     commits, `chore(triage): fold … append(s)`): union `changed_files`
     across every matching commit; `sha` = the newest match in `git log`'s
     (reverse-chronological) output order. Pinned by the duplicate-commit
     fixture test above — not "last write wins" by accident.
   - Soft-fail to `{}` on any git error (non-repo, missing base_ref, timeout)
     and record the outcome (`ok` / `timeout` / `no-repo`, `commits_scanned`,
     `base_ref_used`) for `build_index()` to surface in the `coverage`
     envelope — a slow or failed git scan must be visible, not silently
     reflected only as more `unavailable` rows.
   - **Exactly one join key** (external review openai #1 — high, and moot
     now that `ADR:` reading is cut entirely): the map is keyed by `Run-ID:`
     trailer value only, matched against the entry's already-existing
     `run_id` field (`event.get("run_id") or event.get("adr_id")`,
     unchanged fallback). Legacy pre-2026-05-16 events whose `run_id` is
     `ADR-NNN`-shaped simply won't match any `Run-ID:` trailer and resolve
     `unavailable` — a coverage limitation, not a bug.
2. **`event_context_index.py`: backfill + provenance.** Write tests first in
   `test_event_context.py` (event with empty `commit`/`changed_files` but a
   real `run_id` matching a fixture commit → backfilled + `provenance:
   derived`; event with `commit` already set → untouched + `provenance:
   declared`; event with no matching commit → `provenance: unavailable`;
   event whose only matching commit is a merge → `unavailable`, not
   `derived`; **hostile git data** — a fixture commit whose Run-ID-matched
   diff includes control chars / a `../escape` path / a secret-shaped string
   → backfilled `commit`/`changed_files` MUST route through the same
   `sanitize_text`/`normalize_path` calls the declared path already uses,
   extending `test_hostile_event_text_is_untrusted_redacted_and_bounded`
   rather than adding an unguarded second inlet; **size cap** — a fixture
   commit touching 80 files → `changed_files` capped at 50 with
   `changed_files_truncated: true`, mirroring the existing `summary_truncated`
   convention). Implement: `build_index()` computes the commit map once via
   `commit_trailers.build_run_id_commit_map`, threads it into `_event_entry`.
   Replace `extraction` with `provenance`. Add `coverage` envelope counts
   (per-key derived/declared/unavailable, plus the commit-map scan outcome
   from step 1). Bump `INDEX_SCHEMA_VERSION`, extend `required` in
   `load_or_rebuild_index` (confirmed: the schema-version check runs BEFORE
   the required-key check, so a v1 on-disk cache is rejected and rebuilt,
   never misread as complete — verified against the actual code, not
   assumed).
   - **Cache-validity trade-off, stated explicitly rather than engineered
     around:** git state is now an input to the index but is NOT part of the
     cache-validity key (that would cost a `git log` call on every cache
     *hit*, defeating the point of caching). A cached index can therefore
     show stale provenance for a few minutes between a new commit landing
     and the next event-log-triggered rebuild. Accepted: the index is
     documented as disposable/best-effort, not a live view, and the next
     append to `shipwright_events.jsonl` (which already invalidates the
     cache via the fingerprint check) rebuilds it with current git state
     anyway.
3. **Full test suite + `verify_local.py`.** Confirm
   `test_event_context_workflow.py`'s six-surface assertion is untouched and
   green (proves no producer-contract text drift), run the shared test root
   plus integration-tests.

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

`events-context-index.json` entry schema: `extraction` (object) removed,
`provenance` (object, 5 keys) added. Envelope: `coverage` (object) added.
`INDEX_SCHEMA_VERSION` 1→2 (self-invalidating — no manual migration needed,
`load_or_rebuild_index`'s version check rebuilds automatically).

## 5. Test strategy

Unit (`shared/scripts/tests/test_event_context.py`,
`shared/scripts/tests/test_commit_trailers.py`): fixture git repos +
fixture event logs, no network/subprocess flakiness beyond local `git`.
Integration (`integration-tests/test_event_context_workflow.py`): existing
CLI round-trip test must stay green unmodified. No E2E — no UI/web surface.
Boundary Probe (Step 6, `touches_io_boundary`-equivalent): round-trip
`build_index()` → write → `load_or_rebuild_index()` → read, assert
`provenance`/`coverage` survive the round trip byte-identically.

## 6. Alternative approach (considered, rejected)

**Alternative: a one-off `backfill_events_context.py` migration script**
that rewrites `events-context-index.json` once, separate from
`build_index()`. Rejected because the index is explicitly disposable
(rebuilt from `shipwright_events.jsonl` on every cache-invalidating change
— `load_or_rebuild_index`'s fingerprint check already discards it
routinely), so a one-off script's output would be silently overwritten by
the very next unmodified `build_index()` call and the empty-keys problem
would return. The backfill has to live in the producer itself to survive
past the first cache invalidation — which is also strictly less code than
maintaining a separate migration path.

## Plan Review Findings (internal, Opus — `shipwright-plan:opus-plan-reviewer`, model=opus)

Full review folded into Work Breakdown steps 1-2 above (agentId
a96dc4e349a36baf3). Summary of what changed as a result:

| # | Finding | Severity | Resolution |
|---|---|---|---|
| B1 | `--name-only` emits no diff for merge commits — a Run-ID trailer on a merge would resolve `derived` with an empty file list (worse than the status quo) | blocker | `--no-merges` on the git log call; merge-only matches resolve `unavailable`. Squash-merge commits (this repo's normal PR shape) have one parent and are unaffected |
| B2 | Soft-fail-on-timeout inside `build_index()` risks non-deterministic output across two calls, silently, on a large/slow repo | blocker | explicit `timeout=60`; commit-map scan outcome (`ok`/`timeout`/`no-repo`, `commits_scanned`) surfaced in the `coverage` envelope so degradation is visible, not silent |
| S1 | Windows encoding + `core.quotepath` path-escaping could silently drop non-ASCII paths; rename detection can hide real paths | should-fix | match `git_log_scan._run_git`'s `encoding="utf-8", errors="replace"`; add `-c core.quotepath=false` and `--no-renames` |
| S2 | Duplicate Run-ID across commits is the NORMAL case here (repair commits, triage folds), not a corner case; unhandled it becomes accidental oldest-wins | should-fix | union `changed_files` across matches, newest match wins `sha`, pinned by a duplicate-commit fixture test |
| S3 | Backfilled `commit`/`changed_files` could bypass the existing untrusted-input sanitization the declared path already gets | should-fix | route backfilled values through the same `sanitize_text`/`normalize_path` calls; extend the hostile-input test to a git-sourced fixture |
| S4 | No size bound on backfilled `changed_files` (a release/fold commit can touch hundreds of files) | should-fix | cap at 50 + `changed_files_truncated: true`, mirroring the existing `summary_truncated` convention |
| S5 | Git state is a new input to the index but not part of the cache-validity key | should-fix | accepted trade-off, stated explicitly (see step 2) rather than paying a `git log` call on every cache hit |
| N1 | Delimiter-based parsing (`%x01%H%x02%B%x03`) should be verified empirically, not just assumed reliable | nice-to-have | build step includes an empirical check: parsed record count == `git rev-list --count` on the fixture repo |
| N2 | `Run-ID:` trailer regex requires `(\S+)$` — won't match a value followed by trailing text | nice-to-have | kept identical to the existing regex by design (drift risk of two copies diverging is worse); `unmatched_run_ids` surfaced in `coverage` so a regex miss is visible |
| N3 | Security: shelling out to git with untrusted input | — | not applicable — no attacker-controlled argv (confirmed) |

Confirmed sound, no change needed: schema-version bump ordering (verified
against actual `load_or_rebuild_index` code — version check precedes the
required-key check), and the no-cross-plugin-import decision (confirmed
against `plugins/shipwright-compliance/scripts/lib/collectors/change_history.py`'s
own stated rule; `extraction` has zero consumers repo-wide so its removal
is safe).

## External LLM Review (Branch A — openai + deepseek via OpenRouter, `--mode iterate`)

Both reviewers returned `revise`, no contradiction (`requires_resolution:
false`). Findings folded into the spec ACs and Work Breakdown step 1 above:

| # | Source | Finding | Severity | Resolution |
|---|---|---|---|---|
| 1 | openai | Plan implied matching by `run_id`/`adr_id` but only indexed `Run-ID:` trailers; `ADR:` trailer conflated with the run's own id | high | exactly one join key (`entry.run_id` ↔ `Run-ID:` trailer); `ADR:` trailer redefined as optional OTHER-ADR references, never a join key |
| 2 | openai | Byte-identical determinism claim conflicts with a soft-fail timeout path | medium | AC reworded: determinism holds when the scan completes without timeout; timeout is a recorded, visible `coverage.commit_map.status`, not silent nondeterminism |
| 3 | openai, deepseek | No repo-root/base-ref resolution mechanism specified | high (both flagged independently) | `resolve_base_ref(repo_root)`: `origin/HEAD` → `origin/main` → `origin/master` → local `HEAD`; recorded in `coverage.commit_map.base_ref_used` |
| 4 | openai | Provenance semantics under-specified for empty/rejected results (matched commit with 0 files; all paths rejected by normalize_path; 0 areas matched) | medium | field-level rule, pinned by tests: `commit` derived on any valid sha match; `changed_files` derived whenever a commit was found (an empty result is a genuine computed fact, not "unavailable" — a commit CAN legitimately touch 0 files); `area_ids` derived whenever `changed_files` is non-empty (0 matches is a valid computed answer), `unavailable` only when `changed_files` itself is empty/unavailable |
| 5 | openai | `%x01%H%x02%B%x03` combined with `--name-only` has no safe boundary for hostile commit-body bytes | medium | split into two calls (A: sha→body, no filenames; B: sha→filenames via `%x00%H`, no body/user-text at all) — see Work Breakdown step 1 |
| 6 | openai | `coverage` (envelope) should also gate cache validity, not just per-entry `provenance` | low | added `"coverage" in payload` to the envelope-level validity check in `load_or_rebuild_index`, alongside the schema-version check that already forces a v1→v2 rebuild unconditionally |
| 7 | openai | Duplicate-Run-ID union means `commit` (one sha) and `changed_files` (unioned) no longer describe literally the same diff | low | documented explicitly: `commit` = newest matching sha, `changed_files` = union across all matches — not implied to be one commit's literal diff |
| 8 | deepseek | Same as #3 (independent corroboration) | high | see #3 |
| 9 | deepseek | `--name-only` can list submodule gitlink paths, not just regular files | medium | accepted, documented limitation — no submodule usage found in this repo today; `match_area` already degrades gracefully (returns `None`) on any path it can't match, so no crash risk |
| 10 | deepseek | Backfilled paths should go through `normalize_path`, not `sanitize_text` (which is for free text) | low | already the plan's actual shape — backfilled raw paths feed the SAME existing `_strings()` → `normalize_path()` pipeline declared paths already use, not a parallel path; `sanitize_text` stays scoped to the scalar `commit` sha field |
| 11 | deepseek | Recomputing `area_ids` from `changed_files` on every rebuild means catalogue evolution retroactively changes historical entries | low | confirmed pre-existing behavior (current code already recomputes unconditionally on every `build_index()` call) — not introduced by this change, noted in spec for clarity, no design change |
| 12 | deepseek | Confirm `commit_trailers.py` is importable in all test contexts | low | build-time check — follow the existing `from .area_catalog import ...` relative-import convention already used by `event_context_index.py` |

## External LLM Re-Review (post-implementation, against the trimmed plan)

Re-ran `--mode iterate` after Build to check the trim actually landed clean.
Verdicts: deepseek **approve** ("core problem... addressed with careful
attention to edge cases, security, and determinism"), openai **revise**
(no contradiction — one step apart). Findings:

| # | Source | Severity | Finding | Resolution |
|---|---|---|---|---|
| 1 | openai | high | Call B's `--name-only` splits on `\n`; a filename legally containing an embedded newline would be mis-parsed into two files | **accepted, documented** — matches the codebase's OWN established convention (`plugins/shipwright-compliance/scripts/audit/git_log_scan.py::commit_info`, `shared/scripts/tools/verifiers/git_helpers.py::_commit_changed_paths` both already parse `--name-only` output the same way); this repo's dev environment is Windows, where NTFS cannot even produce such a filename; `-z` NUL-safety would deviate from every other git-output parser in the codebase for a threat this repo's own trusted history does not present |
| 2 | openai | medium | Call A's SHA-regex resync isn't airtight against a body deliberately crafted with NUL + 40 hex chars | **accepted** — no attacker-controlled input reaches this path (the repo's own trusted, already-merged commit history, not third-party submissions); matches N3 from the internal Opus plan review |
| 3 | openai | medium | A timeout/no-repo scan result gets persisted as a schema-valid v2 index and could stay degraded until the next event-log append | **accepted, documented** — self-heals on the next append (routine in an active repo), already visible via `coverage.commit_map.status`; deepseek's parallel low-severity finding on the same point said "accept as-is... no change required unless this becomes a recurring operational issue" |
| 4 | openai | medium | Two `git log <ref>` calls against a movable ref could see different history if the ref advances between them | **fixed** — `build_run_id_commit_map` now resolves `base_ref` to an immutable sha via `git rev-parse --verify` ONCE, before either call, and both walks use that sha; the resolved sha is also recorded in `coverage.commit_map.resolved_sha` for reproducibility, per the reviewer's own suggestion. Pinned by `test_base_ref_is_pinned_to_a_sha_before_scanning` |
| 5 | openai | low | No stated minimum git version for the output features used | moot — no NUL-safety (`-z`) change was made, so no new git-version requirement was introduced |
| 6 | openai | low | The mini-plan's own text (`parse_trailers(body) -> dict`) reads broader than the Run-ID-scoped contract the architecture review asked for | **already true in the actual code** — the mini-plan's Work Breakdown step 1 text was stale/aspirational; the real implementation never built a generic trailer-dict function, only the narrow inline regex search this finding asks for. Corrected the stale text above rather than changing code |
| 7 | deepseek | low | Same newline-filename point as openai #1 | see #1 |
| 8 | deepseek | low | A shallow clone (CI `depth=1`) would silently produce `unavailable` for in-range commits without indicating clone depth as the cause | **accepted, documented limitation** — out of scope for this change; `coverage.commit_map.commits_scanned` is visible and a shallow clone would show as an unusually low count, which is enough signal for the visibility this spec commits to (making degradation VISIBLE, not diagnosing every possible cause of it) |
| 9 | deepseek | low | Removing `extraction` could break an unknown external/dynamic consumer beyond what a repo-wide grep can see | **accepted** — the schema-version bump is the guard for in-repo code (confirmed by the internal Opus review); no external consumer is documented anywhere in this repo |
| 10 | deepseek | low | `timeout=60` may be insufficient for very large histories | **accepted as-is** — deepseek's own assessment: "no change required unless this becomes a recurring operational issue" |

## Review Cascade (SKILL.md Step 8, model=opus per explicit user instruction)

**Stage 1 `spec-reviewer`: PASS**, no citations. Two non-blocking observations
passed to Stage 2 (stale Design Notes text superseded by Out of Scope; the
`hooks-and-pipeline.md` cell needed updating for the new git-history input) —
both folded into Stage 2's own findings below.

**Stage 2 `code-reviewer`: 10 findings** (4 medium, 6 low). Bloat Checklist:
PASS.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | medium | Cache validity (`load_or_rebuild_index`) checked the event-log fingerprint but not git state — a commit landing after a build with no new event (F5b before F6) stayed pinned at `unavailable` indefinitely | **fixed** — `resolve_base_ref` now returns `(ref, sha)`; `load_or_rebuild_index` re-resolves it on every cache-hit path and rebuilds on a sha mismatch. One cheap `rev-parse`, not a history walk. Pinned by `test_new_commit_landing_after_index_build_triggers_rebuild_not_stale_cache` |
| 2 | medium | The 50-file truncation cap sorted alphabetically, which systematically keeps dot-prefixed bookkeeping paths (`.shipwright/`, `.github/`) over source paths — exactly the paths that carry ranking signal | **fixed** — sort key changed to `(path.startswith("."), path)`; non-dot paths always survive the cap first. Pinned by `test_truncation_prefers_source_paths_over_dot_prefixed_bookkeeping` |
| 3 | medium | Both `git log` walks scan full history unfiltered; `--name-only` computes a diff for every non-merge commit even though only a handful can have a `Run-ID:` trailer | **fixed** — both calls carry `--grep=Run-ID: -i` (case-insensitive to match `_RUN_ID_TRAILER_RE`'s own `(?i)`), a strict superset of the anchored regex so it can only admit more commits, never fewer |
| 4 | medium | `docs/hooks-and-pipeline.md:2754` still described the index as rebuildable from "the unchanged raw event log + area catalog", now stale — git history is a third input the fingerprint doesn't cover | **fixed** — cell updated to name git history as an input and describe the new cache-validity re-check |
| 5 | low | `--name-only` paths are relative to the repo root, not the project root, if they ever diverge | **accepted, documented** — every in-repo caller runs from a worktree whose root IS the git toplevel (`setup_iterate_worktree.py`); the divergent case cannot occur in this deployment |
| 6 | low | Newest-wins + loose trailer match could let a hand-edited revert pasting back another run's trailer hijack the map entry | **fixed, narrowly, then partly reverted** — see external re-review #1 below; ended up removing the guard this finding motivated rather than keeping it |
| 7 | low | `changed_files_truncated` is only ever set on the derived branch; a declared list of 5,000 files reports `false` | **accepted, documented** — declared lists are event-log-authored data, not a backfill safety valve; capping them was never in scope and would be a silent behavior change on data the event log itself controls |
| 8 | low | `base_ref`/`pinned_sha` reach git argv unvalidated against a `-`-prefixed value (no live exposure — all in-repo callers pass fixed values) | **fixed** — `--end-of-options` on `rev-parse`, trailing `--` on both `log` calls; `pinned_sha` now only ever comes from `_SHA_RE`-validated `resolve_base_ref` output |
| 9 | low | `resolve_base_ref` and `build_run_id_commit_map` each ran their own `rev-parse` on the same ref | **fixed** — folded into the same refactor as #8: `resolve_base_ref` returns the pinned `(ref, sha)` once, `build_run_id_commit_map` consumes it directly |
| 10 | low | `_git`/`_init_repo`/`_commit` duplicated verbatim between the two new test files | **accepted, non-blocking** — reviewer's own note: two pre-existing files in the same directory already roll their own git helpers (house style), and no coverage is lost either way |

**Stage 3 `doubt-reviewer`: not_applicable.** None of the four triggers
(migrations, async/concurrency, cross-plugin imports, irreversible ops) apply
— this diff is read-only git subprocess calls and regex parsing within one
package.

**External Code-Review Cascade (Branch A — `external_code_review.enabled:
true`, diff 834 lines): openai revise, deepseek approve** (one step apart,
no contradiction).

| # | Source | Severity | Finding | Resolution |
|---|---|---|---|---|
| 1 | openai | medium | The `Revert `-subject exclusion added for Stage-2 finding #6 goes further than the spec's stated merge-only exclusion — it would also discard a LEGITIMATE run whose shipped commit genuinely is `git revert <bad-sha>` carrying its own fresh Run-ID | **fixed** — guard removed. The scenario it defended against (a hand-edited revert pasting back a FOREIGN run's trailer) requires deliberate `git revert -e` misuse and was already shown empirically (`test_default_git_revert_carries_no_trailer_so_original_run_id_wins`) not to occur with default `git revert` usage; the guard's cost (discarding a real, spec-compliant case) outweighed the contrived case it prevented. Pinned by `test_revert_subject_commit_with_its_own_run_id_recovers_normally` |
| 2 | openai | low | `_RUN_ID_TRAILER_RE` is `(?i)` but the new `--grep=Run-ID:` prefilter (Stage-2 finding #3) was case-sensitive, silently narrowing what the Python regex would accept | **fixed** — added `-i` to both `git log --grep` calls, closing the exact gap Stage-2's own fix opened. Pinned by `test_lowercase_trailer_matches_the_case_insensitive_git_grep_prefilter` |
| 3 | openai | low | No test pins the two provenance edge cases: an empty-diff matched commit must still be `changed_files: derived`; changed files matching zero catalog areas must still be `area_ids: derived` with an empty list | **fixed, test-only** — both already worked correctly (the `elif backfill:` branch keys off commit-match presence, not list non-emptiness; `area_ids` provenance keys off `paths` non-emptiness, not `areas`), just untested. Added `test_empty_diff_backfilled_commit_is_derived_not_unavailable` and `test_changed_files_matching_zero_catalog_areas_is_derived_not_unavailable` |
| — | deepseek | — | "No correctness bugs, security flaws, or regression risks are apparent... test coverage matches the specification's ledger" | approve, no findings |

All 6 review-record types closed: `self`/`plan`/`code`/`spec`/`external_code`
= `completed`, `doubt` = `not_applicable`. Full suite re-verified green after
this round (36 tests in the two new files + `test_event_context.py`), ruff
clean, all four touched source/test files under 300 LOC.
