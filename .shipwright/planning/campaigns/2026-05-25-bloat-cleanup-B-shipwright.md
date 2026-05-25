# Campaign — Bloat Cleanup Track B (Shipwright Cleanup) — Kickoff 2026-05-25

> Cleanup of the God-Module + SKILL.md inventory in the Shipwright
> monorepo. Supersedes the May-21 draft
> `2026-05-21-bloat-cleanup-B-shipwright.md` (read-only history;
> kickoff was deferred until Campaign A merged on 2026-05-25).
>
> **Source plan:** `Spec/Launch preparation bloat cleanup.md`
> (§6.1 B-rows, §7.1 topology, §7.4 workflow, §9 acceptance).
>
> **Precondition:** Campaign A merged
> (PRs #85, #86, #88 on 2026-05-25). Pre-commit hook + CI bloat-check
> active; phase-0 baseline frozen at 163 entries in
> `shipwright_bloat_baseline.json`.

## Status

- **Started:** 2026-05-25
- **Branch strategy:** stacked
- **Merge policy:** auto-merge each sub-iterate's PR after CI-green
  (pre-commit + bloat-check + tests). Every sub-iterate must be
  **empirically verified** before merge (F0.5 surface verification
  with real round-trip probes — spec-only authorship counts as no
  test).
- **Baseline at start:** 163 grandfathered entries.
- **Acceptance:** zero `state=grandfathered` entries for shipwright
  code remain (only `state=exception` + `state=deferred-plan` are
  permitted).

## Dependency Topology (serial-stacked)

The autonomous loop runs units in this exact order. Stacked
branching means each unit's branch is created from the **previous
unit's branch** — so each merge to `main` un-stacks the next PR's
base. The first-merged PR drops its base to `main`; the second's base
becomes `main` automatically once the first lands.

| Order | ID | Target | LOC | Depends on | Branch |
|---:|---|---|---:|---|---|
| 1 | `B1.iterate` | `plugins/shipwright-iterate/skills/iterate/SKILL.md` | 1709 | — | `iterate/bloat-B-skill-iterate-split` |
| 2 | `B1.build` | `plugins/shipwright-build/skills/build/SKILL.md` | 1162 | B1.iterate | `iterate/bloat-B-skill-build-split` |
| 3 | `B1.test` | `plugins/shipwright-test/skills/test/SKILL.md` | 986 | B1.build | `iterate/bloat-B-skill-test-split` |
| 4 | `B1.adopt` | `plugins/shipwright-adopt/skills/adopt/SKILL.md` | 848 | B1.test | `iterate/bloat-B-skill-adopt-split` |
| 5 | `B1.design` | `plugins/shipwright-design/skills/design/SKILL.md` | 695 | B1.adopt | `iterate/bloat-B-skill-design-split` |
| 6 | `B1.project` | `plugins/shipwright-project/skills/project/SKILL.md` | 612 | B1.design | `iterate/bloat-B-skill-project-split` |
| 7 | `B1.plan` | `plugins/shipwright-plan/skills/plan/SKILL.md` | 581 | B1.project | `iterate/bloat-B-skill-plan-split` |
| 8 | `B8` | `shared/contracts/{compliance,iterate}.py` (NEW) + adopt-bridge + test-boundary adapters | new | B1.plan | `iterate/bloat-B-contracts` |
| 9 | `B2` | `plugins/shipwright-compliance/scripts/lib/data_collector.py` | 1559 | B8 | `iterate/bloat-B-data-collector-split` |
| 10 | `B6` | `shared/scripts/github_triage.py` | 929 | B2 | `iterate/bloat-B-github-triage-split` |
| 11 | `B3` | `shared/scripts/lib/phase_quality.py` (+ bloat dashboard column) | 1108 | B6 | `iterate/bloat-B-phase-quality-split` |
| 12 | `B4` | `shared/scripts/dev_server.py` | 997 | B3 | `iterate/bloat-B-dev-server-split` |
| 13 | `B5` | `plugins/shipwright-run/scripts/lib/orchestrator.py` | 983 | B4 | `iterate/bloat-B-orchestrator-split` |

> **B1 mini-slices ordering matters.** Each slice splits a SKILL.md
> that other slices may cross-reference. They are kept serial so each
> `/shipwright-<X>` probe (per-slice acceptance criterion 4) runs
> against the post-split state of all prior slices.
>
> **The user's brief mentions parallel pairs `(B2 ∥ B6)` and
> `(B4 ∥ B5)`.** The autonomous-loop machinery and sub-iterate-runner
> contract do not support parallel branches within one campaign
> (single-repo, no worktree per sub-iterate). The campaign therefore
> runs serial-stacked. Equivalence holds: each pair touches disjoint
> file scopes, so serial execution produces the same final state with
> no merge conflicts.

## B7 — `shared/scripts/tools/` Consolidation — OUT OF SCOPE

~60 files / ~16k LOC across `shared/scripts/tools/`. This is a real
migration with callsite refactoring, not a file-split. Stays in
`shipwright_bloat_baseline.json` with `state=deferred-plan` and a
`plan_ref` pointing at a follow-up spec to be written after Campaign B
closes. Track B's Phase-D acceptance explicitly permits
`state=deferred-plan` for this subtree.

---

## CLEANUP-INVARIANT (mandatory for every B sub-iterate)

The same commit that splits a file MUST also update
`shipwright_bloat_baseline.json` according to one of these three
rules:

- **(a) Path still exists post-split, now ≤ limit** (e.g. SKILL.md
  reduced to a thin Kern shell pointing at `references/F*.md`) →
  **REMOVE** the entry from the `entries` array.
- **(b) Path deleted by the split** (replaced by a package directory
  with `__init__.py` re-exports) → **REMOVE** the entry from the
  `entries` array.
- **(c) Path still exists AND is still > limit** (split was
  incomplete) → **FAIL** the iterate. Do NOT merge. Refactor further
  until rule (a) or (b) applies.

Additionally, for every NEW submodule produced by the split:

- Source files (`.py` / `.ts` / `.tsx`) MUST be ≤ **300 LOC**.
- Runtime prompts (`references/*.md` loaded by a SKILL.md) MUST be
  ≤ **400 LOC**.
- If a new file would exceed its limit at commit time → split it
  further BEFORE committing. **Never add a fresh grandfathered entry
  to the baseline** — that defeats the campaign.

**Why this matters:** without the same-commit baseline update,

- Group H6 (Stale-Entry) and H2 (Ratchet-Suggestion) fire post-merge
  on every subsequent `/shipwright-compliance` run — cosmetic but
  increasingly noisy across 13 slices.
- New oversize `references/F*.md` trigger the PostToolUse marker +
  Stop-gate "new crossing" block on the **next** sub-iterate. That's
  the deliberate cross-slice anti-ratchet effect: the next slice
  cannot finalize until the previous slice's leftover crossings are
  resolved.
- Pre-commit hook is fine in isolation (measured < current = no
  block), but the Phase-D acceptance criterion only holds if every
  slice removes its entry.

---

## PER-ITERATE WORKFLOW (autonomous, no human gates)

For each sub-iterate the runner executes:

1. Read the sub-iterate spec (one row of the dependency table).
2. **RED** — write failing tests for the new submodule surface:
   importable, callable, behaves identically to the pre-split callsite.
3. **GREEN** — implement the split.
   - For SKILL.md slices: extract F0/F1/F2/…/F12 (or thematic
     sections if no F-phases exist) into `references/F*.md`; leave
     the Kern SKILL.md as section headers + `see references/Fx.md`
     pointers (~250 LOC target).
   - For `.py` splits: package directory with
     `from .x import y` in `__init__.py` to preserve the import
     surface. The original `path/to/foo.py` becomes a re-export shim
     OR is replaced by `path/to/foo/__init__.py` (rule (b)).
4. **Update `shipwright_bloat_baseline.json` IN THE SAME COMMIT** per
   cleanup-invariant rule (a/b/c).
5. **F0.5 surface verification** — CLI runner over the new
   submodule's tests **AND** an integration probe that consumes the
   original public API. Empirical, not spec-only.
6. **B1-only — `/shipwright-<X>` parity probe.** For B1 slices,
   invoke the corresponding skill (`/shipwright-iterate`,
   `/shipwright-build`, etc.) against a known fixture flow. Behaviour
   MUST be identical pre/post-split. If drift detected →
   **ROLLBACK** that B1 mini-slice, do not merge, reconsider the cut.
7. **External LLM Review** (medium-iterate auto-mode, ADR-029).
8. **Code Review Cascade** (medium-iterate auto-mode, ADR-029).
9. F1–F11 finalization (drift, ADR drop, changelog drop, test
   results, iterate entry, commit, push, PR open).
10. **CI gate** — pre-commit + CI bloat-check workflow MUST report
    `✅ no anti-ratchet violation` on the PR. If red → fix +
    re-push BEFORE merging.
11. **Auto-merge** (orchestrator polls `gh pr checks` → `gh pr merge
    --squash --delete-branch`) once CI is green AND no pending
    review threads remain unresolved.
12. Loop continues with the next sub-iterate.

---

## HARD CONSTRAINTS

- **B7 OUT** — stays `state=deferred-plan`, separate plan written
  after this campaign closes.
- **Test files >300 LOC grandfathered in Phase-0** (e.g.
  `integration-tests/test_core_trilogy_flow.py` 468,
  `test_multi_session_pipeline.py` 432, etc.) are NOT touched by
  Campaign B. They retain their grandfathered entry and remain
  fixable in a later test-hygiene campaign.
- **B1 mini-slices serial only.** No two SKILL.md splits in parallel
  — each needs its own probe iterate, and the SKILL.md ordering
  matters for cross-references.
- **B2 / B6 parallelism is dropped** for runner-machinery reasons
  (see topology note above). Both share no file paths but both
  consume `shared/contracts/*` once B8 lands. Serial execution
  preserves correctness.
- **B3 MUST land before B4 / B5** — their tests consume
  `phase_quality.*` imports.
- **Constitution-edit is OUT** — A.defense already extended §21.
  Do NOT re-edit `shared/constitution.md`.

---

## PHASE-D ACCEPTANCE (post-merge of all 13 sub-iterates)

1. `shipwright_bloat_baseline.json` — **zero `state=grandfathered`
   entries for Shipwright code.** Only `state=exception` (with ADR
   reference) and `state=deferred-plan` (B7 subtree) remain.
2. **Re-run A.foundation Stop-gate probe** — verify the Stop-gate
   still cooperates with the now-smaller baseline.
3. **Re-run A.review Group H detective audit** — verify ratchet /
   stale-entry / anti-ratchet groups H2 / H6 fire on clean signal.
4. **Re-run A.defense pre-commit probe** — verify the local
   pre-commit hook still blocks ratchets.
5. **Update this file:** `Status` block → `complete`, link to all
   merged PRs in dependency order.

---

## Notes (cross-iterate observations)

_Filled in as the campaign progresses. Each sub-iterate may append
one bullet here when it learns something that the NEXT sub-iterate
needs to know (e.g. "B1.iterate found that extracting F-phases into
references/ requires …, follow the same pattern in B1.build")._
