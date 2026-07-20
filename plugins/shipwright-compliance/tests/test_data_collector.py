"""Tests for data_collector.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.lib.data_collector import (
    EVENT_FILE,
    ComplianceData,
    DecisionEntry,
    SectionInfo,
    SplitInfo,
    _resolve_events_path,
    collect_all,
    collect_configs,
    collect_decision_log,
    collect_dependencies,
    collect_events,
    collect_external_review_states,
    collect_sections,
    collect_splits,
)


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in ``cwd``, raising on failure."""
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


def _npm_lock_unlicensed(manifest_dir: Path, *names: str) -> None:
    """Seed a package-lock.json that lists ``names`` but declares NO license —
    i.e. resolved-but-no-license (Fall 2), the genuinely-undeclared case (NOT
    the not-installed scan artifact)."""
    (manifest_dir / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3,
                    "packages": {f"node_modules/{n}": {"version": "1.0.0"} for n in names}}),
        encoding="utf-8",
    )


def _py_distinfo_unlicensed(manifest_dir: Path, name: str, version: str = "1.0.0") -> None:
    """Seed a ``.venv`` dist-info whose METADATA declares no license (Fall 2)."""
    sp = manifest_dir / ".venv" / "Lib" / "site-packages" / f"{name}-{version}.dist-info"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8",
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

    def test_license_not_installed_without_node_modules(self, project_root: Path):
        deps = collect_dependencies(project_root)
        # No node_modules + no package-lock.json → not resolvable = NOT installed
        # (a scan artifact), NOT the genuine "unknown" (resolved-no-license) case.
        assert all(d.license == "not-installed" for d in deps)


class TestSbomLockfileAndWorkspace:
    """Phase 0f (artifact-polish plan): lockfile-first JS license resolution,
    importlib.metadata for Python, workspace-aware traversal."""

    def test_npm_lockfile_v3_license_read(self, tmp_path: Path):
        """package-lock.json (lockfileVersion 3) license field wins over fallback."""
        from scripts.lib.data_collector import _detect_npm_license  # type: ignore

        manifest_dir = tmp_path
        (manifest_dir / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
        )
        (manifest_dir / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "test"},
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        assert _detect_npm_license(manifest_dir, "react") == "MIT"

    def test_npm_lockfile_license_object_type(self, tmp_path: Path):
        """SPDX-object-form `{"type": "Apache-2.0"}` is unwrapped to string."""
        from scripts.lib.data_collector import _detect_npm_license  # type: ignore

        manifest_dir = tmp_path
        (manifest_dir / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/old-pkg": {
                        "version": "1.0.0", "license": {"type": "Apache-2.0"},
                    },
                },
            }),
            encoding="utf-8",
        )
        assert _detect_npm_license(manifest_dir, "old-pkg") == "Apache-2.0"

    def test_npm_falls_back_to_node_modules_when_no_lockfile(self, tmp_path: Path):
        """When no package-lock.json exists, fall back to node_modules/<pkg>/package.json."""
        from scripts.lib.data_collector import _detect_npm_license  # type: ignore

        manifest_dir = tmp_path
        nm = manifest_dir / "node_modules" / "react"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(
            json.dumps({"name": "react", "license": "MIT"}), encoding="utf-8"
        )
        assert _detect_npm_license(manifest_dir, "react") == "MIT"

    def test_npm_not_installed_when_neither_lockfile_nor_node_modules(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_npm_license  # type: ignore

        # Neither lockfile nor node_modules → not resolvable = NOT installed.
        assert _detect_npm_license(tmp_path, "ghost-pkg") == "not-installed"

    def test_python_license_resolver_requires_manifest_dir(self):
        """ADR-056 follow-up: the Python license resolver is pinned to a
        per-manifest .venv (no ambient sys.path probe). Calling it without
        a manifest_dir is a signature error after this iterate.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        import inspect
        sig = inspect.signature(_detect_python_license)
        assert "manifest_dir" in sig.parameters, (
            "_detect_python_license must take manifest_dir; ambient sys.path "
            "lookup via importlib.metadata is non-deterministic (ADR pending)."
        )

    def test_workspace_aware_traversal_finds_nested_manifests(self, tmp_path: Path):
        """Phase 0f: client/ + server/ split workspaces are discovered."""
        from scripts.lib.data_collector import collect_dependencies  # type: ignore

        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
        )
        (tmp_path / "server").mkdir()
        (tmp_path / "server" / "package.json").write_text(
            json.dumps({"dependencies": {"hono": "^4.0.0"}, "devDependencies": {"vitest": "^1.0.0"}}),
            encoding="utf-8",
        )
        deps = collect_dependencies(tmp_path)
        names = sorted(d.name for d in deps)
        assert names == ["hono", "react", "vitest"]

    def test_workspace_exclude_skips_node_modules_and_venv(self, tmp_path: Path):
        """node_modules / .venv / build / dist / .git / .shipwright are NOT traversed."""
        from scripts.lib.data_collector import collect_dependencies  # type: ignore

        for excluded in ["node_modules", ".venv", "dist", "build", ".shipwright"]:
            sub = tmp_path / excluded / "evil"
            sub.mkdir(parents=True)
            (sub / "package.json").write_text(
                json.dumps({"dependencies": {"poison": "^1.0.0"}}), encoding="utf-8"
            )
        deps = collect_dependencies(tmp_path)
        assert all(d.name != "poison" for d in deps), \
            "Manifests inside excluded dirs must NOT be picked up"

    def test_workspace_dedup_across_manifests(self, tmp_path: Path):
        """Same (name, version, dep_type) declared in two manifests → one row."""
        from scripts.lib.data_collector import collect_dependencies  # type: ignore

        for sub in ["client", "server"]:
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "package.json").write_text(
                json.dumps({"dependencies": {"shared-lib": "1.0.0"}}), encoding="utf-8"
            )
        deps = collect_dependencies(tmp_path)
        assert len([d for d in deps if d.name == "shared-lib"]) == 1


class TestPythonLicenseFromVenvMetadata:
    """ADR-056 follow-up: pin Python-license resolution to per-manifest
    .venv dist-info METADATA (NOT ambient sys.path via importlib.metadata).

    Mirrors d325fd6 (deterministic render timestamps): the resolver must
    derive its output from a stable input artifact, not process-Python
    state that varies between runs.
    """

    def _seed_distinfo(
        self,
        manifest_dir: Path,
        package: str,
        version: str,
        metadata_body: str,
        layout: str = "windows",
    ) -> Path:
        """Write a synthetic dist-info under ``<manifest_dir>/.venv``.

        ``layout="windows"`` writes to ``Lib/site-packages/``; ``layout="posix"``
        writes to ``lib/python3.11/site-packages/``. Both shapes are valid
        production layouts; the resolver globs across them.
        """
        if layout == "windows":
            sp = manifest_dir / ".venv" / "Lib" / "site-packages"
        elif layout == "posix":
            sp = manifest_dir / ".venv" / "lib" / "python3.11" / "site-packages"
        else:
            raise ValueError(f"unknown layout: {layout}")
        # PEP 503 normalization: hyphen → underscore in dist-info dir name.
        normalized = package.replace("-", "_")
        distinfo = sp / f"{normalized}-{version}.dist-info"
        distinfo.mkdir(parents=True, exist_ok=True)
        (distinfo / "METADATA").write_text(metadata_body, encoding="utf-8")
        return distinfo

    def test_reads_license_from_windows_layout(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: Apache-2.0\n",
            layout="windows",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "Apache-2.0"

    def test_reads_license_from_posix_layout(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: BSD-3-Clause\n",
            layout="posix",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "BSD-3-Clause"

    def test_returns_not_installed_when_no_venv(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # No .venv at all → NOT installed (scan artifact), deterministically.
        assert _detect_python_license("anything", tmp_path) == "not-installed"

    def test_returns_not_installed_when_no_matching_distinfo(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # .venv exists with some other package, but not the one queried → the
        # queried package was never resolved = NOT installed.
        self._seed_distinfo(
            tmp_path, "other-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: other-pkg\nVersion: 1.0.0\nLicense: MIT\n",
        )
        assert _detect_python_license("ghost-pkg", tmp_path) == "not-installed"

    def test_returns_unknown_when_metadata_has_no_license(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # METADATA exists but no License/License-Expression/Classifier.
        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "unknown"

    def test_treats_literal_unknown_as_unset(self, tmp_path: Path):
        """Some packages emit `License: UNKNOWN` — treat as missing."""
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: UNKNOWN\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "unknown"

    def test_prefers_license_field_over_license_expression(self, tmp_path: Path):
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.4\nName: fake-pkg\nVersion: 1.0.0\n"
            "License: MIT\nLicense-Expression: Apache-2.0\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "MIT"

    def test_falls_back_to_license_expression_when_no_license(self, tmp_path: Path):
        """PEP 639 License-Expression is the canonical PEP 621/639 field."""
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.4\nName: fake-pkg\nVersion: 1.0.0\n"
            "License-Expression: Apache-2.0\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "Apache-2.0"

    def test_falls_back_to_trove_classifier(self, tmp_path: Path):
        """Some packages encode license only via Trove classifiers."""
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\n"
            "Classifier: License :: OSI Approved :: MIT License\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "MIT"

    def test_one_line_clamps_multiline_license(self, tmp_path: Path):
        """RFC822 continuation lines must not bleed into the cell."""
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # PKG-INFO continuation: subsequent lines start with whitespace.
        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\n"
            "License: MIT\n"
            " (a verbose explanation that runs onto multiple lines\n"
            "  but stays inside the License header continuation block)\n",
        )
        result = _detect_python_license("fake-pkg", tmp_path)
        # One-line clamp; result must not contain a newline.
        assert "\n" not in result
        assert result.startswith("MIT")

    def test_resolver_ignores_ambient_sys_path(self, tmp_path: Path):
        """Root-cause probe: even if importlib.metadata can locate the
        package via the *process* Python's sys.path, the resolver MUST
        use the per-manifest .venv. Otherwise determinism is broken.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # No dist-info in the manifest .venv → must return 'not-installed',
        # regardless of whether the process Python has the package.
        # 'pytest' is in the process .venv (used to run THIS test).
        assert _detect_python_license("pytest", tmp_path) == "not-installed"

    def test_cross_manifest_isolation(self, tmp_path: Path):
        """Plugin A and Plugin B may declare the same package with
        different licenses. Each resolver call resolves to the right one.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        plugin_a = tmp_path / "plugin-a"
        plugin_b = tmp_path / "plugin-b"
        plugin_a.mkdir()
        plugin_b.mkdir()
        self._seed_distinfo(
            plugin_a, "shared-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: shared-pkg\nVersion: 1.0.0\nLicense: MIT\n",
        )
        self._seed_distinfo(
            plugin_b, "shared-pkg", "2.0.0",
            "Metadata-Version: 2.1\nName: shared-pkg\nVersion: 2.0.0\nLicense: Apache-2.0\n",
        )
        assert _detect_python_license("shared-pkg", plugin_a) == "MIT"
        assert _detect_python_license("shared-pkg", plugin_b) == "Apache-2.0"

    def test_resolver_deterministic_across_runs(self, tmp_path: Path):
        """Two consecutive calls with the same input filesystem state
        produce byte-identical output, regardless of process-Python
        state between calls (the core determinism contract).
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: Apache-2.0\n",
        )
        first = _detect_python_license("fake-pkg", tmp_path)
        second = _detect_python_license("fake-pkg", tmp_path)
        assert first == second == "Apache-2.0"

    def test_pep503_name_normalization(self, tmp_path: Path):
        """Package names normalize: 'google-genai' on disk is
        'google_genai-VERSION.dist-info'. The resolver must find both.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # Seed with underscore form (the wheel-installed form).
        self._seed_distinfo(
            tmp_path, "google-genai", "1.68.0",
            "Metadata-Version: 2.1\nName: google-genai\nVersion: 1.68.0\nLicense: Apache-2.0\n",
        )
        # Query with hyphen form (the pyproject.toml-declared form).
        assert _detect_python_license("google-genai", tmp_path) == "Apache-2.0"

    def test_collect_dependencies_uses_per_manifest_resolver(self, tmp_path: Path):
        """Integration: a pyproject.toml + populated .venv → DependencyInfo
        carries the per-manifest license, not 'unknown'.
        """
        from scripts.lib.data_collector import collect_dependencies  # type: ignore

        plugin = tmp_path / "plugins" / "demo"
        plugin.mkdir(parents=True)
        (plugin / "pyproject.toml").write_text(
            'dependencies = [\n  "requests>=2.0",\n  "google-genai>=1.0",\n]\n',
            encoding="utf-8",
        )
        # Seed both deps under the plugin's .venv (Windows layout).
        self._seed_distinfo(
            plugin, "requests", "2.33.0",
            "Metadata-Version: 2.1\nName: requests\nVersion: 2.33.0\nLicense: Apache-2.0\n",
        )
        self._seed_distinfo(
            plugin, "google-genai", "1.68.0",
            "Metadata-Version: 2.1\nName: google-genai\nVersion: 1.68.0\nLicense: Apache-2.0\n",
        )
        deps = collect_dependencies(tmp_path)
        license_by_name = {d.name: d.license for d in deps}
        assert license_by_name.get("requests") == "Apache-2.0"
        assert license_by_name.get("google-genai") == "Apache-2.0"

    def test_launch_payload_outcome_simulation(self, tmp_path: Path):
        """AC-7: Simulate the operator workflow. Before `uv sync` the
        plugin .venv has no dist-info → license=not-installed. After (simulated
        by seeding the dist-info), license resolves. The launch payload
        prescription is now empirically truthful.
        """
        from scripts.lib.data_collector import collect_dependencies  # type: ignore

        plugin = tmp_path / "plugins" / "demo"
        plugin.mkdir(parents=True)
        (plugin / "pyproject.toml").write_text(
            'dependencies = [\n  "requests>=2.0",\n]\n', encoding="utf-8",
        )
        # Before `uv sync`: no .venv → not-installed (scan artifact).
        before = collect_dependencies(tmp_path)
        assert next(d for d in before if d.name == "requests").license == "not-installed"
        # After `uv sync` (simulated): dist-info present → resolves.
        self._seed_distinfo(
            plugin, "requests", "2.33.0",
            "Metadata-Version: 2.1\nName: requests\nVersion: 2.33.0\nLicense: Apache-2.0\n",
        )
        after = collect_dependencies(tmp_path)
        assert next(d for d in after if d.name == "requests").license == "Apache-2.0"

    def test_pep503_normalization_dotted_name(self, tmp_path: Path):
        """Gemini HIGH-1: PEP 503 normalizes `[-_.]+` runs uniformly.

        A package declared as `ruamel.yaml` must resolve to a dist-info
        named `ruamel_yaml-VERSION.dist-info`. Plain `replace("-", "_")`
        breaks this.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "ruamel.yaml", "0.18.5",
            "Metadata-Version: 2.1\nName: ruamel.yaml\nVersion: 0.18.5\nLicense: MIT\n",
        )
        assert _detect_python_license("ruamel.yaml", tmp_path) == "MIT"

    def test_pep503_normalization_case_insensitive(self, tmp_path: Path):
        """PEP 503 canonical name is lowercase. `Foo-Bar` in pyproject
        resolves to `foo_bar-*.dist-info` on disk.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # Seed lowercase (the canonical wheel-installed form).
        self._seed_distinfo(
            tmp_path, "foo-bar", "1.0.0",
            "Metadata-Version: 2.1\nName: foo-bar\nVersion: 1.0.0\nLicense: MIT\n",
        )
        # Query with mixed case (pyproject author may declare any case).
        assert _detect_python_license("Foo-Bar", tmp_path) == "MIT"

    def test_multiple_distinfo_picks_deterministically(self, tmp_path: Path):
        """OpenAI HIGH-2: stale dist-info dirs (uncommon but possible)
        must be resolved deterministically — the resolver picks a stable
        candidate, not a filesystem-walk-order artifact.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # Two dist-info dirs for the same normalized package.
        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: MIT\n",
        )
        self._seed_distinfo(
            tmp_path, "fake-pkg", "2.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 2.0.0\nLicense: Apache-2.0\n",
        )
        result = _detect_python_license("fake-pkg", tmp_path)
        assert result == "Apache-2.0", (
            "Expected resolver to pick highest-versioned dist-info when "
            "multiple exist; got: " + repr(result)
        )

    def test_multiple_distinfo_uses_semver_not_lexicographic(self, tmp_path: Path):
        """Code-review HIGH-1: lexicographic dir-name sort puts
        `pkg-10.0.0.dist-info` BEFORE `pkg-2.0.0.dist-info`, so a naive
        `sorted()[-1]` picks the wrong dist-info. Version comparison
        must be semver-aware so 10.0.0 > 2.0.0 (it should).
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "2.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 2.0.0\nLicense: MIT\n",
        )
        self._seed_distinfo(
            tmp_path, "fake-pkg", "10.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 10.0.0\nLicense: Apache-2.0\n",
        )
        result = _detect_python_license("fake-pkg", tmp_path)
        assert result == "Apache-2.0", (
            "Expected resolver to pick 10.0.0 (numerically highest) over "
            "2.0.0; lexicographic sort would return the wrong answer here. "
            "Got: " + repr(result)
        )

    def test_utf8_encoding_for_metadata(self, tmp_path: Path):
        """Gemini MEDIUM-3: METADATA must be read as utf-8. On Windows
        the default encoding is cp1252; a METADATA file with non-ASCII
        (Author names, descriptions) would raise UnicodeDecodeError and
        crash SBOM generation.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        # Author name with non-ASCII (typical real-world case).
        metadata_body = (
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\n"
            "Author: Ömer Sözer\n"  # Ö, ö
            "License: Apache-2.0\n"
        )
        self._seed_distinfo(tmp_path, "fake-pkg", "1.0.0", metadata_body)
        assert _detect_python_license("fake-pkg", tmp_path) == "Apache-2.0"

    def test_multiple_classifiers_finds_license_classifier(self, tmp_path: Path):
        """Gemini MEDIUM-2: real METADATA has many Classifier headers;
        the license one is rarely first. Parser must use get_all, not get.
        """
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\n"
            "Classifier: Development Status :: 5 - Production/Stable\n"
            "Classifier: Intended Audience :: Developers\n"
            "Classifier: License :: OSI Approved :: BSD License\n"
            "Classifier: Programming Language :: Python :: 3\n",
        )
        assert _detect_python_license("fake-pkg", tmp_path) == "BSD"

    def test_filesystem_error_returns_unknown(self, tmp_path: Path, monkeypatch):
        """OpenAI MEDIUM-8: a permission error / unreadable METADATA
        must NOT crash SBOM generation. Return 'unknown' gracefully.
        """
        from scripts.lib import data_collector as dc  # type: ignore

        self._seed_distinfo(
            tmp_path, "fake-pkg", "1.0.0",
            "Metadata-Version: 2.1\nName: fake-pkg\nVersion: 1.0.0\nLicense: MIT\n",
        )

        # Detonate METADATA read with PermissionError.
        original_read = Path.read_text

        def _broken_read(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            if self.name == "METADATA":
                raise PermissionError("simulated unreadable METADATA")
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", _broken_read)
        # Must NOT raise; must return 'unknown'.
        assert dc._detect_python_license("fake-pkg", tmp_path) == "unknown"

    def test_no_importlib_metadata_call_in_resolver_path(self, monkeypatch, tmp_path: Path):
        """Anti-regression probe: the resolver MUST NOT fall back to
        importlib.metadata. If a future refactor accidentally restores
        the ambient-sys.path path, this test catches it by detonating
        every call site.
        """
        from importlib import metadata as _metadata
        from scripts.lib.data_collector import _detect_python_license  # type: ignore

        def _detonate(*args, **kwargs):
            raise AssertionError(
                "_detect_python_license must not call importlib.metadata."
            )

        monkeypatch.setattr(_metadata, "metadata", _detonate)
        monkeypatch.setattr(_metadata, "distribution", _detonate)
        # If the resolver still calls importlib.metadata, this errors;
        # otherwise it returns 'not-installed' (no .venv seeded).
        assert _detect_python_license("anything", tmp_path) == "not-installed"


class TestCollectUndeclaredByWorkspace:
    """Iterate B.2 (ADR-056) — per-workspace grouping for SBOM triage."""

    def test_returns_empty_when_no_manifests(self, tmp_path: Path):
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        assert collect_undeclared_by_workspace(tmp_path) == []

    def test_omits_workspace_with_all_licenses_resolved(self, tmp_path: Path):
        """A package-lock.json resolving every dep → group skipped."""
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
        )
        (tmp_path / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "test"},
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        assert collect_undeclared_by_workspace(tmp_path) == []

    def test_npm_workspace_with_undeclared_emits_group(self, tmp_path: Path):
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "package.json").write_text(
            json.dumps({
                "dependencies": {"react": "^19.0.0"},
                "devDependencies": {"vitest": "^1.0.0"},
            }),
            encoding="utf-8",
        )
        # Resolved (present in lockfile) but no license declared → Fall 2.
        _npm_lock_unlicensed(tmp_path / "client", "react", "vitest")
        groups = collect_undeclared_by_workspace(tmp_path)
        assert len(groups) == 1
        group = groups[0]
        assert group["manifest_rel_path"] == "client/package.json"
        assert group["manifest_type"] == "npm"
        names = sorted(d["name"] for d in group["undeclared"])
        assert names == ["react", "vitest"]

    def test_python_workspace_with_undeclared_emits_group(self, tmp_path: Path):
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        (tmp_path / "pyproject.toml").write_text(
            'dependencies = [\n  "definitely-not-a-real-pypi-package-xyz>=1.0.0",\n]\n',
            encoding="utf-8",
        )
        # Installed (dist-info present) but METADATA declares no license → Fall 2.
        _py_distinfo_unlicensed(tmp_path, "definitely-not-a-real-pypi-package-xyz")
        groups = collect_undeclared_by_workspace(tmp_path)
        assert len(groups) == 1
        group = groups[0]
        assert group["manifest_rel_path"] == "pyproject.toml"
        assert group["manifest_type"] == "python"
        assert any(d["name"] == "definitely-not-a-real-pypi-package-xyz"
                   for d in group["undeclared"])

    def test_uses_forward_slash_paths_on_all_platforms(self, tmp_path: Path):
        """Dedup-key stability requires POSIX-style relative paths."""
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        (tmp_path / "apps" / "web").mkdir(parents=True)
        (tmp_path / "apps" / "web" / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
        )
        _npm_lock_unlicensed(tmp_path / "apps" / "web", "react")
        groups = collect_undeclared_by_workspace(tmp_path)
        assert groups[0]["manifest_rel_path"] == "apps/web/package.json"
        assert "\\" not in groups[0]["manifest_rel_path"]

    def test_excludes_node_modules_and_venv(self, tmp_path: Path):
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        for excluded in ["node_modules", ".venv", "dist", "build", ".shipwright"]:
            sub = tmp_path / excluded / "evil"
            sub.mkdir(parents=True)
            (sub / "package.json").write_text(
                json.dumps({"dependencies": {"poison": "^1.0.0"}}), encoding="utf-8"
            )
        groups = collect_undeclared_by_workspace(tmp_path)
        assert groups == []

    def test_malformed_manifest_is_skipped(self, tmp_path: Path):
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        (tmp_path / "package.json").write_text("not-valid-json", encoding="utf-8")
        assert collect_undeclared_by_workspace(tmp_path) == []

    def test_non_dict_dependencies_section_is_skipped(self, tmp_path: Path):
        """Reviewer-flagged M1: a package.json with `dependencies: []` shouldn't crash."""
        from scripts.lib.data_collector import collect_undeclared_by_workspace  # type: ignore

        # Valid JSON, but `dependencies` is a list instead of an object.
        (tmp_path / "client").mkdir()
        (tmp_path / "client" / "package.json").write_text(
            json.dumps({"dependencies": ["this", "should", "be", "an", "object"],
                        "devDependencies": {"vitest": "^1.0.0"}}),
            encoding="utf-8",
        )
        _npm_lock_unlicensed(tmp_path / "client", "vitest")
        # Must NOT crash; the bad section is skipped, the good one is scanned.
        groups = collect_undeclared_by_workspace(tmp_path)
        assert len(groups) == 1
        names = [d["name"] for d in groups[0]["undeclared"]]
        assert names == ["vitest"]


class TestCollectExternalReviewStates:
    def _seed_split(self, root: Path, split: str, marker: dict | None) -> None:
        split_dir = root / ".shipwright" / "planning" / split
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
        split_dir = root / ".shipwright" / "planning" / "01-auth"
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


class TestEventLogWorktreeResolution:
    """Event-log resolution is a literal per-tree join.

    shipwright_events.jsonl is a **version-controlled, per-tree artifact**: a
    ``/shipwright-iterate`` run writes its ``work_completed`` event into the
    worktree's own copy (F5b) and commits it via F6, so it ships through the
    PR. data_collector must therefore read the WORKTREE's own log
    (``project_root / EVENT_FILE``) — NOT redirect to the main repo.

    Flipped from the old ``git rev-parse --git-common-dir`` redirect in
    iterate-2026-05-29-events-jsonl-worktree-commit: that redirect orphaned the
    event as an uncommitted line in the main tree, outside the iterate PR.
    """

    EVENT_LINE = json.dumps({
        "id": "evt-test-0001",
        "type": "work_completed",
        "source": "iterate",
        "ts": "2026-05-15T12:00:00Z",
        "commit": "abc123",
        "affected_frs": ["FR-01.01"],
        "tests": {"passed": 3, "total": 3},
    })

    def _init_repo(self, root: Path) -> None:
        """Create a git repo with one commit (required for `worktree add`)."""
        root.mkdir(parents=True, exist_ok=True)
        _git(["init"], root)
        _git(["config", "user.email", "test@example.com"], root)
        _git(["config", "user.name", "Test"], root)
        (root / "README.md").write_text("seed\n", encoding="utf-8")
        _git(["add", "README.md"], root)
        _git(["commit", "-m", "seed"], root)

    def test_worktree_reads_its_own_event_log(self, tmp_path: Path):
        """Collection from inside a worktree reads the WORKTREE's own log —
        not the main repo's. A decoy event in the main tree must NOT leak in."""
        main = tmp_path / "main-repo"
        self._init_repo(main)
        # Decoy in the main repo — proves resolution does NOT redirect to main.
        decoy = json.dumps({
            "id": "evt-main-decoy", "type": "work_completed",
            "source": "iterate", "ts": "2026-05-01T00:00:00Z",
            "commit": "deadbeef", "affected_frs": ["FR-99.99"],
        })
        (main / EVENT_FILE).write_text(decoy + "\n", encoding="utf-8")

        worktree = tmp_path / "wt"
        _git(["worktree", "add", str(worktree)], main)

        # The iterate writes its event into the worktree's OWN copy (F5b),
        # which F6 commits and the PR carries.
        (worktree / EVENT_FILE).write_text(self.EVENT_LINE + "\n", encoding="utf-8")

        assert _resolve_events_path(worktree) == worktree / EVENT_FILE
        work_events, _, _ = collect_events(worktree)
        assert len(work_events) == 1
        assert work_events[0].id == "evt-test-0001"
        assert work_events[0].affected_frs == ["FR-01.01"]

    def test_main_repo_reads_own_event_log(self, tmp_path: Path):
        """Non-worktree (plain repo) behavior is unchanged: reads its own log."""
        main = tmp_path / "main-repo"
        self._init_repo(main)
        (main / EVENT_FILE).write_text(self.EVENT_LINE + "\n", encoding="utf-8")

        assert _resolve_events_path(main) == main / EVENT_FILE
        work_events, _, _ = collect_events(main)
        assert len(work_events) == 1
        assert work_events[0].id == "evt-test-0001"

    def test_non_git_dir_falls_back_to_project_root(self, tmp_path: Path):
        """Outside any git repo, resolution falls back to project_root/EVENT_FILE."""
        proj = tmp_path / "plain"
        proj.mkdir()
        (proj / EVENT_FILE).write_text(self.EVENT_LINE + "\n", encoding="utf-8")

        assert _resolve_events_path(proj) == proj / EVENT_FILE
        work_events, _, _ = collect_events(proj)
        assert len(work_events) == 1
