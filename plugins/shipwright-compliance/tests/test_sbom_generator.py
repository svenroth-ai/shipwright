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
        # External-review OpenAI #11: return dict gained `clusters` field
        # (additive). Assert per-key equality, not full-dict.
        assert result["appended"] == 0
        assert result["dismissed"] == 0
        assert result.get("clusters", 0) == 0
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


class TestEmitUndeclaredTriageClusters:
    """ADR-057 follow-up (cluster-collapse iterate): collapse N
    workspaces with the same undeclared-dep signature into ONE
    action-unit instead of N per-workspace items.

    The cluster shape preserves operator visibility ("ein Iterate
    für das gleiche") without forcing the operator to dismiss N
    items for one root cause.
    """

    def _seed_npm(self, root: Path, sub: str, deps: dict) -> None:
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / "package.json").write_text(
            json.dumps({"dependencies": deps}), encoding="utf-8"
        )

    def _seed_python(self, root: Path, sub: str, deps: list[str]) -> None:
        (root / sub).mkdir(parents=True, exist_ok=True)
        dep_lines = "\n  ".join(f'"{d}"' for d in deps)
        (root / sub / "pyproject.toml").write_text(
            f"dependencies = [\n  {dep_lines}\n]\n", encoding="utf-8",
        )

    def test_single_workspace_keeps_per_workspace_shape(
        self, tmp_path: Path, triage_api,
    ):
        """AC-1, AC-11: N=1 → per-workspace key, no cluster."""
        self._seed_npm(tmp_path, "client", {"react": "^19.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 1
        assert result.get("clusters", 0) == 0
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        assert items[0]["dedupKey"] == "sbom:undeclared:client/package.json"
        assert not items[0]["dedupKey"].startswith("sbom:undeclared-cluster:")

    def test_two_workspaces_same_signature_collapse(
        self, tmp_path: Path, triage_api,
    ):
        """AC-1, AC-2: N=2 with identical undeclared set → 1 cluster."""
        self._seed_npm(tmp_path, "client", {"shared-lib": "1.0.0"})
        self._seed_npm(tmp_path, "server", {"shared-lib": "1.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 1
        assert result["clusters"] == 1
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        assert items[0]["dedupKey"].startswith("sbom:undeclared-cluster:")

    def test_three_workspaces_same_signature_collapse(
        self, tmp_path: Path, triage_api,
    ):
        """AC-1: N=3 still collapses into 1 cluster."""
        for sub in ("client", "server", "admin"):
            self._seed_npm(tmp_path, sub, {"shared-lib": "1.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 1
        assert result["clusters"] == 1
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        detail = items[0]["detail"]
        # All three workspaces listed in detail.
        assert "client/package.json" in detail
        assert "server/package.json" in detail
        assert "admin/package.json" in detail

    def test_two_signatures_emit_two_clusters(
        self, tmp_path: Path, triage_api,
    ):
        """AC-6: distinct signatures form distinct clusters."""
        # Cluster 1: A + C with {react}
        self._seed_npm(tmp_path, "a", {"react": "^19.0.0"})
        self._seed_npm(tmp_path, "c", {"react": "^19.0.0"})
        # Cluster 2: B + D with {hono}
        self._seed_npm(tmp_path, "b", {"hono": "^4.0.0"})
        self._seed_npm(tmp_path, "d", {"hono": "^4.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 2
        assert result["clusters"] == 2
        items = _read_sbom_items(triage_api, tmp_path)
        cluster_keys = sorted(i["dedupKey"] for i in items)
        assert len(cluster_keys) == 2
        assert all(k.startswith("sbom:undeclared-cluster:") for k in cluster_keys)
        # Different signatures → different hash → different keys.
        assert cluster_keys[0] != cluster_keys[1]

    def test_mixed_n_one_and_n_many_signatures(
        self, tmp_path: Path, triage_api,
    ):
        """AC-6: A+C share signature (cluster), B is solo (per-workspace)."""
        self._seed_npm(tmp_path, "a", {"pkg-x": "^1.0.0"})
        self._seed_npm(tmp_path, "c", {"pkg-x": "^1.0.0"})
        self._seed_npm(tmp_path, "b", {"pkg-y": "^1.0.0"})
        result = emit_undeclared_triage(tmp_path)
        assert result["appended"] == 2
        assert result["clusters"] == 1
        items = _read_sbom_items(triage_api, tmp_path)
        keys = sorted(i["dedupKey"] for i in items)
        assert len(keys) == 2
        cluster_keys = [k for k in keys if k.startswith("sbom:undeclared-cluster:")]
        ws_keys = [k for k in keys if k.startswith("sbom:undeclared:")]
        assert len(cluster_keys) == 1
        assert len(ws_keys) == 1
        assert ws_keys[0] == "sbom:undeclared:b/package.json"

    def test_cluster_dedup_key_shape_is_sha256_12(
        self, tmp_path: Path, triage_api,
    ):
        """AC-2: cluster key = sbom:undeclared-cluster:<12 hex chars>."""
        import re as _re
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        self._seed_npm(tmp_path, "b", {"shared": "1.0.0"})
        emit_undeclared_triage(tmp_path)
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        key = items[0]["dedupKey"]
        # 12 lowercase hex chars after the prefix.
        m = _re.match(r"^sbom:undeclared-cluster:([0-9a-f]{12})$", key)
        assert m, f"Cluster key shape wrong: {key!r}"

    def test_cluster_idempotent_across_runs(
        self, tmp_path: Path, triage_api,
    ):
        """AC-3: same signature + same members → zero new items on re-run."""
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        self._seed_npm(tmp_path, "b", {"shared": "1.0.0"})
        first = emit_undeclared_triage(tmp_path)
        second = emit_undeclared_triage(tmp_path)
        assert first["appended"] == 1
        assert first["clusters"] == 1
        assert second["appended"] == 0
        assert second["clusters"] == 0
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1  # still ONE cluster, not duplicated

    def test_cluster_launch_payload_lists_all_workspaces_sorted(
        self, tmp_path: Path, triage_api,
    ):
        """AC-4: payload loops over all member workspaces, sorted."""
        for sub in ("zulu", "alpha", "mike"):  # intentionally unsorted
            self._seed_npm(tmp_path, sub, {"shared": "1.0.0"})
        emit_undeclared_triage(tmp_path)
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        payload = items[0]["launchPayload"]
        # All three workspaces present in the for-loop.
        assert "alpha/" in payload or "'alpha/'" in payload or "'alpha'" in payload
        assert "mike/" in payload or "'mike/'" in payload or "'mike'" in payload
        assert "zulu/" in payload or "'zulu/'" in payload or "'zulu'" in payload
        # Alphabetical order: alpha appears before mike before zulu.
        ai = payload.index("alpha")
        mi = payload.index("mike")
        zi = payload.index("zulu")
        assert ai < mi < zi, (
            f"Workspaces not in alphabetical order in payload:\n{payload}"
        )
        # for-loop shape.
        assert "for d in " in payload
        assert "cd \"$d\"" in payload
        # Install command + regen command both present.
        assert "npm install" in payload
        assert "update_compliance.py" in payload

    def test_cluster_launch_payload_quotes_paths_with_spaces(
        self, tmp_path: Path, triage_api,
    ):
        """AC-4: re-use the shell-quote hardening from iterate B.2."""
        for sub in ("my app", "your app"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "package.json").write_text(
                json.dumps({"dependencies": {"shared": "1.0.0"}}), encoding="utf-8"
            )
        emit_undeclared_triage(tmp_path)
        items = _read_sbom_items(triage_api, tmp_path)
        assert len(items) == 1
        payload = items[0]["launchPayload"]
        assert "'my app'" in payload
        assert "'your app'" in payload

    def test_cluster_auto_resolves_when_all_members_clean(
        self, tmp_path: Path, triage_api,
    ):
        """AC-5: cluster auto-dismisses when all members resolve."""
        self._seed_npm(tmp_path, "a", {"react": "^19.0.0"})
        self._seed_npm(tmp_path, "b", {"react": "^19.0.0"})
        emit_undeclared_triage(tmp_path)
        # Lockfile-resolve both workspaces.
        for sub in ("a", "b"):
            (tmp_path / sub / "package-lock.json").write_text(
                json.dumps({
                    "lockfileVersion": 3,
                    "packages": {
                        "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                    },
                }),
                encoding="utf-8",
            )
        result = emit_undeclared_triage(tmp_path)
        assert result["dismissed"] == 1, (
            "Expected the cluster to auto-dismiss when all members resolve, "
            f"got result={result!r}"
        )
        items = _read_sbom_items(triage_api, tmp_path)
        assert items[0]["status"] == "dismissed"
        assert items[0]["statusReason"] == "sbomResolved"

    def test_cluster_dismisses_then_reemits_when_membership_shrinks(
        self, tmp_path: Path, triage_api,
    ):
        """AC-9: cluster {A, B} dismisses when B resolves; A re-emits
        as per-workspace (N=1 fall-through).
        """
        self._seed_npm(tmp_path, "a", {"react": "^19.0.0"})
        self._seed_npm(tmp_path, "b", {"react": "^19.0.0"})
        emit_undeclared_triage(tmp_path)
        # Resolve B only.
        (tmp_path / "b" / "package-lock.json").write_text(
            json.dumps({
                "lockfileVersion": 3,
                "packages": {
                    "node_modules/react": {"version": "19.0.0", "license": "MIT"},
                },
            }),
            encoding="utf-8",
        )
        result = emit_undeclared_triage(tmp_path)
        # Old cluster dismissed, new per-workspace appended for A.
        assert result["dismissed"] == 1
        assert result["appended"] == 1
        assert result["clusters"] == 0  # N=1 → per-workspace, not cluster
        # Verify final state: cluster=dismissed, per-workspace=open.
        items = _read_sbom_items(triage_api, tmp_path)
        by_key = {i["dedupKey"]: i for i in items}
        assert "sbom:undeclared:a/package.json" in by_key
        assert by_key["sbom:undeclared:a/package.json"]["status"] == "triage"
        cluster_items = [
            v for k, v in by_key.items()
            if k.startswith("sbom:undeclared-cluster:")
        ]
        assert len(cluster_items) == 1
        assert cluster_items[0]["status"] == "dismissed"

    def test_npm_and_python_signatures_emit_separate_clusters(
        self, tmp_path: Path, triage_api,
    ):
        """AC-8: manifest-type homogeneity — npm + python with same
        package name still form separate clusters because they need
        different install commands.
        """
        # Won't happen in practice (npm shared-lib vs PyPI shared-lib)
        # but the producer must keep manifest_type as a partition.
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        self._seed_npm(tmp_path, "b", {"shared": "1.0.0"})
        self._seed_python(tmp_path, "c", ["shared>=1.0"])
        self._seed_python(tmp_path, "d", ["shared>=1.0"])
        result = emit_undeclared_triage(tmp_path)
        assert result["clusters"] == 2
        items = _read_sbom_items(triage_api, tmp_path)
        cluster_items = [
            i for i in items
            if i["dedupKey"].startswith("sbom:undeclared-cluster:")
        ]
        assert len(cluster_items) == 2
        # One cluster has npm install, other has uv sync.
        payloads = [i["launchPayload"] for i in cluster_items]
        has_npm = any("npm install" in p for p in payloads)
        has_uv = any("uv sync" in p for p in payloads)
        assert has_npm and has_uv

    def test_telemetry_returns_clusters_count(
        self, tmp_path: Path, triage_api,
    ):
        """AC-10: return shape gains 'clusters' field."""
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        result = emit_undeclared_triage(tmp_path)
        # Even when no cluster emitted (N=1 case), 'clusters' must be
        # present and 0 (consistent shape for callers).
        assert "clusters" in result
        assert result["clusters"] == 0

    def test_cluster_membership_grows_dismisses_old_emits_new(
        self, tmp_path: Path, triage_api,
    ):
        """External review HIGH (OpenAI #2/#3): cluster key MUST encode
        BOTH signature AND member-list. When membership grows from
        {A, C} to {A, C, D} (same signature), the old cluster MUST
        auto-dismiss and a new cluster MUST be appended.
        """
        for sub in ("a", "c"):
            self._seed_npm(tmp_path, sub, {"shared": "1.0.0"})
        first = emit_undeclared_triage(tmp_path)
        assert first["clusters"] == 1
        # Now add a third member to the same signature.
        self._seed_npm(tmp_path, "d", {"shared": "1.0.0"})
        second = emit_undeclared_triage(tmp_path)
        assert second["clusters"] == 1
        assert second["dismissed"] == 1, (
            "Expected old cluster {a,c} to auto-dismiss when membership "
            f"grew to {{a,c,d}}; got result={second!r}"
        )
        assert second["appended"] == 1, (
            "Expected a fresh cluster {a,c,d} to be appended; "
            f"got result={second!r}"
        )
        # Final state: 2 cluster items, 1 dismissed, 1 open.
        items = _read_sbom_items(triage_api, tmp_path)
        cluster_items = [
            i for i in items
            if i["dedupKey"].startswith("sbom:undeclared-cluster:")
        ]
        assert len(cluster_items) == 2
        statuses = sorted(i["status"] for i in cluster_items)
        assert statuses == ["dismissed", "triage"]

    def test_legacy_per_workspace_item_shielded_when_workspace_joins_cluster(
        self, tmp_path: Path, triage_api,
    ):
        """External review HIGH (OpenAI #1, Gemini #1): a pre-existing
        per-workspace item for workspace A (status=triage) MUST NOT be
        auto-dismissed when A joins a NEW cluster. AC-7 says legacy
        items remain individually addressable.
        """
        # Pre-seed an open per-workspace item for workspace A.
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        self._seed_npm(tmp_path, "b", {"shared": "1.0.0"})
        # Directly append a legacy per-workspace item (status=triage).
        triage_api.append_triage_item(
            tmp_path,
            source="sbom",
            severity="low",
            kind="compliance",
            title="legacy item for a",
            detail="left over from before cluster shape existed",
            dedup_key="sbom:undeclared:a/package.json",
        )
        # Now emit. Workspaces a + b form a cluster (shared signature).
        emit_undeclared_triage(tmp_path)
        items = _read_sbom_items(triage_api, tmp_path)
        # Find the legacy item by its dedup key.
        legacy = next(
            i for i in items
            if i["dedupKey"] == "sbom:undeclared:a/package.json"
        )
        assert legacy["status"] == "triage", (
            "Legacy per-workspace item for `a` should be shielded by "
            "shadow-per-workspace-key in current_keys when `a` joins "
            f"a cluster. Got: {legacy!r}"
        )

    def test_unsupported_manifest_type_falls_back_to_per_workspace(
        self, tmp_path: Path, triage_api, monkeypatch,
    ):
        """Code-review M1/M2: when `_cluster_launch_payload` raises
        ValueError (unknown manifest_type) for a cluster-eligible
        bucket, the producer MUST fall back to per-workspace emit so
        member workspaces don't orphan without any triage item.
        """
        from scripts.lib import sbom_generator as sg
        # Monkey-patch collect_undeclared_by_workspace to return
        # workspaces with an unknown manifest_type but cluster-eligible
        # signature (N=2 same names).
        fake_groups = [
            {
                "manifest_rel_path": "crate-a/Cargo.toml",
                "manifest_type": "cargo",  # unknown to _cluster_install_command
                "undeclared": [{"name": "serde", "version": "1.0"}],
            },
            {
                "manifest_rel_path": "crate-b/Cargo.toml",
                "manifest_type": "cargo",
                "undeclared": [{"name": "serde", "version": "1.0"}],
            },
        ]
        # Patch the import inside emit_undeclared_triage. The function
        # does `from scripts.lib.data_collector import ...` locally.
        from scripts.lib import data_collector
        monkeypatch.setattr(
            data_collector,
            "collect_undeclared_by_workspace",
            lambda _root: fake_groups,
        )
        # Patch _launch_payload too (it'd also fail for cargo). Wire
        # it to a noop string so per-workspace path can proceed.
        monkeypatch.setattr(
            sg, "_launch_payload",
            lambda rel, mt: f"# unsupported manifest_type {mt} — manual install required",
        )
        result = emit_undeclared_triage(tmp_path)
        # Both workspaces should land as per-workspace items.
        items = _read_sbom_items(triage_api, tmp_path)
        per_ws_items = [
            i for i in items
            if i["dedupKey"].startswith("sbom:undeclared:")
        ]
        cluster_items = [
            i for i in items
            if i["dedupKey"].startswith("sbom:undeclared-cluster:")
        ]
        assert len(per_ws_items) == 2, (
            "Expected 2 per-workspace items as fallback when cluster "
            f"payload failed; got {len(per_ws_items)} (cluster: "
            f"{len(cluster_items)}). result={result!r}"
        )
        assert len(cluster_items) == 0
        # `error` field should record the cluster-payload failure.
        assert "error" in result
        assert "cluster_payload:cargo" in result["error"]

    def test_legacy_per_workspace_items_untouched_by_cluster_emit(
        self, tmp_path: Path, triage_api,
    ):
        """AC-7: pre-existing per-workspace items in promoted/dismissed
        states remain untouched when cluster-shape items are added.
        """
        # Pre-seed a legacy per-workspace item that's promoted.
        triage_api.append_triage_item(
            tmp_path,
            source="sbom",
            severity="low",
            kind="compliance",
            title="legacy per-workspace",
            detail="historical",
            dedup_key="sbom:undeclared:legacy-workspace/package.json",
        )
        legacy_id = _read_sbom_items(triage_api, tmp_path)[0]["id"]
        triage_api.mark_status(
            tmp_path, legacy_id,
            new_status="promoted", by="user", promoted_task_id="TASK-1",
        )
        # Now emit a fresh cluster.
        self._seed_npm(tmp_path, "a", {"shared": "1.0.0"})
        self._seed_npm(tmp_path, "b", {"shared": "1.0.0"})
        emit_undeclared_triage(tmp_path)
        # Legacy item is still promoted (NOT auto-dismissed by the
        # cluster emit cycle).
        items = _read_sbom_items(triage_api, tmp_path)
        legacy = next(i for i in items if i["id"] == legacy_id)
        assert legacy["status"] == "promoted"
