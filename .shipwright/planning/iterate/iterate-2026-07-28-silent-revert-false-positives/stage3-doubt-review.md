# Stage 3 — adversarial doubt-reviewer (`shipwright-build:doubt-reviewer`, Opus)

Briefed per the handover to attack **case (B)** — the edited-line filter —
hardest, with its author's warning attached: *"this is a design question, not a
one-liner; do not build the first idea."*

**SHIPWRIGHT_VERDICT: revise** — 8 doubts, 4 high. It **disproved the design**:
all four of its constructions returned "nothing was dropped" against a version
that had already passed Stage 1 and Stage 2. Each was reproduced before being
fixed, and each is now a permanent test in `test_silent_revert_not_weakened.py`.

## The four disproofs

| # | The real revert that went green | Fix |
|---|---|---|
| **D1** | The check's OWN motivating test (`test_the_463_shape_is_caught`) with the branch line reworded to mention what it discards. The branch wrote that line *before* seeing theirs, so it cannot be the replacement — the hunk pairing could not tell, and cleared a `-s ours` resolution that throws away documented behaviour while naming it. | Exclude the branch's own pre-merge side (`p1`) from the set of possible replacements. |
| **D2** | The same hole at scale: with `-U0`, two adjacent deletions and one addition share a hunk, so one long pre-existing line clears **both** bullets the default branch added. | Same fix. |
| **D3** | A whitespace-only reindent makes git call every line changed and emit ONE hunk spanning the file, inside which any addition vouches for any deletion 28 lines away — exactly the unbounded matching AC4 exists to forbid. | Diff with `-w`, so hunks and findings agree on what "the same line" means. |
| **D4** | The default branch fixes a typo in a line this branch really had reverted; the exact string vanishes from the tip and the finding with it. Composition hazard: the ref repair makes the tip *fresher*, so this fires *more* often — the two fixes worked against each other. | Replace the line-level tip test with whole-file agreement (`matches_default`) plus "superseded **and** followed" (`superseded_on_default`). |

D4 is the one that reshaped the design: a line-level absence test cannot tell
"they superseded it" from "they merely touched it", so case (A) is no longer
asked that way at all.

## The two accepted, plus one fixed

- **medium — a SKIP swallowed findings.** A SKIP is `ok=True` and blocks nothing,
  so returning one the moment *any* path was unreadable converted a real block
  over every other path into a pass naming none of them. **Fixed**: findings are
  reported and the incomplete comparison is noted alongside them.
- **medium — the blind-spot pin was narrower than the implementation.** Accepted
  and widened in prose: what is accepted is bounded on three sides (same hunk,
  not the base, not the branch's pre-merge side), so it is an edit this branch
  made to a line it had just received.
- **low — `CHURN_ALLOWLIST` vs `churn_merge.classify`.** The verifier tests
  membership only; the resolver also treats campaign `status.json` as churn.
  Pre-existing (from #477), unchanged here, filed rather than fixed.

## Clean bills it gave (useful negative information)

- The union over merges is sound — a line reported under any merge is reported.
- `resolve_default_ref` cannot cause **fewer** merges to be examined: the upgrade
  condition requires `main ⊆ origin/main`, so the ancestor test can only start
  passing.
- #463 itself still trips: a stale-copy overwrite is mostly pure-deletion hunks
  with no `+` to vouch.
- Diff-parser edges (`---`/`+++`/`\ No newline`, binary, bad ref, textconv) all
  yield the value that suppresses nothing.
- Submodules and symlinks produce no suppression.
