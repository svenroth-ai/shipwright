# Iterate: parametrized tests with bracketed values read as never run

- **Run:** iterate-2026-10-25-junit-nested-param-ids
- **Type:** bug · **Complexity:** small · **Risk flags:** none
- **Branch:** iterate/junit-nested-param-ids

## Problem

The traceability join folds a pytest JUnit case such as `test_x[a]` to its function id
`test_x`, because the manifest binds tests by function id. The fold used
`\[[^\]]*\]$`, which stops at the first `]`. A parameter whose VALUE holds brackets, e.g.
`test_pr_filters_make_a_check_possible_only_unless_proved[branches: [main]-main-True]`,
therefore stayed unfolded. The bound function id then had no evidence and its link read
`executed: not_run`, although every case passed.

Consequence: FR-01.17 (AC06 is bound only to such a parametrized test) shows no executed
test in the evidence run, so the layer-promotion sweep escalates it instead of promoting it.

## Root cause

`_PARAM_SUFFIX` in `plugins/shipwright-compliance/scripts/lib/collectors/_evidence_readers.py`
assumes a parameter id holds no `]`. pytest builds the id from the parameter values, so it can.

## Acceptance criteria

- AC1: a JUnit case whose parameter id holds nested brackets folds to the function id in
  `read_junit`, and in `read_junit_cases` (same identity, same counts).
- AC2: the fold stays fail-closed: one failing case among the cases of a function id makes the
  function id `fail`; it is never masked by a passing sibling.
- AC3: ids without nested brackets fold exactly as before.

## Scope

Only the regex and its comment. No change to the join, the vocabulary or the schema.

## Spec impact

NONE. Restores the specified behaviour of FR-01.11 (execution evidence is joined to the
bound test); the FR text is correct.

## Tests

`test_nested_brackets_in_a_param_id_fold_to_the_function_id` in
`plugins/shipwright-compliance/tests/test_execution_evidence_paths.py` (red before the fix).
