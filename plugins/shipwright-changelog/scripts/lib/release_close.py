"""``release.py close-phase``: the phase-complete block of Step 7 in one call (unit P4; A9, B4, operator decision F10).

**F10: the release never commits ``build_dashboard.md``, ``session_handoff.md`` or the run-config bookkeeping, and the tree is
clean afterwards.** In a hand-invoked (standalone) release nothing is written: no dashboard (C2), no handover note (C3), no
``phase_history`` entry, and every derived snapshot an earlier step rewrote is put back to ``HEAD``
(``derived_snapshots.restore_derived_to_head``, through ``checks/restore_derived.py``). In a dispatched (pipeline) run the phase's
canon records are the master's gate input and stay: C2, C3 with ``--canon-marker --phase changelog`` (FR-01.01) and the
``phase_history`` entry with the run id the gate (``orchestrator_pkg/gate_run_id.py``) looks for. ``single-session-apply``
completes the phase task and runs that gate; it never writes ``phase_history`` itself, so the entry stays with this call.
``orchestrator.py update-step`` is never called: the tag/CHANGELOG check it provided runs in ``commit-and-tag`` (F7).

Then A9 (the closing summary and a one-line status, printed by code; the tag line says "pushed" only when the closing verify saw the
release's tag on origin, D113(1)) and B4 (``release_verify``: read-only; a failed check is exit 1).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import release_commit, release_paths, release_runstate, release_verify
from .release_runner import Recorder, uv_script

RULE = "=" * 80
ADVISORY = ".shipwright/triage.jsonl"  # the release audit's advisory finding, untracked on some systems


def summary(version: str, state: dict[str, Any], checks: list[dict[str, Any]], release_status: str | None, release_url: str | None,
            release_note: str | None) -> str:
    remote = next((c for c in checks if c.get("name") == "tag_remote"), {})
    if remote.get("on_origin"):  # D113(1): what origin holds, not what the mode expects
        done = f"Tag + {state.get('branch') or 'main'} pushed to origin" if state.get("on_trunk") else "Tag pushed to origin"
        pushed = done if remote.get("ok") else f"Tag v{version} on origin names another commit than the release"
    elif remote.get("on_origin") is None:  # the lookup failed (or no tag check ran): unknown is not "waiting" and not "missing"
        pushed = f"Tag v{version}: origin could not be asked whether it holds the tag"
    elif release_verify.tag_may_be_pending(state):
        pushed = "Tag is pushed after the PR is merged"
    else:
        pushed = f"Tag v{version} is not on origin"
    pr = "skipped (on main)" if state.get("on_trunk") else state.get("pr_url") or "not opened"
    page = {"ok": release_url, "exists": release_url}.get((release_status or "").lower()) or f"{release_status or 'not reported'}: {release_note or ''}".rstrip(": ")
    return "\n".join([RULE, "SHIPWRIGHT-CHANGELOG COMPLETE", RULE, f"Version:    v{version}",
                      f"Commits:    {state.get('commits', '?')} categorized", "Changelog:  CHANGELOG.md updated",
                      f"Tag:        v{version} created", f"PR:         {pr}", f"Release:    {page}", "", pushed, RULE,
                      "Status:     " + " | ".join(f"{c['name']} {'ok' if c['ok'] else 'FAILED'}" for c in checks)])


def close_phase(rec: Recorder, plugin_root: Path, *, version: str, session_id: str = "", release_status: str | None = None,
                release_url: str | None = None, release_note: str | None = None,
                clock=lambda: datetime.now(timezone.utc)) -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tools, state = shared / "scripts/tools", release_runstate.stored(root, version) or {}
    if not state.get("mode"):  # a missing state must not read as a hand-invoked release: the dashboard would be restored under a driven run
        return 1, {"version": version, "status": "failed", "reason": "run_state_missing", "commands": rec.as_json()}
    pipeline = state.get("mode") == "pipeline"
    run_id = state.get("run_id") or os.environ.get("SHIPWRIGHT_RUN_ID") or f"changelog-v{version}-{clock():%Y%m%d-%H%M%S}"
    out: dict[str, Any] = {"version": version, "mode": state.get("mode", "standalone"), "run_id": run_id, "written": []}
    failed = None
    if pipeline:  # the master's gate reads these three; a hand-invoked release writes none of them (F10)
        ours = "SHIPWRIGHT_RUN_ID" not in os.environ
        os.environ.setdefault("SHIPWRIGHT_RUN_ID", run_id)
        try:
            steps = (("dashboard", "update_build_dashboard.py", ["--phase", "changelog", "--session-id", session_id]),
                     ("handoff", "generate_session_handoff.py", ["--canon-marker", "--phase", "changelog", "--reason", f"release v{version}"]),
                     ("phase-history", "append_phase_history.py", ["--phase", "changelog", "--run-id", run_id,
                                                                    "--entry-json", f'{{"version":"v{version}","outcome":"tagged"}}']))
            for key, script, args in steps:
                done = rec.run(key, uv_script(tools / script, "--project-root", str(root), *args))
                if done.exit == 0:
                    out["written"].append(key)
                if done.exit != 0:
                    failed = done
                    break  # a partial canon record is what the gate could misread: stop at the first failing writer
        finally:
            if ours:
                os.environ.pop("SHIPWRIGHT_RUN_ID", None)
    elif (release_commit.read_state(root) or {}).get("version") != version:  # no release was cut: restoring would drop uncommitted derived work
        return 1, {**out, "status": "failed", "reason": "release_not_committed", "commands": rec.as_json()}
    else:
        restored = rec.run("restore-derived", uv_script(plugin_root / "scripts/checks/restore_derived.py", "--shared-root", str(shared),
                                                        "--project-root", str(root)))
        failed = restored if restored.exit != 0 else None
    if failed:
        return failed.exit or 1, {**out, "status": "failed", "reason": f"{failed.key}_failed", "commands": rec.as_json()}
    checks = release_verify.verify(rec, plugin_root, version=version, state=state, release_status=release_status, release_note=release_note)
    before = set(state.get("tree_before") or [])  # what was already dirty when the release started is not the release's
    status = rec.run("tree-status", ["git", "status", "--porcelain"])
    dirty = "\n".join(line for line in status.stdout.splitlines() if line not in before and not line.rstrip().endswith(ADVISORY))
    if status.exit != 0:  # a status that failed is not a clean tree
        dirty = f"git status failed (exit {status.exit}): {status.stderr[:120]}"
    if not pipeline:  # F10: a hand-invoked release ends with a clean tree (the advisory audit finding is not the release's write)
        checks.append({"name": "tree_clean", "ok": not dirty, "detail": "clean" if not dirty else f"dirty: {dirty[:200]}"})
    text = summary(version, state, checks, release_status, release_url, release_note)
    ok = all(c["ok"] for c in checks)
    return (0 if ok else 1), {**out, "status": "ok" if ok else "verify_failed", "verify": checks, "tree_clean": not dirty,
                              "summary": text, "notices": [text], "commands": rec.as_json()}
