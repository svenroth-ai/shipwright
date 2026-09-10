"""THE KEYSTONE GATE's shared value type and its closed reason vocabulary.

Its own module purely to break a cycle: :mod:`_keystone_core` (the evaluator)
and :mod:`_keystone_layer_gap` (D10's predicate) both produce :class:`Finding`,
and the evaluator calls the predicate. A shared leaf module is the honest shape
for a value type two peers exchange — the alternative, a lazy import inside the
function, only defers *which* module binds and hides the dependency.

Re-exported from :mod:`_keystone_core`, which stays the one import site callers
and tests use.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Reason codes, closed vocabulary. A consumer (and p3.7, which reads `unbound`
#: and `removed_acs` out of the JSON) matches on these exact strings.
BINDING_REMOVED = "binding_removed"
FAILED = "failed"
SKIPPED = "skipped"
NOT_SELECTED = "not_selected"
UNBOUND = "unbound"
LAYER_GAP = "layer_gap"
UNMINTED_CHANGED = "unminted_changed"
NEW_FR_NO_CRITERIA = "new_fr_no_criteria"
READER_DIVERGENCE = "reader_divergence"


@dataclass(frozen=True)
class Finding:
    kind: str          # one of the reason codes above
    fr_id: str
    ac_id: str         # "" for FR-scoped findings (new_fr_no_criteria, reader_divergence)
    detail: str
    severity: str      # "hard" | "advisory"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "fr_id": self.fr_id, "ac_id": self.ac_id,
            "detail": self.detail, "severity": self.severity,
        }
