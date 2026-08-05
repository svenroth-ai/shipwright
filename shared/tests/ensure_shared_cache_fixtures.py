"""Shared layout builders for the ``ensure_shared_cache`` bootstrap tests.

A faithful ``~/.claude/plugins`` tree — cache, marketplace clone, installed
versioned plugin dirs, cross-plugin mirrors — so the real hook can be executed
as a subprocess and resolve its ``Path(__file__)`` walk against it.

Sibling-fixture module, following ``cache_sync_fixtures``: two test modules use
these (``…_integration`` for the fresh-install compose, ``…_partial_reap`` for
the surviving-sentinel cases) and neither owns them.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
LOCK_HELPER = CANONICAL.with_name("cache_repair_lock.py")


def hook_module():
    """Import the canonical bootstrap so fixtures can reuse its real constants.

    ADR-045: register in ``sys.modules`` BEFORE ``exec_module``, so a partially
    initialised module is never observable under this name. Shares the name used
    by ``test_ensure_shared_cache_walk`` — one module object, one ignore set.
    """
    name = "_shipwright_ensure_shared_cache_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, CANONICAL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

SHARED_SENTINEL = Path("scripts") / "lib" / "project_root.py"
PLUGINS_SENTINEL = Path("shipwright-run") / "scripts" / "lib" / "phase_task_lifecycle.py"

#: The cross-plugin sentinel's own source — the ONE file the pre-2026-08-01
#: health check inspected on behalf of all fourteen mirrors.
RUN_SENTINEL_SRC = {
    "scripts/lib/phase_task_lifecycle.py":
        "def find_phase_task_by_session_uuid(*a):\n    return None\n",
}

#: A second plugin, so "the sentinel plugin is fine" and "every plugin is fine"
#: can disagree — which is the whole subject of the partial-reap module.
OTHER_SRC = {
    "scripts/lib/keep.py": "KEEP = 1\n",
    "scripts/lib/reaped.py": "REAPED = 1\n",
    "skills/compliance/SKILL.md": "# compliance\n",
}


def make_shared(root: Path) -> Path:
    """A minimal-but-healthy shared/ tree at ``root`` (with an ignorable junk dir)."""
    (root / SHARED_SENTINEL).parent.mkdir(parents=True, exist_ok=True)
    (root / SHARED_SENTINEL).write_text("# sentinel\n", encoding="utf-8")
    (root / "scripts" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "hooks" / "track_tool_calls.py").write_text("# hook\n", encoding="utf-8")
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__" / "x.pyc").write_text("junk", encoding="utf-8")
    return root


def cache_and_marketplace(tmp_path: Path) -> tuple[Path, Path]:
    """Return (cache/shipwright root, marketplaces/shipwright/shared root)."""
    plugins = tmp_path / ".claude" / "plugins"
    return plugins / "cache" / "shipwright", plugins / "marketplaces" / "shipwright" / "shared"


def install(cache_sw: Path, name: str, version: str, files: dict[str, str]) -> Path:
    """Create an installed plugin dir cache/shipwright/<name>/<version>/ with files."""
    vdir = cache_sw / name / version
    vdir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = vdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return vdir


def install_run(cache_sw: Path) -> Path:
    """An installed shipwright-run carrying the cross-plugin (plugins/) sentinel."""
    return install(cache_sw, "shipwright-run", "1.0.0", RUN_SENTINEL_SRC)


def mirror(cache_sw: Path, name: str, files: dict[str, str]) -> Path:
    """Write a cross-plugin mirror at cache/shipwright/plugins/<name>/."""
    dst = cache_sw / "plugins" / name
    for rel, content in files.items():
        p = dst / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return dst


def mirror_all(cache_sw: Path) -> None:
    """Bring cache/plugins/ to the state a COMPLETED heal leaves behind.

    Every installed plugin's newest version, mirrored — which is what "the
    plugins tree is healthy" now means. Writing only shipwright-run's sentinel
    (as the idempotency fixture did until 2026-08-01) does NOT produce a healthy
    tree; it produces the exact half-mirrored state whose invisibility is the
    defect these modules were extended to cover.

    Uses the hook's OWN ignore callable and version ordering rather than second
    hand-written copies: a fixture that ignored less than the hook, or picked a
    different version than the hook, would leave files the hook then reports as
    gaps — so "already healed" would silently stop meaning healed.
    """
    hook = hook_module()
    for plugin_dir in sorted(cache_sw.iterdir()):
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("shipwright-"):
            continue
        versions = sorted((v for v in plugin_dir.iterdir() if v.is_dir()),
                          key=lambda v: hook._version_key(v.name))
        if versions:
            shutil.copytree(versions[-1], cache_sw / "plugins" / plugin_dir.name,
                            ignore=hook._IGNORE, dirs_exist_ok=True)


def place_hook(cache_sw: Path) -> Path:
    """Install shipwright-build carrying the REAL vendored bootstrap; return its path."""
    vdir = install(cache_sw, "shipwright-build", "0.2.2", {})
    script = vdir / "scripts" / "hooks" / "ensure_shared_cache.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(CANONICAL.read_bytes())
    script.with_name("cache_repair_lock.py").write_bytes(LOCK_HELPER.read_bytes())
    return script


def run(script: Path) -> subprocess.CompletedProcess:
    """Execute the bootstrap exactly where a SessionStart hook would.

    ``sys.executable``, never a probed binary, so there is no silent-skip path
    that would need to hard-fail in CI.
    """
    return subprocess.run(
        [sys.executable, str(script)], input="{}",
        capture_output=True, text=True, timeout=60,
    )
