"""``release.py prepare``: the banner, the mode, setup and Steps 0-3 of ``SKILL.md`` in one call (second pass A1).

Every command is one the prose ran by hand, with the same flags, through the injected runner: ``get_phase_context.py``
(Step C), ``setup-changelog.py`` (Step D), ``resolve_gate_policy.py`` (A2: what each question asks), ``git_utils.py
parse-commits`` (Step 2). The code adds only what the prose left to the model: the answers to the questions
(``gates``, from the catalog), the upgrade-notes check (A3), and the facts later calls need (the run state: version, release
date, run id; A6 and F14). Exit codes are the tools' own where a tool refused (the mode check: 2, the setup script's usage
error), 0 for "nothing to release" (it is a result, not a failure).
"""

from __future__ import annotations

import json
from typing import Any

from pathlib import Path

from . import release_cancel, release_event, release_gates, release_paths, release_runstate, release_upgrade_notes, release_version
from .release_runner import Recorder, uv_script

BANNER = """\
================================================================================
SHIPWRIGHT-CHANGELOG: Release Management
================================================================================
Analyzes git history, generates changelog, creates PR.

Usage: /shipwright-changelog | invoked by /shipwright-run (orchestrator)

Steps: analyze commits -> categorize -> generate entry -> confirm -> sync
manifests/evidence -> commit + tag -> publish GitHub Release -> optional PR
================================================================================"""
STANDALONE_NOTICE = "Running in standalone mode — pipeline state will not be updated."


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(text: str) -> list[Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _autonomy(shared: Path, project_root: Path) -> str | None:
    try:
        return _json(release_paths.run_config_path(shared, project_root).read_text(encoding="utf-8-sig")).get("autonomy")
    except OSError:
        return None


def _stop(rec: Recorder, code: int, reason: str, **fields: Any) -> tuple[int, dict[str, Any]]:
    return code, {"status": "stop", "reason": reason, **fields, "commands": rec.as_json()}


def prepare(rec: Recorder, plugin_root: Path, *, phase_task_id: str | None = None, version: str | None = None,
            clock: release_runstate.Clock = release_runstate.utc_now) -> tuple[int, dict[str, Any]]:
    shared = release_paths.shared_root(plugin_root)
    root = rec.cwd
    ctx_args = ["--phase-task-id", phase_task_id] if phase_task_id else []
    ctx = rec.run("context", uv_script(shared / "scripts/tools/get_phase_context.py", *ctx_args, "--phase", "changelog",
                                       "--project-root", str(root)))
    context = _json(ctx.stdout)
    mode = context.get("mode", "")
    if ctx.exit != 0:  # `error`: a dispatch token that does not resolve. STOP, never continue as standalone
        return _stop(rec, ctx.exit, "mode_error", mode=mode)
    setup = rec.run("setup", uv_script(plugin_root / "scripts/checks/setup-changelog.py", "--plugin-root", str(plugin_root)))
    info = _json(setup.stdout)
    if setup.exit != 0 and not info:  # the script refused to run (Q7/D9: the never-built `--from` is no longer offered)
        return _stop(rec, setup.exit, "setup_refused", mode=mode)
    facts = {"mode": mode, "last_tag": info.get("last_tag"), "branch": info.get("branch"),
             "commits_since_tag": info.get("commits_since_tag"), "previous_tag_has_release": info.get("previous_tag_has_release")}
    if setup.exit != 0 or not info.get("has_unreleased"):
        return _stop(rec, setup.exit, "no_unreleased_changes", **facts, message="No unreleased changes")
    gate_run = rec.run("gates", uv_script(shared / "scripts/tools/resolve_gate_policy.py", "--phase", "changelog", "--list",
                                          "--project-root", str(root)))
    rows = _json(gate_run.stdout).get("gates")
    if gate_run.exit != 0 or not isinstance(rows, list):  # no catalog, no answers: never guess them
        return _stop(rec, gate_run.exit or 2, "gate_catalog_unavailable", **facts)
    last_tag = info.get("last_tag")
    parsed = rec.run("parse-commits", uv_script(plugin_root / "scripts/lib/git_utils.py", "parse-commits",
                                                "--since", last_tag or "", "--format", "json"))  # no tag: an empty --since (finding D4)
    if parsed.exit != 0:
        return _stop(rec, parsed.exit, "parse_commits_failed", **facts)
    chosen = version or info.get("suggested_version")
    if not chosen:
        return _stop(rec, 2, "no_version", **facts)
    try:
        chosen = release_version.normalize(chosen)  # the CLI already did; a library caller or the setup script may not
    except ValueError as bad:
        return _stop(rec, 2, "invalid_version", **facts, message=str(bad))
    merged = rec.run("tags-merged", ["git", "tag", "--merged", "HEAD"])  # D100: only this branch's history counts
    on_branch, odd = release_version.last_release_tag(merged.stdout.split("\n")) if merged.exit == 0 else (None, [])
    if release_version.not_above(chosen, on_branch):  # Q8/D16: a release goes up, never sideways or down
        return _stop(rec, 2, "version_not_above_last_tag", **facts, version=chosen, release_tag=on_branch,
                     message=f"version {chosen} is not higher than the last release tag on this branch, {on_branch}: choose a higher SemVer version "
                             "(a release that stopped after its tag is finished at Step 7, references/rerunning-a-release.md)")
    tag_exists = rec.run("tag-check", ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{chosen}"]).exit == 0
    state = release_runstate.resolve(root, chosen, tag_exists=tag_exists, clock=clock, use_env_run_id=mode == "pipeline",
                                     released=release_upgrade_notes.released(root, chosen))
    autonomy = _autonomy(shared, root)
    gates = release_gates.answers(rows, mode=mode, autonomy=autonomy)
    asks = gates["version"] == "ask" or gates["preview"] == "ask" or (  # F2: a preview that can still be cancelled writes nothing yet
        bool(context.get("requires_out_of_sequence_warning")) and gates["out_of_sequence"] == "ask")
    notes = release_upgrade_notes.check(rec, shared, last_tag, chosen, write=not asks)  # a question that can still end the release is open: write nothing yet (D-P3 review 1)
    if notes["status"] in ("action_drop_failed", "query_failed"):
        return _stop(rec, 1, "upgrade_note_drop_failed" if notes["status"] == "action_drop_failed" else "upgrade_notes_query_failed",
                     **facts, upgrade_notes=notes)
    state.setdefault("tree_before", release_runstate.tree_snapshot(root))  # the baseline close-phase's clean-tree check compares against
    state["drops_before"] = release_cancel.snapshot(root)  # what Cancel puts back (D84): taken anew on every prepare, so a re-run keeps the drops as they are now
    base, source = release_event.trunk(rec)  # F5: the default branch, from the remote
    state.update(mode=mode, autonomy=autonomy, commits=len(_json_list(parsed.stdout)), trunk=base, trunk_source=source)  # facts the later steps read (the close summary, the verify)
    on_trunk = facts["branch"] in release_event.trunks(state)  # Step 7 branches on this: no head push and no PR on a trunk
    state["upgrade_pending"] = notes.get("pending", [])  # `aggregate` files them once the questions are answered
    release_runstate.save(root, state)
    notices = [BANNER] + ([STANDALONE_NOTICE] if mode == "standalone" else []) + (
        [f"Notice: {last_tag} has no GitHub Release — see release-workflow.md"] if info.get("previous_tag_has_release") is False else []) + (
        [f"Notice: the tag(s) {', '.join(odd)} are no SemVer version, so {chosen} was not compared with them"] if odd else []) + (
        ["Notice: the tags reachable from HEAD could not be listed, so the version was not compared"] if merged.exit != 0 else [])
    return 0, {
        "status": "ok", "version": chosen, "suggested": info.get("suggested_version"), "version_reason": info.get("version_reason"),
        **facts, "trunk": base, "trunk_source": source, "on_trunk": on_trunk, "gates": gates,
        "out_of_sequence_warning": bool(context.get("requires_out_of_sequence_warning")),
        "active_phases": context.get("active_phases") or [], "skill_artifacts_to_read": context.get("skill_artifacts_to_read") or [],
        "release": {"date": state["release_date"], "run_id": state["run_id"], "reused": state["reused"], "state_file": str(release_runstate.state_path(root))},
        "upgrade_notes": notes, "notices": notices, "commits": _json_list(parsed.stdout),
        "paths": {"plugin_root": str(plugin_root), "shared_root": str(shared),
                  "orchestrator": str(release_paths.orchestrator_path(plugin_root) or "")},
        "commands": rec.as_json()}
