"""Detect 'split frontend/backend' layouts in a project root.

Used by /shipwright-adopt's Layer-1 codebase analysis. Surfaces
`stack.multi_service` in the snapshot so adopt's Step B.5 can decide
whether to start multiple services for the Playwright crawl, and so the
stack matcher can pick a multi-service profile (e.g. vite-hono).

Decision matrix (single source of truth, mirrors AC7):
    Layout pair  | Both-sides framework signal | Vite proxy | detected | confidence
    -------------+-----------------------------+------------+----------+-----------
    yes          | yes                         | yes        | true     | high
    yes          | yes                         | no         | true     | medium
    yes          | one-sided OR none           | any        | false    | low
    no           | n/a                         | any        | false    | low

In every `detected: false` case, evidence is still recorded so adopt's
interview can ask the user.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Sibling-pair candidate roots (frontend, backend), ordered by specificity
LAYOUT_PAIRS: list[tuple[str, str]] = [
    ("client", "server"),
    ("frontend", "backend"),
    ("web", "api"),
]

FRONTEND_FRAMEWORKS = {
    "vite", "react", "react-dom", "vue", "next", "svelte", "astro",
    "nuxt", "solid-js", "@sveltejs/kit", "@remix-run/react",
}

BACKEND_FRAMEWORKS = {
    "hono", "express", "fastify", "koa", "@nestjs/core",
    "@hono/node-server",
}

VITE_CONFIG_NAMES = ("vite.config.ts", "vite.config.js", "vite.config.mjs", "vite.config.cjs")

# Multiline regex for `proxy: { '/api': { target: '...' } }`
PROXY_RE = re.compile(
    r"""proxy\s*:\s*\{[^{}]*?['"]/api['"]\s*:\s*(?:['"]([^'"]+)['"]|\{[^{}]*?target\s*:\s*['"]([^'"]+)['"])""",
    re.DOTALL,
)


def _read_pkg(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _all_pkg_deps(pkg: dict) -> set[str]:
    deps = pkg.get("dependencies") or {}
    dev = pkg.get("devDependencies") or {}
    return set(deps.keys()) | set(dev.keys())


def _has_frontend_framework(pkg: dict) -> tuple[bool, str | None]:
    deps = _all_pkg_deps(pkg)
    for fw in FRONTEND_FRAMEWORKS:
        if fw in deps:
            return True, fw
    return False, None


def _has_backend_framework(pkg: dict) -> tuple[bool, str | None]:
    deps = _all_pkg_deps(pkg)
    for fw in BACKEND_FRAMEWORKS:
        if fw in deps:
            return True, fw
    # `dev` script counts as backend signal for plain Node-style backends
    scripts = pkg.get("scripts") or {}
    if scripts.get("dev"):
        return True, "node-dev-script"
    return False, None


def _find_vite_proxy_target(project_root: Path, candidate_frontend_roots: list[Path]) -> str | None:
    """Search vite.config in candidate frontend roots + project root for `proxy: /api: target`."""
    search_roots = list(candidate_frontend_roots) + [project_root]
    for root in search_roots:
        for name in VITE_CONFIG_NAMES:
            cfg = root / name
            if cfg.is_file():
                try:
                    text = cfg.read_text(encoding="utf-8")
                except OSError:
                    continue
                m = PROXY_RE.search(text)
                if m:
                    return m.group(1) or m.group(2)
    return None


def _detect_pair(
    project_root: Path, frontend_dir: str, backend_dir: str
) -> dict | None:
    """Probe one layout pair. Returns a partial result dict if package.jsons
    exist on both sides (regardless of framework signal); else None."""
    fe_root = project_root / frontend_dir
    be_root = project_root / backend_dir
    fe_pkg_path = fe_root / "package.json"
    be_pkg_path = be_root / "package.json"
    if not fe_pkg_path.is_file() or not be_pkg_path.is_file():
        return None
    fe_pkg = _read_pkg(fe_pkg_path) or {}
    be_pkg = _read_pkg(be_pkg_path) or {}
    fe_has, fe_fw = _has_frontend_framework(fe_pkg)
    be_has, be_fw = _has_backend_framework(be_pkg)
    fe_dev_cmd = (fe_pkg.get("scripts") or {}).get("dev")
    be_dev_cmd = (be_pkg.get("scripts") or {}).get("dev")
    return {
        "frontend": {
            "name": "frontend",
            "root": frontend_dir,
            "framework": fe_fw,
            "dev_command": f"npm --prefix {frontend_dir} run dev" if fe_dev_cmd else None,
            "proxy_target": None,
        },
        "backend": {
            "name": "backend",
            "root": backend_dir,
            "framework": be_fw,
            "dev_command": f"npm --prefix {backend_dir} run dev" if be_dev_cmd else None,
            "proxy_target": None,
        },
        "fe_has_framework": fe_has,
        "be_has_framework": be_has,
        "frontend_root_path": fe_root,
    }


def detect_multi_service_layout(project_root: Path) -> dict[str, Any]:
    """Detect split frontend/backend layout in `project_root`.

    Returns: {detected: bool, confidence: str, services: list, evidence: list}
    """
    evidence: list[str] = []
    for fe_dir, be_dir in LAYOUT_PAIRS:
        result = _detect_pair(project_root, fe_dir, be_dir)
        if result is None:
            continue
        evidence.append(f"sibling package.jsons found at {fe_dir}/ + {be_dir}/")
        services = [result["frontend"], result["backend"]]
        # Vite proxy probe (broadens confidence to `high`)
        proxy_target = _find_vite_proxy_target(
            project_root, [result["frontend_root_path"]]
        )
        if proxy_target:
            evidence.append(f"vite proxy /api → {proxy_target}")
            services[1]["proxy_target"] = proxy_target

        # Apply decision matrix
        both_have_framework = result["fe_has_framework"] and result["be_has_framework"]
        if not both_have_framework:
            if result["fe_has_framework"]:
                evidence.append(f"frontend framework signal: {result['frontend']['framework']}")
            elif result["be_has_framework"]:
                evidence.append(f"backend framework signal: {result['backend']['framework']}")
            else:
                evidence.append("no framework signal on either side")
            return {
                "detected": False,
                "confidence": "low",
                "services": services,
                "evidence": evidence,
            }
        evidence.append(f"frontend framework signal: {result['frontend']['framework']}")
        evidence.append(f"backend framework signal: {result['backend']['framework']}")
        confidence = "high" if proxy_target else "medium"
        return {
            "detected": True,
            "confidence": confidence,
            "services": services,
            "evidence": evidence,
        }

    # No layout pair matched
    return {
        "detected": False,
        "confidence": "low",
        "services": [],
        "evidence": evidence,
    }
