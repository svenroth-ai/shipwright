"""Set-up helpers of the changelog scenarios: a project the way a Shipwright project really is, plus its history.

The scratch of ``shared/testkit/release_scratch.py`` is the minimal valid project. A real project also has the
canonical ``.gitignore`` block (so locks and runtime files stay out of ``git status``) and tracked
``.shipwright/agent_docs/decision-drops/`` and ``.shipwright/planning/adr/`` directories, which Step 6's pathspec names: a pathspec that matches
no file aborts the commit (finding D21). ``scaffold`` adds exactly that, once, as one commit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from .replay_commands import REPO_ROOT, SHARED

GITIGNORE_TEMPLATE = REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"
ROOT_LOCKS = ("*.md.lock", "*.json.lock", "shipwright_events.jsonl.lock")
KEEP = (".shipwright/agent_docs/decision-drops/.gitkeep", ".shipwright/planning/adr/.gitkeep")
DROP_TOOL = SHARED / "scripts" / "tools" / "write_changelog_drop.py"
DECISION_TOOL = SHARED / "scripts" / "tools" / "write_decision_drop.py"


def canonical_gitignore() -> str:
    text = GITIGNORE_TEMPLATE.read_text(encoding="utf-8")
    first = re.search(r"# === BEGIN Shipwright canonical.*?# === END Shipwright canonical[^\n]*\n", text, re.S)
    assert first, "the canonical gitignore block moved"
    return first.group(0) + "\n" + "\n".join(ROOT_LOCKS) + "\n"


def commit(scratch: Any, path: str, text: str, message: str) -> None:
    target = scratch.repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    scratch.git("add", "--", path)
    scratch.git("commit", "-q", "-m", message)


def scaffold(scratch: Any) -> None:
    """The canonical ignore block and the two tracked directories; one commit, pushed."""
    (scratch.repo / ".gitignore").write_text(canonical_gitignore(), encoding="utf-8", newline="\n")
    for rel in KEEP:
        (scratch.repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (scratch.repo / rel).write_text("", encoding="utf-8")
    scratch.git("add", "-A")
    scratch.git("commit", "-q", "-m", "chore: project scaffolding")
    scratch.git("push", "-q", "origin", scratch.git("rev-parse", "--abbrev-ref", "HEAD"))


def digest(scratch: Any) -> dict[str, str]:
    """Every file of the working tree (not ``.git``, not lock files) by content hash: 'nothing on disk changed'."""
    out: dict[str, str] = {}
    for path in sorted(Path(scratch.repo).rglob("*")):
        rel = path.relative_to(scratch.repo).as_posix()
        if path.is_file() and not rel.startswith(".git/") and not rel.endswith(".lock"):
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def tag(scratch: Any, name: str, message: str | None = None) -> None:
    """An annotated tag on HEAD, pushed (a release that was made earlier)."""
    scratch.git("tag", "-a", name, "-m", message or f"Release {name}")
    scratch.git("push", "-q", "origin", name)


def feature_branch(scratch: Any, name: str = "release/next") -> None:
    """A branch the remote already knows (an iterate branch that was pushed before the release started)."""
    scratch.git("checkout", "-q", "-b", name)
    scratch.git("push", "-q", "origin", name)


def write_drop(scratch: Any, category: str, bullet: str, run_id: str = "iterate-2026-11-01-a", *, tracked: bool = False) -> None:
    """One bullet drop, written by the real tool (as iterate F4 does). Untracked by default: a drop that is
    COMMITTED makes today's Step 6 refuse the release (finding D22, scenario S1t), so only that scenario tracks it."""
    scratch.run([sys.executable, str(DROP_TOOL), "--project-root", str(scratch.repo), "--run-id", run_id,
                 "--category", category, "--bullet", bullet], check=True)
    if tracked:
        scratch.git("add", "--", "CHANGELOG-unreleased.d")
        scratch.git("commit", "-q", "-m", f"docs(changelog): drop {run_id} {category}")


def write_changelog(scratch: Any, text: str) -> None:
    """A hand-made ``CHANGELOG.md`` (committed): what an earlier release left behind."""
    commit(scratch, "CHANGELOG.md", text, "docs: changelog history")


def remove_events_file(scratch: Any) -> None:
    """S1 / D3: a fresh repo has no events file, so Step 7's ``record_event.py`` creates one that is untracked
    and not ignored (the release audit would refuse a dirty tree before Step 7, so it cannot exist earlier)."""
    scratch.git("rm", "-q", "--", "shipwright_events.jsonl")
    scratch.git("commit", "-q", "-m", "chore: no events file yet")


def set_autonomy(scratch: Any, value: str) -> None:
    """``autonomy`` in ``shipwright_run_config.json`` (the setting Steps 3 and 5 read), committed."""
    path = scratch.repo / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["autonomy"] = value
    commit(scratch, "shipwright_run_config.json", json.dumps(config, indent=2) + "\n", f"chore: autonomy {value}")
