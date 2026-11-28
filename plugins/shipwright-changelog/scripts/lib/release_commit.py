"""``release.py commit-and-tag``: Step 6 in one call (unit P4; second pass B1; operator decision F7).

Every invariant of the prose chain is kept: the commit is made **by explicit pathspec** (``git commit -- <paths>``, which reads
the worktree and never sweeps ``.shipwright/compliance/``), the commit comes first and ``HEAD`` is read only after it
succeeded (a failed or empty commit can never tag the previous commit), both ``--verify-commit`` runs read the committed
``HEAD`` (the release audit, and the manifest versions), and the tag is made only when every step before it exited 0. The
three ``git add`` calls are not part of that chain, as in the prose: a failed add does not stop the release, the commit's own
pathspec does.

What the code adds: the pathspecs come from the run state ``sync`` wrote (no copying by the model); **F7** the tag/CHANGELOG
check ``orchestrator.py update-step`` used to run (the tag exists and names this release, the CHANGELOG's top version is this
release) now runs here on every release, and a mismatch removes the local tag again and fails; **B1** the record
``.shipwright/runtime/release_state.json`` (version, release commit, checks that passed) a later guard reads.

Stop 3 (FINDINGS D21, D22, D23, D25): the pathspec names only paths that exist in the tree or the index (a project with no
``decision-drops/`` or ``adr/`` folder no longer aborts the commit); it carries the deletions of the tracked drop files the
aggregate consumed (``consumed_drops``, kept by ``aggregate``) and the event files Step 5.5 wrote (``events_pathspec``, kept by
``sync``). Before anything is staged the tree is checked: a change outside what the release writes (a person's own work in
progress, staged or not, or an untracked file) stops the release with ``unrelated_changes`` naming the paths, and no commit is
made (operator decision 2026-11-26; before, the commit was made and the release audit then refused the dirty tree).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import release_paths, release_runstate
from .release_sync import MANIFEST_RESULT
from .release_runner import Recorder, uv_script

RELEASE_STATE = ".shipwright/runtime/release_state.json"
AGENT_DOCS = ".shipwright/agent_docs"
DROP_DIRS = (f"{AGENT_DOCS}/decision-drops/", ".shipwright/planning/adr/")
BULLET_DOCS = ("architecture", "conventions")
SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def _covers(spec: str, path: str) -> bool:
    """``path`` is ``spec`` or lies under it (a directory pathspec ends in ``/``)."""
    return path == spec.rstrip("/") or path.startswith(spec.rstrip("/") + "/")


def _git_z(root: Path, argv: list[str]) -> list[str] | None:
    try:
        done = subprocess.run(["git", *argv], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return [p for p in done.stdout.split("\0") if p] if done.returncode == 0 else None


def _known_files(root: Path, specs: list[str]) -> list[str] | None:
    """Every file under ``specs`` that is in the index (a deleted tracked file included), in HEAD (a deletion already staged) or
    untracked and not ignored; ``None`` when git cannot list the index (the pathspec is then kept as it is, as before)."""
    listed = _git_z(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *specs])
    if listed is None:
        return None
    return [*listed, *(_git_z(root, ["ls-tree", "-r", "-z", "--name-only", "HEAD", "--", *specs]) or [])]  # no HEAD yet: none


def release_paths_of(root: Path, state: dict[str, Any]) -> list[str]:
    """The paths the release itself changed beyond the fixed ones, from the run state: the drop files ``aggregate`` consumed and
    deleted (D22; a drop it could not delete is still on disk and is not the release's to commit) and the event files Step 5.5
    wrote (``sync``, D23)."""
    gone = [p for p in state.get("consumed_drops", []) if not (root / p).exists()]
    return [*gone, *state.get("events_pathspec", [])]


def commit_pathspec(root: Path, state: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """``(log, docs, paths)``: the agent docs a project has (never architecture.md or conventions.md unconditionally) and the whole
    release pathspec. A path that matches nothing in the tree or the index is left out (D21: one such pathspec makes git refuse
    the whole commit)."""
    docs = [f"{AGENT_DOCS}/{name}.md" for name in BULLET_DOCS if (root / AGENT_DOCS / f"{name}.md").is_file()]
    log = [f"{AGENT_DOCS}/decision_log.md", f"{AGENT_DOCS}/decision_log_index.md"]
    wanted = list(dict.fromkeys(["CHANGELOG.md", *log, *docs, *DROP_DIRS, *state.get("evidence_pathspec", []),
                                 *state.get("manifest_pathspec", []), *release_paths_of(root, state)]))
    known = _known_files(root, wanted)
    if known is not None:
        wanted = [spec for spec in wanted if any(_covers(spec, path) for path in known)]
    return [p for p in log if p in wanted], [p for p in docs if p in wanted], wanted


def _status_paths(porcelain_z: str) -> list[str]:
    """The paths of ``git status --porcelain -z`` (a rename or a copy names both sides)."""
    out, fields, i = [], porcelain_z.split("\0"), 0
    while i < len(fields):
        entry = fields[i]
        if len(entry) > 3:
            out.append(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                i += 1
                if i < len(fields) and fields[i]:
                    out.append(fields[i])
        i += 1
    return out


def unrelated_changes(porcelain_z: str, paths: list[str], prefix: str = "") -> list[str]:
    """The changed paths no release pathspec covers (D25): what the release would leave dirty for its own audit to refuse.
    ``git status --porcelain`` names paths from the top of the work tree, the pathspec is relative to the project root: a
    project in a subfolder passes its ``prefix`` (``git rev-parse --show-prefix``); a path outside it is never the release's."""
    def own(path: str) -> str | None:
        return path[len(prefix):] if path.startswith(prefix) else None
    return sorted({p for p in _status_paths(porcelain_z) if own(p) is None or not any(_covers(spec, own(p)) for spec in paths)})


def _show_prefix(root: Path) -> str:
    """The project root's place inside the work tree (``""`` at its top, and when git cannot answer)."""
    try:
        done = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=root, capture_output=True, text=True, encoding="utf-8",
                              timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _failed(rec: Recorder, reason: str, code: int, **fields: Any) -> tuple[int, dict[str, Any]]:
    return code or 1, {"status": "failed", "reason": reason, **fields, "commands": rec.as_json()}


def write_state(root: Path, record: dict[str, Any]) -> Path:
    path = root / RELEASE_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")  # push-tag rewrites the only record of R after the merge: never leave it torn
    part.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(part, path)
    return path


def read_state(root: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((root / RELEASE_STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not SHA.fullmatch(str(data.get("commit", ""))):  # a hand-edited or torn record is no record
        return None
    return data


def commit_and_tag(rec: Recorder, plugin_root: Path, *, version: str,
                   clock=lambda: datetime.now(timezone.utc)) -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tools, state = shared / "scripts/tools", release_runstate.stored(root, version) or {}
    if "evidence_pathspec" not in state:  # `sync` did not run for this version (or its state is another root's): a commit now would miss the evidence
        return _failed(rec, "sync_not_run", 1)
    log, docs, paths = commit_pathspec(root, state)
    tree = rec.run("tree-check", ["git", "status", "--porcelain", "-z", "-uall"])
    if tree.exit != 0:  # git could not say what is in the tree: stop before anything is staged (external review, stop 3)
        return _failed(rec, "tree_check_failed", tree.exit, message="git status failed; nothing was staged or committed")
    unrelated = unrelated_changes(tree.stdout, paths, _show_prefix(root))
    if unrelated:  # D25 (operator 2026-11-26): stop before anything is staged or committed, and name what is in the way
        return _failed(rec, "unrelated_changes", 1, unrelated=unrelated,
                       message="the working tree has changes that are not part of this release: " + ", ".join(unrelated)
                               + "; stash or remove them, then run commit-and-tag again (nothing was staged or committed)")
    rec.run("git-add-changelog", ["git", "add", "CHANGELOG.md"])  # the three adds are outside the chain, as in the prose
    if log or docs:
        rec.run("git-add-log", ["git", "add", *log, *docs])
    extra = set(DROP_DIRS) | set(release_paths_of(root, state))
    sweep = [p for p in paths if p in extra]
    if sweep:  # never an empty list: `git add -A` with no pathspec stages the whole tree
        rec.run("git-add-drops", ["git", "add", "-A", "--", *sweep])
    subject = f"chore(release): v{version}"
    last = rec.run("last-subject", ["git", "log", "-1", "--format=%s"]).stdout.strip()
    pending = rec.run("pending", ["git", "status", "--porcelain", "--", *paths])
    if last == subject and pending.exit == 0 and not pending.stdout.strip():  # a re-run after a failed audit or tag: the release commit is there, verify and tag it
        commit = None
    else:
        commit = rec.run("commit", ["git", "commit", "-m", subject, "--", *paths])
        if commit.exit != 0:
            return _failed(rec, "commit_failed", commit.exit)
    head = rec.run("head", ["git", "rev-parse", "HEAD"]).stdout.strip()  # only after the commit succeeded
    audit = rec.run("verify-evidence", uv_script(tools / "refresh_compliance_docs.py", "--project-root", str(root),
                                                 "--verify-commit", head, "--release-audit"))
    if audit.exit != 0:
        return _failed(rec, "evidence_audit_failed", audit.exit, commit=head)
    manifests = rec.run("verify-manifests", uv_script(tools / "sync_release_manifests.py", "--project-root", str(root), "--version", version,
                                                      "--verify-commit", head, "--result-file", MANIFEST_RESULT))
    if manifests.exit != 0:
        return _failed(rec, "manifest_verify_failed", manifests.exit, commit=head)
    tag = rec.run("tag", ["git", "tag", "-a", f"v{version}", "-m", f"Release v{version}", head])  # the verified SHA, not whatever HEAD is by now
    if tag.exit != 0:
        return _failed(rec, "tag_failed", tag.exit, commit=head)
    checks = rec.run("verify-tag", uv_script(plugin_root / "scripts/checks/verify_release_tag.py", "--shared-root", str(shared),
                                             "--project-root", str(root), "--version", version))
    try:
        found = json.loads(checks.stdout).get("checks", {})
    except ValueError:
        found = {}
    tagged = rec.run("tag-commit", ["git", "rev-parse", "--verify", "-q", f"refs/tags/v{version}^{{commit}}"]).stdout.strip()
    if checks.exit != 0 or tagged != head:  # F7: a tag that does not name this release, or a CHANGELOG that disagrees, is no release
        removed = rec.run("tag-remove", ["git", "tag", "-d", f"v{version}"])  # our own tag, not yet pushed: nothing else can hold it
        if removed.exit != 0:
            return _failed(rec, "tag_remove_failed", removed.exit, commit=head, checks=found, tag_commit=tagged)
        return _failed(rec, "tag_check_failed", checks.exit, commit=head, checks=found, tag_commit=tagged)
    passed = ["commit", "evidence_audit", "manifest_verify", "tag", *sorted(k for k, v in found.items() if v.get("ok"))]
    record = {"schema": 1, "version": version, "tag": f"v{version}", "commit": head, "checks_passed": passed,
              "tagged_at": clock().isoformat(timespec="seconds")}
    write_state(root, record)
    release_runstate.patch(root, version, release_commit=head)
    return 0, {"status": "ok", "version": version, "commit": head, "tag": f"v{version}", "checks": found,
               "release_state": RELEASE_STATE, "commands": rec.as_json()}
