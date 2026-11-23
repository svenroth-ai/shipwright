"""The CLI driver: ``prepare`` and ``aggregate`` through ``release.py`` (unit P3), the rest as the replay runs it.

It implements the same per-step driver interface as ``driver_replay`` (programme P7). A step it moved becomes one
``release.py`` call; every other step is the replay's, so a scenario written for the replay runs unchanged and its trace
is compared with the frozen one. P4 moves the steps 5.4 to 7 here too.

``release.py`` reports every tool it ran (``commands``: key, exit code, stdout, stderr); this driver replays them into
``log``, so the scenarios that read a tool's own output (``run.commands("aggregate")[-1]["stderr"]``) read the same
bytes as through the replay. The step results map the JSON back to the whitelisted trace fields, with the reason strings
of the replay (``exit_N``) so a frozen trace stays an equality.

Two places where the driver speaks for the model, both on purpose: the replay's ``aggregate`` without a ``release_date``
means "today" (the aggregator's default), and the CLI's default is the stored date (second pass A6), so the driver
spells today out; and an answer the CLI gives (``gates``) is turned into the question the trace records
(``version_question``). ``fail_if_empty=False`` is refused: the CLI owns that flag (A4).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence

import golden_trace as gt

from .driver_replay import STEPS, ReplayDriver
from .replay_commands import CITES, PLUGIN

RELEASE_CLI = PLUGIN / "scripts" / "release.py"
CLI_STEPS = frozenset({"prepare", "aggregate"})


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


class CliDriver(ReplayDriver):
    name = "cli"
    steps = STEPS

    def _release(self, scratch: Any, *args: str) -> tuple[int, dict[str, Any]]:
        """One ``release.py`` call; its tool calls go into ``log`` in order. A crash (no JSON) is exit 1 with no payload."""
        done = scratch.run(["uv", "run", str(RELEASE_CLI), args[0], "--project-root", str(scratch.repo), *args[1:]])
        payload = _json(done.stdout)
        for cmd in payload.get("commands", []):
            self.log.append({"key": cmd["key"], "cites": CITES.get(cmd["key"], []), "exit": cmd["exit"],
                             "stdout": cmd["stdout"], "stderr": cmd["stderr"]})
        if not payload:
            self.log.append({"key": "release-crash", "cites": [], "exit": done.returncode, "stdout": done.stdout, "stderr": done.stderr})
        return done.returncode, payload

    # ---- Step C-3 --------------------------------------------------------------------------
    def step_prepare(self, scratch: Any, phase_task_id: str | None = None, version: str | None = None,
                     from_version: str | None = None) -> gt.StepResult:
        args = ["prepare", *(["--phase-task-id", phase_task_id] if phase_task_id else []),
                *(["--version", version] if version else []), *(["--from", from_version] if from_version else [])]
        code, out = self._release(scratch, *args)
        if not out:
            return gt.StepResult("prepare", code or 1, {"status": "failed", "reason": f"exit_{code}"})
        facts = {k: out.get(k) for k in ("mode", "last_tag", "branch", "commits_since_tag", "previous_tag_has_release")}
        if out["status"] != "ok":
            keep = {"mode": out.get("mode", "")} if out["reason"] in ("mode_error", "setup_refused") else facts
            return gt.StepResult("prepare", code, {"status": "stop", "reason": out["reason"], **keep})
        self.state.update(last_tag=facts["last_tag"], branch=facts["branch"] or "", mode=facts["mode"], version=out["version"])
        fields = {**facts, "version_question": "auto-accepted" if out["gates"]["version"] == "auto" else "asked"}
        if out["out_of_sequence_warning"]:
            fields["out_of_sequence"] = "asked"
        return gt.StepResult("prepare", 0, {"status": "ok", "version": out["version"], "suggested": out["suggested"],
                                            "version_reason": out["version_reason"], **fields})

    # ---- Step 4 ----------------------------------------------------------------------------
    def step_aggregate(self, scratch: Any, version: str, dry_run: bool = False, release_date: str | None = None,
                       fail_if_empty: bool = True, fallback_bullets: Sequence[tuple[str, str]] = ()) -> gt.StepResult:
        if not fail_if_empty:
            raise ValueError("release.py owns --fail-if-empty (second pass A4): the CLI driver cannot switch it off")
        date = release_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        args = ["aggregate", "--version", version, "--release-date", date, *(["--dry-run"] if dry_run else []),
                *[f"--fallback-entry={category}:{entry}" for category, entry in fallback_bullets]]
        code, out = self._release(scratch, *args)
        ok = code == 0 and out.get("status") == "ok"
        if ok:
            self.state["section"] = out.get("section_written", "")
        fields: dict[str, Any] = {"status": "ok" if ok else "failed", "version": out.get("version"),
                                  "section_action": out.get("section_action"), "changelog_updated": out.get("changelog_updated"),
                                  "legacy_bullets": out.get("legacy_unreleased_bullets")}
        if not ok:
            fields["reason"] = f"exit_{code}"
        return gt.StepResult("aggregate", code, fields)

