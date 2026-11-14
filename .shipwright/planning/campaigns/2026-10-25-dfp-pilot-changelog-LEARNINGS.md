# LEARNINGS: deterministic-first pilot of `/shipwright-changelog`

**Opened** by unit P0 on 2026-11-14 from the template of brief section 8 (fixed headings, so the reports of several plugins compare). Every unit appends what it learned while it is fresh; P7 closes it; stop 3 reads it with the findings report. Plain facts, measured where possible. It never blocks a PR.

## 1. Steps and effort

| Step | Unit | PR | Review rounds | Wall-clock | Tokens | What took longer than expected |
|---|---|---|---|---|---|---|
| Inventory, truth table, subprocess map, checker, findings, ledger reconcile, pin list, promise list, P24 before-measurement | P0 | (filled when the PR opens) | architecture review: 1 reject (overruled by the brief), plan review: revise x2 | started 2026-11-13 23:57 UTC; stop-1 hand-over time in the PR | not measured by the runner | the pin measurement: `shared/tests` alone ran about 30 minutes on a busy machine (MEASURE section 7.3: 1,802 s); the architecture review halted the unit once and needed an orchestrator answer |
| Seams, harness, scenarios, promise tests, extraction, thin `SKILL.md`, ratchet, conversion check, operator procedures | P1-P7-op | not started | | | | |

## 2. Code or AI decisions

The deciding question of the convention (`docs/building-skills-plugins-agents.md`): can the answer be checked without understanding language? Inventory class of each moved instruction, first pass (P0):

| Instruction | Decision | Why |
|---|---|---|
| propose the next version from commit types (Step 3) | code | the rule is AC04; `suggest_version_bump` returns it; a test checks it |
| render the changelog section from the drops, number the ADRs (Step 4) | code | output compared byte for byte |
| commit by explicit pathspec, verify the commit, tag only on exit 0 (Step 6) | code | every step has an exit code and a postcondition in git |
| read each changed migration page and write the upgrade-note drop (Step 4, release-workflow) | AI | needs reading comprehension; code can only check that a drop exists |
| edit the previewed entry as the operator describes (Step 5) | AI | free-text instruction; the result is not checkable without understanding it |
| condense the release section for the release page (Step 7) | AI wrapped in code | the model writes, `validate_release_notes.py` checks the shape; already the target pattern |
| open the PR, merge it, push tags (Step 7) | neither: outward command | stays a literal command in the prompt (programme P4); not decided by judgement, but not safe to run from code without the operator's authority |
| accept or type another version (Step 3), accept or cancel the preview (Step 5) | ask | the operator's decision; the question is a row of the truth table |

Changed after review: nothing yet (P0 only).

## 3. Recurring patterns

- The AI judges and code validates: the release-page condensation and (proposed) the upgrade-notes drop.
- A mixed section is the normal case: Step 4 and Step 7 each carry five to eight instructions of three classes, so a section is not the unit of conversion; the instruction is. The inventory therefore lists `parts` for a `mixed` section.
- Where two sources disagree, the prose contradicts itself more often than it contradicts the code (D1, D8, D10, D11): the code is the safer oracle, and the real-model runs decide the rest.

## 4. Pitfalls

- **A green test on a function the skill never calls.** The AC02 `covers` tests exercise `lib/changelog.py`, which no step calls; the ledger rated AC02 `enforced, tested` for months. Found by tracing the skill's own path from `SKILL.md` to the tool it runs, not by reading test names (finding D13; ledger row 2). The AC04 iterate had found the same shape once before.
- **The brief's own numbers and line citations go stale.** "Seven references" (there are ten), three moved line citations, a pre-assessment table that missed the event fold and the upgrade-notes check. Re-measure from the tree the unit starts on, and let a checker hold the citations.
- **A checker test on the real tree is a CI pin.** A first version of the checker's tests also ran it on the real skill; the spec reviewer pointed out that CI runs that test root, so every prose edit would red CI and the ADR's claim "out of CI" would be false. The tests now use throwaway skills only; the pilot's units run the CLI on the real one. The same review caught a `covers` mark on that test (a ritual tag, the D13 mistake).
- **A review can reject what the operator approved.** The architecture review rejected the inventory checker that the brief and programme P10 mandate; the unit halted until the orchestrator overruled the reject by pointing at the brief. Brief the reviewers with the approved scope, or expect one halt per unit that builds a mandated mechanism.
- **Data a conversion tool needs does not belong under `plugins/*/skills/`.** The three inventory data files were first filed next to `SKILL.md`; the PR-review sensitive-path rule blocks new content there even though nothing reads it at runtime, which cost one PR-review round and a move. File such data with the campaign reports.
- **Typed heredocs corrupt files with quotes and backticks** (a Python script with an apostrophe in a string ended the heredoc early): write scripts with the Write tool.

## 5. Tools

| Tool | Class | What a generic version would need |
|---|---|---|
| break-the-prose measure (replace the prompt files with a placeholder, run every test root once, list what fails) | generic | a list of the prompt files and the repo's test roots; one process per root |
| `check_skill_inventory.py` (anchors by heading path and content hash, class/target vocabulary, truth-table and subprocess-map line checks) | generic in method, written against this repo's skill layout (`SKILL.md` + `references/`) | the skill folder convention and a class vocabulary |
| truth table `{context} x {autonomy} x {question}` with a citation per cell | generic | the list of modes and questions |
| subprocess map with a needle per line | generic | none |
| AC ledger reconcile and `measure_ac_evidence_ledger.py` | Shipwright-specific | FR/AC ids, `covers` marks, the ledger |
| `ac_decision.py` record (`unchanged`, `--ac-mode auto`) | Shipwright-specific | the FR catalog |
| `fr_cluster_report.py`, the AC-Move-Map | Shipwright-specific | atomic FR splits |
| golden trace, fork tool, L3 harness | not used yet (P2a onward) | |

## 6. Doable by a stranger?

| Step | Verdict |
|---|---|
| inventory (sections, classes, targets) | yes, with the tools of item 5 |
| truth table and subprocess map | yes: read the prose and the code, cite lines |
| pin list by breaking the prose | yes, with the break-the-prose measure; the machine time is the cost (about 30 minutes for the biggest root here) |
| ledger reconcile against the path the skill takes | no without Shipwright knowledge: it needs the FR/AC ledger and the `covers` convention |
| promise list in plain language | yes with a repo that has acceptance criteria; for a repo without them this step needs a lighter mode (writing the promises first) |
| operator questions in plain language | yes |

**Convention file** (`docs/building-skills-plugins-agents.md`): the migration showed one gap so far. It has no class for an *outward command* (a literal command that is neither judgement nor safe to move into code, e.g. `gh pr merge`); P0 recorded them as `mechanic` with target `keep` and a note.
