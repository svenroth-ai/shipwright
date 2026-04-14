"""Tests for data_collector.py."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.data_collector import (
    ComplianceData,
    DecisionEntry,
    ExternalReviewState,
    SectionInfo,
    SplitInfo,
    collect_all,
    collect_configs,
    collect_decision_log,
    collect_dependencies,
    collect_external_review_states,
    collect_sections,
    collect_splits,
)


class TestCollectConfigs:
    def test_reads_all_configs(self, project_root: Path):
        configs = collect_configs(project_root)
        assert "run" in configs
        assert "project" in configs
        assert "plan" in configs
        assert "build" in configs
        assert configs["run"]["scope"] == "full_app"
        assert configs["project"]["profile"] == "supabase-nextjs"

    def test_missing_configs_return_empty_dict(self, empty_project_root: Path):
        configs = collect_configs(empty_project_root)
        assert configs["run"] == {}
        assert configs["project"] == {}

    def test_partial_configs(self, partial_project_root: Path):
        configs = collect_configs(partial_project_root)
        assert configs["project"] != {}
        assert configs["build"] == {}


class TestCollectSplits:
    def test_reads_splits_from_project_config(self, project_root: Path):
        splits = collect_splits(project_root)
        assert len(splits) == 3
        assert splits[0].name == "01-auth"
        assert splits[0].status == "complete"
        assert splits[2].name == "03-settings"

    def test_no_project_config(self, empty_project_root: Path):
        splits = collect_splits(empty_project_root)
        assert splits == []

    def test_split_info_type(self, project_root: Path):
        splits = collect_splits(project_root)
        assert isinstance(splits[0], SplitInfo)


class TestCollectSections:
    def test_reads_sections_from_build_config(self, project_root: Path):
        sections = collect_sections(project_root)
        assert len(sections) == 3
        # Sections are mapped to current_split from build config
        current = [s for s in sections if s.split == "01-auth"]
        assert len(current) == 3
        login = next(s for s in sections if s.name == "01-login")
        assert login.commit == "abc123def456"
        assert login.tests_passed == 5
        assert login.tests_total == 5

    def test_review_findings_counted(self, project_root: Path):
        sections = collect_sections(project_root)
        by_name = {s.name: s for s in sections}
        # 01-login has 1 finding
        assert by_name["01-login"].review_findings == 1
        assert by_name["01-login"].review_findings_fixed == 1
        # 02-rbac has 0 findings
        assert by_name["02-rbac"].review_findings == 0
        # 03-profile has 2 findings (1 fixed, 1 deferred)
        assert by_name["03-profile"].review_findings == 2
        assert by_name["03-profile"].review_findings_fixed == 1

    def test_no_build_config(self, empty_project_root: Path):
        sections = collect_sections(empty_project_root)
        assert sections == []

    def test_section_info_type(self, project_root: Path):
        sections = collect_sections(project_root)
        assert isinstance(sections[0], SectionInfo)

    def test_multi_split_sections(self, tmp_path: Path):
        """Archived split_NN_sections are read alongside current sections."""
        root = tmp_path / "multi-split"
        root.mkdir()

        # Project config with two splits
        (root / "shipwright_project_config.json").write_text(json.dumps({
            "splits": [
                {"name": "01-auth", "status": "complete"},
                {"name": "02-dashboard", "status": "in_progress"},
            ],
        }), encoding="utf-8")

        # Build config with archived + current sections
        (root / "shipwright_build_config.json").write_text(json.dumps({
            "current_split": "02-dashboard",
            "completed_splits": ["01-auth"],
            "split_01_sections": [
                {"name": "01-login", "status": "complete", "commit": "aaa",
                 "tests_passed": 5, "tests_total": 5},
            ],
            "sections": [
                {"name": "01-widgets", "status": "complete", "commit": "bbb",
                 "tests_passed": 8, "tests_total": 8},
            ],
        }), encoding="utf-8")

        sections = collect_sections(root)
        assert len(sections) == 2

        by_name = {s.name: s for s in sections}
        assert by_name["01-login"].split == "01-auth"
        assert by_name["01-login"].tests_passed == 5
        assert by_name["01-widgets"].split == "02-dashboard"
        assert by_name["01-widgets"].tests_passed == 8


class TestCollectDecisionLog:
    def test_parses_decision_entries(self, project_root: Path):
        entries = collect_decision_log(project_root)
        assert len(entries) == 5

    def test_first_entry_details(self, project_root: Path):
        entries = collect_decision_log(project_root)
        entry = entries[0]
        assert entry.section == "01-login"
        assert "2026-03-20" in entry.timestamp
        assert entry.commit == "abc123"
        assert len(entry.decisions) == 1
        assert entry.decisions[0]["decision"] == "Use Supabase Auth with magic link"
        assert "password" in entry.decisions[0]["context"].lower()
        assert "Password auth" in entry.decisions[0]["rejected"]

    def test_rbac_entries(self, project_root: Path):
        entries = collect_decision_log(project_root)
        rbac = [e for e in entries if e.section == "02-rbac"]
        assert len(rbac) == 2
        assert rbac[0].decisions[0]["decision"] == "Implement RLS policies in Supabase"

    def test_no_decision_log(self, empty_project_root: Path):
        entries = collect_decision_log(empty_project_root)
        assert entries == []

    def test_entry_type(self, project_root: Path):
        entries = collect_decision_log(project_root)
        assert isinstance(entries[0], DecisionEntry)


class TestCollectDependencies:
    def test_reads_npm_dependencies(self, project_root: Path):
        deps = collect_dependencies(project_root)
        runtime = [d for d in deps if d.dep_type == "runtime"]
        dev = [d for d in deps if d.dep_type == "dev"]
        assert len(runtime) == 8
        assert len(dev) == 5

    def test_dependency_names(self, project_root: Path):
        deps = collect_dependencies(project_root)
        names = [d.name for d in deps]
        assert "next" in names
        assert "react" in names
        assert "vitest" in names

    def test_dependency_versions(self, project_root: Path):
        deps = collect_dependencies(project_root)
        next_dep = next(d for d in deps if d.name == "next")
        assert next_dep.version == "16.2.0"

    def test_no_package_json(self, empty_project_root: Path):
        deps = collect_dependencies(empty_project_root)
        assert deps == []

    def test_license_unknown_without_node_modules(self, project_root: Path):
        deps = collect_dependencies(project_root)
        # No node_modules in fixture, so license should be unknown
        assert all(d.license == "unknown" for d in deps)


class TestCollectExternalReviewStates:
    def _seed_split(self, root: Path, split: str, marker: dict | None) -> None:
        split_dir = root / "planning" / split
        split_dir.mkdir(parents=True, exist_ok=True)
        if marker is not None:
            (split_dir / "external_review_state.json").write_text(json.dumps(marker))

    def test_returns_empty_when_no_planning_dir(self, tmp_path: Path):
        root = tmp_path / "proj"
        root.mkdir()
        assert collect_external_review_states(root) == []

    def test_reads_completed_marker(self, tmp_path: Path):
        root = tmp_path / "proj"
        self._seed_split(root, "01-auth", {
            "status": "completed",
            "provider": "openrouter",
            "findings_count": 5,
            "self_review_fallback_ran": False,
            "reason": None,
            "timestamp": "2026-04-14T12:00:00Z",
        })
        states = collect_external_review_states(root)
        assert len(states) == 1
        s = states[0]
        assert s.split == "01-auth"
        assert s.status == "completed"
        assert s.provider == "openrouter"
        assert s.findings_count == 5
        assert s.self_review_fallback_ran is False

    def test_reads_opt_out_marker(self, tmp_path: Path):
        root = tmp_path / "proj"
        self._seed_split(root, "02-api", {
            "status": "skipped_user_opt_out",
            "provider": None,
            "findings_count": 0,
            "self_review_fallback_ran": True,
            "reason": "offline demo",
            "timestamp": "2026-04-14T13:00:00Z",
        })
        states = collect_external_review_states(root)
        assert states[0].status == "skipped_user_opt_out"
        assert states[0].reason == "offline demo"
        assert states[0].self_review_fallback_ran is True

    def test_missing_marker_reported_as_missing(self, tmp_path: Path):
        root = tmp_path / "proj"
        self._seed_split(root, "01-auth", marker=None)
        states = collect_external_review_states(root)
        assert len(states) == 1
        assert states[0].status == "missing"

    def test_skips_iterate_subdirectory(self, tmp_path: Path):
        root = tmp_path / "proj"
        self._seed_split(root, "01-auth", {"status": "completed"})
        self._seed_split(root, "iterate", {"status": "completed"})
        states = collect_external_review_states(root)
        splits = {s.split for s in states}
        assert splits == {"01-auth"}

    def test_corrupt_marker_reported_as_missing(self, tmp_path: Path):
        root = tmp_path / "proj"
        split_dir = root / "planning" / "01-auth"
        split_dir.mkdir(parents=True)
        (split_dir / "external_review_state.json").write_text("{not valid json")
        states = collect_external_review_states(root)
        assert states[0].status == "missing"


class TestCollectAll:
    def test_returns_compliance_data(self, project_root: Path):
        data = collect_all(project_root)
        assert isinstance(data, ComplianceData)
        assert data.project_root == project_root.resolve()
        assert len(data.splits) == 3
        assert len(data.sections) == 3
        assert len(data.decisions) == 5
        assert len(data.dependencies) == 13
        assert data.timestamp  # not empty

    def test_empty_project(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        assert data.splits == []
        assert data.sections == []
        assert data.decisions == []
        assert data.dependencies == []
