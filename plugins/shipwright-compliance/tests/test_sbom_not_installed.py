"""SBOM: 'not installed' vs 'no declared license' distinction.

iterate-2026-06-07-sbom-not-installed-vs-undeclared. Two non-license outcomes
are kept apart on purpose:

- ``NOT_INSTALLED`` — package not resolvable in the scan env (no ``.venv``
  dist-info / no lockfile+node_modules). A scan artifact, not a repo property:
  stays silent (no triage, ``—`` in the doc, excluded from counts/verdict).
- ``UNKNOWN_LICENSE`` — package resolved but declares no license. A genuine
  concern: triaged + surfaced in the doc.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.collectors import NOT_INSTALLED, UNKNOWN_LICENSE
from scripts.lib.data_collector import (
    ComplianceData,
    DependencyInfo,
    _detect_npm_license,
    _detect_python_license,
    collect_undeclared_by_workspace,
)
from scripts.lib.sbom_generator import generate


def _py_distinfo(manifest_dir: Path, name: str, metadata: str, version: str = "1.0.0") -> None:
    di = manifest_dir / ".venv" / "Lib" / "site-packages" / f"{name}-{version}.dist-info"
    di.mkdir(parents=True, exist_ok=True)
    (di / "METADATA").write_text(metadata, encoding="utf-8")


def _npm_lock(manifest_dir: Path, packages: dict) -> None:
    (manifest_dir / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": packages}), encoding="utf-8")


def _data(deps: list[DependencyInfo]) -> ComplianceData:
    d = ComplianceData(project_root=Path("."))
    d.dependencies = deps
    d.timestamp = "2026-06-07T00:00:00Z"
    return d


class TestPythonResolverDistinction:
    """AC-1."""

    def test_no_venv_is_not_installed(self, tmp_path: Path):
        assert _detect_python_license("anything", tmp_path) == NOT_INSTALLED

    def test_distinfo_absent_is_not_installed(self, tmp_path: Path):
        _py_distinfo(tmp_path, "other", "Metadata-Version: 2.1\nName: other\nLicense: MIT\n")
        assert _detect_python_license("ghost", tmp_path) == NOT_INSTALLED

    def test_distinfo_present_no_license_is_unknown(self, tmp_path: Path):
        _py_distinfo(tmp_path, "fake", "Metadata-Version: 2.1\nName: fake\nVersion: 1.0.0\n")
        assert _detect_python_license("fake", tmp_path) == UNKNOWN_LICENSE

    def test_distinfo_present_with_license_resolves(self, tmp_path: Path):
        _py_distinfo(tmp_path, "fake", "Metadata-Version: 2.1\nName: fake\nLicense: MIT\n")
        assert _detect_python_license("fake", tmp_path) == "MIT"


class TestNpmResolverDistinction:
    """AC-2."""

    def test_no_lockfile_no_node_modules_is_not_installed(self, tmp_path: Path):
        assert _detect_npm_license(tmp_path, "ghost") == NOT_INSTALLED

    def test_lockfile_present_no_license_is_unknown(self, tmp_path: Path):
        _npm_lock(tmp_path, {"node_modules/foo": {"version": "1.0.0"}})
        assert _detect_npm_license(tmp_path, "foo") == UNKNOWN_LICENSE

    def test_lockfile_present_with_license_resolves(self, tmp_path: Path):
        _npm_lock(tmp_path, {"node_modules/foo": {"version": "1.0.0", "license": "MIT"}})
        assert _detect_npm_license(tmp_path, "foo") == "MIT"

    def test_lockfile_blank_spdx_object_is_unknown(self, tmp_path: Path):
        # Present in lockfile but license is a blank SPDX object → Fall 2, not a
        # bogus empty "resolved" license (review Finding 2).
        _npm_lock(tmp_path, {"node_modules/foo": {"license": {"type": "  "}}})
        assert _detect_npm_license(tmp_path, "foo") == UNKNOWN_LICENSE

    def test_node_modules_present_no_license_is_unknown(self, tmp_path: Path):
        nm = tmp_path / "node_modules" / "foo"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({"name": "foo"}), encoding="utf-8")
        assert _detect_npm_license(tmp_path, "foo") == UNKNOWN_LICENSE


class TestCollectorSilence:
    """AC-3: NOT_INSTALLED never becomes a triage group; Fall 2 does."""

    def test_not_installed_python_emits_no_group(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            'dependencies = [\n  "ghost-xyz>=1.0",\n]\n', encoding="utf-8")
        assert collect_undeclared_by_workspace(tmp_path) == []

    def test_not_installed_npm_emits_no_group(self, tmp_path: Path):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"ghost": "^1.0.0"}}), encoding="utf-8")
        assert collect_undeclared_by_workspace(tmp_path) == []

    def test_genuine_no_license_python_emits_group(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text(
            'dependencies = [\n  "fake>=1.0",\n]\n', encoding="utf-8")
        _py_distinfo(tmp_path, "fake", "Metadata-Version: 2.1\nName: fake\nVersion: 1.0.0\n")
        groups = collect_undeclared_by_workspace(tmp_path)
        assert [g["manifest_type"] for g in groups] == ["python"]
        assert groups[0]["undeclared"][0]["name"] == "fake"


class TestDocSemantics:
    """AC-5 / AC-6 / AC-7 / AC-8."""

    def test_not_installed_rendered_as_dash_and_excluded(self):
        deps = [
            DependencyInfo("real", "1.0.0", "runtime", "MIT"),
            DependencyInfo("ghost", "1.0.0", "runtime", NOT_INSTALLED),
        ]
        result = generate(_data(deps))
        assert "| ghost | 1.0.0 | - |" in result      # neutral ASCII, not a license
        assert "not-installed" not in result          # sentinel never leaks
        assert "## Unknown Licenses" not in result
        assert "## Dependencies Without a Declared License" not in result
        assert "| Unique licenses | 1 (MIT) |" in result  # sentinel excluded

    def test_genuine_no_license_surfaced_as_section(self):
        deps = [DependencyInfo("nolic", "1.0.0", "runtime", UNKNOWN_LICENSE)]
        result = generate(_data(deps))
        assert "## Dependencies Without a Declared License" in result
        assert "nolic" in result
        assert "declare no license" in result

    def test_doc_is_ascii_even_with_fall2_deps(self):
        # The artifact is consumed by cp1252-default tooling; the Fall-2 path
        # must not leak non-ASCII (review Finding 1: em-dash regression guard).
        deps = [
            DependencyInfo("nolic", "1.0.0", "runtime", UNKNOWN_LICENSE),
            DependencyInfo("ghost", "1.0.0", "runtime", NOT_INSTALLED),
            DependencyInfo("real", "1.0.0", "runtime", "MIT"),
        ]
        generate(_data(deps)).encode("ascii")  # raises UnicodeEncodeError if non-ASCII

    def test_verdict_clean_when_all_permissive(self):
        deps = [DependencyInfo("real", "1.0.0", "runtime", "MIT")]
        result = generate(_data(deps))
        assert "No license concerns" in result

    def test_verdict_nothing_resolved_when_all_not_installed(self):
        deps = [DependencyInfo("ghost", "1.0.0", "runtime", NOT_INSTALLED)]
        result = generate(_data(deps))
        assert "No dependency licenses were resolved in this scan." in result
        assert "No license concerns" not in result

    def test_no_scan_coverage_or_install_nag(self):
        deps = [DependencyInfo("ghost", "1.0.0", "runtime", NOT_INSTALLED)]
        result = generate(_data(deps))
        assert "uv sync" not in result
        assert "regenerate" not in result.lower()
        assert "coverage" not in result.lower()
