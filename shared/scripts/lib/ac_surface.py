"""Does a change touch anything a user or operator can observe? Decided from the diff, never from a label.

The observable surface is every file that defines behaviour: scripts, hooks, prompts (agents, skills and their
references, shared prompts, the constitution), schemas, templates, config defaults, CLI output, CI workflows. A
change is NOT observable when every file it touches is docs, tests, a generated artifact, or its changed lines are
only whitespace, blank lines, comments or a pure rename. The tool computes this from the changed files and the
changed lines; an agent cannot assert it. A Python docstring edit counts as observable (conservative: a
docstring is not told apart from code on a zero-context diff).

Stdlib only; ``git`` is called with a fixed argument list, never through a shell.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

__all__ = ["git_changes", "is_observable_path", "observable_files", "parse_diff"]

_BEHAVIOUR_EXTS = frozenset(".py .sh .ps1 .json .toml .yml .yaml .js .ts .tsx .jsx .css .html .cfg .ini .jsonl".split())
_PROMPT_DIRS = frozenset({"agents", "skills", "prompts", "templates"})
_PROMPT_FILES = frozenset({"constitution.md", "glossary.md", "skill.md", "claude.md"})
_HASH_COMMENT = frozenset(".py .sh .ps1 .toml .yml .yaml .cfg .ini".split())
_SLASH_COMMENT = frozenset(".js .ts .tsx .jsx .css .html".split())


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_observable_path(path: str) -> bool:
    """True when a file at ``path`` defines behaviour (by location and extension only)."""
    parts = path.replace("\\", "/").lower().split("/")
    name, dirs = parts[-1], parts[:-1]
    if parts[0] in (".shipwright", "docs", "changelog-unreleased.d") or "tests" in dirs or "docs" in dirs:
        return False
    if name.startswith(("test_", "readme", "changelog", "shipwright_")) or name.endswith(("_test.py", ".test.ts", ".test.tsx")) or name == "conftest.py":
        return False
    ext = _ext(path)
    if ext in _BEHAVIOUR_EXTS:
        return True
    return ext == ".md" and (name in _PROMPT_FILES or bool(_PROMPT_DIRS & set(dirs)))


def parse_diff(text: str) -> dict[str, dict]:
    """``{path: {"added": [...], "removed": [...], "renamed_from": str|None, "new": bool, "deleted": bool}}`` from a zero-context diff."""
    files: dict[str, dict] = {}
    cur: dict | None = None
    in_hunk = False
    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            m = re.match(r'diff --git "?a/(.*?)"? "?b/(.*?)"?$', line)
            cur = files.setdefault(m.group(2) if m else line, {"added": [], "removed": [], "renamed_from": None, "new": False, "deleted": False})
            in_hunk = False
        elif cur is None:
            continue
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line[:1] in ("+", "-"):
            cur["added" if line[0] == "+" else "removed"].append(line[1:])
        elif line.startswith("rename from "):
            cur["renamed_from"] = line[12:]
        elif line.startswith("new file"):
            cur["new"] = True
        elif line.startswith("deleted file"):
            cur["deleted"] = True
    return files


def _significant(lines: list[str], ext: str) -> Counter:
    out: Counter = Counter()
    for raw in lines:
        s = "".join(raw.split())
        if not s or (ext in _HASH_COMMENT and s.startswith("#")) or (ext in _SLASH_COMMENT and s.startswith(("//", "/*", "*"))):
            continue
        out[s] += 1
    return out


def _is_noop(rec: dict, path: str) -> bool:
    if rec["new"] or rec["deleted"]:
        return False
    return _significant(rec["added"], _ext(path)) == _significant(rec["removed"], _ext(path))


def observable_files(changes: dict[str, dict]) -> dict:
    """``{"observable": bool, "files": [paths that change behaviour], "ignored": count}`` for a parsed diff."""
    hit = sorted(p for p, rec in changes.items() if is_observable_path(p) and not _is_noop(rec, p))
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
            changes[rel] = {"added": body, "removed": [], "renamed_from": None, "new": True, "deleted": False}
    return changes
