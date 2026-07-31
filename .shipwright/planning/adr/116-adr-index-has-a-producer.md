# ADR 116 — A derived view needs a producer on the path that changes it

- Run-ID: `iterate-2026-07-31-adr-index-producer`
- Spec: `.shipwright/planning/iterate/iterate-2026-07-31-adr-index-producer.md`

## Context

`.shipwright/planning/adr/INDEX.md` is a committed derived view of the ADR spec
folder. `aggregate_decisions.aggregate()` called `rebuild_adr_index()` from
inside its `if rendered and not dry_run:` branch, which only runs when the
folded drop list is non-empty — and two earlier guards return before the lock is
taken at all. So the index was refreshed *only* as a side-effect of a release
pass that happened to have drops to fold.

An ADR that an iterate writes straight into the folder therefore never reached
the index. Measured here on 2026-07-31: 39 files on disk, 29 listed, 10 unlisted
(106–115). The same gap was measured independently in webui (ADR-133 listed,
134–138 unlisted) and repaired target-side in PR #334.

## Decision

Give the view a producer on the path that changes it, and give the generator a
title source it can actually read.

- The render moves to `shared/scripts/lib/adr_index.py` as a pure
  `render_adr_index(folder) -> str` plus a writing `rebuild_adr_index(root)`.
  `aggregate_decisions` re-exports the writer, so consumer repos that already
  import it from there keep working.
- **Iterate F3 refreshes the index**, so the row ships in the same commit as the
  ADR file that caused it. F6 stages `.shipwright/planning/adr/` whenever dirty.
- The release pass refreshes on every non-dry-run call, drops or not.
- **A row's label is the ADR file's own first `#` heading**, not the filename
  slug.
- A drift guard fails loudly when the committed index is not byte-equal to the
  render.

## Rationale

The label decision is the load-bearing half. The generator derived labels purely
from the filename slug, so it structurally could not emit `TT6` (filenames are
lowercase) and could not preserve wording a human added. Two rows had been
hand-polished *despite* the file's own "do not edit by hand" header. Making the
generator run more often without fixing its label source would have silently
downgraded those rows on the first pass, someone would have fixed them again,
and the cycle would repeat — a stale-index problem converted into a
wording-destruction treadmill. Reading the heading gives the generator a real
source, makes "do not edit by hand" true, and cost no migration: all 39 files
already carried one.

## Consequences

The index is now regenerated on a **branch** rather than only on main at release
time. That is what makes the row travel with its ADR, and it is safe because the
view derives from the folder listing, which on a branch is correct and complete.
It does create a new merge-conflict class for two parallel ADR-writing iterates;
`INDEX.md` is in no merge-reconciliation register, so `ensure_current` aborts
loudly rather than corrupting. Filed as **trg-1acb5304**.

Adopted repos inherit the new labels on their next refresh. The regeneration
command carries an unresolved `{shared_root}` placeholder because it is rendered
into every adopted repo's committed header and those repos have no `shared/`.

## Rejected alternatives

- **Registering `INDEX.md` in `DERIVED_SNAPSHOTS`.** That list is for views that
  are conflict-generating *and wrong when derived on a branch*. The second
  reason does not hold for a folder listing, and registering it would strip the
  index row out of the very commit that adds the ADR — the opposite of the fix.
- **Moving the call site alone** (out of the `if valid:` branch, no label
  change). Actively harmful without the label decision, for the reason above.
- **Front-matter as the title source.** Would require touching all 39 files to
  add a field; the `#` heading is already there and is already the human title.
- **Renaming ADR files so the slug-derived label reads correctly.** Breaks every
  existing link.
