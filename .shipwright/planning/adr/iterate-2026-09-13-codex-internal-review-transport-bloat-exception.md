# Bloat exception — review-record schema/CLI gain `transport`; transport module hardened after doubt-review

- **Status:** accepted
- **Date:** 2026-09-17
- **Re-Review-Date:** 2026-12-17
- **Incident Reference:** `iterate-2026-09-13-codex-internal-review-transport`

## Context

AC6 of this iterate requires every `reviews.json` row to be able to record
*which harness* answered a review pass — the default same-session Agent-tool
spawn, or the new `codex` transport (`review_via_codex.py`), plus an optional
`transport_note` explaining a codex-attempted-then-fell-back case. Both fields
have to be validated in the schema module and exposed as CLI flags on the tool
that writes rows, so the two natural homes are the existing
`shared/scripts/lib/review_record_schema.py` (entry validation, `TRANSPORTS`
vocabulary) and `shared/scripts/tools/record_review_pass.py` (the `record`
subcommand's argument parser and dispatch). Both were already grandfathered
above the 300-line limit. The additive fields raise
`review_record_schema.py` from 313 to 317 lines and `record_review_pass.py`
from 395 to 400 lines.

A second, later wave of growth on this same iterate came from its own
Stage-3 doubt-reviewer pass (2026-09-17), which surfaced two real correctness
bugs and several hardening gaps in the new transport itself: an empty
review-subject file (e.g. an all-new-file diff) could reach `codex exec` and
come back a schema-valid but meaningless PASS; a shared temp output path
across retry attempts could let a later, empty attempt read back an earlier
failed attempt's stale valid output; the Windows env allowlist had never
actually launched a real `codex exec` process and was missing `COMSPEC`/
`PATHEXT` (needed to resolve the `.cmd` shim `codex` typically is on
Windows) and `TMPDIR`; a committed symlink at the canonical output path
would let `write_text` write through it; and a codex-answered row's
`--transport codex` was never cross-checked against `--model-tier`, letting
a driver that (correctly, elsewhere) follows "every record carries
`--model-tier`" silently misrepresent which model answered. Fixing these
raised `shared/scripts/lib/codex_review_transport.py` from 298 to 334 lines,
`shared/scripts/tools/record_review_pass.py` further from 400 to 408 lines
(the `--transport codex` + `--model-tier` rejection), and
`shared/tests/test_codex_review_transport.py` from 291 to 331 lines (two new
regression tests proving each bug fix actually catches its bug, plus a
basename cross-module parity test).

A third wave came from this same iterate's own mandatory external
code-review cascade (GLM + OpenAI/Codex, 2026-09-17), which found the
`gpt-5.6-sol` binding's public `model=` override parameter on
`run_codex_review()` did not meet AC2's "must raise before any process is
launched" requirement (removed entirely — nothing called it), that three
local operations (role-schema load, `out_dir` creation, canonical-payload
write) could raise instead of returning the contracted `status: "error"`
(now wrapped), and that the env-scrub test only checked four named secrets
rather than the shape-based invariant AC3 requires (a new subset-of-allowlist
test added). This raised `codex_review_transport.py` further to 354 lines
and `test_codex_review_transport.py` further to 349 lines.

## Ousterhout Argument

All four files are deep. `review_record_schema.py`'s and `record_review_pass.py`'s
public surfaces are covered above. `codex_review_transport.py`'s public
surface is one function, `run_codex_review()`, returning a two-shape result
(`completed`/`error`); every fix in the second wave — fresh temp dir per
attempt, the symlink guard, the widened env allowlist — is internal retry
and I/O plumbing behind that one call, never a new export. Its paired test
file's surface is, by construction, the behavior of that same function;
adding regression tests for two newly-fixed bugs is exactly what keeps a
deep module's internals honest without widening what a caller sees.

## YAGNI Check

`transport`/`transport_note` are covered above. The second wave's additions
are the opposite of speculative: each line traces to a specific doubt-review
finding on an already-shipped-this-iterate module (empty-subject rejection,
fresh-per-attempt temp dir, three named env vars, one symlink check, one
CLI-argument conflict check), not a forward-looking capability. No retry
count, transport value, or schema field beyond what those findings required
was added.

## Chesterton-Fence Check

`review_record_schema.py`/`record_review_pass.py` are covered above.
`codex_review_transport.py`'s existing structure — one role-agnostic
`run_codex_review()` handling every review role's subprocess dispatch,
validation, and retry — is load-bearing for the same reason: the bugs the
doubt-review pass found (stale temp file across attempts, an unguarded
symlink write) are precisely the kind of defect that a shared, single
implementation makes fixable once for every role, instead of once per a
hypothetical per-role copy. Splitting the module now, mid-hardening, would
scatter the very invariants (fresh temp dir per attempt, validate-then-copy)
this ADR's fixes just centralized.

## Decision

Set `shared/scripts/lib/review_record_schema.py` to `state: exception`,
`current: 317`; `shared/scripts/tools/record_review_pass.py` to
`state: exception`, `current: 408`; `shared/scripts/lib/codex_review_transport.py`
to `state: exception`, `current: 354`; and
`shared/tests/test_codex_review_transport.py` to `state: exception`,
`current: 349` — all four referencing this ADR pending release numbering.
Re-evaluate by 2026-12-17 whether the review-record schema/CLI warrant a
dedicated `transport`-handling submodule, and whether
`codex_review_transport.py` warrants splitting subprocess dispatch from
prompt-building, once a second transport or a second hardening wave lands.

## Consequences

The anti-ratchet gate accepts these exact sizes for this commit but blocks
any further growth on any of the four files unless separately justified.
Every existing and future caller of `record_review_pass.py record` gains two
new optional flags (`--transport`, `--transport-note`) plus a new rejection
(`--transport codex` with `--model-tier` set); no existing call site's
behavior changes since both new fields default to `None`/absent. Every
caller of `run_codex_review()` now gets a fresh temp directory per retry
attempt (previously shared across attempts) and a wider, still-secret-free
env allowlist — both are pure hardening with no observable behavior change
on a successful single-attempt run, which is what every existing test and
the shipped default (`max_retries=0`) already exercises.

## Rejected alternatives

- Raise the baseline `current` value directly on the existing
  `state: "grandfathered"` entries, without an ADR — rejected: per
  established convention (`shared/scripts/lib/anti_ratchet.py`'s
  `measured > entry.current` rule and this repo's own precedent, e.g. the
  `shared/tests/test_record_event.py` entry bumped only under its existing
  `ADR-092` exception, and every other deliberate size increase in
  `shipwright_bloat_baseline.json` carrying an `exception` state), a bump
  without an ADR is exactly the gaming the anti-ratchet exists to prevent —
  the growth needed a recorded, reviewable justification instead.
- Extract `transport`/`transport_note` handling into a new
  `lib/review_transport_fields.py` + CLI helper — rejected: two fields and
  four lines of argparse wiring do not meet the "genuinely substantial
  implementation behind a narrow interface" bar the Ousterhout argument
  requires; the split would add a new intra-package import with no second
  consumer, purely to dodge the line count.
- Compress the added code onto fewer lines to stay under the pre-existing
  `current` value — rejected in a prior round of this iterate: it produced
  one-liner `if`/inline-conditional constructs that degraded readability for
  no correctness benefit, and was reverted in favor of clean multi-line code
  plus this documented exception.

---

## External Sources Acknowledged

This decision applies the repository's bloat-exception template. Its YAGNI
Check and Chesterton-Fence Check headings are adapted from the sources named
in `.shipwright/planning/adr/_template-bloat-exception.md`.
