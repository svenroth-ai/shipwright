# ADR-124: Bloat exception — `update_build_dashboard.py` raised to 531-LOC, `test_build_dashboard.py` raised to 632-LOC

- **Status:** accepted
- **Date:** 2026-08-05
- **Re-Review-Date:** 2026-11-05
- **Incident Reference:** iterate `iterate-2026-08-05-f5b-dashboard-webui-unit-shape`,
  card `trg-3e49151c` (moved from shipwright-webui `trg-cb7d4938`). F5b
  build-dashboard regeneration crashed on WebUI iterates with
  `AttributeError: 'str' object has no attribute 'get'` because
  `_test_status_from_iterate` assumed every `iterate_latest` layer
  (`unit`/`integration`/`pgtap`/`e2e`/`smoke`) was always the structured
  `{status, passed, total}` mapping F5.md documents, while WebUI's
  historical F5 evidence producer (a separate repo, out of scope here)
  writes a pre-rendered human-readable string for the same keys.

## Context

`shared/scripts/tools/update_build_dashboard.py` already carries a bloat
exception (ADR-111, raised to 498 for the `tests.skipped` call-site
wiring). This iterate raises it again, to 531 (+33 net — three helper
functions added, one duplication removed during code review), to add
tolerant-shape handling: `_single_line_cell`, `_layer_display`,
`_smoke_display` branch on `isinstance(layer, dict)` vs
`isinstance(layer, str)` and replace five inline `.get()` call sites that
could not survive a string input. `shared/scripts/tests/test_build_dashboard.py`
(previously grandfathered at 488, no exception) crosses its ceiling to 632
(+144) from nine new regression cases covering the string shape across
all total-bearing layers, the smoke-only status shape, whitespace/newline
collapse, pipe- and backslash-character escaping, blank-string omission,
mixed shape-per-key blocks, and an explicit-`null` layer — the last two
(backslash escaping, +15) closed a gap the external code-review cascade
found after the first version of this ADR was written.

## Ousterhout Argument

`update_build_dashboard.py` remains the deep renderer ADR-111 already
argued for: one public entrypoint (`generate_dashboard`) behind
event-mode and config-mode table generation, now with one additional
narrow concern — tolerating a second documented `iterate_latest` layer
shape at the single call site that reads it. The three new helpers are
private (`_`-prefixed), each under 15 lines, and exist only to keep
`_test_status_from_iterate` from repeating the same `isinstance` branch
five times inline; splitting them into a separate module would export
internals (the exact per-layer label/key pairing, the whitespace/escaping
policy) that have no reason to be public or reused elsewhere in the repo —
nothing else renders this specific `iterate_latest` shape.

`test_build_dashboard.py` is a test file: the honest comparison (per
ADR-121's own framing for `test_triage_schema.py`) is not against 300
lines but against shipping a producer/consumer shape-tolerance change
with no regression coverage for the shape it was written to tolerate.
Each new case pins one distinct behavior named in the iterate spec's
Test Completeness Ledger (`.shipwright/planning/iterate/iterate-2026-08-05-f5b-dashboard-webui-unit-shape.md`)
— none are incidental padding.

## YAGNI Check

- **`isinstance(dict)` branch, unchanged formatting** — needed today; this
  is the existing, already-shipped mapping contract (F5.md) and must keep
  rendering byte-identically (verified by the pre-existing 9-case suite
  passing unmodified).
- **`isinstance(str)` branch** — needed today; this is the reported crash's
  exact fix, not speculative future-proofing.
- **Whitespace/newline collapse (`_single_line_cell`)** — needed today; a
  raw multi-line string would silently corrupt the single-line `Test
  Status` row's markdown structure. Found by the first external-review
  round, not spec-original, but load-bearing once the string shape is
  accepted at all.
- **Pipe-character escaping via the existing shared `escape_cell`** —
  needed today; `markdown_table.py`'s own docstring documents this exact
  failure mode ("Empirically observed in the shipwright-webui repo") for
  a different table in this same file. Reusing the existing helper (no
  new escaping logic invented) is the smaller addition, not the larger
  one.
- **Explicit `None`-layer tolerance** — already free (the `isinstance`
  branches fall through to `None` for any non-dict, non-str value without
  extra code); the new test only proves it, it added zero implementation
  lines.
- **Refused as speculative:** parsing/normalizing the string content
  itself (e.g. extracting `passed`/`total` numbers via regex) — no format
  is documented anywhere reachable from this repo for the WebUI string
  shape (confirmed by search before writing the fix), so any parser would
  be guessing at a contract that does not exist. Treating the string as
  opaque, already-formatted display text is correct for whatever the
  WebUI producer actually emits, and needs no maintenance when that
  producer's wording changes.

## Chesterton-Fence Check

`update_build_dashboard.py`'s 498-line fence (ADR-111) stands for a
documented reason: it is a deep renderer whose skip-arithmetic was
already extracted to a shared SSOT (`tests_block.py`), leaving only
irreducible call-site residue behind the ceiling. That reason still
holds — this change adds a second call-site residual (shape tolerance)
behind the same narrow interface, it does not reintroduce logic that
was previously extracted.

`test_build_dashboard.py`'s 488-line grandfathered size has no prior ADR
— git history shows it growing one `TestEventTestStatus`/`TestFrColumnFallback`-style
class at a time as the renderer itself grew features (skip-suffix
tracking, run-id embedding, FR-column fallback, intent normalization).
There is no documented fence to tear down; this change continues the
same pattern (one more focused test class addition) rather than working
around an unexplained boundary.

## Decision

New `current` values: `update_build_dashboard.py` → 531 (was 498, ADR-111
lineage continues under this ADR); `test_build_dashboard.py` → 632 (was
488, newly moved from `grandfathered` to `exception` under this ADR since
it now has a recorded reason rather than an unexplained number).
Re-Review-Date 2026-11-05 — by then, if `update_build_dashboard.py` has
accumulated further per-feature residue past this ceiling, evaluate
whether the event-mode and config-mode table generators (currently both
behind `generate_dashboard`) are due to split into their own modules,
which ADR-111 already flagged as the eventual retirement path.

## Consequences

No downstream consumer contract changes — `generate_dashboard`'s output
shape and the `iterate_latest` JSON shape are both unchanged; only the
renderer's tolerance for an already-existing second shape improved.
Future contributors to either file inherit the new ceiling; a further
crossing without justification is blocked by the anti-ratchet hook as
before. If the exception holds past Re-Review-Date without a split, the
next reviewer re-argues Ousterhout rather than silently re-dating.

## Rejected alternatives

- **Just leave the ceiling at 498/300 and split the files now** — rejected:
  splitting `_test_status_from_iterate`'s three new helpers into a
  separate module would export internals with no other caller, adding
  indirection for a ~36-line addition; splitting the test file's
  `TestEventTestStatus` class would separate the new WebUI-shape cases
  from the pre-existing mapping-shape cases they are directly protecting
  against regressing.
- **Shallow refactor — extract the layer-rendering logic to a new shared
  module first, then add the fix there** — rejected: nothing else in the
  repo renders this `iterate_latest` shape, so "shared" would be
  speculative; ADR-111 already extracted the one piece of genuinely
  shared logic (`tests_block.py`) that had a second consumer.
- **Delete/skip the new test coverage to stay under the old ceiling** —
  rejected: this is exactly the "ship the shape-tolerance change with no
  regression coverage for the shape" trade the Ousterhout argument above
  already rejects; the Test Completeness Ledger in the iterate spec would
  fail the F11 gate with untested-testable behaviors.
