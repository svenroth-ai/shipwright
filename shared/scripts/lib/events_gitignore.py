"""Conditional ``.gitignore`` re-include for the event-log files (issue 978, S7).

A consumer repo may ignore ``*.jsonl`` (or a whole folder) in its own ``.gitignore``. The legacy log
survives that because it is already tracked; a drop file does not -- it is new and untracked, so
``git add`` would silently skip it and a "correctly finalized" run would ship without its events.
DESIGN section 6: the self-heal adds a re-include, and tracked-ness is probed with a representative
FILE path (``.shipwright/events/drops/x.jsonl``), never the folder name -- a ``*.jsonl`` rule does not
match the folder itself, only a file inside it.

Strictly conditional (a no-op in a repo that needs nothing): the drops folders are probed only when
the repo has adopted the drops layout (config says ``drops``) or already tracks files in them; the
legacy log only there too, and only when it is tracked (a legacy-layout repo is never touched). Only paths the probe says are ignored get a line.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .events_log import EVENT_FILE
from .events_sentinel import declared_layout

FOLDERS = (".shipwright/events/drops", ".shipwright/events/archive", ".shipwright/events/quarantine")
SAMPLE_NAME = "x.jsonl"


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=30)


def is_ignored(repo_root: Path, rel_path: str) -> bool:
    """``git check-ignore`` on a representative path (rc 0 = ignored; --no-index so a TRACKED file is judged by the rules alone)."""
    try:
        return _git(repo_root, "check-ignore", "-q", "--no-index", "--", rel_path).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _tracks(repo_root: Path, pathspec: str) -> bool:
    try:
        return bool(_git(repo_root, "ls-files", "--", pathspec).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def _effective(root: Path, text: str, lines: list[str], folders: list[str]) -> bool:
    """True when the heal would actually un-ignore every folder in ``folders``.

    Probed in a throw-away repo holding only the healed rules: git cannot re-include a file whose parent
    directory is excluded, so a consumer that ignores ``.shipwright`` as a whole stays ignored whatever is
    appended, and appending the same dead lines on every run only hides that.
    """
    healed, _ = apply_reinclude(text, lines)
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp)
        try:
            if _git(probe, "init", "-q").returncode != 0:
                return True  # cannot probe: keep the lines rather than guess
            (probe / ".gitignore").write_text(healed, encoding="utf-8")
            rcs = [_git(probe, "check-ignore", "-q", "--no-index", "--", f"{f}/{SAMPLE_NAME}").returncode
                   for f in folders]
            if any(rc not in (0, 1) for rc in rcs):
                return True  # a git error is not proof the rules are dead: keep the lines
            return all(rc == 1 for rc in rcs)
        except (OSError, subprocess.SubprocessError):
            return True


def reinclude_lines(repo_root: Path | str) -> list[str]:
    """The ``!`` rules the repo needs (empty = nothing to heal, or nothing that would work: see ``_effective``)."""
    root = Path(repo_root)
    lines: list[str] = []
    if declared_layout(root) == "drops" or any(_tracks(root, f) for f in FOLDERS):
        keep = [f"!/{EVENT_FILE}"] if _tracks(root, EVENT_FILE) and is_ignored(root, EVENT_FILE) else []
        lines.extend(keep)
        needed = [f for f in FOLDERS if is_ignored(root, f"{f}/{SAMPLE_NAME}")]
        for folder in needed:
            # git cannot re-include a file whose PARENT dir is excluded: re-include the parent chain first
            # (``/.shipwright/*`` ignores ``.shipwright/events`` itself), each level once.
            parts = folder.split("/")
            for i in range(2, len(parts)):
                parent = "!/" + "/".join(parts[:i]) + "/"
                if parent not in lines:
                    lines.append(parent)
            lines += [f"!/{folder}/", f"!/{folder}/*.jsonl"]
        if needed:
            try:
                text = (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if not _effective(root, text, lines, needed):
                return keep  # no dead folder rules are written; the F11 committed-event check fails the run (the folder is ignored)
    return lines


def apply_reinclude(text: str, lines: list[str]) -> tuple[str, list[str]]:
    """Append the re-include lines (after every existing rule, so they win); returns (new text, lines added)."""
    added = list(lines)  # appended even when already present: a LATER ignore rule overrides an earlier re-include
    if not added:
        return text, []
    sep = "" if not text or text.endswith("\n") else "\n"
    block = "# Shipwright event logs must stay trackable (issue 978): re-include after an ignore rule\n"
    return text + sep + block + "\n".join(added) + "\n", added
