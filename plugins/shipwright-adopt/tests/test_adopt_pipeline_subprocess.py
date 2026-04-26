"""End-to-end subprocess test of the adopt artifact pipeline (sub-iterate F).

Marked `slow` — runs the REAL `generate_adoption_artifacts.py` as a uv-spawned
subprocess (not via direct import). Synthesizes a minimal but realistic
snapshot.json + routes.json + enrichment.json against a temp git repo,
then verifies every expected output file exists and the JSON result has
the new fields (visual_docs, gitignore_report, enrichment metadata).

This is the test that would have caught a bunch of integration bugs in
sub-iterates A-E before they reached the merge — the existing tests
exercise individual functions but not the wired-up CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.slow


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "tools" / "generate_adoption_artifacts.py"


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def _write_snapshot(project_root: Path) -> None:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {
            "primary_language": "typescript",
            "frontend": {"vite": "^6.0.0", "react": "^19.0.0"},
            "backend": {"hono": "^4.7.0"},
            "multi_service": {
                "detected": True,
                "services": [
                    {"name": "client", "root": "client", "framework": "vite"},
                    {"name": "server", "root": "server", "framework": "hono"},
                ],
            },
        },
        "profile": {"matched": "vite-hono"},
        "commands": {"dev": None, "build": None, "test": "npx vitest run"},
        "features": [
            {"route": "/api/diagnostics", "source_file": "server/src/index.ts",
             "framework": "hono", "method": "GET"},
            {"route": "/api/sessions", "source_file": "server/src/sessions.ts",
             "framework": "hono", "method": "POST"},
        ],
        "git": {"commits_total": 75, "contributors_total": 3, "major_refactor_commits": []},
        "folders": {
            "layers": [{"name": "presentation", "paths": ["client/src/components"]}],
            "loc_by_layer": {"presentation": 1500},
        },
        "conventions": {"linter": "eslint", "formatter": "prettier", "tsconfig_strict": True},
        "ci_pipeline": {"provider": "github-actions"},
        "excludes": [],
    }), encoding="utf-8")
    (snap_dir / "routes.json").write_text(json.dumps([
        {"url": "/", "title": "Home"},
        {"url": "/dashboard", "title": "Dashboard"},
    ]), encoding="utf-8")
    # No enrichment.json → exercises the enrichment_fallback path


def _write_frontend_assets(project_root: Path) -> None:
    """Lay down a tiny client/ tree so visual docs have something to inventory."""
    client = project_root / "client"
    (client / "src" / "components").mkdir(parents=True)
    (client / "src" / "components" / "Button.tsx").write_text(
        "export interface ButtonProps { label: string; onClick: () => void }\n"
        "export function Button(p: ButtonProps) { return null; }\n",
        encoding="utf-8",
    )
    (client / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { "
        "colors: { primary: '#0066cc' }, "
        "fontSize: { display: '4rem' } } } };\n",
        encoding="utf-8",
    )
    (client / "package.json").write_text(
        json.dumps({"name": "client", "devDependencies": {"vite": "^6.0.0"}}),
        encoding="utf-8",
    )


def test_full_pipeline_e2e_via_subprocess(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    _write_frontend_assets(tmp_path)

    # Force UTF-8 stdout for the child Python — Windows cp1252 is fragile here.
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, (
        f"generate_adoption_artifacts subprocess failed: rc={r.returncode}\n"
        f"stdout: {r.stdout[-1500:]}\n"
        f"stderr: {r.stderr[-1500:]}\n"
    )

    # The JSON result is the LAST stdout block (script may print warnings first).
    payload = json.loads(r.stdout[r.stdout.find("{"):])

    # Every expected artifact landed
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "agent_docs" / "decision_log.md").exists()
    assert (tmp_path / "agent_docs" / "architecture.md").exists()
    assert (tmp_path / "shipwright_run_config.json").exists()
    assert (tmp_path / "shipwright_events.jsonl").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / "planning" / "01-adopted" / "spec.md").exists()

    # Tier-5 visual docs were produced (fixture has client/components + tailwind)
    assert (tmp_path / "agent_docs" / "design_tokens.md").exists()
    assert (tmp_path / "agent_docs" / "guideline.md").exists()
    assert payload["visual_docs"]["wrote_docs"] is True
    assert payload["visual_docs"]["component_count"] >= 1
    # frontend_root must be the client dir (multi-service pivot worked)
    assert payload["visual_docs"]["frontend_root"].rstrip("/\\").endswith("client")

    # Tier-4 enrichment fallback was used (no enrichment.json provided)
    assert payload["enrichment"]["source"] == "fallback"

    # Tier-4 gitignore report present
    assert "gitignore_report" in payload
    assert payload["gitignore_report"]["total"] > 0

    # Tier-4 additive merge: spec contains BOTH /dashboard (crawl) AND /api/* (AST)
    spec = (tmp_path / "planning" / "01-adopted" / "spec.md").read_text(encoding="utf-8")
    assert "/api/diagnostics" in spec
    assert "/api/sessions" in spec
    assert "Dashboard" in spec  # crawl entries surface their title
    # Distinct FR rows for all 4 (2 crawl + 2 AST)
    assert spec.count("FR-01.") >= 4


def test_pipeline_loud_failure_on_invalid_enrichment(tmp_path: Path) -> None:
    """Enrichment with missing required keys should make the subprocess exit
    non-zero with a clear stderr diagnostic — not silently fall back."""
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    # Plant a malformed enrichment.json
    enr = tmp_path / ".shipwright" / "adopt" / "enrichment.json"
    enr.write_text(json.dumps({"product_description": "missing other required keys"}),
                    encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    assert r.returncode != 0, "expected loud failure on invalid enrichment"
    combined = (r.stderr + r.stdout).lower()
    assert "enrichment" in combined or "schema" in combined
