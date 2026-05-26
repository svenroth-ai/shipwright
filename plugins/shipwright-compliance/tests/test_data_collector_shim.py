"""Back-compat shim contract — Campaign-B B2.

The B2 split moved every collector into ``scripts/lib/collectors/``;
``scripts/lib/data_collector.py`` is now a re-export shim. This test
pins the shim's public surface so a future refactor that drops a
re-exported symbol fails loudly here — not silently in some
downstream caller that uses the symbol but does NOT have its own
test coverage.

Mirrors the OpenAI/Gemini review concern (regression: shim coverage)
captured in the iterate ADR under "External-Code-Review-Findings".
"""

from __future__ import annotations


def test_public_dataclasses_resolve_through_shim():
    """The 12 public dataclasses must still be importable from the shim."""
    from scripts.lib.data_collector import (
        CommitEntry,
        ComplianceData,
        DecisionEntry,
        DependencyInfo,
        ExternalReviewState,
        KnownFailure,
        RequirementInfo,
        SectionInfo,
        SplitInfo,
        TestResults,
        TestRunEvent,
        WorkEvent,
    )

    # Smoke: every class is a real class.
    for cls in (
        CommitEntry, ComplianceData, DecisionEntry, DependencyInfo,
        ExternalReviewState, KnownFailure, RequirementInfo, SectionInfo,
        SplitInfo, TestResults, TestRunEvent, WorkEvent,
    ):
        assert isinstance(cls, type), cls


def test_public_collectors_resolve_through_shim():
    """Every public ``collect_*`` is reachable from the legacy shim path."""
    from scripts.lib.data_collector import (
        collect_all,
        collect_configs,
        collect_decision_log,
        collect_dependencies,
        collect_events,
        collect_external_review_states,
        collect_git_history,
        collect_known_failures,
        collect_requirements,
        collect_sections,
        collect_splits,
        collect_test_files,
        collect_test_results,
        collect_undeclared_by_workspace,
    )

    for fn in (
        collect_all, collect_configs, collect_decision_log,
        collect_dependencies, collect_events, collect_external_review_states,
        collect_git_history, collect_known_failures, collect_requirements,
        collect_sections, collect_splits, collect_test_files,
        collect_test_results, collect_undeclared_by_workspace,
    ):
        assert callable(fn), fn


def test_constants_resolve_through_shim():
    """``CONFIG_FILES`` + ``EVENT_FILE`` literals stay on the legacy surface."""
    from scripts.lib.data_collector import CONFIG_FILES, EVENT_FILE

    assert isinstance(CONFIG_FILES, dict)
    assert {"run", "project", "plan", "build"} <= set(CONFIG_FILES.keys())
    assert EVENT_FILE == "shipwright_events.jsonl"


def test_private_helpers_resolve_through_shim():
    """The legacy private-but-probed helpers stay reachable.

    External tests reach into these (notably the SBOM test patches
    ``data_collector.collect_undeclared_by_workspace`` and the
    determinism test imports ``_read_event_log``). Pin them here so a
    silent regression on the shim is caught early.
    """
    from scripts.lib.data_collector import (
        _apply_amendments,
        _detect_npm_license,
        _detect_python_license,
        _latest_event_timestamp,
        _parse_pyproject_deps,
        _read_event_log,
        _read_npm_lockfile_licenses,
        _resolve_events_path,
        _sections_from_data,
        _map_requirements_to_events,
        _map_requirements_to_sections,
    )

    for fn in (
        _apply_amendments, _detect_npm_license, _detect_python_license,
        _latest_event_timestamp, _parse_pyproject_deps, _read_event_log,
        _read_npm_lockfile_licenses, _resolve_events_path,
        _sections_from_data, _map_requirements_to_events,
        _map_requirements_to_sections,
    ):
        assert callable(fn), fn


def test_shim_and_package_collect_all_are_same_callable():
    """The shim's ``collect_all`` IS the package's — not a wrapper."""
    from scripts.lib.collectors import collect_all as pkg_collect_all
    from scripts.lib.data_collector import collect_all as shim_collect_all

    assert shim_collect_all is pkg_collect_all


def test_contract_reexport_still_works():
    """``shared.contracts.compliance`` is the cross-plugin entrypoint
    (Campaign-B B8). Its re-export of ``collect_all`` must still
    resolve through the shim after the B2 split.
    """
    # Bootstrap shared/contracts on sys.path the same way contracts does.
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root))
    try:
        from shared.contracts.compliance import (  # noqa: E402
            ComplianceData,
            collect_all,
        )
    finally:
        sys.path.remove(str(repo_root))

    assert callable(collect_all)
    assert isinstance(ComplianceData, type)
