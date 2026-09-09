# Iterate directive: iterate-2026-09-09-fr-criteria-marker-strip

Nine downstream consumers of `lib.fr_criteria` criterion text (fr_hygiene.py
and siblings, spec_parser.py, fr_criterion_shape.py, layer-coverage
detectors) treat criterion text as marker-free. `lib.ac_identity` mints a
`[ACnn]` marker onto criterion bullets. Two effects: (1) a digest gate keyed
to criterion-text changes sees every minted criterion as changed; (2) a
minted placeholder bullet (TBD-shaped) stops collapsing to the bare-
placeholder token set, blinding the placeholder-detection gate for that
criterion.

Resolution: make `lib.fr_criteria` strip the `[ACnn]` marker before any
consumer reads criterion text — fixing all nine consumers at one seam
instead of teaching each one about the marker — rather than the narrower
alternative of making `mint()` skip placeholder bullets. `ac_identity.read()`
must keep seeing the marker (it parses it into an id), so it opts out of the
new default.

Verify, do not assume, that the nine consumers are still nine.
