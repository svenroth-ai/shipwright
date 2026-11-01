# Campaign brief: baseline package (`baseline-package`)

Date: 2026-10-31 · Status: approved by the operator for creation, start by the operator · Successor of the stopped baseline-protection (BP) campaign (see 2026-10-27-baseline-protection-BRIEF.md, STOPPED note).

## 0. Goal
Requirements (FR), acceptance criteria (AC), tests and the iterate specs together form a **package** from which a person or an AI can see WHAT and WHY the application does, and which specs shaped each requirement. The HOW may then be rebuilt freely (for example the deterministic-plugins programme) without losing the WHAT/WHY. Secondary goal: a promise that holds today is not changed unnoticed.

The line between the layers: an AC states an outcome a user or operator could observe or demand, independent of technology. Mechanism, vendor, file, flag and threshold belong in the plan or the code.

## 1. Evidence (AI-labelled, operator confirmed 10 of 10 PR labels)
Measurements: `2026-10-31-baseline-package-MEASURE.md` (AC level, gaps, spec chain) and `2026-10-31-baseline-package-REPLAY2.md` (sharper labels, AC-check replay).
- AC level: about 215 WHAT/WHY, 60 MIXED, 10 HOW of 289 ACs (sample of 60, two blind readers, 92% agreement). 13 of 21 FR titles are slash-command names.
- Holes: of 17 PRs that added behaviour, 11 would be lost in a rebuild from the catalog: #837, #839, #842, #859, #869, #883, #884, #897, #919, #923, #924. All were recorded `spec_impact: none`; 6 named the right FR but no AC was written. Rough rate 15 to 20 per 100 PRs.
- Real contradictions of an existing AC are rare (3 of 35: #887, #920, #925).
- Spec chain: FR to plan to PR resolves for 14 of 20 sampled iterates, AC level for 1 of 20; 45 of 192 runs have no plan; event `commit` is empty on 182 of 219; the traceability matrix is stale.
- AI check replay (Sonnet, blind): flags 6 of the 7 known misses, 0 of 5 no-change PRs, but weak at "AC untrue" (names the AC for 1 of 3) and disagrees on 34% of PRs. It is a gap check, not a contradiction detector.

## 2. Principles
- Nothing holds a PR. Every unit adds a record, a field or a visible block. No new required check.
- Every unit's claim is measured (replay) before the next unit starts. A failed measure stops the campaign for the operator.
- Models: build with Sonnet, every review with Opus. A second, non-Claude model (GPT or GLM through the external-review path) supplies the independent ground truth where a unit says so.
- One unit = one PR. Binding wording of the units is section 3.

## 3. Units
**P1. `affected_acs` on every `work_completed` event.** At F5b, `spec_impact: none` (and every other spec impact) on a feature/change/bug whose diff touches runtime paths (`plugins/**`, `shared/**` excluding tests and docs) must carry `affected_acs`: AC ids changed, implemented, or checked-and-unchanged (each with one line why its promise holds), or `catalog_gap: true` with the nearest FR. Add the field to the event schema, the F5b/F11 consistency check (presence only, never a hold on content), docs, tests. Done when: replay over the 100-PR window shows the field required on all runtime-touching iterates and the F11 check passes on a fresh iterate.
**P2. Close the gap in the same PR, then backfill.** A declared `catalog_gap` makes the iterate write a WHAT/WHY AC through the existing MINT/FOLD path, or record a closed reason (`how-only`). Then backfill the 11 known holes (section 1) in one batch: an Opus agent drafts plain-language WHAT/WHY ACs, a second reads them to check that none names mechanism, vendor or threshold. **Operator stop: the operator reads all 11 drafted ACs in the PR body before merge**; the unit escalates with reason `waiting for operator review of the 11 ACs` instead of merging, and no admin-merge permission exists for this campaign. Done when: the 11 are in the catalog and a new PR with a gap cannot finish without an AC or a reason. Depends on P1.
**P3. Spec chain.** Add `plan_path` and `pr` to the `work_completed` event; every non-trivial run writes a plan stub: three lines (goal = WHAT, reason = WHY, plan or PR reference), tiny runs one line, except runs that change an AC or declare `catalog_gap`, which get the full stub; one filename convention going forward; regenerate the traceability matrix on a schedule or at each release; add an index FR/AC to events to plan to PR and a lookup for "which specs shaped AC X" (backfilled where data exists). Done when: a replay of the 20-iterate sample (seed 20261031) resolves 20 of 20 for runs recorded after the change, and the lookup answers for at least 10 ACs with history.
**P4. Independent AI check as a gap check.** One fresh-context call before the commit, at every complexity, reading the diff, the ACs of the owning FRs and the P1 declaration; output is one PR-body block (requirements changed, checked, check verdict agree/disagree, gap yes/no). It never blocks. Framed as a check for a wrong "none" and for catalog gaps, not as an "AC untrue" detector. Iterate PRs only in this unit; PRs outside iterate are a later decision after the noise measurement. Done when: with a non-Claude model it flags at least 6 of the 7 known misses (#843 #869 #884 #887 #910 #914 #921) and 0 of the 5 no-change PRs (#848 #855 #900 #908 #911), disagrees on at most 25% of the 35 PRs, and the operator agrees on a fresh set of 10. Depends on P1.
**P5. Tidy.** Move model, vendor and threshold detail out of the MIXED ACs into plans (start: FR-01.03 AC03, FR-01.11 AC30/32/35, FR-01.21 AC05); rename the 13 command-named FR titles to capability names. Done when: a second pass over the same 60-AC sample (seed 20261031) finds MIXED at most half of today's count and the traceability and RTM generators still resolve the renamed FRs.

Order (serial): P1, P2, P3, P5, P4. P2 stops for the operator, as stated.

## 4. Not in this campaign
Diff-to-FR inference and any blocking gate on requirement changes (BP), splitting FRs, the AC question at iterate start (revisit after P4), PRs outside iterate for the AI check, the deterministic plugin rebuild itself (this campaign is its safety net).

## 5. Risks
- "Requirement change" and WHAT versus HOW are judged by AI readers; the operator confirmed 10 of 10 labels, not the whole set. P4 therefore uses a second model family and a fresh operator sample.
- P1 can turn into a ritual sentence. P4 is the test of that; if P4 fails its bars the campaign stops and reports.
- Backfilled ACs can themselves drift to HOW; the P2 second reader and the operator's reading are the control.

## 6. Outcome note (2026-11-01)
P1, P2, P3 and P5 are merged. P4 was built and measured but is deliberately NOT merged (draft PR #964): the 25 percent noise bar (disagreement with the author) was not met (63 to 66 percent; 5 of a fresh 10), and the operator preferred to prevent the gap before the build. The successor is `2026-11-01-ac-at-start-BRIEF.md`; P4 may return later as a spot check on `none` declarations.
