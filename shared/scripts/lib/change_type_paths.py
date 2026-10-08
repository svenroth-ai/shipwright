"""Which paths a no-FR ``change_type`` may touch: one classification per change_type.

The FR-gate lets an iterate skip naming a requirement by labelling itself
``docs``, ``tooling``, ``compliance`` or ``infra``. Until now the label was
believed. :mod:`lib.change_type_diff` now checks it against the diff, and this
module says what each label covers.

**Project-aware, not global.** "No runtime code" would be the obvious global
rule, and it is wrong: in the Shipwright monorepo the product IS developer
tooling, so ``tooling`` and ``infra`` legitimately cover ``plugins/**``,
``shared/**`` and ``scripts/**``. A generic project (a WebUI, a service) keeps
its runtime code - ``src/**``, ``server/**``, ``app/**`` - outside every label.
A change whose paths no built-in rule covers links its FR instead. There is
deliberately no per-project override key: a configurable exemption policy is
a permanent contract consumers come to depend on, so it is added only when a
real project needs one (architecture review of U6).

**Every label covers** documentation, tests (not product behaviour; a tooling
change that updates its doc and its tests is still a tooling change) and
Shipwright's own finalization records. ``docs`` covers only those.

Patterns are repo-relative POSIX globs: ``**`` spans directories, ``*`` and
``?`` stay inside one segment, and a pattern without ``**/`` is anchored at the
project root. Standard library only (plus the stdlib-only ``lib.fr_classification``).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from lib.fr_classification import CHANGE_TYPE_VALUES

__all__ = [
    "SHAPE_GENERIC", "SHAPE_SHIPWRIGHT_MONOREPO",
    "allowed_patterns", "detect_shape", "matches", "unclassified_paths",
]

SHAPE_GENERIC = "generic"
SHAPE_SHIPWRIGHT_MONOREPO = "shipwright-monorepo"

#: Shipwright's own finalization records, written by every iterate.
_BOOKKEEPING = (
    ".shipwright/**", "CHANGELOG-unreleased.d/**", "CHANGELOG.md",
    "shipwright_events.jsonl", "shipwright_test_results.json",
)
_DOCS = (
    "docs/**", "**/docs/**", "**/*.md", "**/*.rst", "**/*.adoc",  # not .mdx: it is executable
    "LICENSE*", "NOTICE*", "AUTHORS*", "**/README*",
)
_TESTS = (
    "tests/**", "test/**", "**/tests/**", "**/test/**", "**/__tests__/**",
    "e2e/**", "**/e2e/**", "integration-tests/**",
    "**/test_*.py", "**/*_test.py", "**/conftest.py", "**/*_test.go",
    "**/*.test.*", "**/*.spec.*",
)
_TOOLING = (
    "scripts/**", "tools/**", ".claude/**", ".codex/**", ".vscode/**", ".devcontainer/**",
    ".editorconfig", ".pre-commit-config.yaml", "ruff.toml", ".ruff.toml", "pyproject.toml",
    ".eslintrc*", "eslint.config.*", ".prettierrc*", "prettier.config.*", ".prettierignore",
    "vitest.config.*", "jest.config.*", "playwright.config.*", "pytest.ini", "tox.ini",
    "noxfile.py", "Makefile", "justfile", "shipwright_*.json", "shipwright_*.yaml", "audit_config.json",
)
_INFRA = (
    ".github/**", ".gitlab-ci.yml", ".circleci/**", "Dockerfile*", "**/Dockerfile*",
    ".dockerignore", "docker-compose*", "compose*.yml", "compose*.yaml",
    "infra/**", "deploy/**", "terraform/**", "**/*.tf", "k8s/**", "helm/**",
    ".gitignore", ".gitattributes", "pyproject.toml", "uv.lock", "poetry.lock",
    "requirements*.txt", "package.json", "package-lock.json", "pnpm-lock.yaml",
    "pnpm-workspace.yaml", "yarn.lock", ".npmrc", ".nvmrc", ".python-version",
    "tsconfig*.json", "vite.config.*", "vercel.json", "netlify.toml", "fly.toml",
    "Procfile", ".env.example", "renovate.json", "scripts/**", "shipwright_*.json", "shipwright_*.yaml",
    "audit_config.json", ".trivyignore*",
)
_COMPLIANCE = (
    "SECURITY.md", ".semgrep*", ".semgrep/**", ".gitleaks*", ".trivyignore*",
    ".github/workflows/**", ".github/codeql/**", "THIRD_PARTY*", "**/sbom*",
    "shipwright_*.json", "shipwright_*.yaml", "audit_config.json",
)
#: In the Shipwright monorepo the plugins and shared scripts ARE the tooling.
_MONOREPO_PRODUCT = (
    "plugins/**", "shared/**", "scripts/**", "integration-tests/**",
    ".claude-plugin/**", "conftest.py", "pyproject.toml", "uv.lock",
)

# Keyed by the FR-gate's own enum (docs, tooling, compliance, infra), so the two
# can never name a different set of labels.
_DOCS_CT, _TOOLING_CT, _COMPLIANCE_CT, _INFRA_CT = CHANGE_TYPE_VALUES
_BASE = {
    _DOCS_CT: _TESTS + _DOCS,
    _TOOLING_CT: _TOOLING + _TESTS + _DOCS,
    _INFRA_CT: _INFRA + _TESTS + _DOCS,
    _COMPLIANCE_CT: _COMPLIANCE + _TESTS + _DOCS,
}
_MONOREPO_EXTRA = {
    _DOCS_CT: (),
    _TOOLING_CT: _MONOREPO_PRODUCT + _INFRA,
    _INFRA_CT: _MONOREPO_PRODUCT + _TOOLING,
    _COMPLIANCE_CT: _MONOREPO_PRODUCT,
}


def detect_shape(project_root) -> str:
    """``shipwright-monorepo`` for a repo shaped like this one, else ``generic``."""
    root = Path(project_root)
    try:
        if (root / "shared" / "scripts").is_dir() and (root / ".claude-plugin" / "marketplace.json").is_file():
            return SHAPE_SHIPWRIGHT_MONOREPO
    except OSError:
        pass
    return SHAPE_GENERIC


def allowed_patterns(change_type: str, shape: str) -> tuple[str, ...]:
    """Every pattern ``change_type`` covers in a project of ``shape``."""
    patterns = _BOOKKEEPING + _BASE.get(change_type, ())
    if shape == SHAPE_SHIPWRIGHT_MONOREPO:
        patterns += _MONOREPO_EXTRA.get(change_type, ())
    return patterns


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, pattern: str) -> bool:
    """``path`` (repo-relative, POSIX) matches the glob ``pattern``."""
    return _compile(pattern).match(path) is not None


def unclassified_paths(paths, change_type: str, shape: str) -> list[str]:
    """The paths ``change_type`` does NOT cover, sorted and de-duplicated."""
    patterns = allowed_patterns(change_type, shape)
    out = set()
    for raw in paths:
        path = str(raw).replace("\\", "/").strip()
        while path.startswith("./"):
            path = path[2:]
        if path and not any(matches(path, p) for p in patterns):
            out.add(path)
    return sorted(out)
