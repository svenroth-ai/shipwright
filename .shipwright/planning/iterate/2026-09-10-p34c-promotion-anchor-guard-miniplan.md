# Mini-Plan: Anchor Layers-Promotion to the Newest Verified Ancestor (P3.4c)

- **run_id:** iterate-2026-09-10-p34c-promotion-anchor-guard

## Approach

Build B from the iterate spec's "Options weighed" section: when
`promote_required_layers.py` finds HEAD itself unverified
(`resolve_execution_evidence(sha, ...).status == "unavailable"`), walk
first-parent ancestors of HEAD (bounded by commit count and age) through the
UNMODIFIED `resolve_ci_verification` predicate to find the newest verified
commit, then promote a requirement using THAT commit's CI-confirmed evidence
— but only per-requirement, and only if nothing that could invalidate that
requirement's own evidence (its bound test files as recorded in the
manifest AT the anchor, or its spec.md — both the anchor's and HEAD's) changed
between the anchor and HEAD.

## Work breakdown

1. `shared/scripts/ci_verified_anchor.py` — bounded first-parent ancestor
   walk (`resolve_verified_anchor`), reusing `resolve_ci_verification`
   unmodified. Outcomes: `found` / `unavailable` / `error`.
2. `shared/scripts/lib/manifest_at_commit.py` — shared `git show <sha>:<path>`
   read primitive (TOCTOU-free), used for both HEAD and the anchor commit;
   `promote_required_layers._read_committed_manifest` refactored to delegate
   to it.
3. `shared/scripts/lib/promotion_evidence_staleness.py` — the per-FR
   staleness guard: one `git diff --name-only --no-renames` call per run
   (never per FR), then a pure set-intersection per requirement against the
   requirement's own bound test files (from the anchor's manifest) plus both
   the anchor's and HEAD's `spec_path`.
4. `shared/scripts/lib/layer_promotion_ledger.py` +
   `shared/scripts/lib/layer_promotion_apply.py` — additive `anchor_commit`
   field alongside the existing `ci_run_id`, no schema-version bump.
5. `shared/scripts/tools/promote_required_layers.py` — wire the fallback:
   only triggers on `evidence.status == "unavailable"` from the ORIGINAL,
   unchanged tip-evidence call; `lib.layer_promotion.evaluate_fr` stays pure
   (staleness is an override applied to its `promote` decision, never
   threaded into the evaluator itself).

## Test strategy

Unit tests per new module (`test_ci_verified_anchor.py`,
`test_manifest_at_commit.py`, `test_promotion_evidence_staleness.py`) plus
integration tests in the existing `test_promote_required_layers.py` proving
the four acceptance criteria (untouched evidence promotes; a changed bound
test file skips with `evidence_stale_since_anchor`; no verified ancestor
within the bound reports `unavailable` not an error; the existing
tip-is-verified path is unaffected). No E2E — this is backend compliance
tooling with no UI surface (`surface: none`). This diff IS
`touches_io_boundary` (JSON manifest/ledger read-write, plus a new git
subprocess boundary) and carries the mandatory Boundary Probe the iterate
spec's own Confidence Calibration section documents in full: a real-repo
round trip for `anchor_commit` through the ledger, a real rename-vs-diff
probe against actual git behavior (not a hand-simulated file list), and a
manual probe of `git log --since`'s day-count overflow behavior.

## Alternative approach (medium — considered and rejected)

Option A ("Ritual": refresh/merge/promote with merges paused) was rejected —
see the iterate spec's "Options weighed" section. It is an interim
workaround, not a fix: it costs two manual steps every time a promotion is
wanted, and the refresh PR itself needs an admin override (100% generated
paths, `trg-a99ee30d`). Option C (closing the drift loop automatically) was
refused outright — it needs a robot with default-branch write access, which
has been decided against three separate times already.
