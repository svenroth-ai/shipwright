# Mini-plan: Q1 pre-build AC

Goal: before the build of a feature or change, record the exact AC text (old and new for a change), or an exemption by outcome, or the AC a restore restores; ask the operator on a fixed short list; freeze the text with a hash.

Work: lib/ac_decision.py (lexical HOW test, table, validation, hash, stub lines); tools/ac_decision.py (CLI, exit 0/10/2, autonomous escalation); write_plan_stub --ac-decision; advisory F11 check pre_build_ac_check; runner schema reason_code ac_question_requires_operator; prose in path-a Step 2a, path-b, runner Step 3 (net-zero lines), F5b, hooks-and-pipeline; AC49 under FR-01.11; tests.
Measure: replay of 25 baseline PRs, question sheet, post-merge report note.
