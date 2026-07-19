"""The one versioned requirement model (traceability Spec §11 / R5).

Frozen P1 contract for the requirement→test traceability campaign
(`2026-07-15-traceability-prerequisite`). This module is the **single**
requirement model that ``spec_parser``, the compliance ``rtm`` collector, the
future ``test_links`` collector, and Group D will all import — so the four never
re-parse an FR into divergent shapes (R5).

It is a *contract*, not a parser: a frozen dataclass, the closed vocabularies the
manifest schema pins (layers, statuses, provenance), and the two pure helpers that
build and split the manifest's namespaced requirement key. No spec files are read
here — collectors construct :class:`Requirement` instances from their own parse.

``MODEL_VERSION`` tracks the manifest ``schema_version`` (both are ``3``): a change
to this model's shape is a manifest schema bump.

**v3 — the namespace derives from the requirement id, not from the file path.**
``namespace`` used to be whatever the caller passed (in practice the spec's parent
DIRECTORY name, e.g. ``01-adopted``), so every manifest key was hostage to a
directory rename. It is now a read-only property computed from the id's group
digits (``FR-01.03`` -> ``01``), which no rename can move. The composite keys DO
change value (``01-adopted::FR-01.01`` -> ``01::FR-01.01``); the schema bump is
what announces that. Every requirement's INNER fields are untouched.

Consequence worth knowing: the key is now a pure function of the id, so two specs
declaring the same FR id no longer get distinct keys. That collision is a spec
defect, and the collector FAILS CLOSED on it — publishing a manifest that silently
dropped one of the two would conceal exactly the traceability gap it exists to show.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# The model version travels with the manifest schema_version — bump together.
MODEL_VERSION = 3

# ---------------------------------------------------------------------------
# Closed vocabularies (mirrored by traceability_schema.json — keep in sync)
# ---------------------------------------------------------------------------

Layer = Literal["unit", "integration", "e2e"]
LAYERS: tuple[Layer, ...] = ("unit", "integration", "e2e")

RequirementStatus = Literal["active", "removed"]
REQUIREMENT_STATUSES: tuple[RequirementStatus, ...] = ("active", "removed")

Priority = Literal["Must", "Should", "May"]
PRIORITIES: tuple[Priority, ...] = ("Must", "Should", "May")

# Where a requirement's required_layers came from. The three MUST NOT collapse to
# one default list: D-layer WARNs on a legacy-missing field but FAILs on a
# post-rollout omission (R4 provenance).
RequiredLayersSource = Literal["explicit", "inferred_legacy", "defaulted_legacy"]
REQUIRED_LAYERS_SOURCES: tuple[RequiredLayersSource, ...] = (
    "explicit",
    "inferred_legacy",
    "defaulted_legacy",
)

# The canonical machine token for a requirement id, two-digit.two-digit (D1).
# ``FR-01.03`` is canonical; ``FR-1.3`` / ``FR-7`` are not (the latter is a legal
# *spec heading* id but never a canonical manifest/tag id — see fr_tag_grammar).
CANONICAL_FR_RE = re.compile(r"^FR-\d{2}\.\d{2}$")

# The delimiter that namespaces a requirement key by its spec provenance.
KEY_DELIMITER = "::"


def is_canonical_fr(fr_id: str) -> bool:
    """True when ``fr_id`` is the canonical ``FR-XX.YY`` machine token."""
    return bool(CANONICAL_FR_RE.match(fr_id))


def is_layer(value: str) -> bool:
    """True when ``value`` names a known test layer."""
    return value in LAYERS


def namespace_for_id(fr_id: str) -> str:
    """The manifest-key namespace for ``fr_id`` — its GROUP digits (``FR-01.03`` -> ``01``).

    The slice is safe precisely because the line above pins the canonical shape
    ``FR-XX.YY``, so the group digits are always at ``[3:5]`` — deriving them from
    the already-frozen :data:`CANONICAL_FR_RE` rather than a second regex that
    could drift away from it.

    Raises ``ValueError`` on a non-canonical id. That is not a defensive nicety:
    a requirement whose id is not canonical has no derivable namespace, so a
    silent fallback would invent a key. Every production construction site parses
    ids through ``is_canonical_fr`` first, so this cannot fire on a parsed spec.
    """
    if not is_canonical_fr(fr_id):
        raise ValueError(
            f"cannot derive a namespace from non-canonical requirement id {fr_id!r} "
            "(expected the canonical FR-XX.YY machine token)"
        )
    return fr_id[3:5]


@dataclass(frozen=True)
class Requirement:
    """One functional requirement, in the shape every traceability consumer shares.

    ``spec_path`` is the full relative path to the ``spec.md`` the FR lives in —
    provenance, and the only field that tracks WHERE the requirement was found.
    The manifest key is ``namespace :: id`` (see :func:`namespaced_key`).

    ``namespace`` is deliberately a read-only PROPERTY, not a field (v3). As a
    field it was the caller's to choose, and every caller chose the spec's parent
    directory name — which is why a directory rename rewrote every manifest key.
    Deriving it makes that impossible to get wrong: there is no longer an argument
    a call site could pass a path into.
    """

    id: str                                       # "FR-01.03" (display / canonical)
    spec_path: str = ""                           # ".shipwright/planning/01-adopted/spec.md"
    title: str = ""
    priority: Priority = "Must"
    status: RequirementStatus = "active"
    required_layers: tuple[Layer, ...] = ()
    required_layers_source: RequiredLayersSource = "defaulted_legacy"

    @property
    def namespace(self) -> str:
        """The manifest-key namespace, derived from :attr:`id` (``FR-01.03`` -> ``01``)."""
        return namespace_for_id(self.id)

    @property
    def key(self) -> str:
        """The manifest requirement key: ``namespace :: id``."""
        return namespaced_key(self.namespace, self.id)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def namespaced_key(namespace: str, fr_id: str) -> str:
    """Build the manifest requirement key ``namespace::fr_id`` (v3: ``01::FR-01.03``)."""
    return f"{namespace}{KEY_DELIMITER}{fr_id}"


def key_for_id(fr_id: str) -> str:
    """The full v3 manifest key for ``fr_id`` — ``namespace_for_id(id) :: id``.

    The one helper a manifest CONSUMER should use to look a requirement up, so no
    consumer reconstructs the key from a directory name (which is what made the
    lookup path-fragile before v3).
    """
    return namespaced_key(namespace_for_id(fr_id), fr_id)


def split_namespaced_key(key: str) -> tuple[str, str]:
    """Inverse of :func:`namespaced_key` → ``(namespace, fr_id)``.

    Splits on the **last** delimiter so a namespace that itself contains ``::``
    (a full ``a/b::c`` path) still yields the trailing FR id intact.
    """
    namespace, _, fr_id = key.rpartition(KEY_DELIMITER)
    return namespace, fr_id


__all__ = [
    "MODEL_VERSION",
    "Layer",
    "LAYERS",
    "RequirementStatus",
    "REQUIREMENT_STATUSES",
    "Priority",
    "PRIORITIES",
    "RequiredLayersSource",
    "REQUIRED_LAYERS_SOURCES",
    "CANONICAL_FR_RE",
    "KEY_DELIMITER",
    "Requirement",
    "is_canonical_fr",
    "is_layer",
    "namespace_for_id",
    "namespaced_key",
    "key_for_id",
    "split_namespaced_key",
]
