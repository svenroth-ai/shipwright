# ADR 118 — A view the branch carries needs a merge register, not a snapshot register

- Run-ID: `iterate-2026-07-31-adr-index-churn-register`
- Spec: `.shipwright/planning/iterate/iterate-2026-07-31-adr-index-churn-register.md`
- Follows: ADR-116 (which created the conflict class), trg-1acb5304

## Context

ADR-116 gave `.shipwright/planning/adr/INDEX.md` a producer at iterate F3 so the
index row ships in the same commit as the ADR it points at. That was the right
call, and it has a cost: before it, the index changed only on `main` at release
time and a branch never touched it, so two iterates could not collide on it. Now
two branches each appending a row conflict at the same anchor.

`INDEX.md` was in no merge-reconciliation register, so `classify()` put it in
`blocking` and `ensure_current` aborted, touching nothing. Safe and loud — but it
needs a human, and the whole point of the resolver is that generated artifacts
should not.

## Decision

Register the index in `CHURN_ALLOWLIST` and re-derive it from the **merged**
folder listing in `integrate_regenerate.regenerate_after_merge`.

Three placement decisions, each of which had a plausible wrong answer:

- **`CHURN_ALLOWLIST`, not `DERIVED_SNAPSHOTS`.** The two registers answer
  different questions. `DERIVED_SNAPSHOTS` is "what must not ship on a branch,
  because it is *wrong* when derived there"; `CHURN_ALLOWLIST` is "what the
  resolver may auto-resolve *when a conflict happens*". A folder listing derived
  on a branch is correct, so only the second applies.
- **Not `merge=union`.** Union would concatenate two sorted lists into an
  unsorted one with a duplicated header. The index is a pure re-derive, so
  regenerating is both simpler and always right.
- **In `regenerate_after_merge`, not `regenerate_tracked_snapshots`.** The latter
  is scoped by `only`, and its real caller passes `only=set()` — deliberately,
  because an iterate branch no longer carries the derived snapshots. Anything
  gated there would never run on the one path that matters, while every
  `only=None` unit test kept passing. Placing the call outside that function
  removes the trap instead of documenting it, and putting it after both
  `restore_derived_to_head` and the `regenerate_failed` rollback makes two
  invariants true by construction rather than by comment.

## Consequences

A merge conflict on the index auto-resolves: mainline's copy is taken as a
placeholder, then the index is re-derived from the merged folder, which by then
holds both sides' ADR files. Proven end-to-end on real git against the actual
`integrate_main.integrate`.

Registering the path also makes `is_derived_churn` true for it, so the F11
no-silent-revert check stops comparing it line by line. That is correct for a
wholesale-regenerated file, and in this repo the byte-exact drift guard
(`test_committed_index_is_not_stale`) is the more precise detector. **In an
adopted repo that guard does not ship**, so there the fail-soft refresh plus the
recorded step are the only signal.

The refresh is fail-soft: the merge commit has already landed, so raising would
strand it over a transient lock without undoing anything. Failure is recorded as
a `steps` entry the caller returns *and* printed to stderr.

**Be precise about what that buys, because it is less than it sounds.** No gate
reads those step tokens today: F11 invokes `ensure_current.py` and branches only
on its exit code, and all three failure branches still return `status: "ok"` →
exit 0. So the tokens are available to a future reader and visible in the run's
JSON, but the signal an operator actually sees is the stderr line. In this repo
the real backstop is CI's byte-exact drift guard; in an adopted repo, which does
not get that guard, the stderr line is genuinely the only signal. Making a gate
read the tokens is a reasonable follow-up; claiming they already gate anything
would be false.

The manual `resolve_churn_conflicts.py --mode regenerate` escape hatch does not
refresh the index — only the integration path does. That is the path the conflict
class occurs on; the manual case uses `rebuild_adr_index.py --project-root .`.

## Rejected alternatives

- **Adding it to `DERIVED_SNAPSHOTS`** — would strip the index row out of the very
  commit that adds the ADR, undoing ADR-116.
- **`merge=union` in `.gitattributes`** — produces an unsorted list with a
  duplicated header.
- **Failing the integration on a refresh error** — the merge has already landed,
  so it strands a branch without undoing anything; the drift guard and the
  recorded step are proportionate.
