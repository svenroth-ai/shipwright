"""Shared builders for the brief package tests (layout / hash / links)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import brief_package as bp  # noqa: E402


def _brief(**over) -> dict:
    base = {
        "version": 2, "profile": "vite-hono", "deploy_target": "none", "autonomy": "unattended",
        "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
        "design_system": "visual-guidelines.md", "brief_dir": "brief",
        "allow_parallel_builders": False, "ui_host": "web", "env_preflight": [], "approved_by": "fixture:t", "approved_at": "2026-10-24",
    }
    base.update(over)
    return base


def _write(root: Path, rel: str, text: str, nl: str = "\n") -> None:
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(text.replace("\n", nl).encode("utf-8"))


def _package(root: Path, nl: str = "\n", **over) -> Path:
    _write(root, "brief.md", "# B\n\n## a\ntext\n", nl)
    _write(root, "scope.md", "# S\nin\n", nl)
    _write(root, "visual-guidelines.md", "# V\nplain\n", nl)
    _write(root, "mockups/01.html", "<html>\n</html>\n", nl)
    _write(root, "screen-map.json", json.dumps({"screens": [{"mockup": "01.html"}]}, indent=1) + "\n", nl)
    _write(root, "brief.json", json.dumps(_brief(**over), indent=1) + "\n", nl)
    return root


def _codes(root: Path) -> set[str]:
    return {i["code"] for i in bp.validate_layout(root)}


def _make_link(target: Path, link: Path) -> None:
    """A real directory link: a junction on Windows (no privilege needed), else a symlink."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _record_hash(root: Path) -> None:
    """Write the package's current hash into its ``brief.json`` (what approval records)."""
    brief = json.loads((root / "brief.json").read_text())
    brief["package_sha256"] = bp.package_sha256(root)
    _write(root, "brief.json", json.dumps(brief))
