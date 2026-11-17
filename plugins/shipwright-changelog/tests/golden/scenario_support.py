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
from typing import Any, Callable

import minimal_valid_project as mvp

from .replay_commands import REPO_ROOT, SHARED

GITIGNORE_TEMPLATE = REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"
ROOT_LOCKS = ("*.md.lock", "*.json.lock", "shipwright_events.jsonl.lock")
KEEP = (".shipwright/agent_docs/decision-drops/.gitkeep", ".shipwright/planning/adr/.gitkeep")
ORCHESTRATOR = REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"
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
    scratch.git("rm", "-qf", "--", "shipwright_events.jsonl")
    scratch.git("commit", "-q", "-m", "chore: no events file yet")


def set_autonomy(scratch: Any, value: str) -> None:
    """``autonomy`` in ``shipwright_run_config.json`` (the setting Steps 3 and 5 read), committed."""
    path = scratch.repo / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["autonomy"] = value
    commit(scratch, "shipwright_run_config.json", json.dumps(config, indent=2) + "\n", f"chore: autonomy {value}")


def write_decision(scratch: Any, run_id: str, title: str) -> None:
    """One decision drop, written by the real tool (as iterate F3 does). Today's date in the run id keeps it from
    being quarantined as a pre-tracking drop."""
    scratch.run([sys.executable, str(DECISION_TOOL), "--project-root", str(scratch.repo), "--run-id", run_id,
                 "--section", "demo", "--title", title, "--context", "why", "--decision", "what",
                 "--consequences", "so"], check=True)


def ready_release(make_project: Any, *, autonomy: str | None = None, branch: str | None = "release/next", pushed: bool = True,
                  history: str = "# Changelog\n\n## [1.2.0] - 2026-01-15\n\n### Added\n\n- Earlier feature\n",
                  default_branch: str = "main", setup: Callable[[Any], None] | None = None, tagged: bool = True) -> Any:
    """A project ready for a whole release on the one configuration that can finish it today (legacy events layout,
    no events file yet: findings D21-D23): tagged ``v1.2.0``, a feature and a fix since, each with a pending bullet.
    ``branch=None`` stays on the default branch; ``setup`` runs on the project first (a driven run, S13, S17)."""
    s = make_project(events_layout="legacy", default_branch=default_branch, tagged=tagged)
    if setup:
        setup(s)
    remove_events_file(s)
    if autonomy:
        set_autonomy(s, autonomy)
    write_changelog(s, history)
    tag(s, "v1.2.0")
    if branch and pushed:
        feature_branch(s, branch)
    elif branch:  # a branch the remote has never seen (finding D7: the prose opens the request before it pushes)
        s.git("checkout", "-q", "-b", branch)
    commit(s, "feat.txt", "f\n", "feat: new capability")
    commit(s, "fix.txt", "x\n", "fix: a defect")
    write_drop(s, "Added", "A new capability readers can use")
    write_drop(s, "Fixed", "A defect no longer happens", run_id="iterate-2026-11-02-b")
    return s


def notes_of(scratch: Any) -> str:
    """The first section of ``CHANGELOG.md``."""
    text = (scratch.repo / "CHANGELOG.md").read_text(encoding="utf-8")
    return text[text.index("## ["):].split("\n## [")[0]


def orchestrator(scratch: Any, *args: str) -> dict:
    """One call of the real orchestrator CLI (the surface a driven run uses); its JSON answer."""
    done = scratch.run([sys.executable, str(ORCHESTRATOR), *args, "--project-root", str(scratch.repo)])
    assert done.returncode in (0, 1, 2), done.stderr
    return json.loads(done.stdout)


def apply_phase(scratch: Any, dispatch: dict, artifacts: list[str]) -> dict:
    """``single-session-apply`` of one phase's result, as the master does once a phase-runner is done."""
    result = scratch.stub_state / f"result-{dispatch['phaseTaskId']}.json"
    result.write_text(json.dumps({"ok": True, "phase": dispatch["phase"], "summary": "done", "artifacts": artifacts,
                                  **({"splitId": dispatch["splitId"]} if dispatch.get("splitId") else {})}), encoding="utf-8")
    return orchestrator(scratch, "single-session-apply", "--phase-task-id", dispatch["phaseTaskId"], "--session-uuid",
                        dispatch["sessionUuid"], "--version", str(dispatch["version"]), "--result-json", str(result))


def start_run(scratch: Any, autonomy: str = "guided") -> dict:
    """``write-config`` for a driven run, then the first dispatch (the project phase, claimed and in progress)."""
    orchestrator(scratch, "write-config", "--scope", "full_app", "--profile", "supabase-nextjs", "--autonomy", autonomy,
                 "--mode", "single_session")
    return orchestrator(scratch, "single-session-next")["dispatch"]


def drive_to_changelog(scratch: Any, autonomy: str = "guided") -> dict:
    """Drive the real orchestrator through every phase before the changelog (an honest phase-runner writes the minimal
    artifacts), commit what they left, and return the changelog dispatch (claimed: the task is in progress)."""
    dispatch = start_run(scratch, autonomy)
    while dispatch["phase"] != "changelog":
        apply_phase(scratch, dispatch, mvp.write_phase(scratch.repo, dispatch["phase"], dispatch.get("splitId")))
        dispatch = orchestrator(scratch, "single-session-next")["dispatch"]
    scratch.git("add", "-A")
    scratch.git("commit", "-q", "-m", "chore: the phases before the changelog")
    return dispatch
