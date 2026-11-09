#!/usr/bin/env python3
"""Fork an earlier e2e run at a phase boundary, so one area can be replayed without the whole pipeline.

    uv run integration-tests/e2e-webui/fork/fork_run.py --from <workdir>/run-ABC123 --at build:04-board \
        --repo <shipwright checkout> [--workdir <dir>] [--commit <sha>]

The project of an e2e run is a git repo and the pipeline commits at every phase boundary, together with the
run config of that moment. The fork copies the project, resets it to the boundary commit, drops the ignored
files that were written after it (baselines, loop state, caches), puts the start task back to
"awaiting_launch" with the plugin's own recover-phase-task command and writes a run folder the harness resumes
(SHIPWRIGHT_E2E_RESUME_RUN=<printed folder>). The plugins that then run are the ones of --repo, which is the point.
"""
from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

KEEP_DIRS = ("node_modules", ".venv")
SLACK_SECONDS = 120  # files written in the minutes around the boundary commit belong to it


def git(project: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=True)
    return done.stdout


def config_at(project: Path, commit: str) -> dict | None:
    try:
        return json.loads(git(project, "show", f"{commit}:shipwright_run_config.json"))
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def find_task(config: dict, phase: str, split: str | None) -> dict | None:
    for task in config.get("phase_tasks", []):
        if task.get("phase") == phase and (task.get("splitId") or None) == split:
            return task
    return None


def boundary_commit(project: Path, phase: str, split: str | None) -> tuple[str, dict]:
    """First commit whose run config holds the task with every prerequisite done: the moment the phase could start."""
    for commit in git(project, "log", "--reverse", "--format=%H").split():
        config = config_at(project, commit)
        task = config and find_task(config, phase, split)
        if not task:
            continue
        done = {t["phaseTaskId"] for t in config["phase_tasks"] if t.get("status") in ("done", "skipped")}  # both count as finished
        if all(p in done for p in task.get("prerequisites", [])):
            return commit, task
    raise SystemExit(f"No commit of {project} holds the task {phase}:{split or '-'} with its prerequisites done.")


def drop_later_ignored(project: Path, commit_time: int) -> tuple[int, int]:
    """Ignored files are not in git; those newer than the boundary belong to later phases and would mislead the replay."""
    listed = git(project, "ls-files", "-o", "-i", "--exclude-standard", "-z").split("\0")
    removed = kept = 0
    for rel in filter(None, listed):
        if any(part in KEEP_DIRS for part in rel.split("/")):  # at any depth: a half-deleted package tree breaks the replay
            continue
        path = project / rel
        try:
            if path.stat().st_mtime > commit_time + SLACK_SECONDS:
                path.unlink()
                removed += 1
            else:
                kept += 1
        except OSError:
            pass
    return removed, kept


def require_own_repo(project: Path) -> None:
    """reset --hard and clean -fd must never reach an enclosing repo (a project copy whose .git is missing)."""
    top = git(project, "rev-parse", "--show-toplevel").strip()
    if Path(top).resolve() != project.resolve():
        raise SystemExit(f"{project} is not the top of its own git repository (it sits inside {top}); refusing to reset it.")


def recover_task(repo: Path, project: Path, task_id: str) -> None:
    orchestrator = repo / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"
    done = subprocess.run(["uv", "run", "python", str(orchestrator), "recover-phase-task", "--project-root", str(project),
                           "--phase-task-id", task_id], cwd=repo / "plugins" / "shipwright-run", capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"recover-phase-task failed ({done.returncode}): {done.stdout[-400:]}{done.stderr[-400:]}")
    print(done.stdout.strip()[:300])


def plugin_identity(repo: Path) -> str:
    """The same string src/run-identity.ts computes: the git trees of plugins/ and shared/ at HEAD. A dirty tree is refused,
    because the harness would add a digest of the changes and the run would not match."""
    if git(repo, "status", "--porcelain", "--untracked-files=all", "--", "plugins", "shared").strip():
        raise SystemExit(f"{repo} has uncommitted changes under plugins/ or shared/; commit or discard them first.")
    return " ".join(f"{d}:{git(repo, 'rev-parse', f'HEAD:{d}').strip()}" for d in ("plugins", "shared"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="source", required=True, help="the earlier run folder (run-<id>)")
    ap.add_argument("--at", required=True, help="phase[:split], e.g. build:04-board or design")
    ap.add_argument("--repo", required=True, help="the Shipwright checkout whose plugins the fork runs with")
    ap.add_argument("--workdir", default=None, help="where the new run folder goes (default: the parent of --from)")
    ap.add_argument("--commit", default=None, help="use this commit instead of the detected boundary")
    args = ap.parse_args()

    source, repo = Path(args.source).resolve(), Path(args.repo).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else source.parent
    phase, _, split = args.at.partition(":")
    split = split or None
    manifest = json.loads((source / "run-manifest.json").read_text(encoding="utf-8"))

    sproject = source / "project"
    require_own_repo(sproject)
    commit, task = boundary_commit(sproject, phase, split) if not args.commit else (args.commit, None)
    print(f"boundary: {commit[:9]} {git(sproject, 'log', '-1', '--format=%ad %s', '--date=format:%H:%M', commit).strip()}")

    new = workdir / f"run-fork{secrets.token_hex(3)}"
    project = new / "project"
    new.mkdir(mode=0o700)
    (new / "home").mkdir(mode=0o700)
    shutil.copytree(sproject, project, symlinks=True)
    require_own_repo(project)
    git(project, "reset", "--hard", "-q", commit)
    git(project, "clean", "-fdq", "-e", "node_modules", "-e", ".venv")
    removed, kept = drop_later_ignored(project, int(git(project, "log", "-1", "--format=%ct", commit)))
    print(f"ignored files: {removed} from later phases removed, {kept} kept")

    config = config_at(project, commit) or {}
    task = task or find_task(config, phase, split)
    if not task:
        raise SystemExit("The boundary commit has no run config task for this phase.")
    recover_task(repo, project, task["phaseTaskId"])

    identity = {**{k: manifest[k] for k in ("fixture", "profile", "packageSha256")}, "commit": plugin_identity(repo),
                "created": manifest.get("created"), "pipelineStarted": manifest.get("created"),
                "forkedFrom": {"run": source.name, "at": args.at, "commit": commit}}
    (new / "run-manifest.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    print(f"\nFork ready: {new}\nStart it with SHIPWRIGHT_E2E_RESUME_RUN={new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
