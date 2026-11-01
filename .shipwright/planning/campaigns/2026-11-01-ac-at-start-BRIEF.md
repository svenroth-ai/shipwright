# Campaign brief: criterion before the build (`ac-at-start`)

Date: 2026-11-01 · Status: approved by the operator to create and start; reviewed by Opus (plan review and architecture review) · Successor of baseline-package (P1 to P3, P5 merged; P4 parked as draft PR #964).

## 0. Goal
Every change that gives the product new or different behaviour has its promise written as an acceptance criterion (AC) BEFORE the build, a test bound to that AC, and is checked after the build against that AC. A promise that holds cannot change unnoticed; the HOW can then be rebuilt (less prose, more code) while the tests say whether the product still keeps its promises.

## 1. What exists (verified by the reviewers)
- FEATURE and CHANGE run `Step 2: Spec Update` (always) with the MINT-vs-FOLD gate; NONE is reserved for "behaviour-preserving, nothing observable". Test-first with an AC tag is Step 6, enforced at F11. The CI AC ratchet blocks new unbound ACs.
- All 11 holes still passed because the author classified the change as NONE, bug, restore or tooling-only. The agent that builds the change also chooses the exemption.
- AC47/AC48 (shipped 2026-10-31, warnings only) ask the completion record to name the ACs touched or to close a gap; they are one day old and not yet measured.
- The spec-reviewer reads the iterate spec and the diff, not the catalog ACs. Today a REJECT is only an instruction: nothing in code stops a commit after a REJECT in a standalone run. The cascade runs only at medium and above (or small with a risk flag or more than 100 changed lines). The iterate spec file exists only at medium and above; small runs record the AC in the plan stub.
Conclusion: this is mostly tightening and wiring what exists, not a new step.

## 2. Principles
- No new PR check. Rules live inside the iterate (planning step, review cascade, F11 of the iterate itself).
- The exemption is the audited part. An exemption is defined by outcome ("no user- or operator-observable behaviour changes"), never by a path label, complexity tier or the words bug, trivial, tooling. A fix that restores a promise must NAME the AC it restores; if no AC names it, it is a catalog gap and gets an AC.
- The agent decides alone where a fixed rule is clear and asks the operator only on a short fixed list. Under `--autonomous` an ask stops that unit with a recorded question; it never auto-approves.
- Plain language question, one sentence about the outcome. Sonnet builds, Opus reviews. Each unit is measured before the next; a failed measure stops for the operator.

## 3. Units
**Q1. Pre-build AC, frozen, with audited exemptions.**
1. Before the build, for every FEATURE and CHANGE (at every complexity), the agent records in the iterate spec (medium and above) or the plan stub `ac` field (small): the exact catalog AC text to add or change (old and new text for a change), or the exemption with its outcome reason, or for a restore the AC id it restores. The text is frozen (hash in the plan stub); a later edit is a visible diff for the reviewer.
2. The decision per AC is recorded: `ac_decisions: [{ac, mode: auto|asked, answer}]`.
3. Ask or auto, first matching row wins: (1) an existing AC is changed or removed: ask; (2) no single FR from the MINT-vs-FOLD step owns it: ask; (3) the AC text trips the lexical HOW test (path, snake_case, flag, ADR number, slug, number with unit; reused from the Step 1a altitude self-check): ask; (4) the request leaves open what the user sees: ask; otherwise auto, shown in the PR body.
4. The question (plain language, three answers; removal variant "until now this held: <promise>; after this change it no longer holds"): "This change gives the product a new promise: <one sentence>. Until now: <old promise or nothing>. Should it hold like this? 1 Yes, write it. 2 No, instead: <text>. 3 This is only how it is built, not a promise."
5. AC47/AC48 stay exactly as they are for now (day-old warnings; no rewrite). Whether they are absorbed into the pre-build declaration is decided in the report after the first 20 iterates, with their own counts (how often the warning fires, how often "how, not what" is used). Files: path-a, path-b, iterate spec template, plan stub writer, F5b.md, hooks-and-pipeline.md, tests.
Done when: (a) a replay with the earliest available request text (brief, triage card or spec goal; PR title only where nothing else exists, marked leaky) puts the 25 listed PRs of the baseline sets into the right class: demand an AC: the 11 holes plus #887 (12); answer "only how": #843 #866 #886 #918 #921 #936; restore with a named AC: #910 #914; no change: #848 #855 #900 #908 #911. The control arm is the CURRENT Step 2 text replayed the same way; Q1 must classify at least 3 more PRs correctly than the control and may miss at most 1 of the 12 demand cases and flag at most 1 of the 13 other cases; (b) the operator reads the question on 10 recorded cases and finds each clear; (c) report only, after the merge: ask rate on the first 20 iterates (stop rule: above 30 percent, or the operator rejects more than 3 of 10 sampled ACs).

**Q2. After the build: does the AC match what was built, and is the REJECT real?**
1. The spec-reviewer also receives the frozen ACs added or changed by the run and answers per AC: matches / diverges (cites the line); for a changed AC: old and new promise and whether it weakens a promise that held, unless the operator approved it in Q1 (`ac_decisions`). It also confirms any claimed exemption against the diff, or REJECTs. The instruction depends on the input being present (the reviewer is shared with `/shipwright-build`).
2. It runs whenever the run added or changed an AC, at any complexity (iterate-internal, not a PR check).
3. Wire the verdict: `record_review_pass.py` derives `verdict` from the reviewer reply; the iterate's own F11 refuses a completed `spec` row whose latest reply is REJECT. (F11 is not in the PR CI.)
Done when: on a seeded set (named: #887 #920 #925 and post-P2 backfills as correct; 5 copies with the AC wording altered to promise something the code does not do) the per-AC verdict rejects at least 4 of the 5 altered and 0 of the 5 correct. n is small by design: one false REJECT fails the bar.
Depends on Q1 (a) and (b) only.

## 4. Not in this campaign
Bugs that restore a promise WITH a named AC; any PR-blocking check; outside-model checks of the PR (P4 stays a draft, may return as a spot check on NONE declarations); inferring FR from diffs; rewriting existing ACs; the plugin rebuild itself.

## 5. Risks
- The exemption moves from "none" to "bug" or "how-only": answered by the outcome test, the named AC for restores, the reviewer confirming exemptions, and per-iterate counting of each exemption (alarm when one share rises).
- Ritual ACs and a tag-only test binding prove only that a tag exists: the operator sample reads ACs and tests; we do not claim the tag proves the promise.
- More ACs flow into the existing blocking CI AC ratchet and the bare-Layers hard abort: a drafted AC uses `(inferred)` layers unless its test lands in the same run.
- Cost: one more read and a short review per iterate; measured on the first 20. Operator questions in autonomous runs stop a unit rather than the campaign.
- Changing the shared spec-reviewer needs the mandatory `docs/hooks-and-pipeline.md` update and the plugin cache sync after the merge.
