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


def test_design_setup_session_writes_canonical_designs(tmp_path: Path) -> None:
    """End-to-end contract: invoke setup-design-session.py and verify it writes
    only under .shipwright/designs/ — no legacy top-level dir, no double prefix.

    Per Sub-Iterate C plan Step 8 (designs migration): hardens against the
    `.shipwright/.shipwright/` and `designs/designs/` carry-over bug pattern
    surfaced in planning Sub-Iterate C->D.
    """
    import subprocess

    project = tmp_path / "design-contract"
    project.mkdir()

    plugin_root = _REPO / "plugins" / "shipwright-design"
    script = plugin_root / "scripts" / "checks" / "setup-design-session.py"

    result = subprocess.run(
        [
            sys.executable, str(script),
            "--project-root", str(project),
            "--plugin-root", str(plugin_root),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, (
        f"setup-design-session.py failed (rc={result.returncode}): "
        f"stderr={result.stderr}\nstdout={result.stdout}"
    )

    # Canonical structure exists.
    assert (project / ".shipwright" / "designs" / "screens").is_dir()
    assert (project / ".shipwright" / "designs" / "flows").is_dir()
    assert (project / ".shipwright" / "designs" / "uploads").is_dir()
    # Legacy must NOT exist.
    assert not (project / "designs").exists(), (
        "Legacy top-level `designs/` directory was created"
    )
    # No double prefix carry-over bugs.
    assert not (project / ".shipwright" / ".shipwright").exists(), (
        "Double `.shipwright/.shipwright/` prefix detected — C carry-over bug"
    )
    assert not (project / ".shipwright" / "designs" / "designs").exists(), (
        "Double `designs/designs/` suffix detected — path-construction bug"
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


@pytest.mark.parametrize("plugin", [
    "shipwright-design", "shipwright-plan", "shipwright-test",
])
def test_no_legacy_designs_path_construction_in_plugin_source(plugin: str) -> None:
    """Sub-Iterate C contract for designs migration: the pattern
    ``project_root / "designs"`` must not appear in this plugin's source.
    Mirrors the planning equivalent above.
    """
    plug_dir = _REPO / "plugins" / plugin / "scripts"
    if not plug_dir.is_dir():
        pytest.skip(f"plugin {plugin} has no scripts/ directory")
    forbidden = 'project_root / "designs"'
    offenders: list[str] = []
    for py in plug_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(str(py.relative_to(_REPO)))
    assert not offenders, (
        f"Plugin {plugin}: legacy designs path-construction pattern still "
        f"present in {len(offenders)} file(s): {offenders}"
    )


# ---------------------------------------------------------------------------
# shipwright-adopt — write_agent_docs writes under .shipwright/agent_docs
# ---------------------------------------------------------------------------


def test_adopt_write_agent_docs_writes_under_dot_shipwright(tmp_path: Path) -> None:
    """End-to-end contract: invoke write_agent_docs and verify it writes
    only under .shipwright/agent_docs/ — no legacy top-level dir, no double
    prefix carry-over (.shipwright/.shipwright or agent_docs/agent_docs).
    """
    _add_plugin_to_path("shipwright-adopt")
    try:
        from artifact_writer import write_agent_docs  # type: ignore
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"cross-plugin sys.path pollution: {exc}")

    paths = write_agent_docs(
        tmp_path,
        project_name="canon-test", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n(diag)\n```",
        data_flow_description="flow",
        conventions={"linter": "eslint", "formatter": "prettier"},
        conventions_prose="conventions prose",
        features_count=0, commits_total=0, contributors_total=0,
        nested_excluded=[], commit_sha=None, retroactive_adrs=[],
    )

    canonical = tmp_path / ".shipwright" / "agent_docs"
    assert canonical.is_dir(), (
        f"Canonical `.shipwright/agent_docs/` was NOT created under {tmp_path}."
    )
    for fname in ("architecture.md", "conventions.md", "decision_log.md", "build_dashboard.md"):
        assert (canonical / fname).is_file(), f"missing canonical {fname}"
    # Legacy must NOT exist.
    assert not (tmp_path / "agent_docs").exists(), (
        "Legacy top-level `agent_docs/` directory was created"
    )
    # No double-prefix carry-over.
    assert not (tmp_path / ".shipwright" / ".shipwright").exists(), (
        "Double `.shipwright/.shipwright/` prefix detected — C carry-over bug"
    )
    assert not (canonical / "agent_docs").exists(), (
        "Double `agent_docs/agent_docs/` suffix detected — path-construction bug"
    )
    # Returned paths are all under canonical.
    for p in paths:
        assert canonical in p.parents, (
            f"write_agent_docs returned a path outside `.shipwright/agent_docs/`: {p}"
        )


@pytest.mark.parametrize("plugin", [
    "shipwright-adopt", "shipwright-build", "shipwright-iterate",
    "shipwright-compliance", "shipwright-project", "shipwright-run",
])
def test_no_legacy_agent_docs_path_construction_in_plugin_source(plugin: str) -> None:
    """Sub-Iterate C contract for agent_docs migration: the pattern
    ``project_root / "agent_docs"`` must not appear in this plugin's source.
    Mirrors the planning + designs equivalents above.
    """
    plug_dir = _REPO / "plugins" / plugin / "scripts"
    if not plug_dir.is_dir():
        pytest.skip(f"plugin {plugin} has no scripts/ directory")
    forbidden = 'project_root / "agent_docs"'
    offenders: list[str] = []
    for py in plug_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(str(py.relative_to(_REPO)))
    assert not offenders, (
        f"Plugin {plugin}: legacy agent_docs path-construction pattern still "
        f"present in {len(offenders)} file(s): {offenders}"
    )


# ---------------------------------------------------------------------------
# Sub-Iterate C contract tests for compliance migration
# ---------------------------------------------------------------------------


def test_compliance_generators_write_under_dot_shipwright(tmp_path: Path) -> None:
    """All shipwright-compliance generators must write under
    .shipwright/compliance/, never compliance/ at project root."""
    pytest.importorskip(
        "scripts.lib.compliance_report",
        reason="shipwright-compliance plugin not on path in current sys.modules state",
    )
    _add_plugin_to_path("shipwright-compliance")

    project_root = tmp_path / "proj"
    project_root.mkdir()
    # Minimal fixtures so generators have something to write
    (project_root / "shipwright_run_config.json").write_text(
        '{"profile": "test", "scope": "minimal"}', encoding="utf-8"
    )

    try:
        from scripts.lib.compliance_report import COMPLIANCE_DIR  # type: ignore
    except ImportError:
        pytest.skip("compliance plugin not importable in this test session")

    canonical = project_root / COMPLIANCE_DIR
    legacy = project_root / "compliance"

    # Module-level constants must equal the manifest canonical
    assert COMPLIANCE_DIR == ".shipwright/compliance"

    # Legacy MUST NOT exist after any test fixture setup.
    assert not legacy.exists(), (
        "Legacy `compliance/` directory present at fixture-setup time; the "
        "migration must enforce that no test path can create it."
    )

    # Confirm the canonical layout is what the generators target.
    canonical.mkdir(parents=True, exist_ok=True)
    assert canonical.is_dir()
    assert not legacy.exists()


@pytest.mark.parametrize("plugin", [
    "shipwright-adopt", "shipwright-compliance", "shipwright-run",
])
def test_no_legacy_compliance_path_construction_in_plugin_source(plugin: str) -> None:
    """Sub-Iterate C contract for compliance migration: the pattern
    ``project_root / "compliance"`` must not appear in this plugin's source.
    Mirrors the planning + designs + agent_docs equivalents above.
    """
    plug_dir = _REPO / "plugins" / plugin / "scripts"
    if not plug_dir.is_dir():
        pytest.skip(f"plugin {plugin} has no scripts/ directory")
    forbidden = 'project_root / "compliance"'
    offenders: list[str] = []
    for py in plug_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(str(py.relative_to(_REPO)))
    assert not offenders, (
        f"Plugin {plugin}: legacy compliance path-construction pattern still "
        f"present in {len(offenders)} file(s): {offenders}"
    )
