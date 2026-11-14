# Mini-plan: P0 of the deterministic-first pilot for /shipwright-changelog

Strictly 1:1: no behaviour of the changelog plugin changes. Deliverables are data, a checker, tests and reports.

## Steps
1. `skills/changelog/inventory.json`: every heading section of SKILL.md and the ten reference files, anchor = file + heading path + content hash, class and target from the programme vocabulary; mixed sections list their parts.
2. `truth_table.json` (30 cells: 2 contexts x 3 autonomy x 5 questions, each citing file:line) and `subprocess_map.json` (29 entries, each citing the line that holds its needle).
3. `shared/scripts/tools/check_skill_inventory.py` verifies 1 and 2 against the tree (orphans, stale hashes, vocabulary, runtime inputs, cell coverage, moved lines). Exit 1 on any problem. 259 lines.
4. `shared/scripts/tools/tests/test_check_skill_inventory.py` (tests on throwaway skills only; never on the real one, since CI runs that root).
5. Reports: FINDINGS (D1-D20), LEARNINGS (opened from the template), P0 report (pin list by breaking the prose, promise list, P24 before-measurement, profile keys, open questions); ledger reconciled both ways for FR-01.09.
6. PR left open; PR body carries what operator stop 1 decides.

## Risks
- A checker test on the real skill would be a CI pin; the tests use throwaway skills and the pilot units run the CLI.
- Pin list must be measured on this tree; done in a throwaway worktree at origin/main with the prose replaced by a placeholder, five roots, one process each.

## Test strategy
Unit tests of the checker; the checker run over the real skill; ledger counts re-measured with measure_ac_evidence_ledger.py.
