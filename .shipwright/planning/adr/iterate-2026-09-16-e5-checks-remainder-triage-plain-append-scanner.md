# ADR: AST meta-test gate for the plain `append_triage_item` producer contract

**Run:** `iterate-2026-09-16-e5-checks-remainder`
**Section:** FR-01.14 row #1 (triage producer contract),
`.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`

## Context

FR-01.14 row #1 named a mechanisable oracle ("a meta-test over the call
sites") but had no gate: any new producer could call the plain,
non-deduplicating `append_triage_item` and write duplicates freely, with no
test to catch it. The idempotent path (`append_triage_item_idempotent`) was
opt-in discipline only — followed everywhere it mattered, but nothing made
it hold.

## Decision

Built three files:

- `shared/scripts/lib/triage_plain_append_scan.py` — the AST scanner
  (`find_plain_append_callers`, `find_unparseable_files`), repo-wide, with
  a documented, empirically-checked set of accepted detection limits.
- `shared/scripts/lib/triage_plain_append_scope.py` — a real lexical
  scope-chain resolver with Python-accurate shadowing (parameters,
  reassignments, comprehension scopes, `import` vs `from ... import`),
  split out once the scanner file crossed 300 lines.
- `shared/tests/test_triage_append_producer_registry.py` — the allowlist
  (`ALLOWED_PLAIN_APPEND_CALLERS`) plus the reverse-drift guard against the
  live repo, mirroring the existing `test_triage_precondition_registry.py`
  pattern already established for the sibling `mark_status` concern.

`find_plain_append_callers` scans the whole repo (not just two known
trees); a call site not on the allowlist fails the registry test by name.
The only registered exception is `shared/scripts/tools/triage_add.py`, the
manual operator CLI.

## Consequences

A tenth automated producer calling the plain append instead of
`append_triage_item_idempotent` now fails CI loudly instead of silently
duplicating triage entries.

Ten rounds of external code/plan review (external LLM, both GLM via
openrouter and openai via codex) found and fixed a cascading sequence of
real name-resolution bugs in the scanner: an initial two-directory scope
that was "accidentally true, not structurally guaranteed" (widened to
repo-wide); several same-name false-positive shapes (aliased imports, star
imports, unrelated modules/objects sharing a name); then, across rounds
5-9, a sequence of scope-resolution defects — an unscoped walk letting a
function-local import taint an unrelated function's parameter; a
module-scope-only fix hiding an ordinary function-local import from a call
in its own function; nesting without real Python shadowing; shadowing
without order-independent same-scope precedence for a reassigned name; a
comprehension-scope miss; a relative-import `level` miss — each fixed with
an accompanying regression test, converging on a genuine lexical
scope-chain resolver. Round 10 (GLM) approved with only low-severity,
narrow documentation suggestions.

Remaining known, accepted gaps (each empirically checked against the live
tree, not assumed, and either positively pinned by a test or documented in
the module's own docstring):

- Package-qualified or relative imports of the `triage` module itself
  (`from shared.scripts import triage`, `from shared.scripts.triage import
  append_triage_item`, etc.) — no real producer in this repo's history has
  ever used this form.
- A call reached through `getattr` or a stored/indirect reference.
- `global`/`nonlocal` declarations, and a `def`'s decorators/defaults/
  annotations evaluated in the wrong (function, not enclosing) scope.
- A directory-name-based exclusion list (`EXCLUDED_PARTS`), not
  content-verified per file.
- Two narrow scope-engine quirks (a same-scope reassignment's execution
  order, and a walrus target inside a comprehension binding to the
  comprehension's own scope rather than its enclosing scope).

## Rationale

The row's own oracle named exactly this mechanism. The registry-plus-
reverse-guard shape already has one precedent in this repo
(`test_triage_precondition_registry.py`), so this reuses an established
pattern rather than inventing a new one.

## Rejected alternatives

- **Full symbolic-execution/type-checker-grade import resolution** —
  rejected as the over-engineering the campaign's own D7 abort condition
  warns against; no real producer in this repo's history has ever used a
  package-qualified or indirect-call form, checked empirically via
  repo-wide grep before accepting the gap.
- **Changing `triage_add.py`'s own concurrency behavior** (e.g. requiring
  a `dedup_key` on every hand-typed card) — rejected as out of scope for a
  checks-only sub-iterate. It is a human-driven CLI, not a background
  producer racing another instance of itself; forcing a dedup key onto a
  single, individually-decided human action would be a product/API change
  this sub-iterate does not own.
