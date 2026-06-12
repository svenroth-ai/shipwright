# Iterate Spec — merge=union for curated agent-docs (close the structural gap)

- **Run ID:** iterate-2026-06-12-union-curated-agent-docs
- **Intent:** CHANGE (extend the append-log union driver to two curated agent-docs)
- **Complexity:** medium (modifies a load-bearing merge abstraction + scaffolds into all managed repos)
- **Origin:** follow-up to iterate-2026-06-12-automerge-serial-integrate. That fix made
  `integrate_main`/`ensure_current` auto-resolve the *regenerated* churn snapshots, but
  `.shipwright/agent_docs/architecture.md` + `conventions.md` are **curated prose** (NOT churn,
  not regenerated) — parallel iterates each prepend a bullet to `## Architecture Updates` /
  `## Convention Updates` / `## Learnings`, so the lines collide and the resolver's hard gate
  escalates to a human. PRs #207/#208/#210/#211 each conflicted on exactly these two files.

## Problem

The append-section bullets in `architecture.md` + `conventions.md` are the last
piece of the parallel-iterate merge cascade my previous iterate did NOT solve.
They are curated markdown (excluded from `CHURN_ALLOWLIST`), so neither the
regenerate-at-merge resolver nor GitHub's server-side merge resolves the
two-bullets-at-the-same-anchor collision.

## Decision (approved)

Add `architecture.md` + `conventions.md` to the **`merge=union`** driver. For the
dominant pattern — two iterates each prepending a bullet at the top of an
`## Updates`/`## Learnings` section — union keeps BOTH bullets automatically, with
NO conflict markers, and **GitHub honors `merge=union` server-side**, so even pure
auto-merge resolves it. Reuses the exact mechanism already trusted for
`shipwright_events.jsonl` + `.shipwright/triage.jsonl`.

**Trade-off (accepted):** union is line-based and silent — if two iterates edited
the *same non-append line* of these docs differently, union would merge both
silently instead of conflicting. In practice ~all parallel edits are
append-section prepends; if silent garble ever bites, escalate to per-run
drop-files (Option B). A meta-test pins the append-section coverage.

## Spec Impact

MODIFY — changes the merge strategy of two existing curated artifacts. No FR delta.

## Affected Boundaries

- `shared/scripts/lib/gitattributes_union.py` — the rendered `.gitattributes`
  fragment (the producer/consumer boundary git reads). New `CURATED_DOC_UNION_PATHS`
  + `ALL_UNION_PATHS`; the fragment/merge now cover all four paths.
- `shared/templates/gitattributes-union.template` + monorepo root `.gitattributes`
  (the scaffolded artifact). New curated-doc block.
- Scaffolds into every managed repo (adopt Step E.13c + `self_heal_gitattributes`).

## Approach

1. `gitattributes_union.py`: keep `UNION_PATHS` = the two JSONL append-logs
   (drift-pinned to `churn_merge.{EVENTS_LOG,TRIAGE_LOG}`, the managed-repo signal —
   UNCHANGED). Add `CURATED_DOC_UNION_PATHS = (architecture.md, conventions.md)` and
   `ALL_UNION_PATHS = UNION_PATHS + CURATED_DOC_UNION_PATHS`. Point `missing_union_paths`
   (fragment + self-heal `added`) at `ALL_UNION_PATHS`; keep the managed-repo `ls-files`
   probe on `UNION_PATHS` (JSONL = the managed signal).
2. Template + root `.gitattributes`: add a second comment block + the two curated-doc
   union lines, documenting the prepend-bullet semantics + the garble caveat.
3. Tests: `test_template…` → `ALL_UNION_PATHS`; keep `UNION_PATHS == {EVENTS_LOG,TRIAGE_LOG}`
   green; new `CURATED_DOC_UNION_PATHS` pin; new real-git repro proving two concurrent
   `architecture.md` bullet-prepends union without markers (+ negative control).
4. `docs/hooks-and-pipeline.md`: document curated-doc union; conventions.md Learning.

## Acceptance Criteria

- [ ] Two concurrent `## Architecture Updates` bullet-prepends merge with NO conflict
      markers + no bullet loss (real-git repro) + negative control.
- [ ] `ALL_UNION_PATHS == UNION_PATHS + CURATED_DOC_UNION_PATHS`; template declares all four.
- [ ] `UNION_PATHS == {EVENTS_LOG, TRIAGE_LOG}` still holds (JSONL pin unchanged).
- [ ] Composes with iterate-2026-06-12-automerge-serial-integrate: `integrate_main`
      no longer BLOCKS on an architecture.md/conventions.md-only conflict.
- [ ] Full F0 suite green; no new bloat crossing.

## Confidence Calibration
- **Boundaries touched:** the rendered `.gitattributes` fragment (what git reads at
  merge) — `gitattributes_union.{CURATED_DOC_UNION_PATHS,ALL_UNION_PATHS}`, the
  template, the monorepo root `.gitattributes`, scaffolded into managed repos via
  `merge_into`/`self_heal_gitattributes`/the adopt scaffolder.
- **Empirical probes run:**
  - Real-git repro (parameterized over BOTH architecture.md AND conventions.md):
    two concurrent bullet-prepends merge with NO conflict markers, both bullets in
    order after the heading + before base, heading not duplicated — and a NEGATIVE
    control proving the SAME prepends conflict WITHOUT the union driver.
  - `CURATED_DOC_UNION_PATHS` / `ALL_UNION_PATHS` disjoint-union pin; `UNION_PATHS`
    still `== {EVENTS_LOG, TRIAGE_LOG}` (JSONL pin intact); template declares all 4.
  - Downstream consumers re-verified green: `merge_into`/`self_heal` over 4 paths,
    adopt scaffolder "already_present" now needs all 4. 31 union tests + 5 adopt + ruff.
- **Test Completeness Ledger:** table below — every behavior tested, 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the merge behavior is exercised through REAL `git merge`
    (the actual mechanism git applies), not a simulation — positive + negative
    control on both docs, so a path-wiring or anchor regression on either is caught.
  - *Coverage (breadth):* both curated docs + both directions (union resolves /
    default-conflicts) + the SSoT pins + the scaffold/self-heal/adopt consumers.
    Not separately executed: the silent-garble caveat (same-line non-append edit) —
    deliberately accepted (documented), not a tested behavior.
- **Bloat note:** adding the curated category pushed `gitattributes_union.py` to 319,
  so (per the bloat Iron-Law gate — an already-oversize file got larger) the git
  self-heal commit-path was SPLIT into `lib/gitattributes_selfheal.py`: now
  `gitattributes_union.py` = 141 (pure merge-logic SSoT, stdlib-only top-level) and
  `gitattributes_selfheal.py` = 191 — **both ≤300, no crossing**. The split mirrors
  the existing test split (`test_gitattributes_union.py` vs `…_selfheal.py`); callers
  (`setup_iterate_worktree`, the selfheal test) updated. `test_gitattributes_union.py`
  held at exactly 300.

### Test Completeness Ledger
| Behavior | Disposition | Evidence / reason_code |
|---|---|---|
| concurrent architecture.md bullet-prepends union without markers | tested | new real-git repro |
| negative control: same prepends conflict without union | tested | new repro |
| ALL_UNION_PATHS = UNION_PATHS + curated; template declares all 4 | tested | drift test |
| UNION_PATHS unchanged (JSONL pin) | tested | existing test_union_paths_match_churn_allowlist_append_logs |
| CURATED_DOC_UNION_PATHS == the 2 agent-docs | tested | new pin test |
| merge_into idempotent/never-clobber with 4 paths | tested | existing merge_into tests (now over ALL) |
