"""Prior-art harvester (Fix 2).

Adopt's old behavior was to write an empty decision_log.md (single ADR-0001)
and a thin auto-generated conventions.md, ignoring everything the previous
maintainers wrote. The harvester is best-effort: when a recognized source
exists it copies the content forward verbatim with attribution; when nothing
is found it returns None and the caller falls back to today's behavior.

Non-goal: NLP / LLM extraction. Pure deterministic file + path matching.
"""

from __future__ import annotations

from pathlib import Path

from lib.prior_art_harvester import (
    harvest_conventions,
    harvest_decision_log,
)


# ---------------------------------------------------------------------------
# decision_log harvesting
# ---------------------------------------------------------------------------


def test_harvest_decision_log_returns_none_when_no_source(tmp_path: Path) -> None:
    """Silent skip — caller falls back to today's auto-generated ADR-0001."""
    result = harvest_decision_log(tmp_path)
    assert result is None


def test_harvest_decision_log_finds_nygard_docs_adr_layout(tmp_path: Path) -> None:
    """The classic adr-tools layout: docs/adr/000N-title.md."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-record-architecture-decisions.md").write_text(
        "# 1. Record architecture decisions\n\n"
        "Date: 2024-01-15\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nWe need a way to record decisions.\n\n"
        "## Decision\n\nUse adr-tools.\n",
        encoding="utf-8",
    )
    (adr_dir / "0002-pick-postgres.md").write_text(
        "# 2. Pick Postgres\n\n## Status\n\nAccepted\n\n## Context\n\n"
        "We need a relational database.\n",
        encoding="utf-8",
    )

    result = harvest_decision_log(tmp_path)
    assert result is not None
    assert "Record architecture decisions" in result.content
    assert "Pick Postgres" in result.content
    assert result.source_path == "docs/adr"
    assert result.entry_count == 2


def test_harvest_decision_log_finds_madr_docs_decisions_layout(tmp_path: Path) -> None:
    """MADR's layout: docs/decisions/."""
    d = tmp_path / "docs" / "decisions"
    d.mkdir(parents=True)
    (d / "0001-use-react.md").write_text("# Use React\n\n## Context\n\n...\n", encoding="utf-8")
    (d / "0002-use-vite.md").write_text("# Use Vite\n\n## Context\n\n...\n", encoding="utf-8")
    (d / "0003-use-tailwind.md").write_text("# Use Tailwind\n\n## Context\n\n...\n", encoding="utf-8")

    result = harvest_decision_log(tmp_path)
    assert result is not None
    assert result.entry_count == 3
    assert result.source_path == "docs/decisions"
    assert "Use React" in result.content
    assert "Use Vite" in result.content


def test_harvest_decision_log_finds_docs_architecture_decisions_layout(tmp_path: Path) -> None:
    d = tmp_path / "docs" / "architecture" / "decisions"
    d.mkdir(parents=True)
    (d / "001.md").write_text("# 1. Layered architecture\n\n...\n", encoding="utf-8")
    result = harvest_decision_log(tmp_path)
    assert result is not None
    assert result.source_path == "docs/architecture/decisions"


def test_harvest_decision_log_finds_root_decision_log_md(tmp_path: Path) -> None:
    (tmp_path / "decision_log.md").write_text(
        "# Decision Log\n\n"
        "## ADR-0001: Use TypeScript\n\nWhy: type safety.\n\n"
        "## ADR-0002: Adopt monorepo\n\nWhy: shared packages.\n",
        encoding="utf-8",
    )
    result = harvest_decision_log(tmp_path)
    assert result is not None
    assert "Use TypeScript" in result.content
    assert result.source_path == "decision_log.md"


def test_harvest_decision_log_finds_readme_architecture_section(tmp_path: Path) -> None:
    """The README often carries an `## Architecture` section that's the only
    place decisions live in small projects."""
    (tmp_path / "README.md").write_text(
        "# My App\n\n"
        "Some intro paragraph.\n\n"
        "## Architecture\n\n"
        "We use a layered approach: presentation, domain, data.\n\n"
        "## Installation\n\n"
        "Run npm install.\n",
        encoding="utf-8",
    )
    result = harvest_decision_log(tmp_path)
    assert result is not None
    # Section content should be in the harvest, but not the unrelated ones.
    assert "layered approach" in result.content
    assert "npm install" not in result.content
    assert result.source_path.startswith("README.md")


def test_harvest_decision_log_first_hit_wins(tmp_path: Path) -> None:
    """When multiple sources exist, the highest-priority one is used.
    docs/adr/ outranks README."""
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "0001-x.md").write_text(
        "# 1. X\n\nADR content here.\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "# App\n\n## Architecture\n\nReadme content here.\n", encoding="utf-8"
    )
    result = harvest_decision_log(tmp_path)
    assert result is not None
    assert result.source_path == "docs/adr"
    assert "ADR content here" in result.content
    assert "Readme content here" not in result.content


def test_harvest_decision_log_returns_none_when_readme_lacks_architecture_section(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# App\n\nJust an intro and install instructions.\n\n"
        "## Installation\n\nRun npm install.\n",
        encoding="utf-8",
    )
    result = harvest_decision_log(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# conventions harvesting
# ---------------------------------------------------------------------------


def test_harvest_conventions_returns_none_when_no_source(tmp_path: Path) -> None:
    result = harvest_conventions(tmp_path)
    assert result is None


def test_harvest_conventions_finds_contributing_md(tmp_path: Path) -> None:
    body = (
        "# Contributing\n\n"
        "## Code style\n\n"
        "We use 2-space indentation and Prettier defaults.\n\n"
        "## Naming\n\n"
        "Components: PascalCase. Hooks: useFooBar.\n"
    )
    (tmp_path / "CONTRIBUTING.md").write_text(body, encoding="utf-8")
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert "PascalCase" in result.content
    assert result.source_path == "CONTRIBUTING.md"


def test_harvest_conventions_finds_styleguide_md(tmp_path: Path) -> None:
    (tmp_path / "STYLEGUIDE.md").write_text(
        "# Styleguide\n\nUse arrow functions for components.\n",
        encoding="utf-8",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert "arrow functions" in result.content
    assert result.source_path == "STYLEGUIDE.md"


def test_harvest_conventions_finds_docs_conventions_md(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "conventions.md").write_text(
        "# Project Conventions\n\nAvoid default exports.\n", encoding="utf-8"
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert "default exports" in result.content


def test_harvest_conventions_finds_readme_conventions_section(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# App\n\n## Code style\n\n"
        "Lint with eslint-config-airbnb. Format with prettier.\n\n"
        "## Installation\n\nRun npm install.\n",
        encoding="utf-8",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert "eslint-config-airbnb" in result.content
    assert "npm install" not in result.content


def test_harvest_conventions_finds_agents_md_section(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS playbook\n\n## Conventions\n\nNo any types in TypeScript.\n\n"
        "## Random\n\nUnrelated paragraph.\n",
        encoding="utf-8",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert "No any types" in result.content


def test_harvest_conventions_priority_contributing_outranks_readme(tmp_path: Path) -> None:
    """When a dedicated CONTRIBUTING.md exists, prefer it over a README section
    — the dedicated file is typically richer."""
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nUse Prettier from CONTRIBUTING.\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "# App\n\n## Code style\n\nReadme says use eslint-airbnb.\n",
        encoding="utf-8",
    )
    result = harvest_conventions(tmp_path)
    assert result is not None
    assert result.source_path == "CONTRIBUTING.md"
    assert "Prettier from CONTRIBUTING" in result.content
    assert "eslint-airbnb" not in result.content


def test_harvest_conventions_returns_none_when_readme_lacks_relevant_sections(
    tmp_path: Path,
) -> None:
    """README without a Conventions / Code style / Architecture rules / DO NOT
    section is not a conventions source."""
    (tmp_path / "README.md").write_text(
        "# App\n\nJust an intro paragraph and install steps.\n",
        encoding="utf-8",
    )
    result = harvest_conventions(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Integration with generate() — wiring through to written artifacts
# ---------------------------------------------------------------------------


def test_harvested_decisions_land_in_decision_log_md(tmp_path: Path) -> None:
    """End-to-end: docs/adr/ exists → harvested entries appear verbatim in
    .shipwright/agent_docs/decision_log.md, with an attribution header
    pointing back to the source. Adopt's own ADR-0001 still appears."""
    import json
    import subprocess

    from tools.generate_adoption_artifacts import generate

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=tmp_path, check=True,
    )
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "0001-record-architecture-decisions.md").write_text(
        "# 1. Record architecture decisions\n\n"
        "## Status\n\nAccepted\n\n"
        "## Context\n\nUSER-AUTHORED-ADR-CONTENT\n",
        encoding="utf-8",
    )
    (adr_dir / "0002-pick-postgres.md").write_text(
        "# 2. Pick Postgres\n\nWHY-WE-PICKED-POSTGRES\n",
        encoding="utf-8",
    )
    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [],
        "git": {"commits_total": 0, "contributors_total": 0,
                "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")

    generate(
        tmp_path,
        snapshot_path=snap_dir / "snapshot.json",
        enrichment_path=snap_dir / "enrichment.json",
        routes_path=snap_dir / "routes.json",
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )

    decision_log = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(
        encoding="utf-8"
    )
    # Adopt's own ADR-0001 still anchors the file.
    assert "ADR-0001: Adopt this repository into the Shipwright SDLC" in decision_log
    # Prior-art content lifted verbatim.
    assert "USER-AUTHORED-ADR-CONTENT" in decision_log
    assert "WHY-WE-PICKED-POSTGRES" in decision_log
    # Attribution header documents the source path.
    assert "docs/adr" in decision_log


def test_harvested_conventions_land_in_conventions_md(tmp_path: Path) -> None:
    """End-to-end: CONTRIBUTING.md exists → its content lands in
    .shipwright/agent_docs/conventions.md after the auto-detected linter
    block, with an Imported-from header."""
    import json
    import subprocess

    from tools.generate_adoption_artifacts import generate

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=tmp_path, check=True,
    )
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\n"
        "## Code style\n\n"
        "USE-PRETTIER-AT-100-COLS\n"
        "## Naming\n\n"
        "COMPONENTS-ARE-PASCAL-CASE\n",
        encoding="utf-8",
    )
    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [],
        "git": {"commits_total": 0, "contributors_total": 0,
                "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {"linter": "eslint"},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")

    generate(
        tmp_path,
        snapshot_path=snap_dir / "snapshot.json",
        enrichment_path=snap_dir / "enrichment.json",
        routes_path=snap_dir / "routes.json",
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )

    conventions = (tmp_path / ".shipwright" / "agent_docs" / "conventions.md").read_text(
        encoding="utf-8"
    )
    # Auto-detected linter block still rendered.
    assert "eslint" in conventions
    # Imported content lifted verbatim, after the auto block.
    assert "USE-PRETTIER-AT-100-COLS" in conventions
    assert "COMPONENTS-ARE-PASCAL-CASE" in conventions
    # Attribution header points back to the source file.
    assert "CONTRIBUTING.md" in conventions
    assert "Imported from" in conventions
    # Imported section comes AFTER the auto block (auto block first).
    auto_pos = conventions.find("Linter / Formatter")
    imported_pos = conventions.find("Imported from")
    assert 0 < auto_pos < imported_pos


def test_no_prior_art_falls_back_to_today_behavior(tmp_path: Path) -> None:
    """When no prior art exists, the harvest is a silent no-op and adopt
    writes the historical scaffold-only output. No `Imported from` header,
    no broken attribution."""
    import json
    import subprocess

    from tools.generate_adoption_artifacts import generate

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=tmp_path, check=True,
    )
    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [],
        "git": {"commits_total": 0, "contributors_total": 0,
                "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")

    generate(
        tmp_path,
        snapshot_path=snap_dir / "snapshot.json",
        enrichment_path=snap_dir / "enrichment.json",
        routes_path=snap_dir / "routes.json",
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )

    decision_log = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(
        encoding="utf-8"
    )
    conventions = (tmp_path / ".shipwright" / "agent_docs" / "conventions.md").read_text(
        encoding="utf-8"
    )
    # Adopt scaffold ADR-0001 only — no Imported decisions section.
    assert "ADR-0001" in decision_log
    assert "Imported decisions" not in decision_log
    assert "Imported from" not in conventions
