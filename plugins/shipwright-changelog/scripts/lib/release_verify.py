"""The read-only verify at the end of ``release.py close-phase`` (second pass B4).

Seven questions, each answered from git and the filesystem (nothing is written, nothing is fetched): the tag exists locally and
names the release commit; the tag on ``origin`` names it too (or is not pushed yet, which is what a guided release waits for,
F1b); the CHANGELOG matches the tag (the F7 verifiers); the ``phase_completed`` event is committed; no decision drop is left;
the PR state fits the mode (merged when the run merges it, opened otherwise, none on the trunk); the GitHub Release page is
present, or skipped with a reason. A check that is broken is ``ok: false`` with the reason; ``verify`` never repairs.

After a squash or rebase merge the release record may name the PR's merge commit (``published_commit`` with its proof, D110): the tag
checks then accept the tag on that commit, and the PR check accepts that commit on the base, while the proof still holds
(``scripts/hooks/release_merge_proof``, the rule the release guard uses too). A record without those fields is judged as before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1] / "hooks"))  # appended: never shadow a module of the caller
import release_merge_proof  # noqa: E402  (stdlib-only, shared with the release guard hook)

from . import release_commit, release_paths  # noqa: E402
from .release_runner import Recorder, uv_script  # noqa: E402

AUTONOMOUS = ("autonomous", "unattended")
DROP_DIR = ".shipwright/agent_docs/decision-drops"


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def waits_for_merge(state: dict[str, Any]) -> bool:
    """A hand-invoked release on a feature branch may wait for the PR merge: the tag is pushed after it (F1b). A driven run never merges its PR and never waits.
    ``release.py push-tag`` and the closing verify ask this one question."""
    return not state.get("on_trunk", False) and state.get("mode") == "standalone"


def tag_may_be_pending(state: dict[str, Any]) -> bool:
    """At the closing verify the tag may still be off origin: the release waits (``waits_for_merge``) and a person, not this run, merges the PR."""
    return waits_for_merge(state) and state.get("autonomy") not in AUTONOMOUS


def verify(rec: Recorder, plugin_root: Path, *, version: str, state: dict[str, Any], release_status: str | None,
           release_note: str | None) -> list[dict[str, Any]]:
    root, tag = rec.cwd, f"v{version}"
    record = release_commit.read_state(root) or {}
    commit = record.get("commit") if record.get("version") == version else None
    published = proven_published(rec, record) if commit else None
    named = {c for c in (commit, published) if c}  # the commits the tag may name
    merged = f"; merge commit {published}" if published else ""
    checks: list[dict[str, Any]] = []
    local = rec.run("verify-local-tag", ["git", "rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"]).stdout.strip()
    checks.append(_check("tag_local", local in named, f"{tag} -> {local or 'missing'}; release commit {commit or 'unknown'}{merged}"))
    url = rec.run("verify-remote-url", ["git", "remote", "get-url", "--push", "origin"]).stdout.strip() or "origin"  # where a push goes
    remote = rec.run("verify-remote-tag", ["git", "ls-remote", "--tags", "--end-of-options", url, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
    shas = {line.split()[1]: line.split()[0] for line in remote.stdout.splitlines() if len(line.split()) == 2}
    pushed = shas.get(f"refs/tags/{tag}^{{}}") or shas.get(f"refs/tags/{tag}")
    if pushed:
        checks.append({**_check("tag_remote", pushed in named, f"origin {tag} -> {pushed}"), "on_origin": True})
    else:
        waiting = tag_may_be_pending(state)
        checks.append({**_check("tag_remote", waiting and remote.exit == 0, "not pushed: waits for the PR merge" if waiting else f"{tag} is not on origin"
                                + (f" ({remote.stderr.strip()})" if remote.exit else "")), "on_origin": False if remote.exit == 0 else None})  # None: origin not asked
    shared = release_paths.shared_root(plugin_root)
    tagged = rec.run("verify-tag", uv_script(plugin_root / "scripts/checks/verify_release_tag.py", "--shared-root", str(shared),
                                             "--project-root", str(root), "--version", version))
    try:
        found = json.loads(tagged.stdout)
    except ValueError:
        found = {"ok": False, "checks": {}}
    checks.append(_check("changelog_matches_tag", tagged.exit == 0 and bool(found.get("ok")), json.dumps(found.get("checks", {}))[:300] or tagged.stderr.strip()))
    event = rec.run("verify-event", ["git", "grep", "-l", "-F", "-e", '"type":"phase_completed"', "--and", "-e", '"phase":"changelog"', "--and",
                                     "-e", f'"detail":"v{version} ', "HEAD", "--", *("shipwright_events.jsonl", ".shipwright/events")])  # one event line, in the log or in a run's drop
    checks.append(_check("event_committed", event.exit == 0, f"phase_completed v{version} in HEAD" if event.exit == 0 else "no committed phase_completed event"))
    drops = sorted(str(p.relative_to(root / DROP_DIR).as_posix()) for p in (root / DROP_DIR).rglob("*")
                   if p.is_file() and not p.name.lower().startswith(("readme", "index", ".git")) and not p.name.endswith(".tmp")) if (root / DROP_DIR).is_dir() else []
    checks.append(_check("no_decision_drops", not drops, "none left" if not drops else f"left: {', '.join(drops[:5])}"))
    checks.append(_pr_check(rec, state, commit, published))
    status = (release_status or "").lower()
    if status in ("ok", "exists"):
        checks.append(_check("release_page", True, f"{status}: {release_note or 'url reported'}"))
    elif status in ("skipped", "failed", "waiting"):
        checks.append(_check("release_page", bool(release_note), f"{status}: {release_note or 'no reason given'}"))
    else:
        checks.append(_check("release_page", False, "no release page status was reported (--release-status)"))
    return checks


def proven_published(rec: Recorder, record: dict[str, Any]) -> str | None:
    """The record's merge commit when it claims one and the proof holds (``release_merge_proof``); no git call when it claims none."""
    def git(*args: str) -> tuple[int, str]:
        done = rec.run("verify-proof", ["git", *args])
        return done.exit, done.stdout

    return release_merge_proof.proven(git, record) if release_merge_proof.claimed(record) else None


def _pr_check(rec: Recorder, state: dict[str, Any], commit: str | None, published: str | None = None) -> dict[str, Any]:
    if state.get("on_trunk"):
        return _check("pr_state", not state.get("pr_url"), "released on the trunk: no PR")
    if not state.get("pr_url"):
        return _check("pr_state", False, "released from a feature branch but no PR was opened")
    if state.get("mode") != "standalone" or state.get("autonomy") not in AUTONOMOUS:  # a driven run never merges its PR; a guided one waits for a person
        return _check("pr_state", True, f"PR opened, left for the merge: {state['pr_url']}")
    reached, base, detail = on_base(rec, state, commit)
    what = "the release commit"
    if reached is False and published:  # a squash or rebase merge: the proven merge commit is what reached the base
        (reached, base, detail), what = on_base(rec, state, published), f"the release's merge commit {published[:10]}"
    if reached is None:
        return _check("pr_state", False, f"unknown: cannot tell whether {what} reached {base} ({detail})")
    return _check("pr_state", reached, f"{what} is on {base} (origin)" if reached else f"this run merges its PR, but {what} is not on {base}")


def on_base(rec: Recorder, state: dict[str, Any], commit: str | None) -> tuple[bool | None, str, str]:
    """``(reached, base, detail)``: is the release commit on the PR's base branch on origin? ``None`` = cannot tell (no commit, no
    fetch, or git could not answer: unknown is not "not merged"). Only FETCH_HEAD moves, never a ref or the tree."""
    base = state.get("base_branch") or state.get("trunk") or rec.run("verify-base", ["git", "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"]).stdout.strip().removeprefix("origin/") or "main"
    url = rec.run("verify-remote-url", ["git", "remote", "get-url", "--push", "origin"]).stdout.strip() or "origin"  # where a push goes, like the tag check
    fetched = rec.run("verify-fetch", ["git", "fetch", "--quiet", "--end-of-options", url, base])
    ancestry = rec.run("verify-merged", ["git", "merge-base", "--is-ancestor", commit or "", "FETCH_HEAD"]) if commit and fetched.exit == 0 else None
    if ancestry is None or ancestry.exit not in (0, 1):
        return None, base, (fetched.stderr or (ancestry.stderr if ancestry else "")).strip()[:120] or ("git could not tell" if commit else "no release commit recorded")
    return ancestry.exit == 0, base, ""
