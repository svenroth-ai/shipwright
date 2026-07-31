# Mini-Plan — IT-1 / S2: `expected_status` under the lock

Companion to `2026-07-31-it1-s2-expected-status.md`.

## Chosen approach — refuse the write inside the lock that already exists

`mark_status` already opens exactly one critical section, and it already reads
both stores inside it to derive residence. The precondition belongs in that same
section, between the residence probe and the append, because that is the only
window in which the item's status is actually owned by this process.

```
with _load_file_lock_cls()(_lock_path(project_root)):        # unchanged
    tracked_ids = _append_ids_at(...)                        # unchanged
    outbox_ids  = _append_ids_at(...)                        # unchanged
    if item_id not in tracked_ids and item_id not in outbox_ids: raise KeyError
    previous = <resolved status of item_id>                  # NEW — union read
    if expected_status is not None and previous not in expected:
        raise StatusPreconditionError(item_id, expected, previous)   # NEW
    to_outbox = ...                                          # unchanged
    _append_line(...)                                        # unchanged
return previous                                              # NEW
```

The resolved status comes from `read_all_items(project_root)` called inside the
lock. That is not a new pattern: `append_triage_item_idempotent` already runs its
whole dedup scan through `read_all_items` inside this same lock, for the same
reason. Cost is one extra pass over a ~1000-line file, under a lock we hold for
an `fsync` anyway.

### Why an exception and not a falsy return

A returned `False` is droppable, and every existing caller would drop it — they
all do `resolved += 1` unconditionally on the next line. The defect being fixed
*is* "reported success without writing"; a fix whose failure signal can be
ignored by writing no code reintroduces it for the next caller. An exception
cannot be ignored by omission. `StatusPreconditionError` subclasses `ValueError`
so the existing `except Exception` handlers in the background producers keep
catching it and the CLI's existing `except ValueError → exit 2` keeps its
contract.

### Steps

1. **RED** — new test file `shared/tests/test_triage_expected_status.py`. Each
   test names the production line it must execute and fails without the change.
2. `triage.py`: `StatusPreconditionError`, the `expected_status` parameter, the
   in-lock check, the `previous` return. Docstring records what is and is not
   protected.
3. Nine automatic sites → `expected_status="triage"` + count a miss as *kept*.
   In `github_triage/resolve.py` the three sites collapse into one small helper
   rather than three copies of the same handler.
4. Two operator-CLI sites → pass the precondition; map
   `StatusPreconditionError` back to the CLI's existing `ValueError` wording so
   exit codes and messages do not move.
5. Integration test (AC-6) — the drift-hook / operator interleaving.
6. Round-trip probe (AC-7) — including the byte-identity assertion on refusal.
7. Six baseline bumps, measured, in the same commit.

## Alternative considered — resolve by writer authority, not by refusal

Give status events a `writerClass` (`human` | `automatic`) and teach
`read_all_items` Pass 2 to let a human event outrank a later automatic one.

**Rejected.** Three reasons, in order of weight:

1. It leaves the bad event **in the log**. The store is the audit record; an
   automatic `dismissed` event that the reader has decided to ignore still reads
   as a decision to anyone who greps the file, to the WebUI's own TypeScript
   reader, and to any future consumer that does not implement the same
   precedence rule. Refusal means the event never exists.
2. It changes the resolver's contract for **every** reader, cross-repo. Pass 2's
   ordering is pinned by two external-review findings and by the outbox/tracked
   union; adding a precedence axis on top of `(ts, file-order)` is a change to
   the shared output contract, which is the S3 conversation, not this one.
3. It does not fix the second half of the card at all — the caller would still
   be told the write succeeded, because it did succeed; it just would not win.

A third option, "lock across the resolver's whole read-filter-flip loop", was
rejected because it holds the store's one canonical lock across an unbounded
loop that includes network-fed producers, which is how the sweep's 120-second
commit window became a data-loss window in S1.

## What could go wrong

| Risk | Handling |
|---|---|
| A background producer now leaves items open that it used to close, and nobody notices | The miss is reported as *kept* through one shared shape carrying the item id, the actual status and the expected one — on each producer's existing diagnostic channel (stderr for the hook/plugin producers, stdout for `accepted_risks_converge`, whose whole report is stdout). Visible, and distinguishable from a failure |
| `except Exception` in a producer swallows the new error and mislabels it as a crash | Each site gets an explicit `StatusPreconditionError` arm ahead of its generic handler |
| The extra in-lock read slows a hot path | It is one pass over a file already read twice in the same section; measured, not assumed, in the probes |
| Six baseline bumps collide with a concurrent PR | Line positions compared against `origin/main` before the arm (board Runde 4: only entries ≲6 lines apart collide) |
