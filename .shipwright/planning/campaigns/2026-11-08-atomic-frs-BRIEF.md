# Campaign brief: atomic requirements (`atomic-frs`), for operator review

Date: 2026-11-08 · Status: DRAFT rev 3 (operator decisions 2026-11-08 included), nothing built · Follows `ac-at-start` (Q1 and Q2 phase 1 merged).
Rev 2: the trigger is "can this FR still be split", not a number of ACs.

## 0. Goal
A requirement (FR) names ONE capability with a small, countable set of promises (ACs). Then a new promise can be assigned to the right requirement by AI at 86-96 % (as measured on clean catalogs) instead of 57-62 % (old projects with huge FRs), and a changed promise is easy to see.

## 1. Evidence
- Measured in `ac-at-start`: AI picks the right FR for a new AC in 86-96 % on the two e2e catalogs, only 57-62 % on shipwright and shipwright-webui. Huge FRs absorb everything, so code history cannot rank them either.
- Shipwright's own catalog (`01-adopted/spec.md`): 21 FRs, 305 ACs, median 12 ACs per FR. The tail: FR-01.11 has 49, FR-01.14 29, FR-01.03 22, FR-01.06 and FR-01.07 18 each. The webui has FR-01.66 as its outlier.
- Existing rules (`shared/fr-authoring.md`) cover naming and MINT-vs-FOLD but say nothing about SIZE or scope. FOLD (append ACs to the existing FR) is what grows the big ones.

## 2. Principle: the criterion is "can it be split further", not a count
A count is only a symptom. 20 ACs can be one capability; 8 ACs can be two. So:
- **Code finds the seams.** It groups the ACs of one FR by what they actually share: bound tests, touched files, vocabulary in the AC text. Two or more groups that share almost nothing = splittable. One tightly connected group = stays whole, even at 25 ACs.
- **AI judges only the leftover question:** can each group be named in one plain sentence without "and" (the capability test)?
- **The AC count only sorts the worklist** (biggest FRs are checked first). It is never a rule.
- **Stop rule (against hundreds of tiny FRs):** split only if every part has a name a user understands AND code finds no shared tests or files between the parts.
- **At authoring time** (MINT vs FOLD) the same question replaces a number: does the new AC serve the same purpose as the other ACs of this FR? If not, MINT a new FR. AI decides; the cluster evidence from code is attached.
- **Honest limit:** clusters show what is connected in code. Two promises sharing one test can still be two capabilities. So code proposes, the operator confirms every cut.

| Task | Code | AI / prose |
|---|---|---|
| Group the ACs of an FR into clusters (tests, files, vocabulary) | yes | |
| Rank FRs by splittability (cluster count, size as tie-break) | yes | |
| List split candidates with evidence (bound tests, touched files) | yes | |
| Next free FR number (live and removed) | yes | |
| Form of every AC (Given/When/Then, no paths or symbols) | yes (reuse Q1 wording check) | |
| Conservation on a split: every AC of the old FR appears exactly once in the result, ids/tags/test bindings and traceability preserved | yes (hard check, fails the split) | |
| Is a cluster one capability? (one sentence without "and") | | AI |
| Where the natural cut between two promises lies | | AI proposes ONE grouping; operator confirms |
| Plain-language names of the new FRs | | AI drafts, code checks the name fence (Group I1) |
| Does a NEW AC serve the same purpose as this FR's others | | AI, with cluster evidence from code |

## 3. Units
**U1 (part A, new work, small): scope rule in the project skill and the audit.**
- Add the scope rule to `shared/fr-authoring.md`: one FR = one capability; fold a new AC only if it serves the same purpose, otherwise MINT; the stop rule above.
- Code: a new advisory audit check (next to Group I) that clusters each FR and lists the splittable ones, size as sort order. Project skill spec generation and iterate Step 2 call it. Advisory, never red (legacy must not redden CI), like I1-I3.
- Done when: a fresh run of the project skill on two test briefs yields no splittable FR and the audit check flags a seeded two-capability FR (including one with few ACs) and leaves a seeded large single-capability FR alone.

**U2 (part B, per repo): re-slice the outliers.**
- Tool `fr_split` (code): takes an FR id and the AI/operator grouping, performs the split in spec.md, the catalog, test tags and the traceability manifest, and runs the conservation check. Dry-run first, diff shown.
- Run on shipwright (FR-01.11, FR-01.14, then FR-01.03), then the webui (FR-01.66) as its own iterate in that repo. Each split is one iterate with review cascade; no split is merged unless conservation holds.
- Done when: no FR in either repo is flagged splittable by the audit (or has an explicit, recorded exception), conservation check green, CI green.

**U3: re-measure.** Re-run the FR-assignment measurement (`scratchpad/fr-assign-measure`, report `RESULT.md`) on the re-sliced catalogs. Success bar: AI top-1 above 80 % on both old repos (from 57-62 %). If the bar is missed, report honestly and decide with the operator whether the "agree to auto" path becomes viable.

## 4. Out of scope
Rewriting AC wording; changing Q1/Q2 behaviour; a rule "FR too broad, propose a new FR" inside Q1 (the operator rejected it: this campaign is the answer); mass renumbering of existing FR ids (splits only add ids).

## 5. Risks
- IDs, tags and traceability: a split touches spec, tests, manifest, compliance docs. Mitigation: the conservation check is code and blocks the split.
- Wrong cut: clusters can separate promises that belong together, or join two capabilities through a shared test. Mitigation: operator confirms the grouping; dry-run diff.
- Over-splitting makes assignment worse again. Mitigation: the stop rule; U3 measures the result.
- Cluster signals may be weak on old FRs with thin test tagging. Mitigation: U1 reports clusters with their evidence; if evidence is thin, the audit says "no evidence" instead of guessing.
- Webui work belongs to the other repo's iterate flow; standing grants (admin merge) do NOT cover it.

## 6. Operator decisions (2026-11-08)
1. **Project skill BLOCKS; the audit only advises.** At spec-writing time there is no code or test yet, so the block rests on the AI capability test (one sentence without "and") plus code form checks: the skill may not finish an FR until every ACs group passes. The code-cluster check (tests, files) runs in the audit after the build, advisory only, so legacy catalogs never turn CI red.
2. **Order: U1, U2 shipwright, U2b webui, U3.** U2b = write good ACs for the webui and slice its FRs (REQ3.03/3.06/3.07, triage trg-a8f4b029). Precondition seen there: `spec_parser._ACCEPTANCE_LABELS` needs a label, so `check_s5_fr_coherence` reads 0 ACs on adopt-format specs; to be verified in U1 (the AC catalog `ac_catalog.py` itself reads ACs). Webui is another repo: the ac-at-start admin-merge grant does NOT cover it.
3. **Automatic grouping, but no auto-merge.** Code/AI proposes and performs the cut, conservation check must pass, every split is one PR with a list of the cuts; the operator approves before anything is merged.
4. **Reviews:** normal iterate process (architecture review before build, then spec -> code -> doubt with model=opus passed explicitly). `fr_split` (U2) touches spec, tests and traceability together and is classified high-risk, so it gets the full review.
