# External plan review — iterate-2026-07-27-changelog-aggregator-idempotency

- **Tool:** `shared/scripts/tools/external_review.py --mode iterate`
- **Provider:** openrouter (gemini + openai legs, both `status: success`)
- **Verdicts:** `gemini=approve`, `openai=revise`
- **Contradiction:** not detected — `comparable: true`,
  `requires_resolution: false` ("verdicts agree within one step").

Per-finding disposition lives in the iterate spec under **Review cascade →
External plan review**. Verbatim feedback below.

---

## gemini — verdict: approve

- **Category:** Edge-case / **Severity:** Medium
  **Finding:** Strict string matching between the "recorded section" and the
  "rendered drops" (AC3 vs AC5) is highly susceptible to false negative
  mismatches due to harmless whitespace formatting. Parsed existing markdown
  heavily depends on how chunk boundaries (trailing blank lines, end-of-file vs
  end-of-section behavior) are extracted, while newly rendered drops might have
  different newline terminations.
  **Suggestion:** Normalize both strings (e.g. `.strip()` and normalizing
  internal multi-newlines) before performing the exact match comparison to
  prevent harmless file-formatting differences from triggering the AC5 refusal
  arm.

- **Category:** Risk / **Severity:** Low
  **Finding:** Mini-Plan step 4 specifies raising `AggregatorError` *inside* the
  lock upon refusal. If the locking mechanism does not gracefully handle
  exceptions (e.g. via a context manager `with lock:`), raising an error to exit
  the script could leave a dangling lock file.
  **Suggestion:** Verify that the file lock mechanism guarantees a lock release
  on raised exceptions, or catch/release/re-raise if the lock isn't managed via
  a Python context manager.

- **Category:** Edge-case / **Severity:** Low
  **Finding:** The spec notes AC10 protects trailing prose and the
  link-reference footer upon replacement. If the new rendered drops naturally
  generate a new link-reference footer, a blind "replace" could inadvertently
  duplicate the footer or orphan the old one depending on how the parsed
  bounding box is defined.
  **Suggestion:** Ensure the "rendered drops" comparison string excludes the
  footer if the parsed section also excludes it, so the match predicate only
  compares the actual bulleted content.

**Overall assessment:** This is a highly sound, defensive approach that safely
resolves a partial-write hazard without introducing race conditions or data
loss. The decision to deliberately refuse rather than attempt an unpredictable
text-merge is exactly the right call for automated release boundaries.

`SHIPWRIGHT_VERDICT: approve`

---

## openai — verdict: revise

1. **Category:** edge-case / **Severity:** high
   **Finding:** The action table omits the normal post-success re-run state: the
   target section exists but there are **no remaining drop files**. If the
   implementation renders an empty section and compares it to the existing
   recorded section, it will classify this as a mismatch and refuse. That makes
   a fully completed release non-idempotent on a later invocation. AC11's
   `unchanged` action strongly implies this state is intended, but it is not
   specified.
   **Suggestion:** Explicitly define: "one existing target section and an empty
   drop set" as `unchanged`, with no write, no unlink, and
   `changelog_updated=False`. Add an integration test for rerunning after a
   fully successful aggregation, as distinct from rerunning after
   write-before-unlink interruption.

2. **Category:** approach / **Severity:** medium
   **Finding:** "Exactly one section matches what the drops now render" is
   underspecified for a byte-sensitive user-authored file. The comparison must
   define handling for release dates, newline conventions, generated whitespace,
   and any stable heading formatting. In particular, if rendering supplies
   today's date, an interrupted run resumed on a later date could refuse despite
   otherwise identical release content.
   **Suggestion:** Make the comparison contract explicit: compare the exact
   generated section bytes, including heading/date/newlines, and ensure all
   generated fields are deterministic for the release invocation. If the tool
   currently derives a date at runtime, require it to be passed or persisted
   consistently. Test a resumed run across a changed clock date and CRLF/LF
   behavior where those formats are supported.

3. **Category:** approach / **Severity:** medium
   **Finding:** Reusing `insertion_index` alone does not guarantee that
   replacement uses the same structural interpretation. The aggregator also
   needs to identify all target-version headings and calculate the end of the
   owned section without independently reimplementing heading, footer, and
   boundary rules. Otherwise `_find_structural_insertion_line` is removed but
   its predicate logic reappears in a new target-section scanner, recreating the
   drift the extraction intends to eliminate.
   **Suggestion:** Have `shared/scripts/changelog_sections.py` expose a small
   structural API sufficient for both consumers — for example, parsed section
   spans/heading metadata plus insertion index. The aggregator should use those
   spans for target count, equality comparison, and splice boundaries. Add tests
   proving that trailing prose and link-reference footers are outside the
   replaced span.

4. **Category:** risk / **Severity:** medium
   **Finding:** The plan says a matching section is "replaced in place (a no-op
   on content)," while AC11 says `changelog_updated` means bytes were written.
   An unconditional `_atomic_write` of byte-identical content still changes file
   metadata and may replace mode/ownership behavior depending on
   `_atomic_write`, even though the content is unchanged. It also makes the
   distinction between `replaced` and `unchanged` unclear.
   **Suggestion:** Compute the prospective complete file before writing and skip
   `_atomic_write` when bytes are identical. Define result semantics precisely:
   use `replaced` only when a replacement changes file bytes; use `unchanged`
   for an existing identical section/no-drop re-run (and, if applicable, an
   identical pending-drop convergence). Ensure drop consumption can still occur
   when the changelog write is skipped.

5. **Category:** dependency / **Severity:** medium
   **Finding:** Moving the module changes an import and deployment boundary, not
   just a source path. The approach relies on `ensure_shared_cache` delivering
   the newly promoted module and on every direct import of the deleted
   plugin-local file being updated. Existing tests may pass in a repository
   checkout while runtime cache execution fails if the cache copy/include rules
   do not include the new top-level script.
   **Suggestion:** Search all repository imports and test references before
   deleting the local module. Add a runtime-layout import test that constructs
   the cache path and verifies the imported module's `__file__` is under the
   shared cache location. Confirm the shared-cache copy mechanism includes
   top-level `shared/scripts/*.py`, not only existing known files or
   subdirectories.

6. **Category:** edge-case / **Severity:** medium
   **Finding:** Dry-run behavior is ambiguous for refusal. AC8 requires it to
   report `refuse`, while AC5/AC7 describe refusal as an `AggregatorError` and
   non-zero CLI outcome. Without an explicit contract, dry-run could accidentally
   report a refusal as successful or raise without reporting the planned action.
   **Suggestion:** Specify and test dry-run refusal behavior explicitly: report
   the same refusal reason to stderr, return non-zero, perform no write or
   unlink, and do not return a misleading successful action result. Cover
   insert, replace, unchanged, single-section mismatch, and duplicate-section
   states in dry-run tests.

7. **Category:** security / **Severity:** low
   **Finding:** The plugin will import a bare module name after modifying
   `sys.path`. In a long-lived interpreter, an earlier `changelog_sections` entry
   in `sys.modules`, or an untrusted earlier search-path entry, could resolve a
   different module than the intended shared copy. This is principally a
   correctness risk in this application, but it is also avoidable code-loading
   ambiguity.
   **Suggestion:** Follow the established shared-module import pattern exactly,
   ensure the intended shared scripts directory is inserted ahead of competing
   paths before import, and add an import-origin assertion in the runtime-layout
   test. Avoid retaining compatibility aliases that could allow the deleted
   plugin-local module to shadow the shared implementation.

**Overall:** the core refusal-and-convergence design is sound and appropriately
avoids silent history loss. It needs clarification of the no-drop completed-rerun
state and a shared span-based parsing API before implementation, otherwise the
new idempotency logic can remain ambiguous or reintroduce predicate drift.

`SHIPWRIGHT_VERDICT: revise`
