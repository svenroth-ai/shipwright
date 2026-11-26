"""The replay driver: the command sequence today's ``SKILL.md`` prescribes, one step at a time (programme P7).

It implements the per-step driver interface of ``golden_trace`` for the steps of Step C through Step 7
that the first half of the scenarios (S1-S9) need. Every command it runs cites its ``SKILL.md`` line
(``replay_commands.CITES``); ``ReplayDriver.log`` records each command with its key, so a test can check
the citations against the live prose. It is FROZEN with the traces at the operator's stop 2.

Order follows the prose; where a later unit fixed the prose (P8a: D7, D12, D24; P8b: D15, F9, Q5, Q7) the replay follows
the fixed prose. A command that exits non-zero is a result, never an exception: the scenario records it.

``gh`` is run through the seam prefix of the scratch environment (a bare ``gh`` on Windows would bypass the
shim). The shell chains run under ``bash`` (Git Bash on Windows), as the model would run them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import golden_trace as gt

from .replay_commands import CITES, COMMIT_AND_TAG, EVENT_MAIN, EVENT_PR, PLUGIN, SHARED, fill

STEPS = frozenset({"prepare", "aggregate", "preview", "fold-events", "sync", "evidence", "commit-and-tag",
                   "push-branch", "open-pr", "record-event", "merge-pr", "push-tags", "release-page", "close-phase"})
DEVELOP = "develop"  # SKILL.md:327 "Only if on a feature branch (not main/develop)"; P8a F5 adds the remote's default branch to both


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
        if setup.returncode != 0 and not info:  # Q7: `--from` is no longer offered, so it is an unknown argument (as the CLI's own parser)
            return gt.StepResult("prepare", setup.returncode, {"status": "failed", "reason": f"exit_{setup.returncode}"})
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
        drops = scratch.repo / "CHANGELOG-unreleased.d"  # what a Cancel puts back (see step_preview)
        self.state["drops_before"] = {p: p.read_bytes() for p in drops.rglob("*") if p.is_file()} if drops.is_dir() else {}
        return gt.StepResult("prepare", 0, {"status": "ok", "version": chosen, "suggested": info.get("suggested_version"),
                                            "version_reason": info.get("version_reason"), **fields})

    # ---- Step 4 ----------------------------------------------------------------------------
    def step_aggregate(self, scratch: Any, version: str, dry_run: bool = False, release_date: str | None = None,
                       fail_if_empty: bool = True, fallback_bullets: Sequence[tuple[str, str]] = ()) -> gt.StepResult:
        """The changelog section from the drops, then the decision drops. ``dry_run`` is the preview call only.
        ``fallback_bullets`` (bullets that did not come through iterate F4, e.g. a cherry-pick) are written first as drop files
        (F9: the legacy ``[Unreleased]`` bullet of ``append_changelog_entry.py`` missed its release). Hand-written ``[Unreleased]``
        entries move into the release (Q5: ``--move-unreleased``, as ``release.py aggregate`` passes it)."""
        for category, entry in fallback_bullets:
            self._run("fallback-append", scratch, _uv(SHARED / "scripts/tools/write_changelog_drop.py", "--project-root", str(scratch.repo),
                                                      "--run-id", "release-fallback", "--category", category, "--bullet", entry))
        date = ["--release-date", release_date, "--move-unreleased"] if release_date else ["--move-unreleased"]
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
        """Guided mode asks (SKILL.md:243-249); the replay records the operator's answer and runs nothing. On Cancel it does what
        the P8a prose asked of the model by hand: put back a drop file an Edit changed, from the bytes it saw at ``prepare``. The CLI
        driver runs ``release.py cancel`` for it (D84), and the two traces must agree."""
        if choice == "cancel":
            for path, data in self.state.get("drops_before", {}).items():
                if not path.is_file() or path.read_bytes() != data:
                    path.write_bytes(data)
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
    def trunk(self, scratch: Any) -> str:
        """F5 (operator 2026-11-25, P8a; D24): the default branch is asked of the remote by name (``prepare`` returns it as ``trunk``),
        else the local ``origin/HEAD``, else ``main``. Asked once per run, as ``release_event.trunk`` asks it: a question, not a logged step.
        (A scratch's fetch URL is a fake host its environment refuses, so there the answer is the local ``origin/HEAD`` or the fallback.)
        Deliberately without the code's branch-name check and no-prompt env: a scratch names only plain branches and never prompts."""
        if "trunk" not in self.state:
            head = scratch.run(["git", "-c", "credential.interactive=never", "ls-remote", "--symref", "origin", "HEAD"])
            words = ((head.stdout.splitlines() or [""])[0] if head.returncode == 0 else "").split()
            found, source = (words[1].removeprefix("refs/heads/"), "remote") if len(words) > 1 and words[0] == "ref:" else ("", "")
            if not found:
                local = scratch.run(["git", "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"])
                found, source = (local.stdout.strip().removeprefix("origin/"), "local") if local.returncode == 0 else ("main", "fallback")
            self.state.update(trunk=found or "main", trunk_source=source if found else "fallback")
        return self.state["trunk"]

    def trunks(self, scratch: Any) -> tuple[str, ...]:
        """P8a fix round (D85): additive. The default branch, then ``main`` and ``develop`` always (the prose's "not main/develop"),
        and ``master`` when the default branch could not be asked."""
        base = self.trunk(scratch)
        extra = ("master",) if self.state["trunk_source"] == "fallback" else ()
        return tuple(dict.fromkeys((base, "main", DEVELOP, *extra)))

    def on_feature_branch(self, scratch: Any) -> bool:
        return scratch.git("rev-parse", "--abbrev-ref", "HEAD") not in self.trunks(scratch)

    def step_push_branch(self, scratch: Any) -> gt.StepResult:
        """F3 (operator 2026-11-25, P8a; D7): the head goes to the remote right before ``gh pr create``, which opens a PR only
        for a branch the host has (the stop-2 prose opened the PR first and the host refused it, S14a)."""
        return self._result("push-branch", self._run("push-branch", scratch, ["git", "push", "origin", "HEAD", "--no-follow-tags"]))

    def step_open_pr(self, scratch: Any, version: str) -> gt.StepResult:
        # Q10 (D15): the body comes from a file, so its newlines are real; {entry} is this version's section (the text stays the prose's)
        body = scratch.repo / ".git" / "replay_pr_body.md"
        body.write_text("## Changelog\n\n" + self.state["section"].strip("\n") + "\n", encoding="utf-8", newline="\n")
        return self._open_pr(scratch, version, body)

    def _open_pr(self, scratch: Any, version: str, body: Path) -> gt.StepResult:
        done = self._gh("open-pr", scratch, "pr", "create", "--title", f"Release v{version}", "--body-file", str(body), "--base", self.trunk(scratch))  # F5: the remote's default branch
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

    def step_push_tags(self, scratch: Any, version: str | None = None) -> gt.StepResult:
        """F1a (operator 2026-11-23): from a feature branch only the tag goes out, never a local trunk; on the trunk
        the trunk and exactly this tag go out in one push (``--tags`` would also push the orphan tags of refused releases)."""
        if self.on_feature_branch(scratch):
            argv = ["git", "push", "origin", f"refs/tags/v{version or self.state['version']}"]
        else:
            argv = ["git", "push", "origin", scratch.git("rev-parse", "--abbrev-ref", "HEAD"), f"refs/tags/v{version or self.state['version']}"]  # F5: the trunk the release is on
        return self._result("push-tags", self._run("push-tags", scratch, argv))

    def step_release_page(self, scratch: Any, version: str) -> gt.StepResult:
        done = self._run("release-page", scratch, _uv(SHARED / "scripts/tools/publish_release_notes.py", "--project-root",
                                                      str(scratch.repo), "--version", version))
        info = _json(done.stdout)
        return gt.StepResult("release-page", done.returncode, {"status": info.get("status", "failed"),
                                                              "reason": info.get("reason", "")})

    # ---- the phase-complete block ------------------------------------------------------------
    def step_close_phase(self, scratch: Any, version: str, session_id: str = "replay-session") -> gt.StepResult:
        """F10 (operator 2026-11-23): nothing the release writes is committed and the tree is clean afterwards. A dispatched
        (pipeline) run keeps the three canon records its gate reads (dashboard, handover with the canon marker, ``phase_history``);
        a hand-invoked one writes none and puts the derived snapshots back to ``HEAD``. ``update-step`` is gone (F7: the check
        runs in Step 6). The frozen prose copy ``CLOSE_PHASE`` stays as the pin of what the prose said."""
        tools, done = SHARED / "scripts/tools", None
        if self.state.get("mode") == "pipeline":
            run_id = scratch.env.get("SHIPWRIGHT_RUN_ID") or f"changelog-v{version}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
            for argv in (_uv(tools / "update_build_dashboard.py", "--project-root", str(scratch.repo), "--phase", "changelog", "--session-id", session_id),
                         _uv(tools / "generate_session_handoff.py", "--project-root", str(scratch.repo), "--canon-marker", "--phase", "changelog",
                             "--reason", f"release v{version}"),
                         _uv(tools / "append_phase_history.py", "--project-root", str(scratch.repo), "--phase", "changelog", "--run-id", run_id,
                             "--entry-json", json.dumps({"version": f"v{version}", "outcome": "tagged"}, separators=(",", ":")))):
                done = self._run("close-phase", scratch, argv)
                if done.returncode != 0:
                    break
        else:
            done = self._run("close-phase", scratch, _uv(PLUGIN / "scripts/checks/restore_derived.py", "--shared-root", str(SHARED),
                                                         "--project-root", str(scratch.repo)))
        return self._result("close-phase", done, version=version)
