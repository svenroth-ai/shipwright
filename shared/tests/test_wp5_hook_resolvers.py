#!/usr/bin/env python3
"""WP5 (2026-06-10 deep audit) — hook project-root / worktree resolvers.

Covers the resolver/guard fixes that several hooks shared:

- **F6** ``mark_plugin_edit.is_plugin_side`` must strip a leading
  ``.worktrees/<slug>/`` so worktree-relative plugin edits are still recorded
  (hooks run with cwd = MAIN root → ``_relativize`` yields a worktree-prefixed
  rel). Mirrors ``check_file_size.py`` (ADR-126).
- **F7** ``check_drift._emit_drift_to_triage`` must no-op when the resolved root
  is NOT a Shipwright project (else it writes ``.shipwright/triage.jsonl`` into a
  foreign / non-repo dir).
- **F8** ``check_drift`` content dedup key must be **repo-relative**, so the same
  logical drift recorded from main and from a worktree share one key (no false
  ``driftResolved`` auto-dismiss).
- **F10** the toolcall-counter readers (``estimate_context_pressure`` /
  ``reset_tool_counter``) must resolve the counter file via
  ``resolve_project_root()`` — the same auto-descending resolver the producer
  (``track_tool_calls``) uses — so producer + readers agree in an auto-descent
  (subdirectory-project) layout.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _load(mod_name: str, rel: str):
    path = _SHARED_SCRIPTS / rel
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


mark_plugin_edit = _load("wp5_mark_plugin_edit", "hooks/mark_plugin_edit.py")
check_drift = _load("wp5_check_drift", "hooks/check_drift.py")

from triage import read_all_items  # noqa: E402


def _mark_shipwright_project(root: Path) -> None:
    (root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


# ---------------------------------------------------------------------------
# F6 — is_plugin_side strips .worktrees/<slug>/
# ---------------------------------------------------------------------------

class TestIsPluginSideWorktreePrefix:
    def test_worktree_prefixed_plugin_path_recorded(self):
        # The dominant iterate edit path: hooks run with cwd = MAIN root, so a
        # plugin .py edited inside a worktree relativizes to a .worktrees/<slug>/
        # prefix. Before the fix is_plugin_side(rel) was False (no startswith).
        assert mark_plugin_edit.is_plugin_side(
            ".worktrees/iterate-foo/plugins/shipwright-build/scripts/x.py"
        )

    def test_worktree_prefixed_shared_path_recorded(self):
        assert mark_plugin_edit.is_plugin_side(
            ".worktrees/some-slug/shared/scripts/hooks/y.py"
        )

    def test_worktree_prefixed_skill_md_recorded(self):
        assert mark_plugin_edit.is_plugin_side(
            ".worktrees/s/plugins/shipwright-iterate/skills/iterate/SKILL.md"
        )

    def test_worktree_prefixed_backslash_normalised(self):
        assert mark_plugin_edit.is_plugin_side(
            r".worktrees\slug\plugins\shipwright-test\scripts\z.py"
        )

    def test_worktree_prefixed_shared_tests_still_excluded(self):
        # shared/tests/ is not loaded at runtime → not plugin-side even under a
        # worktree prefix.
        assert not mark_plugin_edit.is_plugin_side(
            ".worktrees/slug/shared/tests/test_x.py"
        )

    def test_worktree_prefixed_non_plugin_path_excluded(self):
        assert not mark_plugin_edit.is_plugin_side(
            ".worktrees/slug/docs/guide.md"
        )

    def test_plain_plugin_path_still_recorded(self):
        # Idempotent for ordinary (non-worktree) paths — main-tree edits.
        assert mark_plugin_edit.is_plugin_side("plugins/shipwright-run/scripts/a.py")

    def test_plain_non_plugin_path_still_excluded(self):
        assert not mark_plugin_edit.is_plugin_side("README.md")


# ---------------------------------------------------------------------------
# F7 — check_drift no-ops in a non-Shipwright dir
# ---------------------------------------------------------------------------

class TestCheckDriftProjectGuard:
    def test_no_triage_written_in_foreign_dir(self, tmp_path: Path):
        # tmp_path has NO Shipwright marker → emit must short-circuit and write
        # nothing (no .shipwright/, no triage.jsonl, no lock).
        appended = check_drift._emit_drift_to_triage(
            tmp_path,
            content_findings=["CLAUDE.md: Structure lists 'gone/' but directory not found"],
        )
        assert appended == 0
        assert not (tmp_path / ".shipwright").exists()
        assert read_all_items(tmp_path) == []

    def test_emits_when_shipwright_project(self, tmp_path: Path):
        _mark_shipwright_project(tmp_path)
        appended = check_drift._emit_drift_to_triage(
            tmp_path,
            content_findings=["CLAUDE.md: Structure lists 'gone/' but directory not found"],
        )
        assert appended == 1
        items = read_all_items(tmp_path)
        assert len(items) == 1
        assert items[0]["source"] == "drift"


# ---------------------------------------------------------------------------
# F8 — content dedup key is repo-relative (stable across trees)
# ---------------------------------------------------------------------------

class TestContentAnchorRepoRelative:
    def test_anchor_is_repo_relative(self, tmp_path: Path):
        # A content finding's path is absolute under whatever tree started the
        # session; the dedup anchor must be repo-relative so main and worktree
        # produce the SAME key.
        main_abs = (tmp_path / "main" / "CLAUDE.md")
        wt_abs = (tmp_path / ".worktrees" / "slug" / "CLAUDE.md")
        finding_main = f"{main_abs}: Structure lists 'x/' but directory not found"
        finding_wt = f"{wt_abs}: Structure lists 'x/' but directory not found"
        anchor_main = check_drift._content_anchor(finding_main, tmp_path / "main")
        anchor_wt = check_drift._content_anchor(
            finding_wt, tmp_path / ".worktrees" / "slug"
        )
        # Repo-relative → both reduce to "CLAUDE.md" (no absolute prefix, no
        # .worktrees/<slug>/ prefix).
        assert anchor_main == anchor_wt
        assert "worktrees" not in anchor_main
        assert ":" not in anchor_main  # no drive letter

    def test_dedup_key_stable_across_trees(self, tmp_path: Path):
        # Same drift, two roots (main + worktree): one shared dedup key →
        # the second tree does NOT see the first's item as "absent" and dismiss it.
        main_root = tmp_path / "main"
        wt_root = tmp_path / ".worktrees" / "slug"
        main_root.mkdir(parents=True)
        wt_root.mkdir(parents=True)
        f_main = f"{main_root / 'CLAUDE.md'}: Structure lists 'x/' but directory not found"
        f_wt = f"{wt_root / 'CLAUDE.md'}: Structure lists 'x/' but directory not found"
        k_main = f"drift:{check_drift._content_anchor(f_main, main_root)}:content"
        k_wt = f"drift:{check_drift._content_anchor(f_wt, wt_root)}:content"
        assert k_main == k_wt

    def test_relative_finding_path_unchanged(self, tmp_path: Path):
        # A finding already carrying a repo-relative path is kept verbatim (NOT
        # realpath'd against the process cwd) and case/sep-folded via normcase
        # exactly like the legacy key. The point: no absolute prefix leaks in.
        import os
        _mark_shipwright_project(tmp_path)
        finding = "webui/CLAUDE.md: Structure lists 'y/' but directory not found"
        anchor = check_drift._content_anchor(finding, tmp_path)
        assert anchor == os.path.normcase("webui/CLAUDE.md")
        assert "01_development" not in anchor  # no leaked absolute root

    def test_absolute_anchor_outside_root_does_not_crash(self, tmp_path: Path):
        # Gemini-High plan-review edge case: an absolute anchor pointing OUTSIDE
        # project_root (relative_to() would raise ValueError). The canonicalizer
        # must NOT crash — it falls back to the normalized full path.
        outside = tmp_path / "elsewhere" / "CLAUDE.md"
        root = tmp_path / "project"
        root.mkdir()
        finding = f"{outside}: Structure lists 'z/' but directory not found"
        anchor = check_drift._content_anchor(finding, root)  # must not raise
        assert isinstance(anchor, str) and anchor
        # And the full _emit path stays best-effort (no exception escapes).
        _mark_shipwright_project(root)
        appended = check_drift._emit_drift_to_triage(
            root, content_findings=[finding],
        )
        assert appended == 1


# ---------------------------------------------------------------------------
# F10 — counter readers resolve via resolve_project_root() (auto-descent)
# ---------------------------------------------------------------------------

_TOOLS = _SHARED_SCRIPTS / "tools"


def _run_tool(script: str, args: list[str], cwd: Path, env: dict | None = None):
    return subprocess.run(
        [sys.executable, str(_TOOLS / script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _make_subproject(workspace: Path, subdir: str) -> Path:
    project = workspace / subdir
    project.mkdir(parents=True, exist_ok=True)
    _mark_shipwright_project(project)
    return project


class TestCounterReadersAutoDescent:
    def test_estimate_reads_subproject_counter(self, tmp_path: Path):
        # Producer (track_tool_calls) auto-descends and writes the count in the
        # SUBDIR project. With os.environ/cwd the reader read the workspace root
        # (counter never exists → 0). Aligned to resolve_project_root() it reads
        # the same subdir.
        project = _make_subproject(tmp_path, "webui")
        counter = project / ".shipwright" / "toolcall_count"
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("130", encoding="utf-8")
        # Run with cwd = workspace root, no SHIPWRIGHT_PROJECT_ROOT env.
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "SHIPWRIGHT_PROJECT_ROOT"}
        res = _run_tool("estimate_context_pressure.py", ["--mode", "builder"], tmp_path, env)
        assert res.returncode == 0, res.stderr
        data = json.loads(res.stdout)
        assert data["tool_calls"] == 130
        assert data["recommend_checkpoint"] is True

    def test_reset_writes_subproject_counter(self, tmp_path: Path):
        project = _make_subproject(tmp_path, "service")
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "SHIPWRIGHT_PROJECT_ROOT"}
        res = _run_tool("reset_tool_counter.py", [], tmp_path, env)
        assert res.returncode == 0, res.stderr
        out = json.loads(res.stdout)
        counter = project / ".shipwright" / "toolcall_count"
        assert counter.exists()
        assert counter.read_text(encoding="utf-8").strip() == "0"
        assert str(counter) == out["counter_file"] or Path(out["counter_file"]) == counter

    def test_explicit_counter_file_arg_wins(self, tmp_path: Path):
        # An absolute --counter-file is honored verbatim (no resolver descent).
        explicit = tmp_path / "custom_count"
        explicit.write_text("5", encoding="utf-8")
        res = _run_tool(
            "estimate_context_pressure.py",
            ["--counter-file", str(explicit), "--threshold", "3"],
            tmp_path,
        )
        assert res.returncode == 0, res.stderr
        data = json.loads(res.stdout)
        assert data["tool_calls"] == 5
        assert data["recommend_checkpoint"] is True

    def test_env_var_root_wins(self, tmp_path: Path):
        project = _make_subproject(tmp_path, "p")
        counter = project / ".shipwright" / "toolcall_count"
        counter.parent.mkdir(parents=True, exist_ok=True)
        counter.write_text("42", encoding="utf-8")
        import os as _os
        env = {**_os.environ, "SHIPWRIGHT_PROJECT_ROOT": str(project)}
        res = _run_tool("estimate_context_pressure.py", [], tmp_path, env)
        assert res.returncode == 0, res.stderr
        assert json.loads(res.stdout)["tool_calls"] == 42


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
