# Mini-Plan — REQ-3 Phase 2, content round (monorepo)

Run ID: `iterate-2026-07-23-req3-phase2-content-mono`

## Chosen approach — scan everything first, then walk requirement by requirement

**Step 1 — Completeness scan (facts, no questions).** For all 16 requirements:
read the skill definition that implements each capability plus the references
and scripts carrying its guarantees. Record per requirement: what it actually
does, what it guarantees when things go wrong, where its boundaries are, what it
deliberately does not do. Scan notes are working material (scratchpad), not repo
artifacts.

**Step 2 — Draft.** Turn each scan into assertion-shaped criteria under
`shared/fr-authoring.md` rules. For the 9 that already have criteria, diff the
scan against what is written and produce a short divergence list instead of a
rewrite.

**Step 3 — Walk, in catalog order.** Per requirement: play back the drafted
criteria and the coverage-checklist state; ask only the genuine decisions, one
question at a time with a recommended answer. Write the confirmed criteria into
`spec.md` as we go, so progress survives a context reset.

**Step 4 — By-product list.** Per criterion, search the suite for a test that
actually proves it; record the ones with none.

**Step 5 — Finalization.** F0 … F11 as normal.

## Why this order rather than strict serial (the alternative considered)

The alternative is a fully serial walk: scan one requirement, grill it, write it,
move on. It matches the campaign's "requirement für requirement" wording most
literally and surfaces a mis-shaped method after requirement #1 instead of #16.

**Rejected as the primary shape, with one element kept.** Scanning all 16 first
is what makes the *cross-requirement* judgements possible — whether a guarantee
belongs to `/shipwright-build` or `/shipwright-test`, whether `/shipwright-grade`
is a fold into compliance or its own capability. Those decisions are invisible
when you look at one requirement at a time, and they are exactly the ones that
are expensive to get wrong (requirement IDs are permanent). What the alternative
gets right is kept: the *walk* in Step 3 is serial and in catalog order, so the
method is under evaluation from the first requirement, not the last.

## Honest limitation of the by-product list — stated up front

The list cannot be derived mechanically today, and it would be a false green to
present it as if it were:

- Test tags exist at **requirement** level, not criterion level — criterion-level
  identity is Phase 3 (P3.1/P3.2). There is nothing to join on.
- Only **5 of 16** requirements carry any test tag at all (`.02 .03 .09 .10 .13`);
  32 of 730 test files are tagged.

So each entry is produced by **searching the suite for a test that proves the
criterion**. A "no test found" verdict therefore means *no test was found by a
targeted search*, not *no test exists*. The list is a **candidate work-list for
the backfill track, not a proven-complete inventory** — which is what that track
needs to start, since writing the test is real authoring work either way. Entries
carry a confidence marker so the backfill run re-checks before writing.

## Deliverables

| Artifact | Change |
|---|---|
| `.shipwright/planning/01-adopted/spec.md` | 7 requirements gain criteria; corrections where the scan found divergence; possibly one new row |
| `.shipwright/planning/campaigns/2026-07-23-req3-acs-without-tests-mono.md` | the by-product list |
| `shared/requirement-elicitation.md` | only if the round proves the method mis-shaped (campaign D13) |
| iterate spec (this run) | reflection: how the method held up |

## Post-merge step (do NOT run mid-flight)

This round edits `shared/glossary.md` (the `split` / `section` entries), which is
plugin-side. After the PR **merges** and local `main` equals `origin/main`:

```bash
bash scripts/update-marketplace.sh
uv run scripts/check_plugin_cache_sync.py --strict
```

Not before. `~/.claude/plugins/cache/shipwright/` is one global directory the
WebUI also runs from, so syncing an unmerged branch into it changes live runtime
state for unrelated work.

## Guardrails

- `Layers` cells stay `(inferred)`. The bare form is binding and hard-fails
  without criterion-bound tests; promotion is Phase 3.
- Requirement IDs are permanent — a new row takes the next free number counting
  retired ones, and is never renumbered later.
- No style rewrites of criteria that are already correct (merge-conflict cost on
  the one file every parallel iterate touches).
- No test is written in this round, and no criterion is invented to match a test
  that happens to exist — that inverts the campaign's D2 (bind, never generate).
