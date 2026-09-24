# Mini-Plan — R5b: serial merge lane (campaign-dag-scheduler)

No mini-plan file was authored during planning for this campaign sub-iterate
(campaign sub-iterates are dispatched directly from
`sub-iterates/R5b-merge-lane.md` + the plan doc's own "R5b — serial merge
lane" section; there is no separate Mini-Plan Protocol step in campaign
mode). This file is written at Build time, before the external plan review,
so that review has a concrete artifact to check against — mirroring
`iteration-planning.md`'s own "no mini-plan file present" fallback, but
supplying one rather than reviewing the spec alone, since the spec itself is
the design authority and a second copy of it adds no signal.

## Problem

`campaign-mode.md` steps 3f-bis through 3i describe the serial merge lane
built by earlier sub-iterates (R1-R4), but four gaps remain before it is
provably safe to run: (1) review attribution is asserted only loosely before
the reviews.json commit; (2) `shipped_head` is dual-written (a legacy path
from R3) instead of read once from `review_pin.json`; (3) nothing confirms
the PR's actual merge commit SHA before recording `merged`, so a concurrent
push race could record the wrong commit; (4) `STRICT-STOP` has no drain
semantics — a mid-wave abort can strand `running`/`merging` units and never
release the session lock.

## Approach

1. **HEAD == reviewed_head exactness** — before the reviews.json commit,
   assert current branch tip literally equals the pinned `reviewed_head`;
   on deviation, invalidate the pin (`check_review_attribution.py --mode
   invalidate`, new) and demote `reviewed -> built` to re-enter 3f-bis.
2. **`shipped_head` read directly from `review_pin.json`** — remove the R3
   legacy dual-write; `head_pin` is now constructed from
   `verify`'s own `.pin.shipped_head` field.
3. **PR-identity + bounded merge-commit confirmation** — after the existing
   MERGED poll, poll `mergeCommit.oid` up to a deadline, validate its shape
   with the same guard `audit_compliance_lifecycle.py::_merge_sha` already
   uses (never reinvented), and record it via `loop_claim.py mark-merged`
   (fencing-checked) — never `git rev-parse origin/{default}` as a fallback.
4. **Currency check while `reviewed`, not `merging`** — `built -> reviewed`
   is recorded first; the mergeability check runs in `reviewed`; only a
   `mergeable` result promotes `reviewed -> merging`. A `conflicting` result
   triggers a rebase-first staleness cascade (`max_rebase_reviews = 2`):
   invalidate the pin, demote to `built`, and re-run 3f-bis; exhaustion
   demotes to `held` (`staleness_cascade_exhausted`).
5. **STRICT-STOP drain** (`campaign_drain.py`, new) — sweep every
   `pending`/`claimed` unit to `held` (`swept_never_started`), wait out
   `{running, merging}` up to `max_drain_seconds`, forcing terminal
   transitions (`lease_expired_during_drain`, `drain_timeout`,
   `swept_after_build`) at the bound, and only release the session lock
   after `cmd_finalize` confirms the drain completed.
6. **Step 3h status-vocabulary mapping** — `merged -> complete`,
   `failed -> failed`, `held -> failed` only for mid-flight-demotion reason
   codes, else `held -> pending`; `campaign_progress.py`'s existing 5-token
   enum is unchanged.

## Alternatives considered and rejected

- **Reinventing a merge-SHA validator** instead of reusing
  `audit_compliance_lifecycle.py::_merge_sha`'s guard pattern — rejected:
  two independently-maintained SHA-shape validators drift out of sync
  silently; the spec explicitly calls this out.
- **Keying the staleness cascade off base-SHA drift** (any origin/main
  advance) instead of an actual rebase of the unit's own branch — rejected:
  an unrelated sibling's merge would falsely invalidate every other
  in-flight unit's pin on every single merge, making the review cascade
  re-run needlessly on units untouched by the drift. Keying off the unit's
  own branch tip changing (a real rebase) is both necessary and sufficient.
- **A new fencing-token mutator** for the demotions above — rejected: `cmd_mark`
  already exists as the audited general-purpose escape hatch for exactly
  these non-happy-path per-unit transitions; a new mutator would duplicate
  its fencing/audit logic for no behavioral gain.

## Test strategy

New file `shared/tests/test_campaign_drain.py` (sweep / drain_once /
remaining_active / run_drain, including the exact STRICT-STOP scenario from
the sub-iterate spec's own test strategy) and
`shared/tests/test_check_review_attribution_invalidate.py` (the spec's
required negative/positive staleness-cascade pair, using real git via the
`git_origin_repo` fixture — one unrelated-sibling-merge negative test, one
actual-rebase positive test). Doc-level mutation-style prose guards added in
`shared/tests/test_campaign_r5b_merge_lane_prose.py` (18 tests) covering the
AC bullets that are best proved against the doc's literal text.
`cmd_mark_merged` and the 9-state edge table were already built by R4 and are
reused as-is (no new tests needed there — R4's own suite already covers
them thoroughly).
