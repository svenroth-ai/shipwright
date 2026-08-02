# Mini-Plan — `spec` into `REVIEW_TYPES`

Spec: `2026-07-31-review-record-spec-promotion.md`

## Chosen approach — promote, and make the read path tolerant in one place

The write path collapses to a single destination (`reviews`); the read path
learns one fallback (`gates`), in **one** helper that every caller already goes
through. Nothing else moves.

| # | Step | File |
|---|---|---|
| 1 | `REVIEW_TYPES` gains `spec`; `GATE_TYPES` → `LEGACY_GATE_TYPES` (read-only); `RECORDABLE_TYPES` collapses to `REVIEW_TYPES` | `lib/review_record_schema.py` |
| 2 | `validate_record`: a `REVIEW_TYPES` member that is also a `LEGACY_GATE_TYPES` member may be absent from `reviews`; validate only entries actually present; keep `_validate_gates` for the legacy sibling | `lib/review_record_schema.py` |
| 3 | `_section` → `_read_sections` (precedence: `reviews`, then `gates`); writes always target `reviews`. `entry_for` is its only caller; `pending_types` and `upsert_review` route through `entry_for` | `lib/review_record_core.py` |
| 4 | `new_record` emits six pending `reviews` and **no** `gates` key | `lib/review_record_core.py` |
| 5 | Replace the `"gates" not in record` guard with "spec absent from both sections" | `tools/verifiers/review_record_floor.py` |
| 6 | Tests, both directions + the real 65-record corpus | `shared/tests/` |
| 7 | Correct the now-false prose | `SKILL.md`, `iteration-reviews.md`, docstrings |

**Ordering:** step 5 before step 3 in the TDD loop — the regression test for the
silently-dying rule must go red against today's code, or it proves nothing.

## Alternative considered — dual-write `spec` to both sections

Write `spec` into `reviews` **and** keep mirroring it under `gates` for a
transition period, so old readers keep working.

**Rejected, and not on taste — it does not work.** The old webui reader rejects
a record when `reviews` carries any key outside its pinned five. The rejection
is triggered by the *presence of the stranger in `reviews`*, not by the absence
of anything in `gates`. Mirroring therefore buys exactly zero compatibility
while creating two live shapes of the same fact — the classic dual-write drift
where the two copies can disagree and nothing says which is authoritative.

The genuine transition mechanism is the **read** fallback (chosen approach) plus
gating the merge on the redeploy (AC10). Compatibility that is only needed in
one direction should not be paid for in both.

## Risk / rollback

- Blast radius is 4 source files + tests; no data migration — old records are
  read as-is and never rewritten (they are immutable by design).

### The supported undo is FIX-FORWARD, not revert

An earlier draft of this section said *"Rollback = revert the commit"* and called
the exposure *"bounded"*. The Stage-3 review took both apart, correctly:

**Revert does not work, and both branches of it are bad.** `shared/scripts/` does
not auto-sync to the plugin cache (that is why AC10 needs
`update-marketplace.sh` on the way *in*), and nothing named the way *out*:

- **Revert without re-syncing the cache** — the runtime keeps writing
  `reviews.spec` while main's `validate_record` rejects it. Repo and runtime
  disagree about the format of a git-tracked artifact, and nothing on main
  notices, because the only corpus check is itself deleted by the revert.
- **Revert *and* re-sync** — every record written in the window becomes
  permanently unreadable: `read_record` raises and `check_review_record` offers
  the two exits this artifact exists to forbid, "repair or delete". That is
  reached on any *re-run* of F11 for the same run, which is the normal loop.

Reverting also **deletes** this run's own `reviews.json` — a file
`_committed_check` exists specifically to guarantee cannot vanish.

**So: no revert.** If the promotion has to be undone after merge, do it forward —
a new commit that restores the old vocabulary *and keeps the read path*, so
records already written stay readable. Whoever does it must also run
`bash scripts/update-marketplace.sh` and verify with
`check_plugin_cache_sync.py --strict`, in that order.

**And the exposure is not "bounded".** Not arming auto-merge bounds when the
merge happens; it bounds nothing about how many records the new producer writes
afterwards. The real bound is *every iterate run between the cache sync and any
undo* — there is no counter, no ceiling and no detector. Stated as a residual
rather than dressed up as a mitigation.

- `SCHEMA_VERSION` staying `1` (AC2) at least adds no *version*-based rejection
  on top of the vocabulary one.
