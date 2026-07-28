# Mini-Plan — iterate-2026-07-28-silent-revert-false-positives

Spec: `iterate-2026-07-28-silent-revert-false-positives.md`.

**Scope of the change (all four are release criteria, not follow-up):**

| Part | File |
|---|---|
| Runtime behaviour | `verifiers/silent_revert.py` (the detector) + `…_filters.py` (the three proofs) + `…_reading.py` (git/text primitives). **Split forced by the repo's own 300-line source cap**, not by design; final sizes 299 / 174 / 201. `check_silent_revert_for_run` remains the sole F11 entry point, signature unchanged. |
| Coverage | `test_silent_revert.py` — 16 existing tests stay green and **untouched** (the true-positive contract). New cases split by intent: `…_false_positives.py` (what must stop being reported), `…_not_weakened.py` (what must still be reported — the Stage-3 disproofs), `…_filters.py` (the predicates and the fail-honest paths). |
| Contract | `docs/hooks-and-pipeline.md` §301-309 — describes the check |
| Requirement | `.shipwright/planning/01-adopted/spec.md` — fold into FR-01.11's existing `(iterate-2026-07-27-no-silent-revert)` criterion. **Spec Impact: MODIFY** |

> **This plan was disproved during review and rebuilt.** What follows is the
> approach as planned; the delivered design differs in one substantial way. The
> case-(A) filter planned here asks "is this line still on the default branch's
> tip?" — Stage-3 review showed that cannot tell "they superseded it" from "they
> merely fixed a typo in a line we really reverted", and built the latter. It
> became whole-file agreement plus "superseded **and** followed". The spec's
> *What the review cascade changed* section carries the full record; this file is
> kept as the pre-review plan rather than rewritten, so the delta is visible.

## Chosen approach

Narrow `dropped_lines`' notion of "missing" with two filters that are decided by
evidence rather than by a threshold, and repair the ref they are anchored to.
Nothing about the check's framing (per integration merge, `gained = theirs - base`,
the `declared_removals` hatch, `CHURN_ALLOWLIST`, the fail-honest skips) changes.

1. **`_resolve_default_ref(root, name)`** — four explicit outcomes:
   `origin/<name>` does not resolve → `<name>`; `merge-base --is-ancestor <name>
   origin/<name>` returns 0 → `origin/<name>`; returns 1 (diverged or locally
   ahead) → `<name>`; any other rc (git failure) → `<name>`. Resolved **once** and
   used for both the merge scoping and the tip filter, so the two can never
   disagree about what "main" means.
2. **`_tokens_in_order(needle, hay)`** — pure, no git. Is `needle`'s whitespace
   token sequence a subsequence of `hay`'s? Empty needle → `False` (cannot occur,
   `_significant` drops blank lines first, but it is not left to rest on that).
3. **`_replacement_hunks(root, tip, head, path)`** — parses `git diff -U0` into
   `[(deleted:set, added:list)]`. With `-U0` a hunk is one contiguous changed
   region, so an added line in the same hunk *is* the line that replaced the
   deleted one.
4. In the per-file loop, only when `missing` is non-empty (cost paid on the
   failing path only), both lookups memoised per path for the call:
   - **Filter 1 / AC1+AC1b** — `tip = _file_lines(root, resolved, path)`. Absent
     (`None`) → the whole path is silenced. Present → drop each line not in it.
   - **Filter 2 / AC2** — skipped entirely when `ours is None` (AC4b: the branch
     deleted the file, so nothing can carry anything forward, and the subtraction
     would raise). Otherwise drop a line when the hunk deleting it also adds a
     line that passes `_tokens_in_order` **and** is not in that merge's
     `base_lines` (AC3).
5. Docstrings state both filters and *why* each is sound, in the register the
   module already uses. Rejected alternatives live in the spec, not the module.

## Alternative considered — fix (A) only, leave (B) to `declared_removals`

Half the diff, no new predicate, no risk of masking a real revert. Rejected: the
edited-line false positive fires on any in-place edit of a line main also touched
— a doc table row, a registry entry, a checklist item — which is routine on
exactly the long-lived branches this check exists for. Leaving it keeps the escape
hatch in weekly use, which is the failure mode the handover is about. The two
filters are independent, so a later doubt about (B) can be reverted without
touching (A).

## Risks

| Risk | Mitigation |
|---|---|
| Filter 2 masks a real revert of a short line | Hunk pairing: a coincidental match elsewhere in the file is in a different hunk and does not count (AC4). This replaced an earlier "any newly authored line" formulation that Gemini falsified. |
| Filter 2 masks a restored pre-merge line | Guard (b) `∉ base_lines` (AC3). Measured: it already rejects one match on the real branch. |
| Filter 1 hides a revert | Impossible by construction — if main's tip lacks the line, HEAD lacking it matches main, so the PR reverts nothing relative to main. |
| Ref change alters behaviour in test repos | No `origin` remote → falls through to the local ref (AC5), which is what every existing test uses. |
| Slower on large files | Both filters run only when `missing` is non-empty; both per-path git reads memoised. |
