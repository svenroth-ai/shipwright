"""Does a change touch anything a user or operator can observe? Decided from the diff, never from a label.

Fail-closed: a file is NOT observable only when it sits under a docs or test DIRECTORY root, is a known
ledger at the repository root, or is plain markdown outside the prompt directories. Everything else - scripts,
hooks, prompts, schemas, templates, config, CI, a Dockerfile, a Makefile, a lock file, ``.go``/``.rs``/``.sql``,
an unknown or missing extension - is observable. Names never decide (``test_gate.py`` and ``changelog.py``
are production code).

Even an observable file is a no-op when EVERY hunk changes only whitespace, blank lines or comments: compared
per hunk, in line order, keeping leading indentation for Python/YAML (indentation is syntax there), and a
shebang counts as code. A pure rename inside the same class is a no-op; a rename that crosses the boundary
(a test file moved into production, or the reverse) is observable. A Python docstring edit counts as observable.

Stdlib only; ``git`` is called with a fixed argument list, never through a shell.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

__all__ = ["git_changes", "is_observable_path", "is_test_path", "observable_files", "parse_diff"]

_DOC_ROOTS = frozenset({".shipwright", "docs", "changelog-unreleased.d"})
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "integration-tests"})
_LEDGERS = frozenset({"changelog.md", "readme.md", "shipwright_events.jsonl", "shipwright_test_results.json", "shipwright_bloat_baseline.json"})
_DOC_EXTS = frozenset({".md", ".rst"})
_PROMPT_DIRS = frozenset({"agents", "skills", "prompts", "templates"})
_PROMPT_FILES = frozenset({"constitution.md", "glossary.md", "skill.md", "claude.md"})
_INDENT_EXTS = frozenset({".py", ".yml", ".yaml"})
_HASH_COMMENT = frozenset({".py", ".sh", ".ps1", ".toml", ".yml", ".yaml", ".cfg", ".ini"})
_SLASH_COMMENT = frozenset({".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".go", ".rs", ".java"})


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name.lstrip(".") else ""


def is_test_path(path: str) -> bool:
    """True when ``path`` sits under a test directory (by directory only, never by file name)."""
    return bool(_TEST_DIRS & set(path.replace("\\", "/").lower().split("/")[:-1]))


def is_observable_path(path: str) -> bool:
    """True when a file at ``path`` can change what a user or operator observes (fail-closed, by location and extension)."""
    parts = path.replace("\\", "/").lower().split("/")
    name, dirs = parts[-1], parts[:-1]
    if parts[0] in _DOC_ROOTS or "docs" in dirs or is_test_path(path) or (not dirs and name in _LEDGERS):
        return False
    if _ext(path) in _DOC_EXTS:
        return name in _PROMPT_FILES or bool(_PROMPT_DIRS & set(dirs))
    return True


def parse_diff(text: str) -> dict[str, dict]:
    """``{path: {"hunks": [{"added", "removed"}], "added", "removed", "renamed_from", "new", "deleted"}}`` from a zero-context diff."""
    files: dict[str, dict] = {}
    cur: dict | None = None
    in_hunk = False
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r'diff --git "?a/(.*?)"? "?b/(.*?)"?$', line)
            cur = files.setdefault(m.group(2) if m else line, {"hunks": [], "added": [], "removed": [], "renamed_from": None, "new": False, "deleted": False})
            in_hunk = False
        elif cur is None:
            continue
        elif line.startswith("@@"):
            in_hunk = True
            cur["hunks"].append({"added": [], "removed": []})
        elif in_hunk and line[:1] in ("+", "-"):
            side = "added" if line[0] == "+" else "removed"
            cur[side].append(line[1:])
            cur["hunks"][-1][side].append(line[1:])
        elif line.startswith("rename from "):
            cur["renamed_from"] = line[12:]
        elif line.startswith("new file"):
            cur["new"] = True
        elif line.startswith("deleted file"):
            cur["deleted"] = True
    return files


def _significant(lines: list[str], ext: str) -> list[str]:
    out: list[str] = []
    for raw in lines:
        body = " ".join(raw.split())
        if not body:
            continue
        if body.startswith("#!"):
            pass
        elif (ext in _HASH_COMMENT and body.startswith("#")) or (ext in _SLASH_COMMENT and body.startswith(("//", "/*", "*"))):
            continue
        indent = raw[: len(raw) - len(raw.lstrip())] if ext in _INDENT_EXTS else ""
        out.append(indent + body)
    return out


def _is_noop(rec: dict, path: str) -> bool:
    if rec["new"] or rec["deleted"] or (not rec["hunks"] and not rec.get("renamed_from")):
        return False  # new, deleted, or a change git shows no text for (binary, mode): cannot be proven harmless
    ext = _ext(path)
    return all(_significant(h["removed"], ext) == _significant(h["added"], ext) for h in rec["hunks"])


def observable_files(changes: dict[str, dict]) -> dict:
    """``{"observable": bool, "files": [paths that change behaviour], "ignored": count}`` for a parsed diff."""
    hit = []
    for path, rec in changes.items():
        old = rec.get("renamed_from")
        if old and is_observable_path(old) != is_observable_path(path):
            hit.append(path)  # a rename crossing the observable boundary
        elif is_observable_path(path) and not _is_noop(rec, path):
            hit.append(path)
    hit.sort()
    return {"observable": bool(hit), "files": hit, "ignored": len(changes) - len(hit)}


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or f"git {args[0]} failed")
    return done.stdout


def git_changes(root: str | Path, base: str, head: str | None = None) -> dict[str, dict]:
    """Parsed changes ``base`` -> ``head``; with no ``head``, base -> working tree PLUS untracked files (as added)."""
    root = Path(root)
    changes = parse_diff(_git(root, "diff", "-U0", "-M", "--no-color", base, *([head] if head else [])))
    if head is None:
        for rel in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
            try:
                body = (root / rel).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                body = ["<binary>"]
            changes[rel] = {"hunks": [{"added": body, "removed": []}], "added": body, "removed": [], "renamed_from": None, "new": True, "deleted": False}
    return changes
