"""Tests for AC12 — stack_detector merges sub-package.json deps when
multi_service detector fires AND root has no real deps.

Plus matcher behavior tests (AC11): vite-hono profile is preferred for
split Vite+Hono repos, NOT preferred for Next.js+API monorepos.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.stack_detector import detect_stack
from lib.profile_matcher import match_profile


SHARED_PROFILES = (
    Path(__file__).resolve().parent.parent.parent.parent / "shared" / "profiles"
)


def _make_pkg(deps=None, dev_deps=None, scripts=None, name="x") -> str:
    return json.dumps({
        "name": name,
        "version": "0.1.0",
        "dependencies": deps or {},
        "devDependencies": dev_deps or {},
        "scripts": scripts or {},
    })


def _build_webui_shape(root: Path, with_root_pkg: bool = False, with_proxy: bool = True):
    (root / "client").mkdir(exist_ok=True)
    (root / "server").mkdir(exist_ok=True)
    (root / "client" / "package.json").write_text(
        _make_pkg(
            deps={
                "vite": "^6.0",
                "react": "^19.0",
                "react-dom": "^19.0",
            },
            dev_deps={"typescript": "^5.6"},
        ),
        encoding="utf-8",
    )
    (root / "server" / "package.json").write_text(
        _make_pkg(
            deps={"hono": "^4.7", "@hono/node-server": "^1.14"},
            dev_deps={"tsx": "^4.19", "typescript": "^5.7"},
            scripts={"dev": "tsx watch src/index.ts"},
        ),
        encoding="utf-8",
    )
    if with_root_pkg:
        (root / "package.json").write_text(_make_pkg(), encoding="utf-8")
    if with_proxy:
        (root / "client" / "vite.config.ts").write_text(
            "export default { server: { proxy: { '/api': { target: 'http://localhost:3847' } } } };",
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# AC12 — signature merge
# ---------------------------------------------------------------------------

def test_detect_stack_merges_split_repo_deps_into_signature(tmp_path: Path):
    _build_webui_shape(tmp_path, with_root_pkg=False)
    sig = detect_stack(tmp_path)
    # Frontend deps merged in
    assert "vite" in sig["frontend"]
    assert "react" in sig["frontend"]
    # Backend deps merged in
    assert "hono" in sig["backend"]
    # TypeScript promoted to runtime
    assert "typescript" in sig["runtime"]
    # Signal flagged
    assert "has-multi-service-layout" in sig["signals"]


def test_detect_stack_skips_merge_when_root_has_real_deps(tmp_path: Path):
    """Workspace-root with real deps → merge MUST NOT run (AC12 narrow trigger)."""
    (tmp_path / "package.json").write_text(
        _make_pkg(deps={"some-tool": "^1.0", "another-tool": "^2.0"}),
        encoding="utf-8",
    )
    _build_webui_shape(tmp_path, with_root_pkg=False)  # adds client/server
    sig = detect_stack(tmp_path)
    # has-multi-service-layout flag is still set (we noticed the layout)
    assert "has-multi-service-layout" in sig["signals"]
    # But sub-deps NOT merged
    assert "vite" not in sig["frontend"]
    assert "hono" not in sig["backend"]


def test_detect_stack_skips_merge_when_root_has_only_dev_deps(tmp_path: Path):
    """Root has devDependencies only → still treated as "real deps", merge skipped."""
    (tmp_path / "package.json").write_text(
        _make_pkg(dev_deps={"prettier": "^3.0"}),
        encoding="utf-8",
    )
    _build_webui_shape(tmp_path, with_root_pkg=False)
    sig = detect_stack(tmp_path)
    assert "vite" not in sig["frontend"]


def test_detect_stack_root_pkg_empty_deps_allows_merge(tmp_path: Path):
    """Empty deps + devDeps → merge runs (workspace tooling/orchestrator pattern)."""
    (tmp_path / "package.json").write_text(_make_pkg(), encoding="utf-8")
    _build_webui_shape(tmp_path, with_root_pkg=False)
    sig = detect_stack(tmp_path)
    assert "vite" in sig["frontend"]
    assert "hono" in sig["backend"]


def test_detect_stack_typescript_promoted_from_service(tmp_path: Path):
    """Service declares typescript → runtime.typescript populated."""
    _build_webui_shape(tmp_path)
    sig = detect_stack(tmp_path)
    assert "typescript" in sig["runtime"]


def test_detect_stack_root_wins_on_conflict(tmp_path: Path):
    """Root pkg with hono → root version wins, service merge skipped (root has real deps)."""
    (tmp_path / "package.json").write_text(
        _make_pkg(deps={"hono": "^3.0"}),  # root has older hono
        encoding="utf-8",
    )
    _build_webui_shape(tmp_path)
    sig = detect_stack(tmp_path)
    # Root populated hono — services don't override (and don't even run merge)
    assert "hono" in sig["backend"]
    assert "^3.0" in sig["backend"]["hono"] or "3.0" in sig["backend"]["hono"]


def test_detect_stack_no_change_for_single_service_repo(tmp_path: Path):
    """Flat root-only project unaffected by AC12 changes (regression guard)."""
    (tmp_path / "package.json").write_text(
        _make_pkg(deps={"next": "^14.0", "react": "^18.0"}),
        encoding="utf-8",
    )
    sig = detect_stack(tmp_path)
    assert "next" in sig["frontend"]
    assert "has-multi-service-layout" not in sig["signals"]


# ---------------------------------------------------------------------------
# AC11 — matcher prefers vite-hono for webui shape
# ---------------------------------------------------------------------------

def test_match_profile_picks_vite_hono_for_split_repo(tmp_path: Path):
    _build_webui_shape(tmp_path)
    sig = detect_stack(tmp_path)
    result = match_profile(sig, SHARED_PROFILES)
    assert result["matched"] == "vite-hono"
    # Higher than supabase-nextjs
    candidates = {c["name"]: c["score"] for c in result["candidates"]}
    if "supabase-nextjs" in candidates:
        assert candidates["vite-hono"] > candidates["supabase-nextjs"]


def test_match_profile_does_not_pick_vite_hono_for_next_api_monorepo(tmp_path: Path):
    """Next.js + Express API split repo MUST NOT match vite-hono."""
    (tmp_path / "client").mkdir()
    (tmp_path / "api").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(
            deps={"next": "^14.0", "react": "^18.0", "react-dom": "^18.0"},
            dev_deps={"typescript": "^5.0"},
        ),
        encoding="utf-8",
    )
    (tmp_path / "api" / "package.json").write_text(
        _make_pkg(deps={"express": "^4.18", "body-parser": "^1.20"}),
        encoding="utf-8",
    )
    sig = detect_stack(tmp_path)
    result = match_profile(sig, SHARED_PROFILES)
    assert result["matched"] != "vite-hono"


def test_match_profile_no_change_for_single_service_repo(tmp_path: Path):
    """Single-service root-only React+Next match behavior unchanged."""
    (tmp_path / "package.json").write_text(
        _make_pkg(deps={"next": "^14.0", "react": "^18.0", "@supabase/supabase-js": "^2.0"}),
        encoding="utf-8",
    )
    sig = detect_stack(tmp_path)
    result = match_profile(sig, SHARED_PROFILES)
    # supabase-nextjs should still match (no regression from AC12)
    assert result["matched"] in {"supabase-nextjs", "generic"}


# ---------------------------------------------------------------------------
# Snapshot integration
# ---------------------------------------------------------------------------

def test_analyze_surfaces_multi_service_in_snapshot(tmp_path: Path):
    """When detector fires, analyze() puts multi_service under stack."""
    import sys
    plugin_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_root / "scripts" / "tools"))
    from analyze_codebase import analyze  # type: ignore

    _build_webui_shape(tmp_path)
    snapshot = analyze(tmp_path, [], None)
    assert "multi_service" in snapshot["stack"]
    assert snapshot["stack"]["multi_service"]["detected"] is True
