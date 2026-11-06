"""``.shipwright/designs/known-differences.md``: where an autonomous run records a rule decision
that makes the built app differ from the approved screens (``## KD-NN: <title>`` entries).

It waives nothing: ``screenshot_check.py`` does not read this file. Writer:
``tools/record_autonomous_decision.py`` (rules: ``autonomous_rules.py``). Stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path

KNOWN_DIFFERENCES_REL = ".shipwright/designs/known-differences.md"
_WS = re.compile(r"\s+")
_KD_RE = re.compile(r"^## KD-(\d+)\b", re.M)
_KD_HEADER = ("# Known differences: built app and approved screens\n\n"
              "Written by autonomous runs (`record_autonomous_decision.py`), one entry per rule decision. "
              "It waives nothing: `screenshot_check.py` does not read this file.\n")


def _norm(text: str) -> str:
    return _WS.sub(" ", text.replace("’", "'")).strip().lower()


def known_difference_exists(project_root: Path, title: str) -> bool:
    """A ``## KD-NN: <title>`` entry already exists (a resumed or repeated call records nothing twice)."""
    try:
        text = (Path(project_root) / KNOWN_DIFFERENCES_REL).read_text(encoding="utf-8")
    except OSError:
        return False
    want = _norm(title)
    return any(_norm(m.group(1)) == want for m in re.finditer(r"^## KD-\d+:\s*(.+)$", text, re.M))


def append_known_difference(project_root: Path, title: str, fields: list[tuple[str, str]]) -> str:
    """Append ``## KD-NN: <title>`` with ``- **field:** value`` lines; returns ``KD-NN``."""
    path = Path(project_root) / KNOWN_DIFFERENCES_REL
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = _KD_HEADER
    number = max((int(n) for n in _KD_RE.findall(text)), default=0) + 1
    kd = f"KD-{number:02d}"
    body = "\n".join(f"- **{k}:** {_WS.sub(' ', v).strip()}" for k, v in fields if v and v.strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip("\n") + f"\n\n## {kd}: {_WS.sub(' ', title).strip()}\n\n{body}\n", encoding="utf-8")
    return kd
