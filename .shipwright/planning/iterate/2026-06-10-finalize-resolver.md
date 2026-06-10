# Iterate Spec — S3: Finalize wiring + churn resolver (regenerate-on-conflict)

**Run ID:** `iterate-2026-06-10-finalize-resolver`
**Campaign:** `2026-06-07-tracked-campaign-status` · **Sub-iterate:** S3 · **Anchor:** `trg-fda5f7a3`
**Intent:** CHANGE (tooling) · **Complexity:** medium · **Spec impact:** none (framework tooling, no FR)
**Risk flags:** `touches_shared_infra`, `touches_io_boundary`

## Problem

S1 made `work_completed` events self-identifying (top-level `campaign` /
`sub_iterate_id`). S2 added the pure projection lib
`shared/scripts/lib/campaign_status.py` (`project_campaign_status` /
`regenerate_campaign_status`) + a `campaign_progress regenerate` CLI — but it is
**NOT wired into the runtime**: a campaign's `status.json` is still write-once
`pending` on a fresh clone and the producer-maintained board only updates via the
autonomous loop's main-tree `campaign_progress update-status` (3g), which writes
the **untracked** main-tree file (never ships in a PR). S3 closes the loop.

## Scope (from the sub-iterate spec)

1. **Worktree finalize.** After F5b records `work_completed`, re-project the
   campaign's `status.json` from the campaign.md skeleton + this worktree's
   (now self-sufficient) event log via `regenerate_campaign_status`, and write
   it into the worktree's `campaigns/<slug>/status.json` so **F6 stages it** and
   it ships in the PR (per-tree, PR-committed — mirrors events.jsonl/triage.jsonl).
2. **Demote campaign-mode 3g** main-tree `update-status` to a local-board
   convenience (the tracked per-tree write is now authoritative).
3. **Churn resolver.** `churn_merge.classify()` admits
   `.shipwright/planning/iterate/campaigns/*/status.json` as resolvable via a
   **glob predicate** (it is a wildcard path, not a fixed allowlist entry);
   `resolve_churn_conflicts.complete_merge` resolves a conflict to a placeholder
   side then **regenerates from the merged event log** (mirroring DERIVED_MDS);
   wire the regenerate into `integrate_main`.

## Acceptance Criteria (sub-iterate)

- **AC-1** F6 `status.json` round-trip (per-tree, PR-committed): finalize writes
  the projected `status.json` into the worktree; the bytes match the
  `campaign_progress regenerate` CLI output (single producer).
- **AC-2** `classify`-glob matches `campaigns/*/status.json` (one slug segment
  only; nested paths and other JSON do NOT match); source still blocks.
- **AC-3** `integrate_main` concurrent-sibling regenerate: a `status.json` merge
  conflict resolves to a placeholder then re-projects from the union event log;
  `events_invalid` still aborts before any regenerate runs.

## Affected Boundaries (Step 7 item 7)

| Boundary | Direction | Round-trip |
|---|---|---|
| `campaigns/<slug>/status.json` | producer (write) | finalize write ↔ `regenerate` CLI write byte-parity |
| `shipwright_events.jsonl` | consumer (read) | projection reads top-level `campaign`/`sub_iterate_id` |
| churn merge conflict | classify + resolve | glob admit ↔ placeholder+regenerate ↔ `events_invalid` abort |

## Plan

- `churn_merge.py`: `CAMPAIGN_STATUS_GLOB`, `is_campaign_status(rel)` (single-segment
  glob guard), `classify()` admits via the predicate.
- `resolve_churn_conflicts.py`: import predicate; placeholder (`--theirs`) branch
  for campaign-status conflicts in `complete_merge`; `_regenerate_campaign_statuses`
  globs every campaign with a `campaign.md` and re-projects from the merged log;
  wired into `regenerate_tracked_snapshots` on a full regen (`only is None`).
- `integrate_main.py`: extend the regenerate-failed transactional rollback to
  restore touched campaign `status.json` files too.
- `finalize_iterate.py`: `_regenerate_campaign_status(project_root, event_extras)`
  helper (best-effort, gated on the `campaign` stamp) + Step 6 in `run()`.
- Skill refs: `F5b.md` (finalize now writes status.json), `F6.md` (stage it
  conditionally), `campaign-mode.md` 3g (demote to local convenience).

## Confidence Calibration
- **Boundaries touched:** finalize → `campaigns/<slug>/status.json` write (Step 6);
  `shipwright_events.jsonl` read (top-level `campaign`/`sub_iterate_id`);
  churn merge classify/resolve/regenerate; integrate transactional rollback.
- **Empirical probes run:**
  - *Real-campaign projection probe* (this campaign, pre-S3-event): S1+S2
    `complete` (self-healed from the stale committed S2=`pending`), S3+S4
    `pending`, top-level `active`, 0 dropped, 0 warnings, idempotent serialize
    round-trips — confirms the producer on the actual artifact before finalize.
  - *Byte-parity*: finalize-written `status.json` == `json.dumps(projected,
    indent=2, ensure_ascii=False)` (test_finalize_campaign_status) == the
    `campaign_progress regenerate` CLI serialization (single producer).
  - *Glob truth table*: single-segment match, backslash-normalised, nested /
    campaign.md / outside-tree all rejected (test_churn_merge).
  - *Concurrent-sibling integrate*: status.json conflict → placeholder →
    union-event re-projection → S1+S2 complete; `events_invalid` aborts before
    regen; regenerate-failure rolls the board back (test_integrate_campaign_status).
- **Test Completeness Ledger:**

  | Behavior (this diff) | Disposition | Evidence |
  |---|---|---|
  | `is_campaign_status` single-segment glob (normalise, reject nested/md/outside) | tested | test_churn_merge::test_is_campaign_status_truth_table, ::test_glob_constant_is_single_segment_wildcard |
  | `classify` admits campaign status / still blocks campaign.md + source | tested | test_churn_merge::test_classify_admits_campaign_status_via_glob, ::test_classify_still_blocks_campaign_md_curated_prose |
  | resolver placeholder-resolves a status.json conflict (`--theirs`) | tested | test_resolve_churn_campaign_status::test_resolves_campaign_status_conflict_to_placeholder |
  | resolver BLOCKS a campaign.md conflict (touch nothing) | tested | ::test_campaign_status_md_conflict_blocks_touching_nothing |
  | full-regen re-projects every campaign + stages (byte-parity) | tested | ::test_regenerate_reprojects_campaign_status_from_events |
  | restricted `only` set skips campaign regen | tested | ::test_regenerate_skips_campaign_status_when_only_restricted |
  | finalize Step 6 writes per-tree board (byte-parity) | tested | test_finalize_campaign_status::test_run_regenerates_campaign_status_with_byte_parity |
  | finalize skips: non-campaign / absent dir / symlink target | tested | ::test_run_skips_campaign_status_for_non_campaign_iterate, ::test_run_skips_when_campaign_dir_absent, ::test_run_skips_symlinked_status_target (POSIX/CI; platform-skips where symlink unprivileged) |
  | integrate concurrent-sibling regenerate (union projection) | tested | test_integrate_campaign_status::test_integrate_concurrent_sibling_status_regenerate |
  | integrate `events_invalid` aborts before campaign regen | tested | ::test_integrate_status_regen_skipped_when_events_invalid |
  | integrate rollback restores campaign status on regenerate failure | tested | ::test_integrate_rolls_back_campaign_status_on_regenerate_failure |
  | never-downgrade / stale-board self-heal | tested | test_campaign_status (S2) + real-campaign probe above |

  0 testable-but-untested. The only platform-gated row (symlink) executes on
  Linux CI; no `could-test-but-didn't`.
- **Confidence-pattern check:** *Depth (asymptote)* — the producer is a single
  pure function reused by all three call sites (finalize/resolver/CLI), so
  byte-parity at one site generalises; the real-campaign probe exercised it on
  the actual artifact, not a fixture. *Breadth (coverage)* — all three callers +
  both merge outcomes (placeholder-conflict and clean-union) + all three abort
  paths (blocked / events_invalid / regenerate_failed) are covered. No web
  surface (pure-Python tooling) → F0.5 `surface=none` with justification.
