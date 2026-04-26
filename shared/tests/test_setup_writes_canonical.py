"""Layer 2: per-plugin setup-contract tests.

Negative-assertion tests that exercise each plugin's path-constructing
entry points and verify they:
1. Write to ``.shipwright/planning/`` (canonical post-migration location).
2. Do NOT create a legacy ``planning/`` directory at the project root.

These are the safety net that catches any code path which accidentally
writes to the legacy location — even if other tests pass with mocked
or fixture-driven paths.

Plugins covered:
- shipwright-design: setup-design-session.py reads planning specs
- shipwright-adopt: artifact_writer + config_writer write splits + config
- shipwright-iterate: campaign_init writes campaign artifacts
- shipwright-compliance: data_collector reads requirements
- shipwright-run: phase_validators reads plan/design/section state
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]


def _add_plugin_to_path(plugin_name: str) -> None:
    """Insert plugin's scripts/ on sys.path so plugin lib modules import.

    Caveat: every plugin defines its own ``lib/`` and ``tools/`` subpackage;
    when run in the full shared/ test suite, sys.modules may already hold a
    different plugin's ``lib`` namespace. Tests that touch path-namespace
    collisions are guarded by ``importorskip`` so the suite stays green.
    """
    plug_scripts = _REPO / "plugins" / plugin_name / "scripts"
    if plug_scripts.is_dir():
        for sub in (plug_scripts, plug_scripts / "lib", plug_scripts / "tools"):
            if sub.is_dir() and str(sub) not in sys.path:
                sys.path.insert(0, str(sub))


def _assert_no_legacy_planning(project_root: Path) -> None:
    legacy = project_root / "planning"
    assert not legacy.exists(), (
        f"Legacy `planning/` directory was created at {legacy}. "
        f"Migration violation: writer is still using the pre-migration path."
    )


def _assert_canonical_planning_exists(project_root: Path) -> None:
    canonical = project_root / ".shipwright" / "planning"
    assert canonical.is_dir(), (
        f"Canonical `.shipwright/planning/` was NOT created under {project_root}. "
        f"Migration regression: writer did not honor the new path."
    )


# ---------------------------------------------------------------------------
# shipwright-adopt — artifact_writer.write_split_spec
# ---------------------------------------------------------------------------


def test_adopt_artifact_writer_writes_under_dot_shipwright(tmp_path: Path) -> None:
    _add_plugin_to_path("shipwright-adopt")
    try:
        from artifact_writer import write_spec  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"cross-plugin sys.path pollution: {exc}")

    spec_path = write_spec(
        tmp_path,
        project_name="contract-test",
        split_name="01-adopted",
        product_description="Sample project for migration safety net.",
        features=[
            {"id": "FR-01.01", "name": "auth", "priority": "Must"},
        ],
        qr_items=["NFR-01: 99% uptime"],
        constraints=["Python 3.11+"],
    )

    _assert_no_legacy_planning(tmp_path)
    _assert_canonical_planning_exists(tmp_path)
    assert spec_path == tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    assert spec_path.is_file()


def test_adopt_config_writer_emits_canonical_planning_dir(tmp_path: Path) -> None:
    _add_plugin_to_path("shipwright-adopt")
    try:
        from config_writer import write_project_config  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"cross-plugin sys.path pollution: {exc}")

    config_path = write_project_config(
        tmp_path,
        scope="full_app",
        profile="custom",
        split_name="01-adopted",
        fr_count=3,
        qr_count=2,
    )
    import json
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["planning_dir"] == ".shipwright/planning", (
        f"Adopt config_writer must emit `.shipwright/planning` as planning_dir; "
        f"got {config['planning_dir']!r}"
    )


# ---------------------------------------------------------------------------
# shipwright-iterate — campaign_init.init_campaign
# ---------------------------------------------------------------------------


def test_iterate_campaign_init_writes_under_dot_shipwright(tmp_path: Path) -> None:
    _add_plugin_to_path("shipwright-iterate")
    try:
        from campaign_init import init_campaign  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"cross-plugin sys.path pollution: {exc}")

    result = init_campaign(
        project_root=tmp_path,
        campaign_slug="test-campaign",
        intent="Migration safety net contract test.",
        sub_iterates=[
            {"id": "A", "slug": "first", "title": "first iterate", "scope": "noop"},
            {"id": "B", "slug": "second", "title": "second iterate", "scope": "noop"},
        ],
    )

    _assert_no_legacy_planning(tmp_path)
    _assert_canonical_planning_exists(tmp_path)
    expected = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / "test-campaign"
    assert expected.is_dir()
    assert (expected / "campaign.md").is_file()
    # init_campaign returns dict with paths; verify it points under .shipwright
    for key in ("campaign_dir", "campaign_md"):
        if key in result:
            assert ".shipwright/planning" in str(result[key]).replace("\\", "/")


# ---------------------------------------------------------------------------
# shipwright-design — setup-design-session.find_specs
# ---------------------------------------------------------------------------


def test_design_setup_session_reads_canonical_planning() -> None:
    """Source-level smoke: setup-design-session.py constructs the canonical path."""
    src = _REPO / "plugins" / "shipwright-design" / "scripts" / "checks" / "setup-design-session.py"
    text = src.read_text(encoding="utf-8")
    assert 'project_root / "planning"' not in text, (
        "setup-design-session.py still constructs the legacy `planning/` path"
    )
    assert 'project_root / ".shipwright" / "planning"' in text, (
        "setup-design-session.py must use the canonical `.shipwright/planning/` path"
    )


# ---------------------------------------------------------------------------
# shipwright-compliance — data_collector.collect_requirements
# ---------------------------------------------------------------------------


def test_compliance_collect_requirements_reads_canonical(tmp_path: Path) -> None:
    _add_plugin_to_path("shipwright-compliance")
    try:
        from data_collector import collect_requirements  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"cross-plugin sys.path pollution: {exc}")

    canonical = tmp_path / ".shipwright" / "planning" / "01-auth"
    canonical.mkdir(parents=True)
    (canonical / "spec.md").write_text(
        "| FR-01.01 | login required | Must |\n", encoding="utf-8"
    )

    legacy = tmp_path / "planning" / "01-stale"
    legacy.mkdir(parents=True)
    (legacy / "spec.md").write_text(
        "| FR-99.99 | should be ignored | Must |\n", encoding="utf-8"
    )

    reqs = collect_requirements(tmp_path)
    fr_ids = {r.id for r in reqs}
    assert "FR-01.01" in fr_ids
    assert "FR-99.99" not in fr_ids, (
        "Compliance data_collector picked up a legacy planning/ FR — should read "
        "only from .shipwright/planning/."
    )


# ---------------------------------------------------------------------------
# shipwright-run — phase_validators._validate_project (spec.md lookup)
# ---------------------------------------------------------------------------


def test_run_phase_validator_looks_under_canonical(tmp_path: Path) -> None:
    """phase_validators reads spec.md at <root>/.shipwright/planning/<split>/."""
    src = _REPO / "plugins" / "shipwright-run" / "scripts" / "lib" / "phase_validators.py"
    text = src.read_text(encoding="utf-8")
    # Smoke check: assert the legacy literal `project_root / "planning"` no
    # longer appears as a path-construction site.
    assert 'project_root / "planning"' not in text, (
        "shipwright-run/phase_validators.py still constructs the legacy path"
    )
    assert 'project_root / ".shipwright" / "planning"' in text, (
        "shipwright-run/phase_validators.py must use the canonical path"
    )


# ---------------------------------------------------------------------------
# Repo-wide negative assertion: nothing under shared/scripts/ writes to
# legacy `planning/` at the top level (catches refactor regressions).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plugin", [
    "shipwright-adopt", "shipwright-design", "shipwright-iterate",
    "shipwright-compliance", "shipwright-run",
])
def test_no_legacy_path_construction_in_plugin_source(plugin: str) -> None:
    """Greenfield-safe smoke: the pattern ``project_root / "planning"`` (Path
    division to the legacy literal) must not appear in this plugin's source.
    """
    plug_dir = _REPO / "plugins" / plugin / "scripts"
    if not plug_dir.is_dir():
        pytest.skip(f"plugin {plugin} has no scripts/ directory")
    forbidden = 'project_root / "planning"'
    offenders: list[str] = []
    for py in plug_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(str(py.relative_to(_REPO)))
    assert not offenders, (
        f"Plugin {plugin}: legacy path-construction pattern still present in "
        f"{len(offenders)} file(s): {offenders}"
    )
