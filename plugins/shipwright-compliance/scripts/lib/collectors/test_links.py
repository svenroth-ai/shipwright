"""``test_links`` collector — the requirement→test traceability manifest (Spec §4 D3).

Traceability campaign TT1 (foundation, data-only). Reads ``@FR`` tags across pytest +
Playwright + Vitest via the frozen ``fr_tag_grammar`` reference parser, joins them to the
FR table (Layers column, active + removed) and per-test execution evidence, and emits
``.shipwright/compliance/test-traceability.json`` (schema v3). This is the missing
*backward* link (test → FR) and the per-layer join the aggregate event count cannot
express. No gates flip here — the committed artifact is derived / RTM-visibility only;
enforcing gates (TT5) regenerate base+head themselves (R3).

This module is the pure tag → FR → manifest assembly plus the ``update_compliance``
wiring. Filesystem-facing helpers live in ``_test_links_io``; the requirement index and
its v3 key-collapse handling in ``_test_links_requirements``; fold-map wiring in
``_test_links_fold``.

KNOWN LIMITATION (un-namespaced tag fan-out) — the frozen ``@FR-XX.YY`` grammar carries
NO spec namespace, so a hit is filed into EVERY active requirement sharing that display
id (a potential false-green). Inherent to the frozen grammar and left as-is here (data
only); TT2's RTM + TT5's gate MUST account for it before relying on per-split coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import _test_links_fold as foldwire
from . import _test_links_io as io
from ._lib_loader import load_shared_lib
from ._suite_tags import propagate_suite_tags
from ._test_links_requirements import (
    assert_keys_derive_from_ids,
    build_requirement_index,
)

COLLECTOR_VERSION = "test_links/1.0.0"
_DEFAULT_TS = "1970-01-01T00:00:00+00:00"
_LAYER_ORDER = ("unit", "integration", "e2e")
# Frozen closed vocabularies (mirror traceability_schema.json testLink enums) — a
# boundary guard so out-of-vocab execution evidence can never ship a schema-invalid link.
_STATUS_VOCAB = frozenset({"enabled", "skipped", "quarantined", "only"})
_EXECUTED_VOCAB = frozenset({"pass", "fail", "not_run"})


def _load_grammar():
    """Import the frozen ``@FR`` reference parser via the robust shared-lib loader
    (ADR-045: safe even when ``sys.modules['lib']`` is already the compliance-local lib)."""
    return load_shared_lib("fr_tag_grammar")


def _cov_status(links: list[dict]) -> str:
    """'ok' iff a tagged test at this layer is BOTH enabled AND executed=pass (R1)."""
    passing = any(l["status"] == "enabled" and l["executed"] == "pass" for l in links)
    return "ok" if passing else "MISSING"


def _make_link(hit, layer: str, evidence: dict, *, resolved_from: str = "") -> dict:
    ev = evidence.get(hit.test, {})
    # Normalize to the frozen closed vocab FAIL-CLOSED — an out-of-vocab evidence value
    # (TT-EV owns the full contract) degrades to a non-enabled/not-run value so a forged
    # or garbled status can never combine with a pass to claim coverage ok. A test with
    # no evidence at all keeps status "enabled" but executed "not_run" (⇒ not ok).
    status = ev.get("status", "enabled")
    executed = ev.get("executed", "not_run")
    link = {
        "id": hit.test,
        "path": hit.test,
        "layer": layer,
        "status": status if status in _STATUS_VOCAB else "quarantined",
        "executed": executed if executed in _EXECUTED_VOCAB else "not_run",
        "tag_source": hit.tag_source,
    }
    # Provenance ONLY, and only when a fold was actually used — the link is filed against
    # the surviving FR, so `resolved_from` records the folded id the source literally
    # carries. Omitted otherwise so a repo with no fold-map emits a byte-identical link.
    if resolved_from:
        link["resolved_from"] = resolved_from
    return link


def build_manifest(
    project_root,
    *,
    spec_files: list[Path] | None = None,
    test_roots: list[Path] | None = None,
    prune_dirs: frozenset[str] | None = None,
    evidence: dict | None = None,
    enumerate_untagged: bool = True,
    generated_at: str = _DEFAULT_TS,
    source_commit: str = io._ZERO_SHA,
    collector_version: str = COLLECTOR_VERSION,
) -> dict:
    """Build the schema-v3 traceability manifest (pure; no writes)."""
    grammar = _load_grammar()
    project_root = Path(project_root)
    evidence = evidence or {}
    if spec_files is None:
        spec_files = io.discover_specs(project_root)
    if test_roots is None:
        test_roots = [project_root]

    # 1. Requirements from every spec. The key namespace derives from each FR's own id
    #    (v3) — nothing reads the spec's parent directory, which is what used to make
    #    every manifest key hostage to a rename. See _test_links_requirements for the
    #    key-collapse handling that id-derivation makes possible.
    entries = foldwire.spec_entries(spec_files, project_root, io.rel)
    index = build_requirement_index(entries)
    requirements, by_display_id = index.by_key, index.by_display_id

    # Each spec's ``## FR-Fold-Map`` alias table (folded id → surviving capability FR).
    fold_ctx = foldwire.build_fold_context(entries, by_display_id)

    # 2. Tags + test enumeration across every test file.
    hits: list = []
    invalid: list = []
    layer_by_test: dict[str, str] = {}
    all_test_ids: set[str] = set()
    for abs_path, rel_path in io.iter_test_files(test_roots, project_root, prune_dirs or io._PRUNE_DIRS):
        source = abs_path.read_text(encoding="utf-8", errors="ignore")
        layer = io.detect_layer(rel_path)
        res = grammar.parse_source(rel_path, source)
        suite_hits, suite_invalid = propagate_suite_tags(source, rel_path, grammar)
        for h in list(res.hits) + suite_hits:  # per-test tags + enclosing-suite tags (AC2)
            hits.append(h)
            layer_by_test[h.test] = layer
        invalid.extend(res.invalid)
        invalid.extend(suite_invalid)
        if enumerate_untagged:
            for tid in io.enumerate_tests(rel_path, source, grammar):
                all_test_ids.add(tid)
                layer_by_test.setdefault(tid, layer)

    # 3. Bind each hit to its FR (coverage link) or record it as an orphan.
    tests_by_key: dict[str, dict[str, list]] = {}
    orphans: list = []
    tagged_ids: set[str] = set()
    for h in hits:
        tagged_ids.add(h.test)
        matches = by_display_id.get(h.fr_id, [])
        active = [r for r in matches if r.is_active]
        # FALLBACK ONLY (never an override): a tag naming a LIVE FR binds there and the
        # fold-map is not consulted. Only a tag that would otherwise orphan is offered to
        # the map, so a granular tag survives a later taxonomy fold instead of turning
        # into a confirmed orphan (webui #287: 66 FRs → 29 capabilities ⇒ 419 orphans).
        resolved_from = terminal = ""
        if not active:
            active, resolved_from, terminal = foldwire.resolve_binding(
                fold_ctx, h.fr_id, by_display_id)
        if active:
            layer = layer_by_test.get(h.test, io.detect_layer(h.test.split("::")[0]))
            link = _make_link(h, layer, evidence, resolved_from=resolved_from)
            for r in active:
                bucket = tests_by_key.setdefault(r.key, {}).setdefault(layer, [])
                dup = next((l for l in bucket if l["id"] == link["id"]
                            and l["tag_source"] == link["tag_source"]), None)
                if dup is None:
                    # A COPY per bucket: a collision display id files one hit into several
                    # requirement nodes, and sharing one dict would let the supersede
                    # branch below mutate a sibling node's link by aliasing.
                    bucket.append(dict(link))
                elif not resolved_from:
                    # The same test also carries a DIRECT tag for this FR. The direct
                    # binding is the truer provenance, so it supersedes the fold-resolved
                    # one rather than adding a second link for the same (test, source).
                    dup.pop("resolved_from", None)
        else:
            # Classify by what the tag actually points AT. The tagged id itself is the
            # first answer; failing that, the id the fold walk stopped at — so a tag whose
            # survivor was RETIRED reads `fr_removed` rather than the misleading
            # `fr_absent` ("this FR never existed") the folded id alone would imply.
            dead = matches or (by_display_id.get(terminal) if terminal else None)
            reason = "fr_removed" if dead else "fr_absent"
            orphans.append({
                "test": h.test, "tagged_fr": h.fr_id,
                "reason": reason, "category": "confirmed_orphan",
            })
    for iv in invalid:
        tagged_ids.add(iv.test)

    # 4. Assemble the requirement nodes (coverage per layer, removed ⇒ n/a).
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

    return {
        "schema_version": 3,
        "collector_version": collector_version,
        "generated_at": generated_at,
        "source_commit": source_commit,
        "spec_hash": io.spec_hash([text for text, _ in entries]),
        "requirements": req_nodes,
        "orphans": orphans,
        # A frozen-grammar edge (e.g. covers("")) yields raw="" which the schema forbids
        # (invalidTag.raw minLength 1); coerce to a non-empty marker and carry the grammar
        # reason so the diagnostic survives and the artifact stays schema-valid.
        "invalid_tags": [
            {"test": iv.test, "raw": iv.raw or "<empty>",
             "reason": getattr(iv, "reason", "") or "non_canonical_fr_id"}
            for iv in invalid
        ],
        # FRs whose explicitly-headed Layers cell resolved to zero valid layers. Kept
        # `explicit` upstream so D-layer's hard gate still fires (Spec §11-R4).
        "invalid_layers": index.invalid_layers,
        "untagged_tests": sorted(all_test_ids - tagged_ids),
        # `fold_map` / `fold_defects` are present ONLY when the repo actually declares a
        # fold-map, so a project without one emits a byte-identical manifest (this
        # artifact is committed churn — an empty key would diff on every regen).
        **fold_ctx.as_manifest_fields(),
    }


def _validate_manifest(manifest: dict) -> None:
    """Fail-closed write-time check: raise unless the manifest is v3-schema-valid AND
    every key agrees with its own node's id, so producer/schema drift blows up loud in
    regen instead of silently shipping a corrupt artifact.

    The schema's ``^\\d{2}::FR-XX.YY$`` pattern constrains the key's SHAPE but cannot
    express that the two halves AGREE, so ``assert_keys_derive_from_ids`` carries that
    half (see ``_test_links_requirements``)."""
    import jsonschema  # noqa: PLC0415 — compliance dep; lazy so non-compliance imports stay light

    schema_path = Path(__file__).resolve().parents[1] / "traceability_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(manifest))
    if errors:
        raise ValueError(
            "test-traceability manifest failed v3-schema validation: " + errors[0].message
        )
    assert_keys_derive_from_ids(manifest)


def generate_file(project_root, data=None) -> Path:
    """Write ``.shipwright/compliance/test-traceability.json`` (update_compliance wiring).

    Real-project scope: the FR table + ``@FR``-tagged tests + the untagged tests found
    under the collector's test roots — by default the *conventional* roots (``tests/``,
    ``e2e/``, ``integration-tests/``, …), or exactly the ``traceability.test_roots`` a project
    opts into via ``shipwright_compliance_config.json`` (e.g. a monorepo adds ``plugins/*/tests``
    + ``shared/tests``, and ``traceability.exclude_dirs`` to keep fixture mini-repos out).
    ``untagged_tests`` honestly reflects what was scanned (never a silently-empty list),
    but the COMPLETE repo-wide inventory + backfill of scattered/non-conventional test
    dirs is the shared engine's job (adopt TT7 / retrofit TT8), not a compliance regen.
    """
    project_root = Path(project_root).resolve()
    # TT-EV: refresh the per-test execution-evidence index from any raw runner
    # reports THIS regen dropped, so coverage is execution-backed (R1). If no fresh
    # report was produced, we pass EMPTY evidence (fail-closed not_run) rather than
    # trusting a prior run's possibly-stale index — a regen with no evidence can
    # never self-report a previous pass. The on-disk index is left untouched for
    # audit; enforcing gates (TT2/TT5) regenerate base+head themselves (R3).
    from ._execution_evidence_io import refresh_index  # noqa: PLC0415 — local to avoid import cost when unused
    fresh = refresh_index(project_root)
    evidence = io.load_evidence(project_root) if fresh else {}
    generated_at = getattr(data, "timestamp", None) or _DEFAULT_TS
    manifest = build_manifest(
        project_root,
        test_roots=io.configured_test_roots(project_root),
        prune_dirs=io.configured_prune_dirs(project_root),
        evidence=evidence,
        enumerate_untagged=True,
        generated_at=generated_at,
        source_commit=io.git_head(project_root),
    )
    _validate_manifest(manifest)  # fail-closed before writing the artifact
    out = project_root / ".shipwright" / "compliance" / "test-traceability.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the test-traceability manifest")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    path = generate_file(Path(args.project_root))
    print(json.dumps({"success": True, "written": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
