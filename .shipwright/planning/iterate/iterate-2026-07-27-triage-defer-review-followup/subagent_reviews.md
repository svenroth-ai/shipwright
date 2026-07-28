# Subagent review record — iterate-2026-07-27-triage-defer-review-followup

Both passes ran on this run's real diff, in the worktree, model `opus`. They
were requested by the operator after the predecessor run (PR #444) had already
merged with these two rows closed `not_run`.

## Stage-2 `code-reviewer` — 13 findings, all addressed

Verdict per AC: AC-1/4/5/6/7 held; AC-2 held mechanically but the mechanism was
forgeable; AC-3 held for the three fields it named. **AC-8/AC-9/AC-10 were the
weak ones — four live copies of the three retracted claims were left standing.**

| Sev | Finding | Disposition |
|---|---|---|
| high | `test_triage_defer.py` docstring still asserted the retracted "byte-for-byte" pin — inside the test a reader would take as its proof | fixed |
| med | `defer()`'s docstring still said "neither surface can un-defer", plus a cross-repo parity claim two lines under a paragraph forbidding them | fixed |
| med | `conventions.md` + `decision_log.md` (ADR-057) still carry "thin wrapper over the same lib" — always-loaded agent context outranks shipped docs at read time, and the retraction's own closing sentence says to grep every surface | fixed: retraction appended (forward-only) AND both carriers annotated in place |
| med | the `[deferred]` marker was an unanchored substring on a row that also prints `source` / `dedupKey`, both attacker-influenceable → an open item could be classified parked | fixed: token at a fixed position on BOTH row types, tests classify by prefix, forgery test added |
| med | `FIELD_MAX_LEN` cited `aggregate_triage._TRUNCATE_LEN`, which does not exist (it is `FIELD_TRUNCATE_AT`), and `_clip` omitted the sibling's `rstrip` | fixed both |
| med | module docstring contradicted the constant 20 lines below it | fixed |
| med | AC-9's strengthening was itself overclaimed — one English phrase in an arbitrary 200-character window | fixed: line-scoped, wider denylist, and the docstring downgraded to what a denylist can actually prove |
| med | reducibility: the +9 docstring lines that forced a baseline entry were a fourth copy of one sentence | fixed (pointer, canonical home in the glossary); the trim was then partly reverted — see Stage-3 |
| low | `id` / `severity` / `kind` uncapped while the docstring said "capped" | fixed by qualifying the claim and capping the one-line free-text fields of both blocks |
| low | a zero-width space survives `.split()` → blank `reason:` at a second character | fixed (the first fix was wrong — see Stage-3) |
| low | `_x_runs`, a 12-line single-use helper, for a property two literals express | fixed |
| low | the third false claim in the prior run's self-review was left un-annotated | fixed |
| low | the corrections traded unverifiable cross-repo claims for different ones | fixed: the webui module, route and verification date now appear in the shipped text |

Two things it checked and explicitly did **not** file: the `_DECIDABLE.get`
default (a documented trade-off, not dead code) and the
`_clip` / `_truncate` / `_cap_detail` triplication (`lib/` cannot import
`tools/`; deferred in the spec).

## Stage-3 `doubt-reviewer` — 9 doubts, 2 high, all addressed

| Sev | Doubt | Disposition |
|---|---|---|
| high | the retraction enumerates four carriers and fixes two — `conventions.md:200` and ADR-057 still assert it | fixed. The doubt pass proved this was *still* true after the Stage-2 fix attempt |
| high | **the honesty pass shipped a NEW false claim**: "nothing caps a reason written by the Command Center, which stores it unvalidated" is disproved by the very function cited as its evidence — `parseDismissSnoozeBody` caps at the identical 500 and strips the identical control-char class, and normalises whitespace-only to `null`, so the blank-but-present case is *not* reachable from that surface | fixed: verified directly in the webui source, then all three sentences corrected. The cap's real job is a hand-edited file or a direct `mark_status` caller |
| med | "a formatting-only change would pass every test in both repositories" is still too generous — no CI job in either repo re-runs the CLI, so a renamed field is equally silent | fixed |
| med | dropping Unicode category `Cf` neither closes the class (U+FE0F is `Mn`) nor costs nothing (U+200D splits ZWJ emoji, U+200C changes Persian / Devanagari rendering) | fixed: reverted, replaced by a Unicode-property predicate; its residual limit (Hangul filler, braille blank — letters and symbols that merely render blank) is documented rather than hidden |
| med | the cap landed on the block with the *least* exposure and was withheld from the open block, whose `title` the sibling renderer does cap | fixed: both blocks' one-line fields clipped, the payload fence stays exempt |
| med | trimming to 299 to dodge a baseline entry removed load-bearing detail and inverts the repo's own convention | fixed: all three items restored, file registered at 304 |
| low | the negation denylist is a spot-check, and `len(lines) == 1` is brittle where the guide already carries two placeholder styles | fixed |
| low | the F0.5 runner omitted the two files carrying AC-7 and AC-9; AC-6 had no test; one test docstring was stale | all three fixed |
| low | the row shape is user-visible and had no changelog drop | fixed (Changed + Fixed drops) |

Areas it attacked and found **sound**, stated as such rather than padded: the
row token cannot be forged or broken by any stored value (it walked the whole
newline surface, including U+2028 / U+2029 and the payload path); `_clip` has no
off-by-one and its parity with `aggregate_triage._truncate` is exact; the
`NO_REASON` reordering and the `dedupKey` fix are correct; AC-5's rewrite
genuinely kills the mutant; two of the three retracted-claim replacements verify
true at the cited coordinates; lint and imports are clean; and the two
out-of-scope carve-outs are the right two.

## The pattern worth keeping

Both passes found their most serious item in the *corrections*, not in the
feature: an honesty pass is exactly as prone to overclaiming as the work it
corrects, and one of its new claims was refuted by the same twenty lines of
TypeScript it cited as proof. The cheap guard is mechanical — assert the absence
of retracted literals with a retraction-marker allowance, the way
`integration-tests/_fr_history_docs.py` already does for other claims. Carried
as a follow-up rather than built here.
