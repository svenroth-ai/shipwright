"""TT3 — adopt infers ``required_layers`` from the detected surface (AC2).

The adopt onboarding path reverse-engineers FRs from a brownfield repo; each FR
declares the layers it must be covered at, inferred from its surface:

* a route / page / UI framework  ⇒ ``e2e``
* a migration / schema / table / RLS policy  ⇒ ``integration``
* every FR  ⇒ ``unit``

The rendered adopt ``spec.md`` carries the inferred set in a ``Layers`` column so
the traceability manifest reads it as an explicit ``required_layers`` value.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import adopt's own ``lib.*`` modules FIRST (conftest put adopt's ``scripts/`` on the
# path). This MUST precede the ``load_shared_lib`` call below: that loader leaves
# ``shared/scripts`` on ``sys.path``, after which a bare ``from lib.X`` would resolve
# to SHARED's ``lib`` instead of adopt's — the exact ADR-045 order-fragility. Caching
# adopt's ``lib`` package first keeps every later ``from lib.X`` bound to adopt's.
from lib.render_helpers import infer_required_layers  # noqa: E402
from lib.artifact_writer import _render_spec_md  # noqa: E402
from lib.feature_inferrer import infer_features_ast  # noqa: E402
from lib.stack_detector import detect_stack  # noqa: E402

# ADR-045 discipline (this campaign is literally about it): import the SHARED model
# AND the compliance requirement-model parser through the robust loader that
# save/clears/restores ``sys.modules['lib']`` — NOT a bare ``sys.path`` + ``from
# requirement_model import``. The compliance plugin owns ``load_shared_lib``; adding
# its root makes the collector package importable (``scripts.lib`` ≠ adopt's ``lib``).
_COMPLIANCE_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "shipwright-compliance"
if str(_COMPLIANCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_COMPLIANCE_ROOT))
from scripts.lib.collectors._lib_loader import load_shared_lib  # noqa: E402
from scripts.lib.collectors._requirement_parse import parse_requirements  # noqa: E402

LAYERS = load_shared_lib("requirement_model").LAYERS


def test_route_feature_infers_e2e_and_unit():
    feat = {
        "route": "/dashboard",
        "source_file": "src/app/dashboard/page.tsx",
        "framework": "next-app-router",
    }
    assert infer_required_layers(feat) == ("unit", "e2e")


def test_page_source_without_explicit_route_still_infers_e2e():
    feat = {"source_file": "pages/orders.tsx"}
    assert infer_required_layers(feat) == ("unit", "e2e")


def test_migration_feature_infers_integration_and_unit():
    feat = {"source_file": "db/migrations/001_create_orders.sql"}
    assert infer_required_layers(feat) == ("unit", "integration")


def test_rls_policy_feature_infers_integration():
    feat = {"source_file": "supabase/policies/orders_rls.sql"}
    assert infer_required_layers(feat) == ("unit", "integration")


def test_unknown_surface_defaults_to_unit_only():
    feat = {"source_file": "lib/util.py"}
    assert infer_required_layers(feat) == ("unit",)


def test_incidental_table_in_component_name_does_not_infer_integration():
    # A UI component literally named "…Table" must not be mis-read as a DB table
    # surface (review: incidental keyword occurrences must not misclassify).
    feat = {"source_file": "src/components/UserTable.tsx"}
    layers = infer_required_layers(feat)
    assert "integration" not in layers
    assert layers == ("unit", "e2e")   # it is a UI component ⇒ e2e


def test_multiple_surfaces_union_all_three_layers():
    # A feature that is a UI surface (UI framework) AND touches persistence unions the
    # layers: e2e (from the UI framework) + integration (from the db source) + unit.
    feat = {"framework": "svelte", "source_file": "src/lib/db/orders_schema.ts"}
    assert infer_required_layers(feat) == ("unit", "integration", "e2e")


def test_backend_api_route_is_not_e2e():
    # MUST-FIX 4: feature_inferrer sets route+framework on EVERY feature, incl.
    # backend (fastapi/flask/express). A pure-API route must NOT infer e2e — a bare
    # framework/route is not a UI surface; e2e needs a UI framework or UI-file source.
    for fw, src, route in (
        ("fastapi", "app/routers/health.py", "/health"),
        ("flask", "app/views/api.py", "/status"),
        ("express", "src/routes/orders.js", "/orders"),
    ):
        layers = infer_required_layers({"framework": fw, "source_file": src, "route": route})
        assert "e2e" not in layers, f"{fw} API route wrongly inferred e2e: {layers}"


def test_backend_data_route_infers_integration_not_e2e():
    # A backend route whose source IS a persistence surface ⇒ integration (not e2e).
    feat = {"framework": "fastapi", "source_file": "app/db/models/orders.py", "route": "/orders"}
    assert infer_required_layers(feat) == ("unit", "integration")


def test_unit_is_always_present_and_first():
    for feat in ({"route": "/x"}, {"source_file": "migrations/x.sql"}, {}):
        layers = infer_required_layers(feat)
        assert layers[0] == "unit"


def test_every_inferred_layer_is_in_the_shared_vocab():
    for feat in ({"route": "/x"}, {"source_file": "migrations/x.sql"}, {"source_file": "u.py"}):
        for layer in infer_required_layers(feat):
            assert layer in LAYERS


def test_rendered_spec_carries_a_layers_column():
    features = [
        {
            "fr_id": "FR-01.01", "label": "/dashboard", "description": "Dashboard page",
            "source_file": "src/app/dashboard/page.tsx", "framework": "next-app-router",
            "route": "/dashboard",
        },
        {
            "fr_id": "FR-01.02", "label": "orders schema", "description": "Persist orders",
            "source_file": "db/migrations/001_create_orders.sql",
        },
    ]
    md = _render_spec_md(
        project_name="Demo", split_name="01-adopted", product_description="x",
        features=features, qr_items=[], constraints=[],
    )
    fr_section = md.split("## Functional Requirements", 1)[1].split("## Quality", 1)[0]
    # header carries the new column
    assert "Layers" in fr_section.splitlines()[2]
    # the route FR declares e2e; the migration FR declares integration
    route_row = next(l for l in fr_section.splitlines() if "FR-01.01" in l)
    migration_row = next(l for l in fr_section.splitlines() if "FR-01.02" in l)
    assert "e2e" in route_row and "unit" in route_row
    assert "integration" in migration_row and "unit" in migration_row
    # adopt-derived layers are annotated `(inferred)` so the model parser reads them
    # as advisory (inferred_legacy), never the `explicit` hard-gate regime (Spec §9).
    assert "(inferred)" in route_row and "(inferred)" in migration_row


def test_brownfield_fixture_route_frs_declare_e2e_end_to_end(nextjs_repo):
    """AC2 via a real brownfield fixture: run the actual feature detection over the
    nextjs repo, render the spec, and assert the reverse-engineered route FRs carry
    an `e2e (inferred)` Layers declaration (the crawl→feature→spec path, not a
    hand-built dict). The migration→integration signal is pinned at the unit level
    above (`feature_inferrer` enumerates routes, not migrations)."""
    features = infer_features_ast(nextjs_repo, detect_stack(nextjs_repo))
    assert features, "fixture should yield at least one route feature"
    # every detected route feature requires e2e (+ unit)
    for feat in features:
        layers = infer_required_layers(feat)
        assert "e2e" in layers and "unit" in layers
    md = _render_spec_md(
        project_name="Fixture", split_name="01-adopted", product_description="x",
        features=features, qr_items=[], constraints=[],
    )
    fr_section = md.split("## Functional Requirements", 1)[1].split("## Quality", 1)[0]
    fr_rows = [l for l in fr_section.splitlines() if l.strip().startswith("| FR-")]
    assert fr_rows, "rendered spec should carry FR rows"
    assert all("e2e" in row and "(inferred)" in row for row in fr_rows)


def test_inferred_marker_roundtrip_binds_adopt_emit_to_compliance_read():
    """MUST-FIX 3 — bind adopt's emitted `(inferred)` marker to compliance's reader.

    The marker is a bare literal duplicated across two plugins: adopt `artifact_writer`
    WRITES ` (inferred)`, compliance `_INFERRED_MARKER_RE` READS `(inferred)`. With no
    spanning test, a drift on either side (` (inferred)`→` [inferred]`) would flip every
    adopted FR to `explicit` → hard-gated → false-RED blocking brownfield merges, while
    BOTH plugin suites stay green. This round-trip renders a real adopt spec and pipes it
    through the real compliance parser, asserting the emitted marker still reads advisory.
    """
    features = [
        {"fr_id": "FR-01.01", "label": "/dashboard", "description": "Dashboard page",
         "source_file": "src/app/dashboard/page.tsx", "framework": "next-app-router",
         "route": "/dashboard"},
        {"fr_id": "FR-01.02", "label": "orders schema", "description": "Persist orders",
         "source_file": "db/migrations/001_create_orders.sql"},
    ]
    md = _render_spec_md(
        project_name="RT", split_name="01-adopted", product_description="x",
        features=features, qr_items=[], constraints=[],
    )
    reqs = parse_requirements(md, spec_path="spec.md")
    by = {r.id: r for r in reqs}
    # the emitted `(inferred)` marker must read as advisory, NOT the explicit hard gate
    assert by["FR-01.01"].required_layers_source == "inferred_legacy"
    assert by["FR-01.02"].required_layers_source == "inferred_legacy"
    assert by["FR-01.01"].required_layers == ("unit", "e2e")
    assert by["FR-01.02"].required_layers == ("unit", "integration")
