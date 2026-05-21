"""Tests for sbom_generator.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.lib.data_collector import ComplianceData, DependencyInfo, collect_all
from scripts.lib.sbom_generator import (
    emit_undeclared_triage,
    generate,
    generate_file,
)


def _make_data(deps: list[DependencyInfo]) -> ComplianceData:
    data = ComplianceData(project_root=Path("."))
    data.dependencies = deps
    data.timestamp = "2026-03-21T14:00:00Z"
    return data


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Software Bill of Materials (SBOM)" in result
        assert "## Summary" in result

    def test_summary_counts(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Runtime dependencies | 8 |" in result
        assert "| Dev dependencies | 5 |" in result
        assert "| Total packages | 13 |" in result

    def test_runtime_table(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Runtime Dependencies" in result
        assert "next" in result
        assert "react" in result

    def test_dev_table(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Dev Dependencies" in result
        assert "vitest" in result
        assert "typescript" in result

    def test_mermaid_pie(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "```mermaid" in result
        assert "pie title" in result

    def test_copyleft_warning(self):
        deps = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
            DependencyInfo("gpl-pkg", "1.0.0", "runtime", "GPL-3.0"),
        ]
        result = generate(_make_data(deps))
        assert "WARNING: Copyleft licenses detected" in result
        assert "gpl-pkg" in result

    def test_no_copyleft(self):
        deps = [
            DependencyInfo("react", "19.0.0", "runtime", "MIT"),
        ]
        result = generate(_make_data(deps))
        assert "No copyleft licenses detected" in result

    def test_unknown_licenses_section(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # All licenses are unknown because no node_modules
        assert "## Unknown Licenses" in result
        assert "13 packages" in result

    def test_no_deps(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "No dependency manifests found" in result


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "sbom.md"


@pytest.fixture
def triage_api():
    """Bring ``shared/scripts/triage`` onto ``sys.path`` for reads in tests."""
    shared = Path(__file__).resolve().parents[3] / "shared" / "scripts"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import triage  # type: ignore
    return triage


def _read_sbom_items(triage_api, project_root: Path) -> list[dict]:
    return [
        i for i in triage_api.read_all_items(project_root)
        if i.get("source") == "sbom"
    ]


class TestEmitUndeclaredTriage:
    """Iterate B.2 (ADR-056) — per-workspace ``source="sbom"`` triage emit."""

    def _seed_npm_workspace(self, root: Path, sub: str, deps: dict) -> None:
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / "package.json").write_text(
            json.dumps({"dependencies": deps}), encoding="utf-8"
        )

    def test_no_undeclared_no_triage(self, tmp_path: Path, triage_api):
        # Resolvable package via lockfile → no undeclared → no item.
        self._seed_npm_workspace(tmp_path, ".", {"react": "^19.0.0"})
        (tmp_path / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        result = emit_undeclared_triage(tmp_path)
        assert result == {"appended": 0, "dismissed": 0}
        assert _read_sbom_items(triage_api, tmp_path) == []

    def test_one_item_per_workspace(self, tmp_path: Path, triage_api):
        self._seed_npm_workspace(tmp_path, "client", {"react": "^19.0.0"})
        self._seed_npm_workspace(tmp_path, "server", {"hono": "^4.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 2
        assert "error" not in result
        items = _read_sbom_items(triage_api, tmp_path)
        assert {i["dedupKey"] for i in items} == {
            "sbom:undeclared:client/package.json",
            "sbom:undeclared:server/package.json",
        }
        for item in items:
            assert item["severity"] == "low"
            assert item["kind"] == "compliance"
            assert item["status"] == "triage"
            assert item["launchPayload"]
            assert "npm install" in item["launchPayload"]
            # Reviewer-flagged H1: payload commands chained with `&&`
            # so a failing cd short-circuits the install. No bare lines.
            assert "&&" in item["launchPayload"]

    def test_top_20_truncation_and_more_footer(self, tmp_path: Path, triage_api):
        many = {f"pkg-{i:02d}": "1.0.0" for i in range(25)}
        self._seed_npm_workspace(tmp_path, ".", many)
        emit_undeclared_triage(tmp_path)
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        detail = items[0]["detail"]
        assert "25 package(s)" in detail
        assert "+5 more" in detail
        # First 20 alphabetically: pkg-00..pkg-19
        assert "pkg-00@1.0.0" in detail
        assert "pkg-19@1.0.0" in detail
        # pkg-20 is the 21st; the truncation cuts it before printing.
        assert "pkg-20@1.0.0" not in detail

    def test_idempotent_across_runs(self, tmp_path: Path, triage_api):
        self._seed_npm_workspace(tmp_path, "client", {"react": "^19.0.0"})
        first = emit_undeclared_triage(tmp_path)
        second = emit_undeclared_triage(tmp_path)
        assert first["appended"] == 1
        assert second["appended"] == 0
        assert len(_read_sbom_items(triage_api, tmp_path)) == 1

    def test_auto_resolve_when_workspace_clean(self, tmp_path: Path, triage_api):
        # First run: undeclared exists → triage emitted.
        self._seed_npm_workspace(tmp_path, "client", {"react": "^19.0.0"})
        emit_undeclared_triage(tmp_path)
        # Now make the lockfile declare the license → clean state.
        (tmp_path / "client" / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        result = emit_undeclared_triage(tmp_path)
        assert result["dismissed"] == 1
        items = _read_sbom_items(triage_api, tmp_path)
        assert items and items[0]["status"] == "dismissed"
        assert items[0]["statusReason"] == "sbomResolved"

    def test_promoted_item_not_auto_resolved(self, tmp_path: Path, triage_api):
        """Operator-promoted items stay promoted even when clean (HIGH-2 contract)."""
        self._seed_npm_workspace(tmp_path, "client", {"react": "^19.0.0"})
        emit_undeclared_triage(tmp_path)
        item = _read_sbom_items(triage_api, tmp_path)[0]
        triage_api.mark_status(
            tmp_path, item["id"],
            new_status="promoted", by="user", promoted_task_id="TASK-1",
        )
        # Clean the workspace.
        (tmp_path / "client" / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        result = emit_undeclared_triage(tmp_path)
        assert result["dismissed"] == 0
        kept = _read_sbom_items(triage_api, tmp_path)[0]
        assert kept["status"] == "promoted"

    def test_launch_payload_for_python_workspace(self, tmp_path: Path, triage_api):
        (tmp_path / "subpkg").mkdir()
        (tmp_path / "subpkg" / "pyproject.toml").write_text(
            'dependencies = [\n  "definitely-not-a-real-pypi-package-xyz>=1.0.0",\n]\n',
            encoding="utf-8",
        )
        emit_undeclared_triage(tmp_path)
        item = _read_sbom_items(triage_api, tmp_path)[0]
        assert item["dedupKey"] == "sbom:undeclared:subpkg/pyproject.toml"
        payload = item["launchPayload"]
        assert "cd 'subpkg'" in payload
        assert "uv sync" in payload
        assert "npm install" not in payload
        # Reviewer-flagged: `cd -` must come BEFORE the regenerate
        # command so the regen runs from the repo root, not the workspace.
        cd_back = payload.index("cd -")
        regen = payload.index("update_compliance.py")
        assert cd_back < regen

    def test_root_manifest_omits_cd(self, tmp_path: Path, triage_api):
        self._seed_npm_workspace(tmp_path, ".", {"react": "^19.0.0"})
        emit_undeclared_triage(tmp_path)
        item = _read_sbom_items(triage_api, tmp_path)[0]
        payload = item["launchPayload"]
        assert "cd " not in payload.splitlines()[0]
        assert payload.startswith("npm install")

    def test_launch_payload_quotes_paths_with_spaces(self, tmp_path: Path, triage_api):
        """Reviewer-flagged H1 / M5: shell-significant chars in repo paths."""
        (tmp_path / "my app").mkdir()
        (tmp_path / "my app" / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
        )
        emit_undeclared_triage(tmp_path)
        item = _read_sbom_items(triage_api, tmp_path)[0]
        payload = item["launchPayload"]
        # Workspace path is single-quoted so spaces / metacharacters
        # don't break the install step.
        assert "cd 'my app'" in payload
        # Defense in depth: any later command starts on its own line,
        # gated by `&&`.
        assert "  && npm install" in payload

    def test_detail_sort_stable_for_duplicate_names(self, tmp_path: Path, triage_api):
        """Reviewer-flagged M6: same name + different versions must sort deterministically."""
        from scripts.lib.sbom_generator import _render_detail  # type: ignore

        undeclared = [
            {"name": "pkg-a", "version": "2.0.0"},
            {"name": "pkg-a", "version": "1.0.0"},
            {"name": "pkg-b", "version": "1.0.0"},
        ]
        detail = _render_detail(undeclared)
        # By (name, version) → pkg-a@1.0.0 before pkg-a@2.0.0 before pkg-b.
        ai = detail.index("pkg-a@1.0.0")
        a2 = detail.index("pkg-a@2.0.0")
        bi = detail.index("pkg-b@1.0.0")
        assert ai < a2 < bi

    def test_emit_does_not_touch_non_sbom_items(self, tmp_path: Path, triage_api):
        """Reviewer-flagged M7: auto-dismiss only touches source='sbom' items."""
        # Pre-seed a non-sbom item with a similar-looking dedup-key.
        triage_api.append_triage_item(
            tmp_path,
            source="compliance",
            severity="medium",
            kind="compliance",
            title="unrelated finding",
            detail="not sbom",
            dedup_key="sbom:undeclared:phony",  # deliberately collides
        )
        # Now run emit against a clean workspace.
        result = emit_undeclared_triage(tmp_path)
        assert result["dismissed"] == 0
        # The unrelated item must still be open.
        items = [
            i for i in triage_api.read_all_items(tmp_path)
            if i.get("source") == "compliance"
        ]
        assert items and items[0]["status"] == "triage"

    def test_emit_reports_append_errors(self, tmp_path: Path, monkeypatch, triage_api):
        """Reviewer-flagged M2: per-workspace append failures must surface via `error`."""
        self._seed_npm_workspace(tmp_path, "client", {"react": "^19.0.0"})
        # Patch the lazy importer to return a failing append.
        from scripts.lib import sbom_generator

        def _broken_append(*args, **kwargs):
            raise RuntimeError("simulated triage outage")

        monkeypatch.setattr(
            sbom_generator,
            "_import_triage_api",
            lambda: (_broken_append, triage_api.mark_status, triage_api.read_all_items),
        )
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 0
        assert "error" in result
        assert "append:client/package.json" in result["error"]
        assert "RuntimeError" in result["error"]

    def test_python_no_venv_still_emits(self, tmp_path: Path, triage_api):
        """Reviewer-flagged M11: confirm no-venv → undeclared → triage emitted.

        ``importlib.metadata`` returns 'unknown' for non-installed
        packages, which is exactly the undeclared-license case the
        producer handles. A no-venv Python workspace gets the same
        ``uv sync`` payload as a stale-venv one.
        """
        (tmp_path / "pyproject.toml").write_text(
            'dependencies = [\n  "ghost-package-not-installed-xyz>=1.0.0",\n]\n',
            encoding="utf-8",
        )
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 1
        item = _read_sbom_items(triage_api, tmp_path)[0]
        assert "uv sync" in item["launchPayload"]
