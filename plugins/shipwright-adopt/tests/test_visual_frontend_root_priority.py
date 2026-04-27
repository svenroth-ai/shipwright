"""Pin the multi-service frontend-root resolution priority (sub-iterate F).

External review caught: the resolver only checked names in
`{frontend, client, web}` but the spec says `primary: true` should win
first. This matters when a project marks a service like `app` as primary.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.generate_adoption_artifacts import generate


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
                    "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def _write_inputs(
    project_root: Path,
    *,
    services: list[dict],
    snapshot_features: list[dict],
) -> tuple[Path, Path, Path]:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snap_dir / "snapshot.json"
    snapshot.write_text(json.dumps({
        "stack": {
            "primary_language": "typescript",
            "multi_service": {"detected": True, "services": services},
        },
        "profile": {"matched": "vite-hono"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": snapshot_features,
        "git": {"commits_total": 5, "contributors_total": 1, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")
    return snapshot, snap_dir / "enrichment.json", snap_dir / "routes.json"


def test_primary_true_wins_over_name_heuristic(tmp_path: Path) -> None:
    """A service named 'app' but flagged primary:true must be picked,
    even though 'frontend' / 'client' / 'web' would normally match by name."""
    _git_init(tmp_path)
    # Put a Tailwind config + component in a subdir named 'app' so we can prove
    # the resolver pivoted there (rather than a sibling 'client').
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { colors: { primary_app: '#aaa' } } } };\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "src" / "components").mkdir(parents=True)
    (tmp_path / "app" / "src" / "components" / "Hero.tsx").write_text(
        "export const Hero = () => null;\n", encoding="utf-8",
    )
    # And put a 'client' dir too — empty — to prove name-heuristic isn't winning.
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { colors: { wrong_client: '#000' } } } };\n",
        encoding="utf-8",
    )

    services = [
        {"name": "client", "root": "client"},  # name match but NOT primary
        {"name": "app", "root": "app", "primary": True},  # primary wins
    ]
    snap, enr, rts = _write_inputs(tmp_path, services=services, snapshot_features=[])

    result = generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    assert result["visual_docs"]["wrote_docs"] is True
    assert result["visual_docs"]["frontend_root"].endswith("app")
    tokens = (tmp_path / ".shipwright" / "agent_docs" / "design_tokens.md").read_text(encoding="utf-8")
    assert "primary_app" in tokens
    assert "wrong_client" not in tokens


def test_name_heuristic_wins_when_no_primary_flagged(tmp_path: Path) -> None:
    """Existing back-compat: when no service flags `primary: true`, the
    name-based heuristic still matches frontend/client/web."""
    _git_init(tmp_path)
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { colors: { ok_client: '#000' } } } };\n",
        encoding="utf-8",
    )
    (tmp_path / "client" / "src" / "components").mkdir(parents=True)
    (tmp_path / "client" / "src" / "components" / "Foo.tsx").write_text(
        "export const Foo = () => null;\n", encoding="utf-8",
    )

    services = [
        {"name": "backend", "root": "server"},
        {"name": "client", "root": "client"},  # name match
    ]
    snap, enr, rts = _write_inputs(tmp_path, services=services, snapshot_features=[])
    generate(
        tmp_path,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )
    tokens = (tmp_path / ".shipwright" / "agent_docs" / "design_tokens.md").read_text(encoding="utf-8")
    assert "ok_client" in tokens
