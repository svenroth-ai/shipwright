#!/usr/bin/env python3
"""PostToolUse hook: nudge when an edit pushes a source file past the line limit.

Non-blocking by design. Reads the PostToolUse JSON payload from stdin and
emits a single advisory message (always exit 0) **only when the current
edit crossed the threshold** -- the file is over the limit now but was at
or under it immediately before this tool call. Editing a file that was
already oversized stays silent, so a one-line fix in a legacy 400-line
module never re-fires.

Rationale: large files degrade AI agent performance by consuming excessive
context window space and weakening edit localisation. This hook is a
*reminder*, not a gate -- splitting a file is a judgement call the operator
makes, best made at the moment the file crosses the line.

Crossing detection (stateless -- no session state file):

  - ``Edit`` (without ``replace_all``): the before-size is computed
    exactly from the payload --
    ``before = now - (newlines(new_string) - newlines(old_string))``.
  - ``Write`` / ``Edit`` with ``replace_all`` / anything else: the
    before-size is the file's line count at ``git HEAD``. A file absent
    from HEAD (brand-new) counts as 0 lines; if git can't answer the
    before-size is unknown and the nudge fires (conservative).

Configuration: ``shipwright_build_config.json`` -> ``enforcement.max_file_lines``
(default: 300).

Ignored (never nudged):
  - Lock files, generated / vendored / built artefacts, ``node_modules``
  - Markdown, JSON, YAML, TOML, CSV, SVG, XML, HTML, CSS
  - SQL migration files (long by nature)

Exit codes:
  0 = always. This hook is advisory; it never blocks an edit.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_LINES = 300

# Non-source files that are legitimately long.
_SKIP_PATH = re.compile(
    r"(\.lock$|package-lock|node_modules[/\\]|vendor[/\\]|dist[/\\]"
    r"|build[/\\]|\.min\.|__pycache__|\.pyc$|\.generated\."
    r"|migrations?[/\\].*\.sql)",
    re.IGNORECASE,
)
# Config / docs extensions -- often long, but not AI-context-sensitive source.
_SKIP_EXT = re.compile(
    r"\.(md|ya?ml|json|toml|csv|svg|xml|html|css)$",
    re.IGNORECASE,
)


def _read_payload() -> dict:
    """Parse the PostToolUse JSON payload from stdin; ``{}`` on any failure."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _should_skip(file_path: str) -> bool:
    return bool(_SKIP_PATH.search(file_path) or _SKIP_EXT.search(file_path))


def _max_lines(cwd: Path) -> int:
    """Threshold from ``shipwright_build_config.json``; ``DEFAULT_MAX_LINES`` otherwise."""
    config = cwd / "shipwright_build_config.json"
    if not config.is_file():
        return DEFAULT_MAX_LINES
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        value = data.get("enforcement", {}).get("max_file_lines", DEFAULT_MAX_LINES)
        return int(value)
    except (json.JSONDecodeError, OSError, AttributeError, TypeError, ValueError):
        return DEFAULT_MAX_LINES


def _file_newlines(path: Path) -> int:
    """Count newline bytes in the file -- matches ``wc -l`` semantics."""
    try:
        with path.open("rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return 0


def _git_head_newlines(path: Path) -> int | None:
    """Newline count of ``path`` at git HEAD.

    Returns ``0`` when the path is inside the repo but absent from HEAD
    (a brand-new file), and ``None`` when git can't answer (not a repo,
    git missing, path outside the repo).
    """
    try:
        top = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if top.returncode != 0:
            return None
        repo_root = Path(top.stdout.strip())
        try:
            rel = path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            return None
        blob = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{rel.as_posix()}"],
            capture_output=True, timeout=5,
        )
        if blob.returncode != 0:
            return 0  # tracked-repo-relative but not in HEAD -> brand-new file
        return blob.stdout.count(b"\n")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _before_newlines(
    tool_name: str, tool_input: dict, now: int, path: Path,
) -> int | None:
    """Newline count of the file immediately before this tool call.

    ``None`` means undeterminable -- callers treat that as "fire the
    nudge" (a missed silence is cheaper than a missed warning).
    """
    if tool_name == "Edit" and not tool_input.get("replace_all"):
        old = tool_input.get("old_string")
        new = tool_input.get("new_string")
        if isinstance(old, str) and isinstance(new, str):
            # Replacing old_string with new_string shifts the file's
            # newline count by exactly this delta.
            delta = new.count("\n") - old.count("\n")
            return now - delta
    # Write, replace_all Edit, or unknown tool -> fall back to git HEAD.
    return _git_head_newlines(path)


def _emit_nudge(file_path: str, now: int, limit: int) -> None:
    message = (
        f"NOTE - {file_path} just crossed the {limit}-line size guideline "
        f"(now {now} lines). Large source files are harder for AI agents to "
        f"edit reliably -- more context consumed, weaker edit localisation. "
        f"Mention this to the user and offer to split the file into smaller "
        f"modules. This is a non-blocking suggestion -- do not treat it as a "
        f"gate and do not block on it."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }))


def main() -> int:
    payload = _read_payload()

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return 0

    path = Path(file_path)
    if not path.is_file():
        return 0
    if _should_skip(file_path):
        return 0

    limit = _max_lines(Path.cwd())
    now = _file_newlines(path)
    if now <= limit:
        return 0  # within the guideline -- nothing to flag

    before = _before_newlines(
        str(payload.get("tool_name") or ""), tool_input, now, path,
    )
    if before is not None and before > limit:
        # The file was already oversized before this edit -- this edit did
        # not cross the threshold. Stay silent so routine edits to legacy
        # large files don't re-fire the nudge on every touch.
        return 0

    _emit_nudge(file_path, now, limit)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 -- advisory hook: never break the tool flow
        sys.exit(0)
