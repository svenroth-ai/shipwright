"""Shared helpers for the complexity-history test files (not collected)."""

import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLASSIFY_CLI = (
    REPO_ROOT
    / "plugins" / "shipwright-iterate" / "scripts" / "lib"
    / "classify_complexity.py"
)

# A prompt with no scope keyword and no risk flag (fall-through path).
FALLTHROUGH_MSG = "fix the data collector regression and extend coverage"
# A prompt that matches a scope keyword (medium: 'dashboard').
KEYWORD_MSG = "fix dashboard rendering of the run summary"


def write_entry(root: Path, run_id: str, date: str, complexity: str,
                **extra) -> Path:
    """Write a minimal F5c-shaped entry file (mirrors the shared writer)."""
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_id": run_id,
        "date": date,
        "type": "change",
        "complexity": complexity,
        "branch": f"iterate/{run_id}",
        "tests_passed": True,
    }
    entry.update(extra)
    p = d / f"{run_id}.json"
    p.write_text(json.dumps(entry), encoding="utf-8")
    return p


def seeded_root(tmp_path: Path, complexities: list[str]) -> Path:
    """Project root with one valid entry per complexity, dates ascending."""
    for i, cx in enumerate(complexities):
        write_entry(
            tmp_path,
            f"iterate-2026-01-{(i % 27) + 1:02d}-run-{i:03d}",
            f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00Z",
            cx,
        )
    return tmp_path
