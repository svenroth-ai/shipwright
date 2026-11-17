"""The replay driver: the command sequence today's ``SKILL.md`` prescribes, one step at a time (programme P7).

It implements the per-step driver interface of ``golden_trace`` for the steps of Step C through Step 7
that the first half of the scenarios (S1-S9) need. Every command it runs cites its ``SKILL.md`` line
(``replay_commands.CITES``); ``ReplayDriver.log`` records each command with its key, so a test can check
the citations against the live prose. It is FROZEN with the traces at the operator's stop 2.

Order follows the prose, including the places where the prose is wrong (findings D7, D15): ``gh pr create``
runs before the head is pushed, the PR body keeps its literal ``\\n`` and an undefined ``{entry}`` is the
aggregated section. A command that exits non-zero is a result, never an exception: the scenario records it.

``gh`` is run through the seam prefix of the scratch environment (a bare ``gh`` on Windows would bypass the
shim). The shell chains run under ``bash`` (Git Bash on Windows), as the model would run them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

import golden_trace as gt

from .replay_commands import CITES, CLOSE_PHASE, COMMIT_AND_TAG, EVENT_MAIN, EVENT_PR, PLUGIN, SHARED, fill

STEPS = frozenset({"prepare", "aggregate", "preview", "fold-events", "sync", "evidence", "commit-and-tag",
                   "open-pr", "record-event", "merge-pr", "push-tags", "release-page", "close-phase"})
MAIN_BRANCHES = ("main", "develop")  # SKILL.md:327 "Only if on a feature branch (not main/develop)"


def find_bash() -> str | None:
    found = shutil.which("bash")
    if os.name == "nt" and found and "system32" in found.lower():  # the WSL launcher: use Git's bash
        git = shutil.which("git")
        cand = Path(git).resolve().parent.parent / "bin" / "bash.exe" if git else None
        found = str(cand) if cand and cand.exists() else None
    return found


def _json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _uv(script: Path, *args: str) -> list[str]:
    return ["uv", "run", str(script), *args]


class ReplayDriver:
    name = "replay"
    steps = STEPS

    def __init__(self) -> None:
        self.log: list[dict[str, Any]] = []  # every command run: key, cited lines, exit code
        self.state: dict[str, Any] = {"evidence": [], "manifests": [], "pr_url": "", "section": ""}

    # ---- plumbing --------------------------------------------------------------------------
    def _run(self, key: str, scratch: Any, argv: Sequence[str]) -> subprocess.CompletedProcess:
        try:
            done = scratch.run(list(argv))
        except FileNotFoundError as exc:  # a program that is not installed (the 'gh missing' scenario) is a result, not a crash
            done = subprocess.CompletedProcess(list(argv), 127, "", f"{type(exc).__name__}: {exc}")
        self.log.append({"key": key, "cites": CITES[key], "exit": done.returncode, "stdout": done.stdout, "stderr": done.stderr})
        return done

    def _gh(self, key: str, scratch: Any, *args: str) -> subprocess.CompletedProcess:
        prefix = json.loads(scratch.env["SHIPWRIGHT_TEST_GH_ARGV_PREFIX"])
        return self._run(key, scratch, [*prefix, *args])

    def _bash(self, key: str, scratch: Any, script: str) -> subprocess.CompletedProcess:
        bash = find_bash()
        if bash is None:
            raise RuntimeError("bash is required to replay the SKILL.md command chains")
        return self._run(key, scratch, [bash, "-c", script])

    def run_step(self, step: str, scratch: Any, **params: Any) -> gt.StepResult:
        if step not in STEPS:
            raise KeyError(step)
        return getattr(self, "step_" + step.replace("-", "_"))(scratch, **params)

    @staticmethod
    def _result(step: str, done: subprocess.CompletedProcess, **fields: Any) -> gt.StepResult:
        out = {"status": "ok" if done.returncode == 0 else "failed", **fields}
        if done.returncode != 0:
            out["reason"] = f"exit_{done.returncode}"  # tool error text stays out of the trace; scenarios assert stderr itself
        return gt.StepResult(step, done.returncode, out)

    # ---- Step C-3 --------------------------------------------------------------------------
    def step_prepare(self, scratch: Any, phase_task_id: str | None = None, version: str | None = None,
                     from_version: str | None = None) -> gt.StepResult:
        """Mode, setup script, history, commit types, version (``version`` is a guided operator's custom entry;
        ``from_version`` is the banner's advertised ``--from vX``, which no script implements: finding D9)."""
        ctx_args = ["--phase-task-id", phase_task_id] if phase_task_id else []
        ctx = self._run("context", scratch, _uv(SHARED / "scripts/tools/get_phase_context.py", *ctx_args,
                                                "--phase", "changelog", "--project-root", str(scratch.repo)))
        context = _json(ctx.stdout)
        mode = context.get("mode", "")
        if ctx.returncode != 0:  # SKILL.md:67-70 `error`: STOP, never continue as standalone
            return gt.StepResult("prepare", ctx.returncode, {"status": "stop", "reason": "mode_error", "mode": mode})
        setup = self._run("setup", scratch, _uv(PLUGIN / "scripts/checks/setup-changelog.py", "--plugin-root", str(PLUGIN),
                                                *(["--from", from_version] if from_version else [])))
        info = _json(setup.stdout)
        if setup.returncode != 0 and not info:  # the script refused its arguments: there is no setup output to read
            return gt.StepResult("prepare", setup.returncode, {"status": "stop", "reason": "setup_refused", "mode": mode})
        self.state.update(last_tag=info.get("last_tag"), branch=info.get("branch", ""), mode=mode)
        fields = {"mode": mode, "last_tag": info.get("last_tag"), "branch": info.get("branch"),
                  "commits_since_tag": info.get("commits_since_tag"),
                  "previous_tag_has_release": info.get("previous_tag_has_release")}
        if setup.returncode != 0 or not info.get("has_unreleased"):  # SKILL.md:103 "No unreleased changes"
            return gt.StepResult("prepare", setup.returncode, {"status": "stop", "reason": "no_unreleased_changes", **fields})
        # SKILL.md:115 passes --since "{last_tag}": with no tag the value is empty (finding D4)
        self._run("parse-commits", scratch, _uv(PLUGIN / "scripts/lib/git_utils.py", "parse-commits",
                                                "--since", info.get("last_tag") or "", "--format", "json"))
        chosen = version or info.get("suggested_version")
        # SKILL.md:142-150: autonomous and unattended accept the suggestion with no prompt, guided asks; the replay
        # records which of the two the plan reaches (the question itself is an operator decision, no command runs)
        autonomy = (_json((scratch.repo / "shipwright_run_config.json").read_text(encoding="utf-8"))
                    if (scratch.repo / "shipwright_run_config.json").is_file() else {}).get("autonomy")
        fields["version_question"] = ("auto-accepted" if autonomy in ("autonomous", "unattended") or mode == "pipeline"
                                      else "asked")  # first-actions.md:17-22: a driven run auto-accepts at every autonomy
        if context.get("requires_out_of_sequence_warning"):  # SKILL.md:63-66: warn and ask (a question, no command)
            fields["out_of_sequence"] = "asked"
        self.state["version"] = chosen
        return gt.StepResult("prepare", 0, {"status": "ok", "version": chosen, "suggested": info.get("suggested_version"),
                                            "version_reason": info.get("version_reason"), **fields})

    # ---- Step 4 ----------------------------------------------------------------------------
    def step_aggregate(self, scratch: Any, version: str, dry_run: bool = False, release_date: str | None = None,
                       fail_if_empty: bool = True, fallback_bullets: Sequence[tuple[str, str]] = ()) -> gt.StepResult:
        """The changelog section from the drops, then the decision drops. ``dry_run`` is the preview call only.
        ``fallback_bullets`` are written first by ``append_changelog_entry.py`` (SKILL.md:222-226: bullets that did
        not come through iterate F4, e.g. a cherry-pick)."""
        for category, entry in fallback_bullets:
            self._run("fallback-append", scratch, _uv(SHARED / "scripts/tools/append_changelog_entry.py", "--project-root",
                                                      str(scratch.repo), "--category", category, "--entry", entry))
        date = ["--release-date", release_date] if release_date else []
        tool = SHARED / "scripts/tools/aggregate_changelog.py"
        if dry_run:
            done = self._run("aggregate-dry", scratch, _uv(tool, "--project-root", str(scratch.repo), "--version", version,
                                                             *date, "--dry-run"))
            return self._aggregated("aggregate", done)
        flag = ["--fail-if-empty"] if fail_if_empty else []
        done = self._run("aggregate", scratch, _uv(tool, "--project-root", str(scratch.repo), "--version", version, *date, *flag))
        result = self._aggregated("aggregate", done)
        if done.returncode == 0:
            self._run("decisions", scratch, _uv(SHARED / "scripts/tools/aggregate_decisions.py", "--project-root", str(scratch.repo)))
        return result

    def _aggregated(self, step: str, done: subprocess.CompletedProcess) -> gt.StepResult:
        info = _json(done.stdout)
        if done.returncode == 0:
            self.state["section"] = info.get("section_written", "")
        return self._result(step, done, version=info.get("version"), section_action=info.get("section_action"),
                            changelog_updated=info.get("changelog_updated"),
                            legacy_bullets=info.get("legacy_unreleased_bullets"))

    # ---- Step 5 ----------------------------------------------------------------------------
    def step_preview(self, scratch: Any, choice: str = "accept") -> gt.StepResult:
        """Guided mode asks (SKILL.md:243-249); the replay records the operator's answer and runs nothing."""
        return gt.StepResult("preview", 0, {"status": choice})

    def step_fold_events(self, scratch: Any) -> gt.StepResult:
        done = self._run("fold-events", scratch, _uv(SHARED / "scripts/tools/fold_events_for_release.py",
                                                     "--project-root", str(scratch.repo)))
        info = _json(done.stdout)
        return gt.StepResult("fold-events", done.returncode, {"status": info.get("status", "failed")})

    def step_sync(self, scratch: Any, version: str) -> gt.StepResult:
        done = self._run("sync", scratch, _uv(SHARED / "scripts/tools/sync_release_manifests.py", "--project-root", ".",
                                              "--version", version, "--stage", "--result-file",
                                              ".shipwright/runtime/manifest_sync_result.json"))
        info = _json(done.stdout)
        self.state["manifests"] = info.get("manifest_pathspec", [])
        return gt.StepResult("sync", done.returncode, {"status": info.get("status", "failed"), "version": info.get("version"),
                                                       "pathspec": self.state["manifests"]})

    def step_evidence(self, scratch: Any, version: str) -> gt.StepResult:
        done = self._run("evidence", scratch, _uv(SHARED / "scripts/tools/refresh_compliance_docs.py", "--project-root",
                                                  str(scratch.repo), "--stage", "--release", f"v{version}"))
        info = _json(done.stdout)
        self.state["evidence"] = info.get("evidence_pathspec", [])
        return gt.StepResult("evidence", done.returncode, {"status": info.get("status", "failed"),
                                                           "pathspec": self.state["evidence"]})

    # ---- Step 6 ----------------------------------------------------------------------------
    def step_commit_and_tag(self, scratch: Any, version: str) -> gt.StepResult:
        script = fill(COMMIT_AND_TAG, version=version, shared=SHARED.as_posix(),
                      evidence=" ".join(self.state["evidence"]), manifests=" ".join(self.state["manifests"]))
        done = self._bash("commit-and-tag", scratch, script)
        return self._result("commit-and-tag", done, version=version)

    # ---- Step 7 ----------------------------------------------------------------------------
    def on_feature_branch(self, scratch: Any) -> bool:
        return scratch.git("rev-parse", "--abbrev-ref", "HEAD") not in MAIN_BRANCHES

    def step_open_pr(self, scratch: Any, version: str) -> gt.StepResult:
        # SKILL.md:332: inside bash double quotes the "\n" stays two characters (D15); {entry} is the aggregated section
        body = "## Changelog\\n\\n" + self.state["section"]
        done = self._gh("open-pr", scratch, "pr", "create", "--title", f"Release v{version}", "--body", body, "--base", "main")
        self.state["pr_url"] = done.stdout.strip() if done.returncode == 0 else ""
        return self._result("open-pr", done)

    def step_record_event(self, scratch: Any, version: str) -> gt.StepResult:
        if self.on_feature_branch(scratch):
            script, key = fill(EVENT_PR, version=version, shared=SHARED.as_posix(), pr_url=self.state["pr_url"]), "record-event-pr"
        else:
            script, key = fill(EVENT_MAIN, version=version, shared=SHARED.as_posix()), "record-event-main"
        return self._result("record-event", self._bash(key, scratch, script))

    def step_merge_pr(self, scratch: Any) -> gt.StepResult:
        """Autonomous and unattended only (SKILL.md:349-351)."""
        return self._result("merge-pr", self._gh("merge-pr", scratch, "pr", "merge", "--merge", "--delete-branch"))

    def step_push_tags(self, scratch: Any) -> gt.StepResult:
        return self._result("push-tags", self._run("push-tags", scratch, ["git", "push", "--tags", "origin", "main"]))

    def step_release_page(self, scratch: Any, version: str) -> gt.StepResult:
        done = self._run("release-page", scratch, _uv(SHARED / "scripts/tools/publish_release_notes.py", "--project-root",
                                                      str(scratch.repo), "--version", version))
        info = _json(done.stdout)
        return gt.StepResult("release-page", done.returncode, {"status": info.get("status", "failed"),
                                                              "reason": info.get("reason", "")})

    # ---- the phase-complete block ------------------------------------------------------------
    def step_close_phase(self, scratch: Any, version: str, session_id: str = "replay-session") -> gt.StepResult:
        """SKILL.md:380-414, one shell as the prose has it (``SHIPWRIGHT_RUN_ID`` is set in line 386, used in line 404)."""
        script = fill(CLOSE_PHASE, version=version, shared=SHARED.as_posix(), plugin=PLUGIN.as_posix(), session=session_id)
        done = self._bash("close-phase", scratch, script)
        return self._result("close-phase", done, version=version)
