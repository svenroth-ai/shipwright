# Iterate Spec: tag-gate follow-up (data-driven tests, base-side prune set, TS lexing, decorator edits, skip-set)

- **Run ID:** iterate-2026-10-08-tag-gate-followup
- **Type:** change
- **Complexity:** medium
- **Status:** draft

## Goal
Close the accepted limits (a)-(d) of the U1 test-tag gate (`iterate-2026-10-08-u1-test-tag-gate-reviews`) and the U11 gap
where the integration scenario read a SKIPPED gate as green (triage trg-0c6749d2 / trg-d3853d97).

## Acceptance Criteria
- [ ] `it.each(table)('title', ...)` / `test.each(table)('title', ...)` / ``test.each`table`('title', ...)`` (table on one line or
      wrapped over several) is enumerated by the collector as ONE test whose id is the title text; an untagged one added by a diff
      makes `check_test_tag_binding` fail with `untagged-added`, a `{ tag: ['@FR-02.01'] }` one passes; `describe.each`,
      `test.describe.each`, `test.step` and commented lines stay non-declarations.
- [ ] The head manifest is built so a folder is skipped only if BOTH the base and the head `traceability.exclude_dirs` exclude it: a diff that adds an untagged test under a
      directory it also adds to `exclude_dirs` fails the gate; a new test under a directory the BASE already excluded stays invisible.
- [ ] A quote inside a regex literal (`/it's/`) or inside JSX text (`<p>Don't</p>`) no longer swallows the rest of the test body: an edit
      after it changes the body digest, a whitespace-only change in the JSX text does not, and identifiers inside `{...}` JSX
      expressions stay visible to the `mechanical-refactor` rename check. `.ts` files are not lexed as JSX.
- [ ] The digest of a TS test covers its callee (`test.skip`, an `.each` table); the digest of a Python test covers its decorators, its classes'
      decorators and the module `pytestmark`, except `covers` tags (every other mark counts, `slow` included, since a project can deselect by marker; skip/skipif/xfail/parametrize/usefixtures
      marks count; non-mark decorators such as `patch` or `unittest.skip` always count): removing a skip/xfail or editing parametrize rows is an edit (`untagged-modified`),
      adding a `covers` tag or a class tag is not.
- [ ] `shared/tests/test_finalization_claims_scenario.py` records per gate whether it ran or was skipped; the compliant run must skip
      exactly `{U4,U5}` at trivial, `{U5}` at small, `{U4}` at medium, and a broken-claim case fails if the owning gate was skipped.

## Spec Impact
- **Classification:** modify
- **MODIFY:** FR-01.11 - new AC42 (data-driven tests, skip/parameter edits and head-side exclusions count as added/edited tests).

## Out of Scope
- Multi-line template tables whose closing line does not carry the title quote; a `/` after `)`/`]`/`}` is judged by the last token only.
- A `.each` table longer than 400 lines (collector) or 20000 characters (gate) is not seen; a pathological table string holding `)(` + a quote.
- Parametrize argnames are not anonymised on a mechanical rename; TS `describe.skip` and similar suite modifiers are not in a test's digest.
- Adding a fixture repo AND the config line that excludes it needs two PRs (base must already exclude it); a regex literal right after `)` (`(a) /re/`) reads as division.
- Collector caps a `.each` table at 400 lines, the gate at 20000 characters; a table in between is enumerated but not digested.
- A brand-new test root named only by head config (the union floor and base-dir re-scan cover the usual cases).
- The base-INTERSECT-head prune rule is opt-in (`base_prune_only`) and only the test-tag gate uses it; the coverage gates keep the head's own `exclude_dirs` as the fixture fence.
- The collector's `.each` table scan (`_file_tags._each_end`) knows strings and comments but not regex literals or JSX text, so a wrapped table holding `/it's/` is not folded and the test stays invisible to the collector (the gate's lexer does handle it). The collector lives in a separate plugin and cannot import the gate's lexer.
- Python: two marks written in a different order digest differently (false STOP on a pure reorder); several `pytestmark =` assignments are summed rather than last-wins.
- Gate declaration search is per title and rescans `.each` tables (up to 20000 chars): quadratic on files with hundreds of `.each` tests, not measured.
- `.gitattributes export-ignore` shrinking the archived head tree (limit (b) names it; only `exclude_dirs` is closed here).
- `_is_test_id` path heuristic (e) and the merge-base recomputation (f).

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `fr_tag_grammar._TEST_DECL_RE` / `_file_tags.join_multiline_decls` (collector enumeration) | `_tag_binding_ts._decls` (gate) | test id = `<file>::<title>` |
| `_layer_coverage_regen._base_and_renames` (base prune set) | `_layer_coverage_regen.regenerate_base_head` (head build) | frozenset of dir names, in-process |

Both pairs are exercised end to end by the real-git integration tests (`test_tag_binding_followup.py`).

## Confidence Calibration
- **Boundaries touched:** the collector -> gate test-id contract; base prune set -> head build.
- **Empirical probes run:** see the Test Completeness Ledger (all through the real collector and real git).
- **Test Completeness Ledger:** recorded at F5 (`iterate_latest.test_completeness`).
- **Confidence-pattern check:** each fix has a test that fails on the old behavior (verified by the regenerated fixtures below).

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Plan matches the built code; main risks are the base-prune change reaching the removal and cross-layer gates, and the wrapped-table shape with the title on the next line.
- **Findings:** (1) prune set shared by other gates, medium, disclosed (Out of Scope names it; intersection rule keeps additions visible). (2) `])(` newline title shape invisible, medium, fixed (joiner returns the title line; collector test). (3) module `pytestmark` skip not in digest, low, fixed. (4) `it` vs `test` callee, low, fixed (normalised). (5) table size caps differ, low, disclosed (400 lines / 20000 chars, Out of Scope). (6) per-line `_each_end` cost, low, fixed (cheap first-line test). (7) new-test-root and U6-no-skip-channel notes, low, disclosed. (8) U1 ADR limits list, low, recorded via decision drop.
- **Known limitations:** table caps; brand-new test root named only by head config; `export-ignore`; U6 has no skip channel.
- **Status:** 4 fixed, 4 disclosed, 0 declined

## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** yes
- **Severity:** medium
- **Summary:** Take option A; use the intersection of base and head exclude sets, decide the decorator blast radius on purpose, keep the lexer minimal.
- **Findings:** intersection of exclude sets, medium, fixed. Class-decorator blast radius, medium, fixed (first narrowed to behavioural marks; the doubt review showed a project can deselect by any marker, so every decorator and class-body/module `pytestmark` (assign, annotated, `+=`) counts except `covers`). Lexer cost vs benefit, medium, declined (already built and tested; split judged not worth a second iterate; limits documented in the module docstring). JSX extensions, low, fixed (`.tsx/.jsx/.js`; `.mjs/.cjs` dropped on re-review). Same-title collisions, low, disclosed (existing `ambiguous-name` rule covers them). Hard-coded skip sets, low, disclosed (asserted literal). Regex backtracking, low, fixed (bounded quantifiers).
- **Known limitations:** hand lexer approximates TS lexical grammar.
- **Status:** 5 fixed, 2 disclosed, 1 declined

## Architecture Review
- **Brief:** `.shipwright/planning/iterate/iterate-2026-10-08-tag-gate-followup/architecture_brief.md`
- **Verdicts:** glm=approve · openai=approve
- **Smallest thing that would do (per reviewers):** as proposed (glm: keep the lexer as a literal-skipper)
- **Findings:** lexer ambition (glm, medium): rejected-with-reason - JSX element lexing is needed to keep `{expr}` identifiers visible to the rename check; the module docstring caps the scope. Silent-regression risk (glm, low): accepted - the regex/JSX fixtures in `test_tag_binding_followup.py` are the adversarial corpus.
- **Reconciliation:** the brief listed a real parser (B) and a config-change hard stop (D); both reviewers pick A. Plan alternative (real parser) was rejected for the stdlib-only constraint, consistent with their verdicts.

## External Plan Review (glm revise, openai revise)
Accepted-and-fixed: tests for adding a row to a legacy `.each` table through the real gate, un-excluding a dir, no base config, nested JSX/template/division, `.ts` generic arrow. Disclosed: digest format is recomputed in-process for both sides, so no migration. Pathological `)(`+quote inside a table string is a known limit of the regex form.

## External Code Review (openai revise, glm)
| # | Reviewer | Finding | Disposition |
|---|---|---|---|
| 1 | openai | Wrapped-table scanner counts parens inside comments and regex literals | Accepted for comments (fixed: `_each_end` skips `//` and `/* */`; test `test_comments_with_quotes_and_parens_inside_a_wrapped_table_do_not_break_the_fold`); regex/JSX inside a collector table disclosed in Out of Scope |
| 2 | openai | Module `pytestmark` as an annotated assignment ignored | Accepted, fixed (`_scope_marks` handles Assign, AnnAssign, AugAssign; test added) |
| 3 | glm | `_quoted_end` never stops at a newline and mispairs quotes | Accepted, fixed (single/double quotes end at a newline; fold aborts) |
| 4 | glm | `.each` followed by a backtick table on the next line is never folded | Rejected: already handled by `_EACH_BARE_RE` (bare `.each` line, table opens below); covered by the bare-template case in `test_comments_with_quotes_and_parens_inside_a_wrapped_table_do_not_break_the_fold` |
| 5 | glm | `/` after `)` read as division | Disclosed (module docstring and Out of Scope) |
| 6 | glm | `_base_and_renames` 3-tuple breaks other unpack sites | Rejected: grep shows `regenerate_base_head` is the only unpacking site |
| 7 | glm | No collector test for an apostrophe in a comment inside a wrapped table | Rejected: the comments test above already covers it |
