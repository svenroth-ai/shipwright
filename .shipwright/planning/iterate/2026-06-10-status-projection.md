# Iterate Spec: status-projection (campaign S2)

- **Run ID:** iterate-2026-06-10-status-projection
- **Type:** feature
- **Complexity:** medium (escalated from small; self-declared `touches_io_boundary`)
- **Status:** draft
- **Campaign:** 2026-06-07-tracked-campaign-status · **Sub-iterate:** S2
- **Sub-iterate spec:** `.shipwright/planning/iterate/campaigns/2026-06-07-tracked-campaign-status/sub-iterates/S2-status-projection.md`

## Goal

Add a pure `regenerate_campaign_status(campaign_dir, events_log)` producer that
projects each campaign sub-iterate's status from the (S1-stamped) event log and
merges it over the committed `status.json` under a never-downgrade guard, so a
fresh clone / deployed WebUI can rebuild the campaign board from tracked
artifacts. S2 ships the pure projection + a thin CLI wrapper only; finalize +
churn-resolver wiring is S3.

## Acceptance Criteria

- [ ] **AC1** projection over a divergent campaign is exact once every sub is
  stamped: each sub with a matching `work_completed` event → `complete`, ids /
  slugs / order driven by the `campaign.md` skeleton.
- [ ] **AC2** never-downgrade preserves a hand-run / unstamped `complete` sub:
  a sub `complete` in the committed `status.json` with no matching event stays
  `complete` (status ladder `pending < in_progress < complete`; `failed` /
  `escalated` explicit).
- [ ] **AC3** the `campaign.md` skeleton drives ordering; a missing
  `campaign.md` raises an error.
- [ ] **AC4** event projection reads the **top-level** `event["campaign"]` /
  `event["sub_iterate_id"]` (S1 shape), not `event["extras"][...]`; a real
  `commit=""` worktree event never clobbers a committed non-empty commit.
- [ ] **AC5** lifecycle recompute reuses `all_subs_complete` (campaign top-level
  `status` → `complete` iff every sub complete; otherwise prior status preserved).
- [ ] **AC6** thin CLI wrapper (`campaign_progress.py regenerate --campaign-dir`)
  writes the projected `status.json` and prints a JSON summary.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** Internal SDLC-framework producer + CLI; no
  target-project FR is touched. `change_type: tooling`. (Mirrors S1.)

## Out of Scope

- Wiring `regenerate_campaign_status` into worktree finalize (F6 status.json
  round-trip) — **S3**.
- `churn_merge.classify()` glob for `campaigns/*/status.json` + the
  `resolve_churn_conflicts` regenerate branch + `integrate_main` wiring — **S3**.
- Demoting campaign-mode 3g main-tree `update-status` to a local-board
  convenience — **S3**.
- Backfilling existing campaigns + the token-vocabulary SSoT doc — **S4**.
- Any change to the `status.json` schema or the WebUI `campaign-store.ts`
  contract (status.json stays authoritative, shape unchanged).

## Design Notes

No UI. The producer is a pure function; the only on-disk write is via the CLI
wrapper. `all_subs_complete` is promoted from `campaign_progress.py` to the new
`shared/scripts/lib/campaign_status.py` as the canonical SSoT (so both the
plugin CLI and S3's shared churn-resolver import one definition); the plugin
re-imports it.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `campaign_progress.py:cmd_regenerate` → `<campaign-dir>/status.json` | `campaign-store.ts` (WebUI), `campaign_progress.py:_load_status`, S3 finalize/resolver | JSON |
| `finalize_iterate`/runner F5b → `shipwright_events.jsonl` (`work_completed`, top-level `campaign`/`sub_iterate_id`) | `campaign_status.regenerate_campaign_status` (reads) | JSONL |
| `campaign_init.py` → `<campaign-dir>/campaign.md` (Sub-Iterates table) | `campaign_status.parse_campaign_skeleton` (reads) | Markdown table |

## Confidence Calibration

- **Boundaries touched:** events.jsonl (read, `json.loads`), status.json (write
  via CLI, `json.dumps`), campaign.md (read/parse) — see Affected Boundaries.
- **Empirical probes run:**
  - **Real-data round-trip** (read-only, against the ACTUAL tracked
    `2026-06-07-tracked-campaign-status` campaign + the real merged S1 event):
    → S1 `complete`, commit `efa1dcfc…` **preserved** (the event's `commit=""`
    did NOT clobber it), tests `3457/3458` carried; S2–S4 `pending`; top
    `active`; `matched_events=1`, `dropped_subs=[]`, `warnings=[]`. Confirms
    never-downgrade + no-clobber on live data.
  - **ts-latest selection:** two events for one sub, later ts carries its
    commit/tests (`test_latest_ts_wins`); both ts missing → file-order last-wins
    (`test_missing_ts_file_order_fallback`).
  - **Idempotence:** `regenerate ∘ regenerate == regenerate` at serialized
    level (`test_idempotent_serialized`).
  - **Producer↔parser contract:** real `campaign_init` output parses
    (`test_real_campaign_md_parses`).
  - **Suites:** shared 3067 passed / 19 skipped; iterate plugin 356 passed;
    ruff (gating ruleset) clean.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | AC1 exact projection over a stamped divergent campaign | tested | `test_campaign_status_project::test_exact_when_all_stamped` PASSED |
  | 2 | AC2 never-downgrade preserves unstamped complete sub | tested | `…::test_never_downgrade_unstamped_complete` PASSED |
  | 3 | AC3 missing campaign.md raises | tested | `test_campaign_status::test_missing_campaign_md_raises` + `test_campaign_status_projection::test_missing_md_returns_1` PASSED |
  | 4 | AC4 reads top-level keys (not extras) | tested | `…::test_reads_top_level_keys_not_extras` PASSED |
  | 5 | AC4 commit="" no-clobber (synthetic + real S1 shape) | tested | `…::test_commit_empty_no_clobber` + `test_campaign_status_projection::test_boundary_probe_real_s1_shape_no_clobber` PASSED |
  | 6 | AC5 lifecycle: all-complete overrides prior failed | tested | `…::test_lifecycle_all_complete_overrides_prior_failed` PASSED |
  | 7 | AC5 lifecycle: partial preserves prior | tested | `…::test_lifecycle_partial_preserves_prior` PASSED |
  | 8 | AC5 `_all_subs_complete` is the shared canonical (SSoT alias) | tested | `…::TestAllSubsCompleteAlias::test_alias_is_the_shared_canonical` PASSED |
  | 9 | AC6 CLI writes status.json + fixed summary | tested | `…::test_writes_status_and_prints_summary` PASSED |
  | 10 | AC7 skeleton drives ordering | tested | `…::test_skeleton_drives_order` PASSED |
  | 11 | field-level no-clobber (tests_passed/total null) | tested | `…::test_tests_null_no_clobber` PASSED |
  | 12 | latest-ts + missing-ts fallback | tested | `…::test_latest_ts_wins`, `…::test_missing_ts_file_order_fallback` PASSED |
  | 13 | drop non-skeleton committed subs + report | tested | `…::test_drops_non_skeleton_committed_subs` PASSED |
  | 14 | corrupt/blank event line skipped + warning | tested | `…::test_corrupt_line_skipped_with_warning` PASSED |
  | 15 | skeleton strict-validate (missing table / dup / empty id) | tested | `test_campaign_status::TestParseSkeleton` (3 cases) PASSED |
  | 16 | never-downgrade ladder incl. failed/escalated, no KeyError | tested | `test_campaign_status::TestMergeStatus` (6 cases) PASSED |
  | 17 | producer↔parser contract (real campaign_init output) | tested | `test_campaign_status_projection::test_real_campaign_md_parses` PASSED |
  | 18 | idempotent regeneration | tested | `test_campaign_status::test_idempotent_serialized` PASSED |
  | 19 | cross-layout shared-lib walk-up import | tested | live probe (dev worktree + plugin-cache) + `…::TestAllSubsCompleteAlias` + 356 plugin suite |

  0 testable-but-untested. No `untestable` rows (no prod-credential / device /
  visual / tty / external-service behavior in this diff).

- **Confidence-pattern check:**
  - *asymptote (depth):* the "confident with the plan?" check did NOT terminate
    at "yes" — the external review then surfaced 9 hardening findings (ts
    robustness, off-ladder KeyError, strict skeleton, field-level no-clobber, …),
    each folded in and pinned by a test; the real-data probe ran AFTER. Depth
    satisfied (one more probe followed every "looks fine").
  - *coverage (breadth):* all 19 ledger rows `tested`; 0 untested-testable.

## Verification (medium+)

- **Surface:** none
- **Runner command:** n/a
- **Evidence path:** unit suite (`plugins/shipwright-iterate/tests/test_campaign_status_projection.py`, `shared/tests/...`)
- **Justification (surface=none):** S2 ships a pure library + CLI only and is
  **not** wired into finalize/runtime (S3). No `status.json` is regenerated in
  any deployed/UI flow from S2, and the WebUI status.json contract is unchanged,
  so there is no startable web/api/cli-app surface to drive. The empirical
  verification is the Boundary Probe round-trip (real S1 event → projected
  status.json, asserted exact) plus the regenerate-CLI smoke, both in the unit
  suite.
