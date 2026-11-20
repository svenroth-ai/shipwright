"""Package-source redirection checks (``SURFACE_REGISTRY_REDIRECT``).

A committed ``.npmrc`` / ``pip.conf`` / ``uv.toml`` that points package
resolution at a non-default host changes *where every install comes from* — the
classic dependency-confusion / typosquat-mirror vector. Trivy sees the resulting
packages, not the redirect, and Gitleaks sees only credentials.

Part of the advisory ``skill_surface_scan`` package; see its docstring for the
attribution note (categories inspired by NVIDIA SkillSpector, Apache-2.0; rules
re-implemented, no code or text copied).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_surface_hooks import is_loopback  # noqa: E402

REGISTRY_FILES = {
    ".npmrc", ".yarnrc", ".yarnrc.yml", "pip.conf", "pip.ini", "uv.toml", "pyproject.toml",
}

# Canonical hosts for the ecosystems these files configure.
DEFAULT_HOSTS = {
    "registry.npmjs.org", "registry.yarnpkg.com", "pypi.org", "files.pythonhosted.org",
    # First-party hosts that ordinary projects point at (GitHub Packages, the PyTorch wheel index).
    "npm.pkg.github.com", "download.pytorch.org",
}

_URL = re.compile(r"https?://[^\s\"'<>,]+", re.IGNORECASE)
# Greedy `(.*)` + strip in Python: a lazy group followed by `\s*$` backtracks quadratically.
_NPM_KEY = re.compile(r"^\s*(?:@[\w.-]+:)?registry\s*=(.*)$", re.IGNORECASE)
_YARN_KEY = re.compile(r"^\s*(?:registry\s+|npmRegistryServer\s*:)(.*)$")
_PIP_KEY = re.compile(r"^\s*(index[-_]url|extra[-_]index[-_]url)\s*[=:](.*)$", re.IGNORECASE)
# Value may be a string, a list (`["https://..."]`, often over several lines) or an inline table.
_TOML_KEY = re.compile(r"^\s*(index-url|extra-index-url|url|index|find-links)\s*=\s*(.*)$")
_TOML_SECTION = re.compile(r"^\s*\[\[?([^\]]*)\]\]?\s*(?:#.*)?$")

_HINT = (
    "Confirm the index is an intended internal mirror. A redirected source lets "
    "whoever runs it substitute any package; pin the host or drop the override."
)


def _foreign_host(value: str) -> str | None:
    """First host in ``value`` that is neither default nor loopback.

    Every URL is checked: pip accepts several whitespace-separated indexes on one line, so a
    default index listed first must not hide a foreign one after it.
    """
    for match in _URL.finditer(value):
        try:
            host = (urlsplit(match.group(0)).hostname or "").lower()
        except ValueError:
            continue
        if host and host not in DEFAULT_HOSTS and not is_loopback(host):
            return host
    return None


def _flag(emit, line_no: int, key: str, host: str) -> None:
    emit(
        "medium",
        "SURFACE_REGISTRY_REDIRECT",
        f"Package source is redirected: '{key}' points at {host}, not the ecosystem's "
        f"default registry. Every install resolved through this file trusts that host.",
        line_no,
        _HINT,
    )


def scan_registry(name: str, text: str, emit) -> None:
    """Emit one finding per redirected package source in ``text``."""
    section = ""
    pending: tuple[str, str] | None = None  # (key, closer) while a multi-line value is open
    for line_no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ";", "//")):
            continue

        if pending is not None:
            key, closer = pending
            if closer == "pip" and not raw[:1].isspace():
                pending = None  # an unindented line ends a pip continuation; fall through
            else:
                host = _foreign_host(raw)
                if host:
                    _flag(emit, line_no, key, host)
                if closer == "]" and "]" in raw:
                    pending = None
                continue

        if name in {"uv.toml", "pyproject.toml"}:
            head = _TOML_SECTION.match(raw)
            if head:
                section = head.group(1).strip().lower()
                continue
            hit = _TOML_KEY.match(raw)
            if not hit:
                continue
            key, value = hit.group(1), hit.group(2)
            # `url` is only a package index inside an index table; in pyproject.toml
            # only uv/pip tables configure resolution at all.
            in_index_table = section.rsplit(".", 1)[-1] == "index"
            if key == "url" and not in_index_table:
                continue
            if name == "pyproject.toml" and not (section == "tool.uv" or section.startswith("tool.uv.")):
                continue
            if value.count("[") > value.count("]"):
                pending = (key, "]")
            host = _foreign_host(value)
            if host:
                _flag(emit, line_no, key, host)
            continue

        pattern = _NPM_KEY if name == ".npmrc" else _YARN_KEY if name.startswith(".yarnrc") else _PIP_KEY
        hit = pattern.match(raw)
        if not hit:
            continue
        value = hit.group(hit.lastindex)
        key = hit.group(1) if pattern is _PIP_KEY else "registry"
        if pattern is _PIP_KEY and not value.strip():
            pending = (key, "pip")
        host = _foreign_host(value)
        if host:
            _flag(emit, line_no, key, host)
