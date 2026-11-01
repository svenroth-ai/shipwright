"""Does a change touch anything a user or operator can observe? Decided from the diff, never from a label.

Fail-closed: a file is NOT observable only when it sits under a docs or test DIRECTORY ROOT (the repository root,
or a plugin's own root - ``src/docs/router.ts`` is code), is a known ledger at the repository root, or is plain
markdown outside the prompt directories. Everything else - scripts, hooks, prompts, schemas, templates, config,
CI, ``.shipwright/profiles/``, a Dockerfile, a Makefile, a lock file, ``.go``/``.rs``/``.sql``, an unknown or
missing extension - is observable. Names never decide (``test_gate.py`` and ``changelog.py`` are production code).

Even an observable file is a no-op when EVERY hunk changes only blank lines or FULL-LINE comments of its own
extension's syntax. Compared per hunk, in line order, keeping leading indentation for Python/YAML and tabs for a
Makefile (indentation is syntax there); inner spacing is kept (it can sit inside a string); a shebang counts as
code; a ``#`` line inside a Python multi-line string is text, not a comment (found with ``tokenize``; when that
cannot be decided the line counts as code); a ``*`` line is a comment only inside a ``/* */`` block of the same
hunk. A pure rename inside the same class is a no-op; a rename that crosses the boundary is observable. Anything
that cannot be proven harmless (new or deleted file, binary or mode change, an oversize untracked file) is observable.

Stdlib only; ``git`` is called with a fixed argument list, never through a shell, always with a timeout.
"""

from __future__ import annotations

import io
import re
import subprocess
import tokenize
from pathlib import Path

__all__ = ["git_changes", "is_observable_path", "is_test_path", "merge_base", "observable_files", "parse_diff", "read_blobs", "run_git"]

_GIT_TIMEOUT_SECONDS = 30
_MAX_UNTRACKED_BYTES = 1_000_000
_DOC_ROOTS = frozenset({".shipwright", "docs", "changelog-unreleased.d"})
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "integration-tests"})
_TEST_PREFIXES = (("shared", "tests"), ("shared", "scripts", "tests"), ("shared", "scripts", "tools", "tests"))
_LEDGERS = frozenset({"changelog.md", "readme.md", "shipwright_events.jsonl", "shipwright_test_results.json", "shipwright_bloat_baseline.json"})
_DOC_EXTS = frozenset({".md", ".rst"})
_PROMPT_DIRS = frozenset({"agents", "skills", "prompts", "templates"})
_PROMPT_FILES = frozenset({"constitution.md", "glossary.md", "skill.md", "claude.md"})
_INDENT_EXTS = frozenset({".py", ".yml", ".yaml", ".mk"})
_HASH_COMMENT = frozenset({".py", ".sh", ".ps1", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".mk"})
_SLASH_COMMENT = frozenset({".js", ".ts", ".tsx", ".jsx", ".css", ".go", ".rs", ".java"})
_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def run_git(root: str | Path, *args: str, data: bytes | None = None) -> bytes:
    """Run ``git -C root args`` with a timeout; raises ``RuntimeError`` (with git's message) on any failure."""
    try:
        done = subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(root), *args], input=data, capture_output=True,
                              check=False, timeout=_GIT_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise RuntimeError(f"git {args[0]} did not run: {exc}") from exc
    if done.returncode != 0:
        raise RuntimeError(done.stderr.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return done.stdout


def merge_base(root: str | Path, ref: str, head: str = "HEAD") -> str:
    """The fork point of ``ref`` and ``head`` (what F11 compares against), as a commit id."""
    return run_git(root, "merge-base", ref, head).decode("utf-8", "replace").strip()


def read_blobs(root: str | Path, ref: str, paths: list[str]) -> dict[str, str | None]:
    """``{path: text}`` at ``ref`` through ONE ``git cat-file --batch``; ``None`` for a path that does not exist there."""
    if not paths:
        return {}
    out = run_git(root, "cat-file", "--batch", data="".join(f"{ref}:{p}\n" for p in paths).encode("utf-8"))
    result: dict[str, str | None] = {}
    pos = 0
    for p in paths:
        end = out.index(b"\n", pos)
        header = out[pos:end].decode("utf-8", "replace").split()
        pos = end + 1
        if len(header) == 3 and header[1] == "blob":
            size = int(header[2])
            result[p] = out[pos:pos + size].decode("utf-8", "replace")
            pos += size + 1
        elif header and header[-1] == "missing":
            result[p] = None
        else:
            raise RuntimeError(f"cannot read {p} at {ref}: {' '.join(header)}")
    return result


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].lower()
    if name == "makefile":
        return ".mk"
    return "." + name.rsplit(".", 1)[-1] if "." in name.lstrip(".") else ""


def is_test_path(path: str) -> bool:
    """True when ``path`` sits under a test directory at the repo root, a plugin root or a shared test root (never by file name)."""
    dirs = path.replace("\\", "/").lower().split("/")[:-1]
    return bool(dirs) and (dirs[0] in _TEST_DIRS or (dirs[0] == "plugins" and len(dirs) > 2 and dirs[2] in _TEST_DIRS)
                           or any(tuple(dirs[:len(p)]) == p for p in _TEST_PREFIXES))


def is_observable_path(path: str) -> bool:
    """True when a file at ``path`` can change what a user or operator observes (fail-closed, by location and extension)."""
    parts = path.replace("\\", "/").lower().split("/")
    name, dirs = parts[-1], parts[:-1]
    in_docs = parts[0] in _DOC_ROOTS or (parts[0] == "plugins" and len(parts) > 3 and parts[2] == "docs")
    if path.replace("\\", "/").lower().startswith(".shipwright/" + "prof" + "iles/"):  # observable: a human-authored input, not a resolver path
        return True
    if in_docs and dirs or is_test_path(path) or (not dirs and name in _LEDGERS):
        return False
    if _ext(path) in _DOC_EXTS:
        return name in _PROMPT_FILES or bool(_PROMPT_DIRS & set(dirs))
    return True


def parse_diff(text: str) -> dict[str, dict]:
    """``{path: {"hunks": [{"added", "removed", "old_start", "new_start"}], "added", "removed", "renamed_from", "new", "deleted"}}`` from a zero-context diff."""
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
            h = _HUNK.match(line)
            cur["hunks"].append({"added": [], "removed": [], "old_start": int(h.group(1)) if h else 0, "new_start": int(h.group(2)) if h else 0})
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


def _string_rows(text: str | None) -> set[int] | None:
    """Rows of a Python file that lie inside a multi-line string; ``None`` when the file cannot be tokenized."""
    if text is None:
        return None
    rows: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                rows.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    return rows


def _significant(lines: list[str], ext: str, start: int, strings: set[int] | None) -> list[str]:
    """The lines that carry meaning: blanks and full-line comments of the extension's own syntax are dropped."""
    out: list[str] = []
    in_block = False
    for i, raw in enumerate(lines):
        body = raw.strip()
        if not body:
            continue
        if ext in _HASH_COMMENT and body.startswith("#") and not body.startswith("#!"):
            if ext != ".py" or (strings is not None and (start + i) not in strings):
                continue
        elif ext in _SLASH_COMMENT:
            if body.startswith("//"):
                continue
            if body.startswith("/*") or in_block:
                in_block = "*/" not in body
                continue
        indent = raw[: len(raw) - len(raw.lstrip())] if ext in _INDENT_EXTS else ""
        out.append(indent + body)
    return out


def _is_noop(rec: dict, path: str) -> bool:
    if rec["new"] or rec["deleted"] or (not rec["hunks"] and not rec.get("renamed_from")):
        return False  # new, deleted, or a change git shows no text for (binary, mode): cannot be proven harmless
    ext = _ext(path)
    reader = rec.get("read")
    cache: dict[str, set[int] | None] = {}

    def strings(side: str) -> set[int] | None:
        if ext != ".py" or reader is None:
            return None
        if side not in cache:
            cache[side] = _string_rows(reader(side))
        return cache[side]

    return all(_significant(h["removed"], ext, h.get("old_start", 0), strings("old") if ext == ".py" else None)
               == _significant(h["added"], ext, h.get("new_start", 0), strings("new") if ext == ".py" else None) for h in rec["hunks"])


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


def git_changes(root: str | Path, base: str, head: str | None = None) -> dict[str, dict]:
    """Parsed changes ``base`` -> ``head``; with no ``head``, base -> working tree PLUS untracked files (as added)."""
    root = Path(root)
    changes = parse_diff(run_git(root, "diff", "-U0", "-M", "--no-color", base, *([head] if head else [])).decode("utf-8", "replace"))

    def reader(path: str, rec: dict):
        def read(side: str) -> str | None:
            try:
                if side == "old":
                    return read_blobs(root, base, [rec.get("renamed_from") or path])[rec.get("renamed_from") or path]
                if head:
                    return read_blobs(root, head, [path])[path]
                return (root / path).read_text(encoding="utf-8")
            except (RuntimeError, OSError, ValueError):
                return None
        return read

    for path, rec in changes.items():
        rec["read"] = reader(path, rec)
    if head is None:
        for rel in run_git(root, "ls-files", "--others", "--exclude-standard").decode("utf-8", "replace").splitlines():
            try:
                with (root / rel).open("rb") as fh:
                    raw = fh.read(_MAX_UNTRACKED_BYTES + 1)
                body = ["<oversize>"] if len(raw) > _MAX_UNTRACKED_BYTES else raw.decode("utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                body = ["<binary>"]
            changes[rel] = {"hunks": [{"added": body, "removed": [], "old_start": 0, "new_start": 1}], "added": body, "removed": [], "renamed_from": None, "new": True, "deleted": False}
    return changes
