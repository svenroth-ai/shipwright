# ADR 106 — FR-unmapped framework-internal tests are the accepted steady state (STEP 3)

- Run-ID: `iterate-2026-07-17-step3-fr-unmapped-review`
- Campaign: `2026-07-15-test-traceability-layers` — ordered follow-up **STEP 3** (review-only)
- Triage card decided: `trg-0942da1f` (source `traceability-followup`, P3, kind maintenance) → **dismissed**
- Manifest evidence commit: `a419ce46` (HEAD at decision time; STEP 1 `feat(traceability): backfill 189 plugin/shared @FR tags`)
- Supersedes: the TT8 retrofit "unmapped-summary" card (already restructured into `trg-0942da1f`)

## Decision

**Dismiss the standing review card `trg-0942da1f`** ("review 7137 FR-unmapped tests")
and record this accepted-state policy in its place. In the Shipwright framework
monorepo, tests that carry **no `@FR` tag** (`untagged_tests` in the traceability
manifest) are the **expected steady state, not a backlog**. We do **not** force-tag
them to the coarse capability-FRs, and we do **not** re-file a bulk "review N unmapped
tests" card. Nothing is deleted; no test changes.

This is explicitly **not** `@FR`-tag work (STEP 1 already did that); it is the campaign's
review-only closing step, and the operator asked the executing agent to **decide**, not
defer.

## Why the monorepo is different from a product app

The traceability campaign exists to catch the rot where a *product* requirement's
tests silently drift across layers. That value is real **for a target app**, where FRs
are granular per-feature requirements and each should map to tests.

This repo is the **framework itself**. It was brought under traceability via
`/shipwright-adopt` (brownfield self-adopt), which produced **15 coarse capability-FRs**
(`01-adopted::FR-01.01`…`FR-01.15`) — essentially one FR per plugin/phase (orchestrate,
decompose, plan, design, build, test, security, deploy, changelog, compliance, iterate,
preview, adopt, triage, webui-contracts). There is **no granular per-feature FR spec**.
The framework's requirements live in ADRs, conventions, and the constitution — not in a
fine-grained FR table.

Mapping ~6.8k fine-grained internal tests onto 15 whole-plugin buckets is mechanical
(a compliance-plugin test "maps to" FR-01.10 by its path alone) and yields **zero
drift-detection value** — a coarse FR "covered" by hundreds of tests cannot meaningfully
drift-detect. That is the opposite of what the campaign is for.

## Evidence (fresh manifest regenerated at HEAD `a419ce46`, configured scope)

The committed working-tree manifest was **stale** (generated at a divergent
triage-sweep commit `573311d9` that predates STEP 1's tags — it showed only 3 links).
Regenerating in-memory at HEAD with the configured `traceability.test_roots`
(`plugins/*/tests` + `shared/tests`, `fixtures`/`.worktrees` pruned) gives the true state:

| Metric | Value |
|---|---|
| FRs | 15 (all `01-adopted::`) |
| FRs with ≥1 test link | 5 |
| Total test→FR links | **192** (FR-01.06=28, FR-01.09=7, FR-01.11=64, FR-01.13=15, FR-01.14=78) |
| `orphans` (tagged→removed/absent FR) | **0** |
| `invalid_tags` | **0** |
| `untagged_tests` | **6844** (down from 7137 at card creation; STEP 1 tagged the mappable ones + corpus grew) |

This also **reconciles** the external reviewer's HIGH finding ("189 tags vs 3 links"):
the 3 was a stale artifact; the collector resolves all 192 links correctly at HEAD.
No traceability defect — the collector is not dropping tags.

## Bounded, reproducible skim (not exhaustive review)

The 6844 untagged tests split as **6686 unit / 158 integration**, across `shared/tests`
(≈3.4k) and every plugin suite. A keyword pass over the most "product-facing" surfaces —
CLI helpers, cross-plugin `contract` tests, integration/e2e flows, WebUI/adopt-snapshot
contract tests — was inspected by sample:

- **CLI (≈318):** framework path-sanitizer/arg helpers (`test_cli_paths::test_double_quoted_becomes_clean_path`) — internal utilities.
- **"contract" (≈157):** `test_shared_contracts_consumers::test_boundary_coverage_no_sys_path_insert` — internal B8 architecture-boundary enforcement, not a product contract.
- **integration/e2e (≈230):** `test_autopilot_flow`, `test_shipwright_run_e2e::test_full_pipeline` — framework pipeline composition.
- **adopt snapshot contract (`test_snapshot_contract.py`):** the one genuine cross-repo output contract → relates to **FR-01.13**, which STEP 1 already tagged (15 links).

**Finding:** no hidden product feature. The clusters that *do* map to a specific coarse
FR were already caught by STEP 1's deterministic backfill; the remainder are
framework-internal or cross-cutting (no unambiguous single FR), which is exactly why the
deterministic engine left them untagged.

## Safety: dismissing cannot cause a CI resurface

`untagged_tests` is **informational** — no gate fails on its absolute count. The only
untagged-related gate is `layer_coverage_removal` (TT5), a strict **delta** check: a test
that was tagged to an FR at base and loses its tag at head is a HARD finding. The static
baseline of 6844 pre-existing untagged tests trips nothing. Closing the card removes an
un-actionable reminder only.

## Scope and revisit triggers

This decision is scoped to the **current `01-adopted::` coarse-FR baseline** and the
current corpus. It does **not** waive tagging where a specific FR genuinely applies —
targeted `@FR` tagging stays appropriate whenever a concrete FR-to-test relationship is
identifiable. **Revisit** if any of these land:

1. **Granular product/consumer-facing FRs** are introduced for the framework (e.g. the
   monorepo is re-decomposed via `/shipwright-project` rather than self-adopted).
2. A **new externally-supported interface/plugin** ships whose behavior deserves its own FR.
3. A **replacement traceability policy or gate** changes what "untagged" means.

Note the known limitation this scope acknowledges: because TT5 is delta-only, it will not
flag a *newly added* framework-internal test that "should" be tagged under the coarse
model — acceptable here, since under a coarse self-adopted FR set "product-facing" ≈
"framework-facing" and force-tagging adds no drift signal. Granular monorepo traceability
would be a separate, scoped initiative (decompose the framework into fine-grained FRs) —
far larger than "review N tests", and YAGNI now.

## External review (GPT-5.4 + Gemini 3.1 Pro via OpenRouter — succeeded, not degraded)

Both endorsed **DISMISS**. Refinements accepted:

| # | Reviewer | Finding | Disposition |
|---|---|---|---|
| 1 | GPT | HIGH: "189 tags vs 3 links" inconsistency weakens the premise. | accepted-and-reconciled: regenerated at HEAD → 192 links / 0 orphans; the 3 was a stale (pre-STEP-1, divergent-commit) manifest. Evidence table added. |
| 2 | GPT | "all framework-internal" needs a reproducible bounded method, incl. externally-consumed contract/CLI/WebUI suites. | accepted: bounded-skim section above (by layer + product-facing buckets sampled). |
| 3 | GPT | Scope the policy to the current coarse baseline; add revisit triggers; note TT5 is removal-only. | accepted: Scope-and-revisit-triggers section. |
| 4 | GPT | Commit the authoritative record now (don't defer to release); include card id, SHA, counts, scope. | accepted: this ADR + a `conventions.md` bullet ship in the dismissal PR; the dismissal reason links here. |
| 5 | GPT | Verify the card is still open + stamp SHA/counts immediately before dismissal. | accepted: verified open + stamped at execution. |
| 6 | GPT | Phrase the dismissal narrowly (bulk review not meaningful under current granularity; targeted tagging still applies). | accepted: reason phrased narrowly. |
| 7 | Gemini | Add future-test policy, not just the historical backlog. | accepted: the `conventions.md` bullet is always-loaded Layer-1 guidance for future tests. |
| 8 | Gemini | Write the durable record first, reference it in the dismiss reason. | accepted: ADR + conventions committed, then dismissal references the run_id/ADR. |
| 9 | Gemini | Keep the memory update precise (expected absolute count ≠ a regression). | accepted: memory distinguishes the informational count from the hard delta gate. |

## Self-Review (review-only decision; no code)

1. **Spec compliance** — pass: executes the campaign's STEP 3 (review-only, never
   auto-delete, decide dismiss-or-leave); not `@FR`-tag work.
2. **Correctness of the claim** — pass: evidence regenerated at HEAD, reconciles the
   stale-manifest discrepancy; bounded skim supports "framework-internal".
3. **No harm** — pass: no test/file deleted or changed; `untagged_tests` stays
   informational; no gate affected.
4. **Durability** — pass: ADR + always-loaded `conventions.md` bullet + tracked triage
   dismissal reason + memory; discoverable and scoped with revisit triggers.
5. **Reversibility** — pass: the append-log preserves the card; a future granular-FR
   initiative can reopen the topic cleanly.
