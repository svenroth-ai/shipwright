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

``MODEL_VERSION`` tracks the manifest ``schema_version`` (both are ``2``): a change
to this model's shape is a manifest schema bump.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# The model version travels with the manifest schema_version — bump together.
MODEL_VERSION = 2

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


@dataclass(frozen=True)
class Requirement:
    """One functional requirement, in the shape every traceability consumer shares.

    ``namespace`` is the manifest-key namespace (the spec's *split* id, e.g.
    ``01-adopted``) so two splits can each own an ``FR-01.03`` without collision;
    ``spec_path`` is the full relative path to the ``spec.md`` the FR lives in.
    The manifest key is ``namespace :: id`` (see :func:`namespaced_key`).
    """

    id: str                                       # "FR-01.03" (display / canonical)
    namespace: str                                # "01-adopted" (manifest-key namespace)
    spec_path: str = ""                           # ".shipwright/planning/01-adopted/spec.md"
    title: str = ""
    priority: Priority = "Must"
    status: RequirementStatus = "active"
    required_layers: tuple[Layer, ...] = ()
    required_layers_source: RequiredLayersSource = "defaulted_legacy"

    @property
    def key(self) -> str:
        """The manifest requirement key: ``namespace :: id``."""
        return namespaced_key(self.namespace, self.id)

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def namespaced_key(namespace: str, fr_id: str) -> str:
    """Build the manifest requirement key ``namespace::fr_id``.

    The manifest keys requirements by ``spec-provenance :: FR-id`` so the same
    display id in two splits stays distinct (Spec §11 ``01-adopted::FR-01.03``).
    """
    return f"{namespace}{KEY_DELIMITER}{fr_id}"


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
    "namespaced_key",
    "split_namespaced_key",
]
