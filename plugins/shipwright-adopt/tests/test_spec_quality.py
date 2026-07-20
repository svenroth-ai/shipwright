"""Spec.md quality fixes (Fix 3).

Three small but important corrections:

1. Test files are not features — filter out anything matching common
   test path patterns (`*.test.*`, `*.spec.*`, `__tests__/`).
2. Pass through `enrichment.features[i].acceptance_draft` as the FR's
   Acceptance Criteria. Today the spec.md falls back to a generic
   "Acceptance criteria are TBD" disclaimer regardless of input.
3. Deduplicate AST + crawl features that point at the same route
   (with trailing-slash normalization), keeping `origin: ast+crawl` and
   the enrichment description (richest source).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.generate_adoption_artifacts import generate


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=root, check=True,
    )


def _write_inputs(
    project_root: Path,
    *,
    snapshot_features: list[dict],
    routes: list[dict] | None = None,
    enrichment_features: list[dict] | None = None,
) -> tuple[Path, Path, Path]:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snap_dir / "snapshot.json"
    snapshot.write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": snapshot_features,
        "git": {"commits_total": 0, "contributors_total": 0, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")
    enrichment_path = snap_dir / "enrichment.json"
    if enrichment_features is not None:
        enrichment_path.write_text(json.dumps({
            "product_description": "Test product.",
            "features": enrichment_features,
            "architecture_prose": "Tested.",
            "architecture_diagram": "```\n  fixture\n```",
            "conventions_prose": "Tested.",
            "adrs": [],
        }), encoding="utf-8")
    routes_path = snap_dir / "routes.json"
    if routes is not None:
        routes_path.write_text(json.dumps(routes), encoding="utf-8")
    return snapshot, enrichment_path, routes_path


def _read_spec(project_root: Path, split_name: str = "01-adopted") -> str:
    return (project_root / ".shipwright" / "planning" / split_name / "spec.md").read_text(
        encoding="utf-8"
    )


def _fr_names(spec_text: str) -> set[str]:
    """The Name cell of every FR row, read through the shared reader.

    Campaign S5 dropped the `Source` column, so a feature's source-file path no
    longer appears anywhere in the spec (decision D3: a path is implementation
    detail). These tests used the path as a proxy for "this feature became a
    requirement"; the Name cell is the direct answer, and comparing the whole SET
    is stricter than the substring checks it replaces — `"/api/users" in spec`
    was also satisfied by a row for `/api/users-test`.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib"))
    from fr_table_reader import read_active_fr_rows

    return {row.name for row in read_active_fr_rows(spec_text)}


def _fr_basis(spec_text: str) -> dict[str, str]:
    """Name → Basis cell, for asserting HOW a requirement came to be known."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib"))
    from fr_table_reader import read_active_fr_rows

    return {row.name: row.basis_cell for row in read_active_fr_rows(spec_text)}


# ---------------------------------------------------------------------------
# Sub-Fix 3a: test files filtered from FR list
# ---------------------------------------------------------------------------


def test_test_files_excluded_from_fr_list(tmp_path: Path) -> None:
    _git_init(tmp_path)
    snap_features = [
        {"route": "/api/users", "source_file": "src/api/users.ts", "framework": "express"},
        {"route": "/api/users-test", "source_file": "src/api/users.test.ts", "framework": "express"},
        {"route": "/api/users-spec", "source_file": "src/api/users.spec.ts", "framework": "express"},
        {"route": "/api/legacy", "source_file": "src/__tests__/legacy.ts", "framework": "express"},
    ]
    snap, enr, rts = _write_inputs(tmp_path, snapshot_features=snap_features)

    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    # Exactly the production route becomes a requirement; the three test-file
    # routes do not. Asserted as a SET, so a stray extra row cannot pass.
    assert _fr_names(spec) == {"/api/users"}
    assert "users.test.ts" not in spec
    assert "users.spec.ts" not in spec
    assert "__tests__" not in spec


def test_python_test_files_excluded(tmp_path: Path) -> None:
    _git_init(tmp_path)
    snap_features = [
        {"route": "/health", "source_file": "src/api/health.py", "framework": "flask"},
        {"route": "/health-tests", "source_file": "tests/test_health.py", "framework": "flask"},
        {"route": "/api-conftest", "source_file": "src/conftest.py", "framework": "flask"},
    ]
    snap, enr, rts = _write_inputs(tmp_path, snapshot_features=snap_features)
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    assert _fr_names(spec) == {"/health"}
    assert "tests/test_health.py" not in spec
    assert "conftest.py" not in spec


# ---------------------------------------------------------------------------
# Sub-Fix 3b: enrichment acceptance_draft passes through
# ---------------------------------------------------------------------------


def test_acceptance_draft_passed_through_to_spec(tmp_path: Path) -> None:
    _git_init(tmp_path)
    snap, enr, rts = _write_inputs(
        tmp_path,
        snapshot_features=[
            {"route": "/dashboard", "source_file": "src/app/dashboard/page.tsx",
             "framework": "next-app-router"},
        ],
        enrichment_features=[
            {
                "route": "/dashboard",
                "label": "Dashboard",
                "description": "Project dashboard view.",
                "acceptance_draft": (
                    "Given a logged-in user, when they navigate to /dashboard, "
                    "then they see their active projects."
                ),
            }
        ],
    )
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    assert "Given a logged-in user" in spec
    assert "active projects" in spec


def test_tbd_acceptance_draft_does_not_pollute_spec(tmp_path: Path) -> None:
    """When the enrichment falls back to "TBD", spec.md should not echo a
    bullet that says exactly "TBD" — leave today's generic placeholder."""
    _git_init(tmp_path)
    snap, enr, rts = _write_inputs(
        tmp_path,
        snapshot_features=[
            {"route": "/x", "source_file": "src/x.ts", "framework": "express"},
        ],
        enrichment_features=[
            {"route": "/x", "label": "X", "description": "X.", "acceptance_draft": "TBD"}
        ],
    )
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    # No bullet that's literally `- TBD`.
    assert "\n- TBD\n" not in spec


# ---------------------------------------------------------------------------
# Sub-Fix 3c: AST + crawl dedup on route, with trailing-slash normalization
# ---------------------------------------------------------------------------


def test_ast_and_crawl_same_route_merge_with_origin_ast_plus_crawl(tmp_path: Path) -> None:
    _git_init(tmp_path)
    snap, enr, rts = _write_inputs(
        tmp_path,
        snapshot_features=[
            {"route": "/dashboard", "source_file": "src/app/dashboard/page.tsx",
             "framework": "next-app-router"},
        ],
        routes=[{"url": "/dashboard", "title": "Dashboard — App"}],
        enrichment_features=[
            {"route": "/dashboard", "label": "Dashboard", "description": "View."},
        ],
    )
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    # `/dashboard` should appear exactly once as an FR row.
    assert spec.count("| /dashboard |") + spec.count("| `/dashboard` |") <= 1
    assert spec.count("Dashboard") >= 1


def test_trailing_slash_routes_dedup(tmp_path: Path) -> None:
    """`/about` (AST) and `/about/` (crawl) describe the same route."""
    _git_init(tmp_path)
    snap, enr, rts = _write_inputs(
        tmp_path,
        snapshot_features=[
            {"route": "/about", "source_file": "src/app/about/page.tsx",
             "framework": "next-app-router"},
        ],
        routes=[{"url": "/about/", "title": "About"}],
    )
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    spec = _read_spec(tmp_path)
    # Only one row for /about — `/about/` and `/about` collapse.
    fr_rows = [
        line for line in spec.splitlines()
        if line.startswith("| FR-") and "/about" in line
    ]
    assert len(fr_rows) == 1, f"Expected single /about FR, got: {fr_rows}"
