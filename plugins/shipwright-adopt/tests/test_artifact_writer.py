"""Unit tests for artifact_writer."""

import re
from pathlib import Path

from lib.artifact_writer import write_agent_docs, write_claude_md, write_spec


def test_write_claude_md(tmp_path: Path) -> None:
    path = write_claude_md(
        tmp_path,
        project_name="Demo",
        profile="supabase-nextjs",
        stack={"runtime": {"node": "22.x"}, "frontend": {"next": "Next.js@16"}, "backend": {}, "database": {}, "auth": {}},
        commands={"build": "npm run build", "test": "npx vitest", "dev": "npm run dev"},
        product_description="A demo app that does X, Y, Z.",
    )
    content = path.read_text(encoding="utf-8")
    assert "# Demo" in content
    assert "supabase-nextjs" in content
    assert "A demo app that does X, Y, Z." in content
    assert "npm run build" in content
    assert "/shipwright-iterate" in content


def test_write_agent_docs(tmp_path: Path) -> None:
    paths = write_agent_docs(
        tmp_path,
        project_name="Demo", profile="supabase-nextjs", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[{"name": "presentation", "paths": ["src/app"]}],
        loc_by_layer={"presentation": 100},
        architecture_diagram="```\n(diagram)\n```",
        data_flow_description="Data flows from X to Y.",
        conventions={"linter": "eslint-flat", "formatter": "prettier"},
        conventions_prose="Test conventions prose.",
        features_count=3, commits_total=42, contributors_total=2,
        nested_excluded=["webui"], commit_sha="abc",
        retroactive_adrs=[],
    )
    names = [p.name for p in paths]
    assert "architecture.md" in names
    assert "conventions.md" in names
    assert "decision_log.md" in names
    assert "build_dashboard.md" in names
    dec = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    assert "ADR-0001" in dec
    assert "Adopt" in dec
    dash = (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(encoding="utf-8")
    assert "42" in dash  # commits_total
    assert "webui" in dash


def test_write_spec_has_fr_ids(tmp_path: Path) -> None:
    features = [
        {"fr_id": "FR-01.01", "label": "Dashboard", "description": "User views active projects", "source_file": "src/app/dashboard/page.tsx"},
        {"fr_id": "FR-01.02", "label": "Login", "description": "User logs in", "source_file": "src/app/login/page.tsx"},
    ]
    path = write_spec(
        tmp_path,
        project_name="Demo", split_name="01-adopted",
        product_description="Demo app.",
        features=features,
        qr_items=["CI pipeline must pass"],
        constraints=["Node 22.x"],
    )
    content = path.read_text(encoding="utf-8")
    assert "FR-01.01" in content
    assert "FR-01.02" in content
    assert re.search(r"\bFR-\d+\.\d+\b", content)
    assert "Demo app." in content
    assert "CI pipeline must pass" in content
