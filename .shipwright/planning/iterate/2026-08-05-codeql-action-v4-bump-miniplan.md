# Mini-Plan: codeql-action-v4-bump

- **Run ID:** iterate-2026-08-05-codeql-action-v4-bump

## Files to create/modify
- `.github/workflows/codeql.yml` — edit (3 lines: `init@v3`→`@v4`,
  `autobuild@v3`→`@v4`, `analyze@v3`→`@v4`)
- `shared/templates/github-actions/codeql.yml.template` — edit (same 3
  lines)
- `shared/tests/test_codeql_config_query_filters.py` — edit (new test
  asserting the live workflow's version pins)
- `shared/tests/test_codeql_workflow_convention.py` — edit (new test
  asserting the template's version pins)
- `.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json` — new,
  written by `record_ci_supplychain_ack.py` (touches `.github/workflows/**`)

## Work breakdown
1. Write the two new pytest assertions first (RED — they fail against the
   current `@v3` pins).
2. Bump the 6 version strings in the two YAML/template files (GREEN).
3. Re-run the full `shared/tests` suite to confirm nothing else regressed
   (prefix-matching tests, e.g. `check_ci_gate_coverage`, are
   version-agnostic and were already expected to stay green).
4. Record the CI-supplychain acknowledgement.

## Data model changes
None.

## Test strategy
Two new unit-level YAML-shape assertions (see above). No E2E — this is a
static CI-config change with no running surface (`Verification: surface =
none`, justified in the iterate spec).

## External review findings — how addressed
- **openai (revise) / deepseek (approve):** both flag that static YAML tests
  can't prove CodeQL v4 actually runs green (init/autobuild/analyze). Both
  workflows here are `runs-on: ubuntu-latest` (GitHub-hosted, no self-hosted
  runner / GHES version concern per openai's point 1). Addressed by treating
  the PR's own `CodeQL` check (this workflow already triggers on
  `pull_request`) as the live-run proof — F11 will not deliver until it's
  green, and Self-Review explicitly re-confirms that check's result before
  calling the run done (not just generic CI).
- **openai point 3 / deepseek point 3 (test precision):** tighten the new
  tests to locate `init`/`autobuild`/`analyze` by exact step name and assert
  each `uses:` equals the full `github/codeql-action/<step>@v4` string
  (reject `@v3`), not a substring/prefix match.
- **openai point 4 (byte-identical fields):** already covered by the
  existing field-level tests (permissions, continue-on-error, queries,
  config-file) re-run after the edit — no separate snapshot/diff test added
  (deepseek independently called an extra test here unneeded).
- **deepseek point 2 (downstream adopted repos don't auto-receive the
  template bump):** already out-of-scope by design — noted, no action.

## External code-review (Stage 2 external cascade) findings — how addressed
- **openai (revise) / deepseek (approve):** openai correctly caught that
  `_codeql_action_steps()` was last-write-wins — a duplicate step (e.g. a
  leftover `@v3` step alongside an added `@v4` one) would silently pass.
  Fixed: the helper now collects every match per step name into a list, and
  the test asserts `len(matches) == 1` before checking the version, in both
  `test_codeql_config_query_filters.py` and `test_codeql_workflow_convention.py`
  (and `_init_step()` updated to match). Re-verified green (45/45).

## Alternative approach (considered and rejected)
**Alternative:** pin `github/codeql-action` to an exact SHA instead of the
mutable `@v4` tag, matching this repo's SHA-pinning convention for
third-party actions.
**Rejected because:** `github/codeql-action` is GitHub-owned, and this
repo's own decision record (`project_actions_pinning_decision` /
ADR referenced in the CI-supplychain risk-flag description) explicitly
keeps GitHub-owned actions on mutable major-version tags — only
third-party actions are SHA-pinned. Switching codeql-action to a SHA pin
here would contradict that standing decision and add unrelated scope
(a SHA-pin policy change belongs in its own iterate, not folded into a
routine deprecation bump).
