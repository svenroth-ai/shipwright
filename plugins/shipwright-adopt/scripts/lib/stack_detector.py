"""Layer-1 deterministic stack detection for /shipwright-adopt.

Reads package.json, pyproject.toml, go.mod, Cargo.toml, composer.json,
Gemfile to produce a structured stack signature. Pure, no side effects.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# Frontend frameworks (matched against npm deps)
_FRONTEND_HINTS = {
    "next": "Next.js",
    "react": "React",
    "react-dom": "React",
    "vue": "Vue",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "@remix-run/react": "Remix",
    "nuxt": "Nuxt",
    "astro": "Astro",
    "solid-js": "SolidJS",
}

# Backend / server frameworks
_BACKEND_HINTS_JS = {
    "express": "Express",
    "fastify": "Fastify",
    "hono": "Hono",
    "koa": "Koa",
    "@nestjs/core": "NestJS",
    "next": "Next.js (API routes)",
}
_BACKEND_HINTS_PY = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "starlette": "Starlette",
    "aiohttp": "aiohttp",
}

# Database clients
_DB_HINTS_JS = {
    "@supabase/supabase-js": "Supabase",
    "pg": "PostgreSQL (pg)",
    "mysql2": "MySQL",
    "mongoose": "MongoDB (mongoose)",
    "mongodb": "MongoDB",
    "prisma": "Prisma",
    "drizzle-orm": "Drizzle",
    "@planetscale/database": "PlanetScale",
}
_DB_HINTS_PY = {
    "psycopg2": "PostgreSQL (psycopg2)",
    "psycopg": "PostgreSQL (psycopg3)",
    "sqlalchemy": "SQLAlchemy",
    "asyncpg": "PostgreSQL (asyncpg)",
    "pymongo": "MongoDB",
    "supabase": "Supabase",
}

# Auth libraries
_AUTH_HINTS_JS = {
    "@supabase/auth-helpers-nextjs": "Supabase Auth",
    "@supabase/ssr": "Supabase SSR Auth",
    "next-auth": "NextAuth.js",
    "@clerk/nextjs": "Clerk",
    "@auth0/nextjs-auth0": "Auth0",
    "passport": "Passport",
    "lucia": "Lucia",
}
_AUTH_HINTS_PY = {
    "authlib": "Authlib",
    "python-jose": "JOSE (JWT)",
    "pyjwt": "PyJWT",
    "django-allauth": "django-allauth",
    "flask-login": "Flask-Login",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _match_hints(deps: dict[str, str], hints: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for dep, label in hints.items():
        if dep in deps:
            out[dep] = f"{label}@{deps[dep]}"
    return out


def _extract_pyproject_deps(content: str) -> dict[str, str]:
    """Best-effort extraction of dependency names from pyproject.toml.

    Handles both PEP-621 `[project].dependencies = [...]` and older
    poetry `[tool.poetry.dependencies]`. Version strings are approximated.
    """
    deps: dict[str, str] = {}
    # PEP-621: dependencies = ["fastapi>=0.100", ...]
    pep621_match = re.search(
        r"^\s*dependencies\s*=\s*\[([^\]]*)\]",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if pep621_match:
        for item in re.findall(r'"([^"]+)"', pep621_match.group(1)):
            name = re.split(r"[<>=!~\s\[]", item, maxsplit=1)[0].strip().lower()
            ver = item[len(name):].strip() or "*"
            if name:
                deps[name] = ver
    # Poetry: [tool.poetry.dependencies] block
    poetry_match = re.search(
        r"\[tool\.poetry\.dependencies\]\s*\n((?:[^\[]+\n)*)",
        content,
    )
    if poetry_match:
        for line in poetry_match.group(1).splitlines():
            m = re.match(r'\s*([\w.-]+)\s*=\s*"([^"]+)"', line)
            if m:
                deps[m.group(1).lower()] = m.group(2)
    return deps


def detect_stack(project_root: Path, excludes: set[str] | None = None) -> dict[str, Any]:
    """Detect stack signature from manifest files. Returns a JSON-serializable dict."""
    excludes = excludes or set()
    signatures: list[str] = []
    runtime: dict[str, str] = {}
    frontend: dict[str, str] = {}
    backend: dict[str, str] = {}
    database: dict[str, str] = {}
    auth: dict[str, str] = {}
    primary_language = "unknown"

    # Skip files under excluded paths
    def _is_excluded(p: Path) -> bool:
        rel = p.relative_to(project_root).as_posix() if p.is_relative_to(project_root) else p.as_posix()
        return any(rel == e or rel.startswith(e + "/") for e in excludes)

    # package.json — JavaScript / TypeScript
    pkg = project_root / "package.json"
    if pkg.exists() and not _is_excluded(pkg):
        data = _read_json(pkg) or {}
        engines = data.get("engines", {})
        if engines.get("node"):
            runtime["node"] = engines["node"]
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        if "typescript" in deps:
            runtime["typescript"] = deps["typescript"]
            primary_language = "typescript"
        elif deps:
            primary_language = "javascript"
        frontend.update(_match_hints(deps, _FRONTEND_HINTS))
        backend.update(_match_hints(deps, _BACKEND_HINTS_JS))
        database.update(_match_hints(deps, _DB_HINTS_JS))
        auth.update(_match_hints(deps, _AUTH_HINTS_JS))
        signatures.append("has-package-json")

    # pyproject.toml — Python
    pypro = project_root / "pyproject.toml"
    if pypro.exists() and not _is_excluded(pypro):
        content = _read_text(pypro) or ""
        pyver = re.search(r'requires-python\s*=\s*"([^"]+)"', content)
        if pyver:
            runtime["python"] = pyver.group(1)
        deps = _extract_pyproject_deps(content)
        backend.update(_match_hints(deps, _BACKEND_HINTS_PY))
        database.update(_match_hints(deps, _DB_HINTS_PY))
        auth.update(_match_hints(deps, _AUTH_HINTS_PY))
        if primary_language == "unknown" or (deps and primary_language == "javascript"):
            primary_language = "python" if primary_language == "unknown" else "mixed"
        signatures.append("has-pyproject-toml")

    # go.mod — Go
    gomod = project_root / "go.mod"
    if gomod.exists() and not _is_excluded(gomod):
        content = _read_text(gomod) or ""
        gover = re.search(r"^go\s+(\S+)", content, re.MULTILINE)
        if gover:
            runtime["go"] = gover.group(1)
        primary_language = "go" if primary_language in {"unknown"} else "mixed"
        signatures.append("has-go-mod")

    # Cargo.toml — Rust
    cargo = project_root / "Cargo.toml"
    if cargo.exists() and not _is_excluded(cargo):
        content = _read_text(cargo) or ""
        rver = re.search(r'rust-version\s*=\s*"([^"]+)"', content)
        if rver:
            runtime["rust"] = rver.group(1)
        primary_language = "rust" if primary_language in {"unknown"} else "mixed"
        signatures.append("has-cargo-toml")

    # composer.json — PHP
    composer = project_root / "composer.json"
    if composer.exists() and not _is_excluded(composer):
        data = _read_json(composer) or {}
        require = data.get("require", {})
        if "php" in require:
            runtime["php"] = require["php"]
        primary_language = "php" if primary_language in {"unknown"} else "mixed"
        signatures.append("has-composer-json")

    # Gemfile — Ruby
    gemfile = project_root / "Gemfile"
    if gemfile.exists() and not _is_excluded(gemfile):
        content = _read_text(gemfile) or ""
        rver = re.search(r'ruby\s+"([^"]+)"', content)
        if rver:
            runtime["ruby"] = rver.group(1)
        primary_language = "ruby" if primary_language in {"unknown"} else "mixed"
        signatures.append("has-gemfile")

    # Supabase signal
    if (project_root / "supabase").is_dir():
        signatures.append("has-supabase-dir")

    # TS strict mode signal
    tsconfig = project_root / "tsconfig.json"
    if tsconfig.exists():
        data = _read_json(tsconfig) or {}
        if data.get("compilerOptions", {}).get("strict") is True:
            signatures.append("has-tsconfig-strict")

    return {
        "primary_language": primary_language,
        "runtime": runtime,
        "frontend": frontend,
        "backend": backend,
        "database": database,
        "auth": auth,
        "signals": signatures,
    }
