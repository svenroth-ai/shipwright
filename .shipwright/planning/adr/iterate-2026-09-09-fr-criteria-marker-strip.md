# ADR: Strip the minted [ACnn] marker in lib.fr_criteria, not in each of its nine readers

## Context

`lib.ac_identity.mint()` inserts a leading `[ACnn]` marker into a criterion
bullet's text. Nine downstream readers of `lib.fr_criteria` criterion text
(`fr_hygiene.py` and its siblings, `spec_parser.py`, `fr_criterion_shape.py`,
the layer-coverage detectors, `group_i_criteria.py`) treated that text as
marker-free prose. Two live effects follow:

- The cross-layer digest gate would see every minted criterion as changed
  (its digest includes the marker).
- A minted placeholder bullet (`TBD`-shaped) would stop collapsing to the
  bare-placeholder token set, because the marker survives the
  placeholder-normalization strip — blinding the TBD-age gate for that
  criterion.

Neither effect was active yet (minted criteria happened to start with a
recognized prefix; no placeholder bullet existed in the current `spec.md`),
but P3.4's doubt review (#689) flagged the risk as live rather than
deferred, and it sits directly under P3.6, so it had to close first.

## Decision

Strip the leading `[ACnn]` marker inside `lib.fr_criteria`'s own
text-extraction seam (`criteria_texts()`, in the new `lib._criteria_text`
module), gated by a `strip_ac_marker` kwarg (default `True`) threaded
through `block_criteria`/`criteria_for`/`has_criteria`/`leading_criteria`.
`lib.ac_identity.read()` is the one caller that must still see the marker,
so it is the only call site that passes `strip_ac_marker=False`. All nine
other readers get marker-free text with zero code changes of their own.

## Consequences

One seam fixes all nine consumers instead of teaching each one the
marker's shape; `mint()` stays free to write placeholder bullets later
without a fresh sweep of readers. The tradeoff is an added boolean
parameter threaded through four public `fr_criteria` functions and one new
small module (`lib._criteria_text.py`, split out of `fr_criteria.py` after
the added parameter and docstring crossed the 300-line bloat-baseline
guideline). Stripping is lenient by marker SHAPE (a non-canonical `[AC7]`
is stripped too) and applies only to a bullet's opening line, never a
continuation line, since `insert_marker` never splices `[ACnn]` onto a
continuation line and a wrapped criterion may legitimately reference
another AC by id mid-prose.

## Rejected alternative

Teaching each of the nine readers about the marker's shape individually —
rejected because it multiplies the surface that must be kept in sync with
any future change to the marker grammar, and because three of the nine
never call `fr_criteria` directly (they consume an upstream reader's
already-extracted output), making a per-caller fix incoherent for them.
