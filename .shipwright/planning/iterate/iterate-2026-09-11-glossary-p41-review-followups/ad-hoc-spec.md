# Ad-hoc spec — glossary-p41-review-followups (small, BUG intent, no iterate-spec file at this complexity)

Origin: PR #699 review (campaign req3-09-p4-grill-glossary, sub-iterate P4.1,
run_id iterate-2026-09-09-p4-1-glossary-generator). Deferred as non-blocking:

1. `shared/tests/test_write_context_term_cli.py`'s function names still say
   `wired_cli` though it now covers the legacy flag path only (docstring
   already fixed, naming not). **AC:** rename the two `test_wired_cli_*`
   functions to reflect the legacy-flag-path scope; update any stale
   cross-references to the old names.
2. Legacy `--term`/`--definition`/`--avoid` CLI flags carry no argparse help
   text warning against shell-composed interview text. **AC:** add `help=`
   text to those three `argparse` arguments pointing at `--payload-file` for
   free interview text.
3. `test_requirement_elicitation_refs.py`'s doc guard checks `--payload-file`
   is present but doesn't assert a `--term`-shaped bash snippet is absent
   from `interview-protocol.md`'s fenced blocks. **AC:** add an assertion
   (in the actual doc-guard test that checks `--payload-file`'s presence,
   wherever it lives) that no fenced ```bash block in `interview-protocol.md`
   contains a `--term`-shaped invocation.
4. A payload with `avoid` set to an empty string (rather than omitted/null)
   hard-fails with an error message naming CLI flags the payload caller
   never used. **AC:** the blank-avoid rejection message must be
   understandable by both a CLI-flag caller and a `--payload-file` caller —
   name the payload's own field spelling (`avoid`/`clear_avoid`), not only
   the CLI flag spelling. The blank-avoid rejection itself must remain (a
   given-but-blank avoid is still invalid input, per doubt-reviewer D5 in
   the P4.1 history).
5. `term_markup_count`'s duplicate-term scan still counts a bolded
   cross-reference inside a Language entry's own definition text, which can
   permanently block upserting that term with no hand-edit recovery path
   available mid-interview. **AC:** find and fix the real false-positive
   case (verified empirically: a hand-authored `_Avoid_` line that wraps
   onto a second physical line, where that wrapped line starts with a
   bolded cross-reference to another term, orphans into an unparsed raw
   block that `term_markup_count` then counts as a permanent duplicate for
   that term). Add a regression test. Do not weaken the existing hidden-
   duplicate detection (`test_write_context_term_duplicates.py`'s three
   existing rejection cases must keep passing).

## Out of scope
No new features. No behavior change to the sanctioned `--payload-file`
interview path beyond the error-message wording (item 4) and the parser
fix (item 5, which also benefits `--payload-file` callers since it's the
same `upsert_term`/`parse_language_entries` code path).
