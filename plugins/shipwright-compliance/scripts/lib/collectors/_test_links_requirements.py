"""Build the requirement index the TT1 manifest is assembled from (schema v3).

Split out of ``test_links`` so that module stays inside its anti-ratchet baseline and
the seam is meaningful: everything here answers *which requirements exist and under
what key*, while ``test_links`` answers *how tags and evidence join to them*.

**The v3 collapse this module exists to catch.** A v3 manifest key is
``<FR group digits>::<FR id>`` — a pure function of the id — so it no longer varies with
the spec's directory. That is the point (a split rename cannot move a key), but it has a
consequence v2 did not have: two specs declaring the SAME FR id used to receive two
distinct keys (``01-a::FR-03.01`` and ``02-b::FR-03.01``) and now claim ONE.

That is resolved for two ACTIVE rows by FAILING CLOSED, not by picking a winner. Both
tolerant options were considered and rejected in external review: a plain
``dict[key] = req`` is last-writer-wins, which silently deletes a requirement from the
manifest; and keeping-the-first-plus-reporting-the-rest still deletes it, merely with a
footnote. The WebUI consumes ``Object.values(requirements)``, so a dropped node is a
requirement that simply stops existing on the traceability screen — a concealed
traceability gap in the artifact whose entire job is to reveal them. An incomplete
manifest must not be published, so generation raises instead.

Two ACTIVE rows sharing an id is an authoring defect either way. v2 only appeared to
tolerate it: within a SINGLE spec, two rows sharing an id already collapsed silently
under v2, because the namespace was equal there too. v3 makes the same defect uniformly
visible rather than newly inventing it.

**A ``removed`` row is deliberately EXCLUDED from that rule.** An id that is active in
one split and carries a tombstone row in another is a legitimate, already-documented
state (``_group_d_manifest.collision_ids``: "REMOVED in ns-B is not a same-namespace
duplicate"), and S3 must not make a supported state unrepresentable. Two independent
reasons the fail-closed rationale does not reach it: a removed node has no ``tests``, so
it cannot false-green anyone's coverage; and the remedy this module prints — renumber one
of the rows — contradicts the campaign's own convention that ids are stable and never
renumbered (SPEC §3.1). "Renumber" is right advice for two live rows and wrong advice for
a tombstone.

KNOWN GAP for S4 (one header-driven parser), NOT closed here: only the
``## Removed Requirements`` heading sets ``status="removed"``. The inline ``**REMOVED**
by`` marker this repo actually uses (SPEC §2.5) is not recognised at all, so an
inline-removed row still parses as ``active`` and would collide as the hardest form.
That is pre-existing parser behaviour and belongs to S4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._requirement_parse import parse_requirements


class ManifestIntegrityError(Exception):
    """A manifest cannot be built or must not be published, and the reason is authoring.

    Deliberately NOT a ``ValueError``. The cross-layer/removal verifiers regenerate a
    base+head manifest inside ``_layer_coverage_regen``, which catches
    ``(OSError, ValueError)`` and degrades to ``None`` — rendering the fixed string
    "git unavailable / no base ref / collector unavailable". A ValueError subclass would
    therefore be swallowed and reported as an infrastructure problem, sending an operator
    to check git, the base ref and the collector while the real cause is a duplicate FR id
    in their spec. Subclassing ``Exception`` lets it reach the outer ``except Exception``
    handler, which names the type.
    """


class DuplicateRequirementId(ManifestIntegrityError):
    """Two ACTIVE rows claim one v3 manifest key. Raised so no incomplete manifest ships."""


class KeyNotDerivedFromId(ManifestIntegrityError):
    """A requirement key disagrees with its own node's id (a path-derived namespace)."""


@dataclass
class RequirementIndex:
    """The requirements a manifest build found, plus the diagnostics it accumulated."""

    by_key: dict = field(default_factory=dict)          # manifest key -> Requirement
    by_display_id: dict = field(default_factory=dict)   # "FR-XX.YY" -> [Requirement]
    invalid_layers: list = field(default_factory=list)  # Layers cell with no valid layer
    invalid_ids: list = field(default_factory=list)     # row declined by the FR-table reader


def build_requirement_index(entries) -> RequirementIndex:
    """Parse every ``(spec_text, rel_spec_path)`` entry into a :class:`RequirementIndex`.

    Raises :class:`DuplicateRequirementId` when two ACTIVE rows declare the same FR id.
    The message names the id and BOTH contributing spec paths, because the fix is to
    renumber one of them and an error that does not say where is an error you cannot
    act on.

    A ``removed`` row never triggers it, and never displaces a live one: an active row
    always wins the key, whatever order the specs are discovered in. So an id that is
    active in one split and tombstoned in another keeps its ACTIVE node — the state
    ``_group_d_manifest`` already documents as legitimate.
    """
    index = RequirementIndex()
    for text, rel_spec in entries:
        for req in parse_requirements(
            text, spec_path=rel_spec, invalid_layers=index.invalid_layers,
            invalid_ids=index.invalid_ids,
        ):
            prior = index.by_key.get(req.key)
            if prior is not None:
                if prior.is_active and req.is_active:
                    raise DuplicateRequirementId(
                        f"requirement id {req.id} is declared as an ACTIVE requirement "
                        f"twice: {prior.spec_path} and {req.spec_path}. Since manifest "
                        f"schema v3 the key ({req.key}) derives from the id alone, so both "
                        "rows claim one manifest node and one of them would be silently "
                        "dropped. Renumber one of the two rows."
                    )
                # Tombstone vs live: keep whichever is ACTIVE, so discovery order cannot
                # decide whether a live requirement or its gravestone reaches the manifest.
                if prior.is_active:
                    continue
                index.by_display_id[req.id] = [
                    r for r in index.by_display_id.get(req.id, []) if r is not prior
                ]
            index.by_key[req.key] = req
            index.by_display_id.setdefault(req.id, []).append(req)
    return index


def assert_keys_derive_from_ids(manifest: dict) -> None:
    r"""Raise unless every requirement key agrees with its own node's id.

    The v3 JSON-schema pins the key SHAPE (``^\d{2}::FR-XX.YY$``) but cannot express
    that the two halves agree: ``01::FR-02.03`` matches the pattern while being wrongly
    namespaced. Shape alone would therefore catch only an obviously non-numeric
    namespace (``01-adopted::``) and would wave through a numerically-named directory
    (``01/``, ``02/``) — precisely the repos where a path-derived namespace is hardest
    to notice. This is what makes id-derivation enforced rather than conventional.
    """
    for key, node in (manifest.get("requirements") or {}).items():
        expected = f"{node['id'][3:5]}::{node['id']}"
        if key != expected:
            raise KeyNotDerivedFromId(
                f"test-traceability manifest key {key!r} disagrees with its node id "
                f"{node['id']!r} (expected {expected!r}). Since v3 the key namespace is "
                "derived from the id — a key built from anything else (a split "
                "directory) must never be written."
            )


__all__ = ["ManifestIntegrityError", "DuplicateRequirementId", "KeyNotDerivedFromId",
           "RequirementIndex", "build_requirement_index", "assert_keys_derive_from_ids"]


_LAYER_ORDER = ("unit", "integration", "e2e")


def _cov_status(links: list[dict]) -> str:
    """'ok' iff a tagged test at this layer is BOTH enabled AND executed=pass (R1)."""
    passing = any(l["status"] == "enabled" and l["executed"] == "pass" for l in links)
    return "ok" if passing else "MISSING"


def build_requirement_nodes(requirements: dict, tests_by_key: dict) -> dict:
    """Shape each requirement into its manifest node (coverage per layer).

    Moved here from ``test_links.build_manifest`` when the ``invalid_ids``
    accumulator pushed that module past its bloat baseline. The seam is the
    honest one rather than the convenient one: this module already owns the
    requirement INDEX, so shaping a requirement's manifest NODE — and the
    per-layer coverage predicate that shaping depends on — belongs beside it,
    while ``test_links`` keeps tag collection, fold resolution and assembly.

    A REMOVED requirement reports ``n/a`` at every layer it required rather than
    MISSING: a tombstone has no tests by definition, so scoring it as uncovered
    would manufacture a permanent false deficit.
    """
    req_nodes: dict = {}
    for key, req in requirements.items():
        tests_node: dict = {}
        coverage: dict = {}
        if req.is_active:
            filed = tests_by_key.get(key, {})
            layers = list(req.required_layers) + [l for l in filed if l not in req.required_layers]
            for layer in _LAYER_ORDER:
                if layer in filed:
                    tests_node[layer] = filed[layer]
                if layer in layers:
                    coverage[layer] = _cov_status(filed.get(layer, []))
        else:
            for layer in _LAYER_ORDER:
                if layer in req.required_layers:
                    coverage[layer] = "n/a"
        req_nodes[key] = {
            "id": req.id, "spec_path": req.spec_path, "title": req.title,
            "priority": req.priority, "status": req.status,
            "required_layers": list(req.required_layers),
            "required_layers_source": req.required_layers_source,
            "tests": tests_node, "coverage": coverage,
        }
    return req_nodes
