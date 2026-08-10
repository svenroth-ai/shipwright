# F11 pre-push verification of the integrated tree

P2.39 closes the gap between F0's early working-tree check and the commit CI
actually judges. F11 now runs the marked local CI-gate mirror after successful
integration/regeneration and before its initial push; delivery refresh repeats the
same check before its own push. The late STOP is intentional: a new workflow gate
or allowlist brought in by main must block delivery even after the work commit exists.

Keeping F0 retains fast common-case feedback. Replacing it with only F11 would move
ordinary local failures behind the full suite and finalization, while failing to cover
the delivery-refresh push would retain the original tail under a different caller.
