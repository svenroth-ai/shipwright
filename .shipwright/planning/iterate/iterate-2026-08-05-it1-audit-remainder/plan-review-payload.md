# External plan review — iterate-2026-08-05-it1-audit-remainder

Provider: openrouter · mode: iterate · reviews_succeeded: 2 · degraded: false
Verdicts: **openai = revise**, **deepseek = approve**
Contradiction: not detected (`verdicts agree within one step`).

Reviewed: `2026-08-05-it1-audit-remainder.md` (spec) +
`2026-08-05-it1-audit-remainder-miniplan.md` (plan).

## openai — SHIPWRIGHT_VERDICT: revise

1. **edge-case / high** — Canonicalization can treat materially different JSON text as
   the same record when either document contains duplicate object keys. Python's
   `json.loads` silently retains only the final duplicate key, so
   `{"event":"append","id":"A","ts":"T1","ts":"T2"}` and
   `{"event":"append","id":"A","ts":"T2"}` produce the same parsed object and canonical
   form. Conflicts with AC-1, particularly given the acknowledged foreign producer.
   *Suggestion:* treat duplicate-key documents as non-canonicalizable and use raw-text
   membership for them, via an `object_pairs_hook` decode helper used consistently for
   both origin and outbox paths; add a regression test proving duplicate-key variants do
   not cross-match.

2. **edge-case / medium** — "Semantically equal serialization" is broader than
   `_canonical` guarantees. It handles key ordering, whitespace and escaped-vs-literal
   Unicode after parsing, but Python preserves numeric representation: `{"n":1}`
   canonicalizes differently from `{"n":1.0}`. A foreign producer re-emitting through a
   runtime with different number formatting could still leave status entries permanently
   buffered, contrary to the F27 intent. *Suggestion:* define the supported equivalence
   boundary explicitly in implementation and tests.

3. **risk / medium** — The planned tests exercise `parse_delivered` / `is_delivered`
   directly, but the behaviour at risk is the actual sweep decision under its lock. The
   change also alters the meaning of the first returned set while retaining tuple arity,
   making a call-site interpretation error easy to miss even if helper unit tests pass.
   *Suggestion:* add at least one focused end-to-end `sweep_outbox`/GC test per
   consequential direction — a same-id changed append remains in the outbox, and a
   canonically equivalent status line is removed.

4. **dependency / low** — The plan assumes `sweep_outbox.py` is the only consumer because
   tuple arity is unchanged. Internal callers, fixtures or scripts can still depend on the
   former "append IDs plus raw text" semantics without a signature change revealing the
   break. *Suggestion:* perform and record a repository-wide reference search for both
   helpers before changing semantics.

5. **security / low** — Canonical serialization adds a full sorted re-encoding of every
   parseable origin and outbox object while the sweep holds its canonical lock. Inputs
   include a known non-cooperating producer, so unusually large or deeply nested records
   can increase lock hold time. The assertion that `json.dumps` "cannot fail" is only safe
   while inputs remain ordinary JSON-derived values and within recursion limits.
   *Suggestion:* make canonicalization failure-safe — on serialization/recursion failure
   treat the line as raw-text-only membership, preserving "retain rather than drop".

> Overall, the core approach is sound: canonical record membership correctly addresses
> the id-only append loss and raw-text serialization drift, and mirroring the status guard
> with a twin-behavior test is appropriately narrow. The duplicate-key handling and a real
> sweep-path regression test should be resolved before merging because this change is
> specifically intended to prevent incorrect GC deletion.

## deepseek — SHIPWRIGHT_VERDICT: approve

1. **dependency / medium** — The plan assumes the caller only passes the id-set into
   `is_delivered` and never uses it directly. If existing code iterates over `append_ids`
   or does a membership test outside that function, replacing the id-set with a
   canonical-string set produces a silent logic error. *Suggestion:* grep `sweep_outbox.py`
   for any use of the returned set other than passing it to `is_delivered`.

2. **edge-case / low** — The AC-5 drift test compares `triage.read_all_items` and
   `triage_gc._resolve_tracked_only` on the same fixture, but `read_all_items` consumes an
   entire triage file, not an in-memory list. *Suggestion:* invoke each resolver the way it
   is called in production and verify the outcomes are identical.

3. **risk / low** — Switching from raw-text to canonical membership for all parseable
   lines will fail existing tests that relied on the old matching; hidden assumptions in
   integration suites could break unexpectedly. *Suggestion:* run the full `shared/tests/`
   suite early.

4. **approach / low** — `parse_delivered` returns `(canonical, text)` but its docstring
   still says `append_ids`; the semantic shift may confuse future maintainers.
   *Suggestion:* rewrite the docstring.

> Overall assessment: The approach is sound; it fixes the three reported issues with
> minimal code changes, keeps the direction of risk safe, and deliberately avoids
> refactoring that would obscure the behavioural diff.

## Disposition

All nine findings accepted and folded into the mini-plan's
"Revision after external plan review" section (R1–R5, DeepSeek-2/3/4), including the
precondition search for R4/DeepSeek-1 which **confirmed** `sweep_outbox.py:246,273` is the
only production consumer and forwards both sets without a direct membership test.

R3/R4 additionally surfaced **R6**, found by this run and not by either reviewer: two
existing tests in `test_sweep_outbox_review_cascade.py` pin the defect itself, using an
*added key* as their stand-in for "re-serialization" while the module docstring defines
FIX B as key-order/whitespace immunity. Their fixtures are corrected to the documented
intent and the missing AC-1 case is added.
