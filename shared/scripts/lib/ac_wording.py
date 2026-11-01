"""Outcome wording for an acceptance criterion (AC), checked against the catalog and the diff - a hard validation.

An AC says what a user or operator can rely on. It must not say how the code does it. The text is refused (the
agent rewrites it as outcome wording; this is NOT a question to the operator) when it contains:

* a file path (two or more slashes, a last segment with an extension, a leading dot, tilde or slash, or a repo
  root directory first) or a bare file name with a known extension;
* an identifier taken from the CHANGED CODE: a function, class or constant name, a flag, a module name;
* a snake_case, camelCase, CamelCase or UPPER_SNAKE token, or a double-dash flag;
* backticked code;
* an ADR number, an AC id or an FR id (the requirement catalog's own ids).

Ordinary prose passes: end-to-end, and/or, read/write, CI, API, brand names such as GitHub. Plain one-word
function names are not extracted from the diff (they are ordinary words); only code-shaped names are.
"""

from __future__ import annotations

import re

__all__ = ["diff_identifiers", "wording_violations"]

_ROOTS = frozenset({"plugins", "shared", "docs", "scripts", "tests", "src", ".shipwright", "integration-tests"})
_FILE = re.compile(r"\b[\w-]+\.(?:py|md|json|jsonl|ya?ml|toml|sh|js|ts|tsx|css|html|txt|cfg|ini)\b")
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_UPPER = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_CAMEL = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[a-z]+(?:[A-Z][a-z0-9]+)+)\b")
_FLAG = re.compile(r"(?<![\w-])--[A-Za-z][\w-]*")
_TICKS = re.compile(r"`(?!/[a-z][a-z-]*`)[^`]+`")  # a slash command the user types is product wording, not code
_NUMBERS = re.compile(r"\b(?:ADR-\d+|FR-\d+(?:\.\d+)*(?:\.AC\d+)?|AC\d+)\b")
# Product and brand names read as product wording, not code (a name with a dot is removed before the file-name rule).
_BRANDS = frozenset({"GitHub", "JavaScript", "TypeScript", "OpenAI", "OpenRouter", "PowerShell", "GitLab", "DevOps", "YouTube", "LinkedIn", "PyPI",
                     "WebUI", "CodeQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "GraphQL", "FastAPI", "OpenTelemetry", "SonarQube", "VSCode"})
_DOTTED = ("Node.js", "Next.js", "Vue.js", "Nuxt.js", "Express.js", "React.js", "Three.js", "Chart.js")
_COMMAND = re.compile(r"^/shipwright-[a-z]+$")
_DEF = re.compile(r"\b(?:def|class|function|const|let|var)\s+([A-Za-z_]\w+)")
_CONST = re.compile(r"^\s*([A-Z][A-Z0-9_]{3,})\s*[:=]")


def _path_like(token: str) -> bool:
    token = token.strip("()[]{}<>\"',;:.!?")
    if "/" not in token or "://" in token:
        return False
    segs = [s for s in token.split("/") if s]
    if _COMMAND.match(token):
        return False  # a bare slash command the user types (/shipwright-iterate) is product wording
    return (token.count("/") >= 2 or bool(re.search(r"\.\w{1,5}$", segs[-1] if segs else ""))
            or token[:1] in (".", "~", "/") or token.split("/")[0] in _ROOTS)


def _code_shaped(name: str) -> bool:
    return len(name) >= 4 and ("_" in name or "-" in name or bool(re.search(r"[a-z][A-Z]", name)) or name.startswith("--"))


def diff_identifiers(changes: dict[str, dict]) -> set[str]:
    """Code-shaped names (function, class, constant, flag, module) found in a parsed diff's changed lines and file names."""
    names: set[str] = set()
    for path, rec in (changes or {}).items():
        names.add(path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        for line in [*rec.get("added", []), *rec.get("removed", [])]:
            names.update(_DEF.findall(line))
            names.update(_CONST.findall(line))
            names.update(_FLAG.findall(line))
    return {n for n in names if _code_shaped(n)}


def wording_violations(text: object, identifiers: set[str] | None = None) -> list[str]:
    """What in ``text`` is not outcome wording (empty list = it reads as an outcome)."""
    if not isinstance(text, str):
        return []
    hits = [f"file path {t.strip('()[]{}<>,;:.')!r}" for t in text.split() if _path_like(t)]
    plain = text
    for dotted in _DOTTED:
        plain = plain.replace(dotted, "")
    hits += [f"file name {m!r}" for m in _FILE.findall(plain)]
    hits += [f"backticked code {m!r}" for m in _TICKS.findall(text)]
    for kind, rx in (("snake_case name", _SNAKE), ("UPPER_SNAKE name", _UPPER), ("flag", _FLAG), ("ADR/AC/FR number", _NUMBERS)):
        hits += [f"{kind} {m!r}" for m in rx.findall(text)]
    hits += [f"camelCase name {m!r}" for m in _CAMEL.findall(text) if m not in _BRANDS]
    for name in sorted(identifiers or ()):
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
            hits.append(f"name from the changed code {name!r}")
    return list(dict.fromkeys(hits))
