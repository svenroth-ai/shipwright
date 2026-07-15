"""``test_links`` collector — the requirement→test traceability manifest (Spec §4 D3).

Traceability campaign TT1 (foundation, data-only). Reads ``@FR`` tags across pytest +
Playwright + Vitest via the frozen ``fr_tag_grammar`` reference parser, joins them to the
FR table (Layers column, active + removed) and per-test execution evidence, and emits
``.shipwright/compliance/test-traceability.json`` (schema v2). This is the missing
*backward* link (test → FR) and the per-layer join the aggregate event count cannot
express. No gates flip here — the committed artifact is derived / RTM-visibility only;
enforcing gates (TT5) regenerate base+head themselves (R3).

Filesystem-facing helpers (which files are tests, layer detection, spec/evidence
discovery, provenance) live in ``_test_links_io.py``; this module is the pure
tag → FR → manifest assembly plus the ``update_compliance`` wiring.

KNOWN LIMITATION (un-namespaced tag fan-out) — the frozen ``@FR-XX.YY`` grammar carries
NO spec namespace, so a hit is filed into EVERY active requirement sharing that display
id: in a multi-split repo where two splits both declare ``FR-03.01``, one tagged test
marks coverage ``ok`` for both (a potential false-green). This is inherent to the frozen
grammar and is left as-is here (data only); TT2's RTM + TT5's gate MUST account for it
(e.g. by preferring same-split resolution) before relying on per-split coverage.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import _test_links_io as io
from ._lib_loader import load_shared_lib
from ._requirement_parse import parse_requirements
from ._suite_tags import propagate_suite_tags

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


def _make_link(hit, layer: str, evidence: dict) -> dict:
    ev = evidence.get(hit.test, {})
    # Normalize to the frozen closed vocab — an out-of-vocab evidence value (TT-EV owns
    # the full evidence contract) degrades to the safe default, never a schema-invalid link.
    status = ev.get("status", "enabled")
    executed = ev.get("executed", "not_run")
    return {
        "id": hit.test,
        "path": hit.test,
        "layer": layer,
        "status": status if status in _STATUS_VOCAB else "enabled",
        "executed": executed if executed in _EXECUTED_VOCAB else "not_run",
        "tag_source": hit.tag_source,
    }


def build_manifest(
    project_root,
    *,
    spec_files: list[Path] | None = None,
    test_roots: list[Path] | None = None,
    evidence: dict | None = None,
    enumerate_untagged: bool = True,
    generated_at: str = _DEFAULT_TS,
    source_commit: str = io._ZERO_SHA,
    collector_version: str = COLLECTOR_VERSION,
) -> dict:
    """Build the schema-v2 traceability manifest (pure; no writes)."""
    grammar = _load_grammar()
    project_root = Path(project_root)
    evidence = evidence or {}
    if spec_files is None:
        spec_files = io.discover_specs(project_root)
    if test_roots is None:
        test_roots = [project_root]

    # 1. Requirements from every spec (namespaced by the spec's parent dir).
    requirements: dict = {}          # manifest key → Requirement
    by_display_id: dict[str, list] = {}
    spec_texts: list[str] = []
    for spec in spec_files:
        text = Path(spec).read_text(encoding="utf-8", errors="ignore")
        spec_texts.append(text)
        namespace = Path(spec).resolve().parent.name
        rel_spec = io.rel(spec, project_root)
        for req in parse_requirements(text, namespace=namespace, spec_path=rel_spec):
            requirements[req.key] = req
            by_display_id.setdefault(req.id, []).append(req)

    # 2. Tags + test enumeration across every test file.
    hits: list = []
    invalid: list = []
    layer_by_test: dict[str, str] = {}
    all_test_ids: set[str] = set()
    for abs_path, rel_path in io.iter_test_files(test_roots, project_root):
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
        if active:
            layer = layer_by_test.get(h.test, io.detect_layer(h.test.split("::")[0]))
            link = _make_link(h, layer, evidence)
            for r in active:
                bucket = tests_by_key.setdefault(r.key, {}).setdefault(layer, [])
                if not any(l["id"] == link["id"] and l["tag_source"] == link["tag_source"] for l in bucket):
                    bucket.append(link)
        else:
            reason = "fr_removed" if matches else "fr_absent"
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
        "schema_version": 2,
        "collector_version": collector_version,
        "generated_at": generated_at,
        "source_commit": source_commit,
        "spec_hash": io.spec_hash(spec_texts),
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
        "untagged_tests": sorted(all_test_ids - tagged_ids),
    }


def _validate_manifest(manifest: dict) -> None:
    """Fail-closed write-time schema check: raise if the assembled manifest is not
    v2-schema-valid, so producer/schema drift blows up loud in regen instead of
    silently shipping a corrupt artifact."""
    import jsonschema  # noqa: PLC0415 — compliance dep; lazy so non-compliance imports stay light

    schema_path = Path(__file__).resolve().parents[1] / "traceability_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(manifest))
    if errors:
        raise ValueError(
            "test-traceability manifest failed v2-schema validation: " + errors[0].message
        )


def generate_file(project_root, data=None) -> Path:
    """Write ``.shipwright/compliance/test-traceability.json`` (update_compliance wiring).

    Real-project scope: the FR table + ``@FR``-tagged tests + the untagged tests found
    under the *conventional* test roots (``tests/``, ``e2e/``, ``integration-tests/``, …).
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
        test_roots=io.default_test_roots(project_root),
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
