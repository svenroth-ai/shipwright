"""Cross-link to user-facing docs (Fix 4).

After adopt, /shipwright-iterate should be able to discover the existing
docs without a human pointing at them. The simplest signal: a `## See also`
section in `architecture.md` (and a similar block in `build_dashboard.md`
for CHANGELOG.md). Only emit links to files that actually exist; never
emit broken links.
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


def _write_inputs(project_root: Path) -> tuple[Path, Path, Path]:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snap_dir / "snapshot.json"
    snapshot.write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [{"route": "/", "source_file": "src/index.ts", "framework": "express"}],
        "git": {"commits_total": 0, "contributors_total": 0, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")
    return snapshot, snap_dir / "enrichment.json", snap_dir / "routes.json"


def _run(project_root: Path) -> None:
    snap, enr, rts = _write_inputs(project_root)
    generate(
        project_root,
        snapshot_path=snap, enrichment_path=enr, routes_path=rts,
        split_name="01-adopted", plugin_version="0.2.0",
        scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )


def test_architecture_links_to_readme_when_present(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "README.md").write_text("# App\n\nIntro.\n", encoding="utf-8")
    _run(tmp_path)
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "## See also" in arch
    assert "README.md" in arch


def test_architecture_links_to_substantive_guide(tmp_path: Path) -> None:
    """A docs/guide.md with >100 non-empty lines is non-trivial — link it."""
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    body = "\n".join(f"line {i}: explanation of feature" for i in range(120))
    (tmp_path / "docs" / "guide.md").write_text(body, encoding="utf-8")
    _run(tmp_path)
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "docs/guide.md" in arch


def test_architecture_skips_thin_guide(tmp_path: Path) -> None:
    """A docs/guide.md with <100 lines is not yet substantive enough."""
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nTODO\n", encoding="utf-8")
    _run(tmp_path)
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "docs/guide.md" not in arch


def test_architecture_links_alternative_doc_filenames(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "docs").mkdir()
    body = "\n".join(f"manual line {i}" for i in range(150))
    (tmp_path / "docs" / "handbook.md").write_text(body, encoding="utf-8")
    _run(tmp_path)
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    assert "docs/handbook.md" in arch


def test_no_broken_links_emitted(tmp_path: Path) -> None:
    """When no user-facing docs exist beyond an absent README, the section
    is omitted entirely — no half-empty `## See also`, no broken bullets."""
    _git_init(tmp_path)
    _run(tmp_path)
    arch = (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").read_text(
        encoding="utf-8"
    )
    # No See also section because nothing to link.
    assert "## See also" not in arch


def test_build_dashboard_links_changelog_when_present(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n- Stuff happened\n",
        encoding="utf-8",
    )
    _run(tmp_path)
    dash = (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(
        encoding="utf-8"
    )
    assert "CHANGELOG.md" in dash


def test_build_dashboard_omits_changelog_section_when_absent(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _run(tmp_path)
    dash = (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").read_text(
        encoding="utf-8"
    )
    assert "CHANGELOG.md" not in dash
