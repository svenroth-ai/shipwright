"""``release.py aggregate``: Step 4 in one call (second pass A4).

The flag rules of the prose live here and nowhere else: the preview (``dry_run``) passes ``--dry-run`` and never
``--fail-if-empty`` (it would turn "nothing pending" into a failure); the real run always passes ``--fail-if-empty`` (an
empty first release is refused, not tagged). The release date is the one ``prepare`` stored (A6; an explicit
``release_date`` overrides it), so a re-run after an interruption renders the same heading. A real run then numbers the
ADR drops (``aggregate_decisions.py``); bullets from a cherry-pick (``fallback_entries``) are written first, as drop
files (F9: a legacy ``[Unreleased]`` bullet missed the release it was written for), and only on a real run (a preview
writes nothing, AC10). Hand-written entries under ``## [Unreleased]`` move into the release (Q5,
``--move-unreleased``, passed only while this version's section is not yet written); the preview marks them
``(hand-written)`` in ``section_preview``. A re-run after an interruption converges when the first run moved no
hand-written entry (after a finished release it always does). When it moved some and was interrupted before the
drops were consumed, the re-run refuses by design (the section on record says more than the drops; FINDINGS D92, D102)
and the operator reconciles by hand. The exit code is the aggregator's own: a refused re-run (AC08) is exit 1 with its
stderr naming the disagreement, and stays an operator action, never a retry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from . import release_paths, release_runstate, release_upgrade_notes
from .release_runner import Recorder, uv_script

FALLBACK_RUN_ID = "release-fallback"  # fixed, so a cherry-picked bullet sorts after the iterate drops of its category on every run


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def aggregate(rec: Recorder, plugin_root: Path, *, version: str, dry_run: bool = False, release_date: str | None = None,
              fallback_entries: Sequence[tuple[str, str]] = (),
              clock: release_runstate.Clock = release_runstate.utc_now) -> tuple[int, dict[str, Any]]:
    shared, root = release_paths.shared_root(plugin_root), rec.cwd
    tag_exists = rec.run("tag-check", ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"]).exit == 0
    already = release_upgrade_notes.released(root, version)
    state = release_runstate.resolve(root, version, tag_exists=tag_exists, release_date=release_date, clock=clock,
                                     require_fresh=False, released=already)  # only `prepare` starts a release; aggregate consumes what it stored
    tools = shared / "scripts/tools"
    pending = [f"{category}: {entry}" for category, entry in fallback_entries]  # a preview names them; it writes nothing
    skip_fallbacks = dry_run or already  # a rendered section means an earlier run already took them: a re-run must not append twice (D31)
    fallbacks = [] if skip_fallbacks else [rec.run("fallback-append", uv_script(  # one drop per bullet, idempotent per run id
        tools / "write_changelog_drop.py", "--project-root", str(root), "--run-id", FALLBACK_RUN_ID,
        "--category", category, "--bullet", entry)) for category, entry in fallback_entries]
    if any(r.exit != 0 for r in fallbacks):  # a lost cherry-picked bullet must stop the release, not vanish
        return 1, {"status": "failed", "reason": "fallback_entry_failed", "dry_run": dry_run, "fallback_entries": [r.exit for r in fallbacks],
                   "commands": rec.as_json()}
    pending_notes = state.get("upgrade_pending") or []
    if pending_notes and not dry_run and not already:  # prepare held them back while a question was open (D-P3 review 1)
        drops = release_upgrade_notes.write_pending(rec, shared, pending_notes)
        if "failed" in drops:
            return 1, {"status": "failed", "reason": "upgrade_note_drop_failed", "dry_run": dry_run, "commands": rec.as_json()}
        state["upgrade_pending"] = []
    flags = ["--dry-run"] if dry_run else ["--fail-if-empty"]
    done = rec.run("aggregate-dry" if dry_run else "aggregate", uv_script(
        tools / "aggregate_changelog.py", "--project-root", str(root), "--version", version,
        "--release-date", state["release_date"], *([] if already else ["--move-unreleased"]), *flags))  # a finished section never takes newer hand-written entries (fix round 1)
    info = _json(done.stdout)
    out: dict[str, Any] = {
        "status": "ok" if done.exit == 0 else "failed", "version": info.get("version"), "dry_run": dry_run,
        "section_action": info.get("section_action"), "changelog_updated": info.get("changelog_updated"),
        "legacy_unreleased_bullets": info.get("legacy_unreleased_bullets"),
        "legacy_unreleased_bullet_texts": info.get("legacy_unreleased_bullet_texts") or [],
        "section_written": info.get("section_written", ""),
        "hand_written": info.get("hand_written_entries") or [],
        **({"section_preview": info.get("section_preview", "")} if dry_run else {}),
        "release": {"date": state["release_date"], "run_id": state["run_id"], "state_file": str(release_runstate.state_path(root))},
        "fallback_entries": [r.exit for r in fallbacks],
        "fallback_pending": pending if dry_run else [], "upgrade_notes_pending": [p["note"] for p in pending_notes] if dry_run else [], "fallback_skipped": "release_written" if already and pending and not dry_run else None}
    if done.exit != 0:
        out["reason"] = "aggregator_refused"  # reconcile by hand: references/rerunning-a-release.md, never a retry
    elif not dry_run:
        release_runstate.save(root, state)
        decisions = rec.run("decisions", uv_script(tools / "aggregate_decisions.py", "--project-root", str(root)))
        out["decisions"] = {"exit": decisions.exit}
        if decisions.exit != 0:
            out["status"], out["reason"] = "failed", "decisions_numbering_failed"
            out["commands"] = rec.as_json()
            return decisions.exit, out
    if dry_run and done.exit == 0:  # the preview names the ADR numbers the real run will give (it writes nothing)
        out["decisions_preview"] = {"summary": rec.run("decisions-dry", uv_script(
            tools / "aggregate_decisions.py", "--project-root", str(root), "--dry-run")).stdout.strip()}
    out["commands"] = rec.as_json()
    return done.exit, out
