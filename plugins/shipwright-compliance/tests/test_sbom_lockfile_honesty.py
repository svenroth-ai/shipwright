"""AR-04 SBOM data quality / honesty (iterate-2026-06-28-sbom-honesty): version
+ dedup from ``uv.lock``, license across ALL ``.venv``s, honest summary/pie/
verdict counting ALL packages, ASCII output. Triage producer unchanged."""

from __future__ import annotations

from pathlib import Path

from scripts.lib.collectors import DependencyInfo, NOT_INSTALLED, UNKNOWN_LICENSE
from scripts.lib.collectors._python_license import parse_pyproject_dep_specs
from scripts.lib.collectors._uv_lock import load_lock_versions
from scripts.lib.collectors._venv_scan import (
    detect_python_license_across,
    iter_all_site_packages,
)
from scripts.lib.collectors.sbom import collect_dependencies
from scripts.lib.data_collector import ComplianceData, collect_all
from scripts.lib.sbom_generator import generate
from scripts.lib.sbom_render import (
    is_copyleft,
    license_cell,
    license_compliance_lines,
    summary_lines,
)


# --------------------------------------------------------------------------- #
# seed helpers
# --------------------------------------------------------------------------- #
def _pyproject(d: Path, runtime=(), dev=()) -> None:
    d.mkdir(parents=True, exist_ok=True)
    lines = ['[project]', 'name = "x"', "dependencies = ["]
    lines += [f'  "{r}",' for r in runtime]
    lines.append("]")
    if dev:
        lines += ["[project.optional-dependencies]", "dev = ["]
        lines += [f'  "{v}",' for v in dev]
        lines.append("]")
    (d / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _uv_lock(d: Path, pkgs: dict) -> None:
    blocks = ["version = 1", ""]
    for name, ver in pkgs.items():
        blocks += [
            "[[package]]",
            f'name = "{name}"',
            f'version = "{ver}"',
            'source = { registry = "https://pypi.org/simple" }',
            "",
        ]
    (d / "uv.lock").write_text("\n".join(blocks), encoding="utf-8")


def _distinfo(workspace: Path, name: str, version: str, license_line: str = "") -> None:
    di = workspace / ".venv" / "Lib" / "site-packages" / f"{name}-{version}.dist-info"
    di.mkdir(parents=True, exist_ok=True)
    meta = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    if license_line:
        meta += license_line + "\n"
    (di / "METADATA").write_text(meta, encoding="utf-8")


def _data(deps: list[DependencyInfo], *, deduped: int = 0, lock: bool = False) -> ComplianceData:
    d = ComplianceData(project_root=Path("."))
    d.dependencies = deps
    d.dependencies_deduped = deduped
    d.dependencies_lock_resolved = lock
    d.timestamp = "2026-06-28T00:00:00Z"
    return d


# --------------------------------------------------------------------------- #
# uv.lock parsing
# --------------------------------------------------------------------------- #
class TestLoadLockVersions:
    def test_maps_canonical_names(self, tmp_path: Path):
        _uv_lock(tmp_path, {"openai": "2.30.0", "google-genai": "1.68.0"})
        m = load_lock_versions(tmp_path)
        assert m["openai"] == "2.30.0"
        assert m["google-genai"] == "1.68.0"

    def test_canonicalizes_separators(self, tmp_path: Path):
        _uv_lock(tmp_path, {"PyYAML": "6.0.3"})
        assert load_lock_versions(tmp_path)["pyyaml"] == "6.0.3"

    def test_missing_lock_is_empty(self, tmp_path: Path):
        assert load_lock_versions(tmp_path) == {}

    def test_malformed_lock_is_empty(self, tmp_path: Path):
        (tmp_path / "uv.lock").write_text("this is not toml = = [", encoding="utf-8")
        assert load_lock_versions(tmp_path) == {}


# --------------------------------------------------------------------------- #
# version-from-lock + dedup by installed version
# --------------------------------------------------------------------------- #
class TestDedupByInstalledVersion:
    def test_openai_collapses_to_one_installed_version(self, tmp_path: Path):
        """The headline AR-04 bug: openai>=2.30.0 (root) + openai>=1.0.0 (plan)
        both lock to 2.30.0 -> ONE row, not two."""
        _pyproject(tmp_path, runtime=["openai>=2.30.0"])
        _uv_lock(tmp_path, {"openai": "2.30.0"})
        _distinfo(tmp_path, "openai", "2.30.0", "License: Apache-2.0")
        _pyproject(tmp_path / "plugins" / "plan", runtime=["openai>=1.0.0"])
        _uv_lock(tmp_path / "plugins" / "plan", {"openai": "2.30.0"})

        rows = [d for d in collect_dependencies(tmp_path) if d.name == "openai"]
        assert len(rows) == 1
        assert rows[0].version == "2.30.0"          # installed, not the >=1.0.0 floor
        assert rows[0].license == "Apache-2.0"

    def test_dedup_survives_one_missing_lock_via_global_union(self, tmp_path: Path):
        # Code-review finding #1: one manifest's uv.lock missing/stale -> the
        # project-wide union still resolves the version, so openai stays ONE row.
        _pyproject(tmp_path, runtime=["openai>=2.30.0"])
        _uv_lock(tmp_path, {"openai": "2.30.0"})           # root lock present
        _distinfo(tmp_path, "openai", "2.30.0", "License: Apache-2.0")
        _pyproject(tmp_path / "plugins" / "plan", runtime=["openai>=1.0.0"])
        # plan/uv.lock intentionally ABSENT -> would fall back to floor 1.0.0
        rows = [d for d in collect_dependencies(tmp_path) if d.name == "openai"]
        assert len(rows) == 1                              # still ONE row
        assert rows[0].version == "2.30.0"                 # from the union, not the floor

    def test_version_comes_from_lock_not_floor(self, tmp_path: Path):
        _pyproject(tmp_path, runtime=["google-genai>=1.0.0"])
        _uv_lock(tmp_path, {"google-genai": "1.68.0"})
        _distinfo(tmp_path, "google_genai", "1.68.0", "License: Apache-2.0")
        gg = [d for d in collect_dependencies(tmp_path) if d.name == "google-genai"][0]
        assert gg.version == "1.68.0"               # lock, not floor 1.0.0

    def test_floor_used_when_no_lock(self, tmp_path: Path):
        _pyproject(tmp_path, runtime=["requests>=2.31.0"])
        # no uv.lock
        req = [d for d in collect_dependencies(tmp_path) if d.name == "requests"][0]
        assert req.version == "2.31.0"              # graceful fallback to floor


# --------------------------------------------------------------------------- #
# global (all-venv) license resolution
# --------------------------------------------------------------------------- #
class TestGlobalLicenseResolution:
    def test_resolves_from_a_sibling_workspace_venv(self, tmp_path: Path):
        # requests declared at root (empty root venv) but installed in a sibling
        # workspace venv -> the global scan resolves it (root-cause fix for `-`).
        _pyproject(tmp_path, runtime=["requests>=2.31.0"])
        _uv_lock(tmp_path, {"requests": "2.33.0"})
        _distinfo(tmp_path / "plugins" / "other", "requests", "2.33.0", "License: Apache-2.0")
        req = [d for d in collect_dependencies(tmp_path) if d.name == "requests"][0]
        assert req.version == "2.33.0"
        assert req.license == "Apache-2.0"

    def test_not_installed_anywhere_is_not_installed(self, tmp_path: Path):
        sps = iter_all_site_packages(tmp_path)
        assert detect_python_license_across("ghost", sps) == NOT_INSTALLED

    def test_installed_without_license_is_unknown(self, tmp_path: Path):
        _distinfo(tmp_path, "fake", "1.0.0")  # METADATA has no License
        sps = iter_all_site_packages(tmp_path)
        assert detect_python_license_across("fake", sps) == UNKNOWN_LICENSE

    def test_real_license_anywhere_wins_over_unknown(self, tmp_path: Path):
        # installed-no-license in one venv, installed-with-license in another
        _distinfo(tmp_path / "a", "dup", "1.0.0")
        _distinfo(tmp_path / "b", "dup", "1.0.0", "License: MIT")
        sps = iter_all_site_packages(tmp_path)
        assert detect_python_license_across("dup", sps) == "MIT"


class TestParsePyprojectDepSpecs:
    def test_returns_name_floor_type(self, tmp_path: Path):
        _pyproject(tmp_path, runtime=["openai>=2.30.0"], dev=["pytest>=8.0.0"])
        specs = parse_pyproject_dep_specs(tmp_path / "pyproject.toml")
        assert ("openai", "2.30.0", "runtime") in specs
        assert ("pytest", "8.0.0", "dev") in specs


# --------------------------------------------------------------------------- #
# ComplianceData flags + collect_all wiring
# --------------------------------------------------------------------------- #
class TestCollectAllFlags:
    def test_dedup_and_lock_flags_set(self, tmp_path: Path):
        _pyproject(tmp_path, runtime=["openai>=2.30.0"])
        _uv_lock(tmp_path, {"openai": "2.30.0"})
        _distinfo(tmp_path, "openai", "2.30.0", "License: Apache-2.0")
        _pyproject(tmp_path / "plugins" / "plan", runtime=["openai>=1.0.0"])
        _uv_lock(tmp_path / "plugins" / "plan", {"openai": "2.30.0"})
        data = collect_all(tmp_path)
        assert data.dependencies_deduped >= 1
        assert data.dependencies_lock_resolved is True

    def test_flags_default_false_without_lock(self, tmp_path: Path):
        _pyproject(tmp_path, runtime=["requests>=2.31.0"])
        data = collect_all(tmp_path)
        assert data.dependencies_deduped == 0
        assert data.dependencies_lock_resolved is False


# --------------------------------------------------------------------------- #
# honest generator output (ASCII-only)
# --------------------------------------------------------------------------- #
class TestHonestRender:
    def test_summary_has_licenses_resolved_row(self):
        deps = [
            DependencyInfo("a", "1.0", "runtime", "MIT"),
            DependencyInfo("b", "1.0", "runtime", NOT_INSTALLED),
        ]
        out = generate(_data(deps))
        assert "| Licenses resolved | 1 / 2 |" in out

    def test_runtime_count_annotated_when_deduped(self):
        deps = [DependencyInfo("a", "1.0", "runtime", "MIT")]
        out = generate(_data(deps, deduped=1))
        assert "(deduplicated)" in out

    def test_runtime_count_plain_when_not_deduped(self):
        deps = [DependencyInfo("a", "1.0", "runtime", "MIT")]
        out = generate(_data(deps, deduped=0))
        assert "(deduplicated)" not in out

    def test_header_notes_lock_resolution(self):
        deps = [DependencyInfo("a", "1.0", "runtime", "MIT")]
        out = generate(_data(deps, lock=True))
        assert "resolved from uv.lock" in out

    def test_pie_counts_all_packages(self):
        deps = [
            DependencyInfo("a", "1.0", "runtime", "MIT"),
            DependencyInfo("b", "1.0", "runtime", NOT_INSTALLED),
        ]
        out = generate(_data(deps))
        assert "(all 2 packages)" in out
        assert '"unknown" : 1' in out

    def test_clean_verdict_when_all_resolved(self):
        deps = [DependencyInfo("a", "1.0", "runtime", "MIT")]
        out = generate(_data(deps))
        assert "No license concerns: all 1 packages resolved (0 unknown, 0 copyleft)." in out

    def test_dishonest_claim_suppressed_when_unresolved(self):
        deps = [
            DependencyInfo("a", "1.0", "runtime", "MIT"),
            DependencyInfo("b", "1.0", "runtime", NOT_INSTALLED),
        ]
        out = generate(_data(deps))
        assert "could not be resolved in this scan" in out
        assert "verify before distribution" in out
        assert "all 2 packages resolved" not in out
        assert "permissively licensed" not in out

    def test_not_installed_and_no_license_both_counted_unresolved(self):
        deps = [
            DependencyInfo("ni", "1.0", "runtime", NOT_INSTALLED),
            DependencyInfo("nl", "1.0", "runtime", UNKNOWN_LICENSE),
        ]
        out = generate(_data(deps))
        assert "| Licenses resolved | 0 / 2 |" in out
        # genuine no-declared-license keeps its dedicated section + wording
        assert "declare no license" in out
        assert "## Dependencies Without a Declared License" in out

    def test_output_is_ascii(self):
        deps = [
            DependencyInfo("a", "1.0", "runtime", "MIT"),
            DependencyInfo("b", "1.0", "runtime", NOT_INSTALLED),
            DependencyInfo("c", "1.0", "dev", UNKNOWN_LICENSE),
        ]
        generate(_data(deps, deduped=1, lock=True)).encode("ascii")  # raises if non-ASCII

    def test_copyleft_still_warns(self):
        deps = [DependencyInfo("g", "1.0", "runtime", "GPL-3.0")]
        out = generate(_data(deps))
        assert "WARNING: Copyleft licenses detected" in out


class TestSbomRenderUnits:
    def test_is_copyleft(self):
        assert is_copyleft("GPL-3.0")
        assert is_copyleft("agpl-3.0")
        assert not is_copyleft("MIT")

    def test_license_cell_dash_for_not_installed(self):
        assert license_cell(NOT_INSTALLED) == "-"
        assert license_cell("MIT") == "MIT"
        assert license_cell(UNKNOWN_LICENSE) == UNKNOWN_LICENSE

    def test_summary_lines_resolved_ratio(self):
        deps = [
            DependencyInfo("a", "1.0", "runtime", "MIT"),
            DependencyInfo("b", "1.0", "dev", NOT_INSTALLED),
        ]
        out = "\n".join(summary_lines(deps, deduped=0))
        assert "| Licenses resolved | 1 / 2 |" in out

    def test_compliance_lines_clean(self):
        deps = [DependencyInfo("a", "1.0", "runtime", "MIT")]
        out = "\n".join(license_compliance_lines(deps))
        assert "No license concerns" in out
