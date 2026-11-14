# Skill inventory data and checker for the deterministic-first pilot

Unit P0 of the pilot for `/shipwright-changelog` (run `iterate-2026-11-14-p0-changelog-inventory`). Strictly 1:1: no behaviour of the plugin changes.

## What was decided

Three data files with the campaign reports in `.shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-inventory/` (`inventory.json`, `truth_table.json`, `subprocess_map.json`; not in the plugin, the PR-review sensitive-path rule blocks new data under `plugins/*/skills/`) and `shared/scripts/tools/check_skill_inventory.py` with its tests keep the migration inventory honest while the pilot runs: every heading section of `SKILL.md` and its reference files has a class and a target, every cell of the decision table cites a real line, every spawn-map entry still finds its needle. A red result means "re-pin (`--refresh`, then classify what is new) or revert the edit". The checker stays out of shared CI and out of `verify_local.py`; the pilot's own units run it. Owner: the pilot campaign. Retirement: deliverable of pilot unit P7 (delete the checker, its tests and the three data files).

## Architecture Review

External architecture review, `--mode architecture`, over a brief that lists the options without reasons:

- **glm: approve (low findings).** The scaffold is time-boxed and proportionate; retirement depends on someone remembering it; the failure message should say "re-pin or revert".
- **openai: reject (medium).** Quoted: "A continuously checked inventory is disproportionate to a preparatory snapshot; no recurring consumer or need for ongoing synchronization is established." It recommends a one-time report tied to the starting commit (option 1), verified once at conversion start; it also notes that "retired when conversion ends" needs an owner and a trigger and that the checker "makes harmless prose edits and incremental conversion harder".

**Reconciliation (orchestrator decision, 2026-11-14): the reject is OVERRULED BY THE BRIEF, not accepted as risk.** The question "should this be built at all" was answered by the operator in the reviewed pilot brief rev 6 (P0 touch set; section 5 P0; P7 "inventory and coverage checks retired for changelog") and in programme P8 and P10, which make the inventory and its coverage checks binding for every plugin campaign and retire them per plugin at its definition of done. The reviewer's costs are real and are mitigated: the checker is out of CI and `verify_local`; the owner is the pilot campaign; the retirement trigger is P7, now an explicit deliverable line in the brief; the failure message names the two ways out (re-pin or revert); the refresh procedure is in the checker's docstring. The plan reviewers' points were adopted: counts in the mini-plan are outputs, not constants; the pin list is measured on the starting commit (origin/main at unit start).

## Doubt-review responses

- Truth-table citations without a content anchor, and subprocess-map completeness unchecked: accepted for a scaffold retired at P7; the refresh procedure in the checker docstring now says both are re-checked by hand.
- Strict promise count: stated side by side in the P0 report (14 of 15, strictly 10 of 15).
- Legacy bullets are `ask` in the inventory (the prose says the operator chooses) but `no-question` in the table (nothing is asked in any mode today): a prose/behaviour mismatch for the operator at stop 1, not changed here (1:1).
- Out-of-sequence cells cite a gate that `fires: never`: the verdict rests on first-actions.md under single_session and SKILL.md:63-66; kept as `contradicted`.
- The three data files ship in the plugin until P7 retires them; nothing reads them at runtime. Accepted until P7.

## External-Code-Review-Findings

External code review (openai: revise, glm: approve). Dispositions:

| Finding | Disposition |
|---|---|
| Subprocess line range not bounds-checked (both reviewers) | accepted-and-fixed: range must satisfy `1 <= line <= end <= file length`; test added for 0, negative, reversed and oversized |
| Truth-table citations carry no moved-line needle (openai) | rejected-with-reason: a cited line must exist; drift of the cited text is caught by the owner at re-pin, and the table is read by the operator at stop 1, not gated |
| An emptied or shortened subprocess map passes (openai) | rejected-with-reason: coverage of call sites is the job of the P5 coverage check, not this scaffold; it verifies the entries that exist |
| Runtime-input check per section vs per file; unbalanced fence message; missing `references/` exit 2; literal digest test (glm, low) | rejected-with-reason: edge cases of a scaffold retired at P7; today's data has one section in the runtime-input file |
| Mini-plan counts differ from the artifact (glm, low) | rejected-with-reason: counts are outputs, recorded as measured in the reports |
