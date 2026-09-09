---
run_id: iterate-2026-09-09-pr-review-nonconverging-halt
---

# Mini-Plan: PR-review non-converging halt (F11 exit 8)

## Files to create/modify

- `shared/scripts/lib/pr_delivery.py` — edit: add `EXIT_NON_CONVERGING = 8`.
- `shared/scripts/lib/pr_review_convergence.py` — new: pure sameness predicate
  (extraction, normalization, overlap, `non_converging` entrypoint).
- `shared/scripts/lib/deliver_pr_non_converging.py` — new: host-touching glue
  (`escalate_if_non_converging`, `describe_non_converging`).
- `shared/scripts/tools/deliver_pr.py` — edit: wire the escalation into
  `deliver()`/`_body()`, add the `summary()` branch.
- `plugins/shipwright-iterate/skills/iterate/references/F11.md` — edit: exit-8
  arm in the `case "$?"` block.
- `docs/hooks-and-pipeline.md` — edit: one documentation paragraph.
- `shipwright_bloat_baseline.json` — edit: bump `deliver_pr.py`'s `current`
  under its existing exception entry.
- `shared/tests/_pr690_review_fixtures.py` — new: real PR #690 comment bytes.
- `shared/tests/test_pr_review_convergence.py` — new: 15 tests.
- `shared/tests/test_deliver_pr.py` — edit: 4 new end-to-end tests.
- `shared/tests/test_deliver_pr_summary.py` — edit: 1 new test.

## Work breakdown

1. Read `F11.md`'s `case "$?"` block and `deliver_pr.py`'s full ladder to find
   the one seam that owns every delivery outcome — confirm exit 8 is the whole
   integration, per the brief. (done — no second escalation channel invented)
2. Read `pr_review_render.py`/the system prompt to pin the exact comment shape
   (`### 🚫 Blocking issues`, `file:line — claim` bullets) the matcher parses.
   (done)
3. Fetch PR #690's real round-1/round-2 comments via `gh`, measure the
   claim-overlap the matcher would compute BEFORE fixing thresholds. (done —
   9 shared tokens, 0.32 overlap coefficient)
4. Write `pr_review_convergence.py` (pure, host-free) with thresholds set
   below the measured real-fixture value, with margin. Test: extraction,
   normalization, overlap arithmetic, both acceptance fixtures (recur / do
   not recur). (done — 15 tests)
5. Write `deliver_pr_non_converging.py` (host-touching glue) and wire it into
   `deliver_pr.py`. Test: end-to-end through the fake-host ladder (no-history,
   wrong-check-name, the acceptance escalation, fail-open on an unreadable
   comments payload). (done — 4 tests)
6. Add the F11 exit-8 arm and the `docs/hooks-and-pipeline.md` paragraph.
   (done)
7. Re-run the full delivery-ladder suite (179 tests) — 0 regressions. Run
   `ruff` and the anti-ratchet gate against the staged diff — both clean
   after bumping the `deliver_pr.py` baseline entry to the measured LOC.
   (done)

## Data model changes

None.

## Test strategy

Unit tests for the pure predicate (no `gh`, no host) plus end-to-end tests
through the existing fake-host ladder harness (`_pr_delivery_fakes.py`) —
matches this codebase's own established split for `lib.pr_delivery` /
`lib.pr_self_merge`. No E2E/browser layer: this is a backend CLI tool with no
UI surface (`Verification: surface none` in the iterate spec).

## Alternative approach (rejected)

**A push counter ("stop after N pushes").** Volume is the wrong axis: it
halts a run that is genuinely converging through a list of distinct real
findings (the good, common case) and, on PR #690 specifically, would have
fired three rounds later than the sameness predicate does. Rejected per the
brief's own reasoning, restated in the iterate spec's "Why not a push count".
