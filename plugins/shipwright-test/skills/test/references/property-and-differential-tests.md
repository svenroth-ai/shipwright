# Property-Based and Differential Tests

Two test shapes for code where hand-picked examples share the author's blind spots. Both run
as ordinary unit tests (Step 1) — no extra layer, no extra runner.

## Property-based tests

State something that must hold for **every** input, and let a library generate hundreds of
inputs that try to break it. Tools: Hypothesis (Python), fast-check (JS/TS), proptest (Rust).

| Property | Use it for | Example |
|---|---|---|
| Round-trip | parsers, serializers, JSONL ledgers, config writers | `parse(render(x)) == x` |
| Invariant | counters, balances, ordered logs | an append never shortens the ledger |
| Idempotency | migrations, normalisers, retries, "ensure current" helpers | running it twice equals running it once |
| Equivalence | optimised or rewritten code | fast path returns what the naive path returns |

Rules:
- Add one when the code **parses, serializes, hashes or must be safe to run twice** — not for
  every function. Three example tests beat a property nobody can state.
- Add the property library (hypothesis, fast-check, ...) as a dev dependency only to the package that uses it.
- A failing example is a finding: pin it as a plain regression test, then fix the code. Never
  narrow the generator to dodge it.
- Keep it fast and reproducible: bounded `max_examples`, no clock, network or shared state, and
  a fixed seed or derandomized run in CI (Hypothesis `derandomize=True`, fast-check `seed`) so a
  failure comes back on the next run (see the flaky-test rule in `shared/constitution.md`).

## Differential tests

For a refactor or migration, the old implementation is the oracle.

1. Run old and new on the same inputs — generated, or sampled from real data.
2. Normalise differences that do not matter (whitespace, key order, timestamps).
3. Every remaining difference is a bug or an intended change. Intended changes go on a
   short **approved-differences list** in the test, each with its reason.
4. Delete the old implementation and the comparison only once every remaining difference is
   fixed or on the approved-differences list.

Use it when a rewrite must preserve behaviour and no spec is complete enough to test against.
