"""Centralized environment variable loading for Shipwright plugins.

All plugins load credentials from the project's .env.local file (CWD).
Variables already present in os.environ are never overwritten.
"""

import os
import re
from pathlib import Path


def find_shipwright_root(start: Path | None = None) -> Path:
    """Find the Shipwright repo root by walking up from *start*.

    Looks for a directory containing both ``plugins/`` and ``shared/``.
    Falls back to ``SHIPWRIGHT_ROOT`` env var if the walk fails.
    """
    if start is None:
        start = Path(__file__).resolve().parent

    current = start
    for _ in range(10):  # safety limit
        if (current / "plugins").is_dir() and (current / "shared").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback: env var
    root_env = os.environ.get("SHIPWRIGHT_ROOT")
    if root_env:
        return Path(root_env)

    raise FileNotFoundError(
        "Could not locate Shipwright repo root. "
        "Set SHIPWRIGHT_ROOT or run from within the repo."
    )


def _strip_inline_comment(raw: str) -> str:
    """See ``shared/scripts/validate_env._strip_inline_comment`` for the
    canonical contract. Duplicated here intentionally: ``shared/scripts/lib/``
    is imported by ``load_shipwright_env`` from any plugin without going
    through the parent ``shared.scripts`` package, so a cross-module import
    here would create a circular shape. Drift between the two copies is
    locked down by ``TestParseEnvFileLibCopy``.
    """
    raw = raw.lstrip()
    if not raw or raw[0] == "#":
        return ""
    if raw[0] in ('"', "'"):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end == -1:
            return raw[1:].rstrip()
        return raw[1:end]
    m = re.search(r"\s+#", raw)
    if m:
        raw = raw[:m.start()]
    return raw.rstrip()


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict of key-value pairs.

    Handles ``KEY=value``, ``KEY="value"``, ``KEY='value'``, ``export KEY=value``
    (POSIX-style), inline ``# comment`` (whitespace-separated, unquoted only),
    full-line comments, and blank lines. Does NOT expand variable references.
    """
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    # ``utf-8-sig`` strips a leading UTF-8 BOM (Windows Notepad writes one
    # when saving as UTF-8). Without this the first key on a BOM-prefixed
    # file gets a ``﻿`` prefix and the runtime can't find it. See
    # iterate-2026-05-03-adopt-env-local-scaffold for the empirical catch.
    text = env_path.read_text(encoding="utf-8-sig")

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[len("export"):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = _strip_inline_comment(value)
        if key:
            env_vars[key] = value
    return env_vars


def load_shipwright_env(project_root: Path | None = None) -> Path | None:
    """Load ``<project_root>/.env.local`` into ``os.environ``.

    *project_root* defaults to CWD (= the target project when Claude Code
    runs scripts).  Existing environment variables are never overwritten.
    Returns the path that was loaded, or ``None`` if no file found.
    """
    root = Path(project_root) if project_root else Path.cwd()
    env_path = root / ".env.local"
    if not env_path.exists():
        return None

    for key, value in parse_env_file(env_path).items():
        if key not in os.environ:
            os.environ[key] = value

    return env_path
