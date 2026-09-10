"""Tests for the Stop hook that generates session_handoff.md.

The hook writes to ``.shipwright/agent_docs/runtime/`` (gitignored); the
tracked ``.shipwright/agent_docs/session_handoff.md`` is produced
exclusively by iterate-finalize. ``runtime_handoff_path`` targets live state.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Declared here too so the direct-import unit tests below don't depend on
# definition order with the subprocess-based ones.
_HOOK_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(_HOOK_SCRIPT_DIR))
import generate_handoff_on_stop as _ghs  # noqa: E402
from generate_handoff_on_stop import _phase_tasks_progress  # noqa: E402


class TestPhaseTasksProgress:
    """``_phase_tasks_progress`` is the phase-completion fallback detector's
    primary signal — NOT the write-once ``current_step``/``completed_steps``
    fields ``config_factory`` stamps once at run creation."""

    def test_no_phase_tasks_returns_none_and_empty(self):
        assert _phase_tasks_progress({}) == (None, set())

    def test_derives_current_and_completed_from_phase_tasks(self):
        run_config = {
            "pipeline": ["project", "design", "plan", "build", "test"],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "design", "status": "done"},
                {"phase": "build", "status": "in_progress"},
            ],
        }
        current, completed = _phase_tasks_progress(run_config)
        assert current == "build"
        assert completed == {"project", "design"}

    def test_a_split_phase_is_complete_only_once_every_split_is(self):
        run_config = {
            "phase_tasks": [
                {"phase": "build", "status": "done"},
                {"phase": "build", "status": "in_progress"},
            ],
        }
        current, completed = _phase_tasks_progress(run_config)
        assert current == "build"
        assert "build" not in completed

    def test_ignores_stale_current_step_and_completed_steps(self):
        """current_step/completed_steps claim something DIFFERENT from
        phase_tasks[] here; this helper must not read them at all."""
        run_config = {
            "current_step": "project",
            "completed_steps": [],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "test", "status": "in_progress"},
            ],
        }
        current, completed = _phase_tasks_progress(run_config)
        assert current == "test"
        assert completed == {"project"}

    def test_malformed_status_does_not_crash(self):
        """A non-string status (list/dict) must not raise — mirrors
        handoff_phase_status.status_of()'s unhashable-check guard. It reads
        as CURRENT (not confidently complete), never vanishing silently."""
        run_config = {"phase_tasks": [{"phase": "build", "status": ["done"]}]}
        current, completed = _phase_tasks_progress(run_config)
        assert current == "build"
        assert completed == set()

    def test_backlog_only_phase_counts_as_current(self):
        """A phase whose only phase_tasks[] entry is still queued
        (backlog/awaiting_launch — materialized but not yet claimed) counts
        as CURRENT, not merely 'no confident signal' (external plan review,
        sub-iterate s3: an ACTIVE-status-only version regressed a healthy
        mid-transition run to the write-once fields this campaign retires)."""
        run_config = {
            "pipeline": ["project", "build"],
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "build", "status": "backlog"},
            ],
        }
        current, completed = _phase_tasks_progress(run_config)
        assert current == "build"
        assert completed == {"project"}


class TestMainPhaseCompletionWiring:
    """``main()``'s ordering: a driven config's phase_tasks[]-derived current
    phase wins over a stale ``current_step``, and a standalone (no
    phase_tasks[]) config uses the one-time legacy cutover (s5). Calls
    ``main()`` in-process, stubbing ``_run_phase_completion`` — the real
    producer, which shells out to ``orchestrator.py update-step``."""

    @staticmethod
    def _call_main(tmp_project: Path, monkeypatch, run_config: dict) -> list[tuple]:
        (tmp_project / "shipwright_run_config.json").write_text(
            json.dumps(run_config), encoding="utf-8",
        )
        calls: list[tuple] = []
        monkeypatch.setattr(
            _ghs, "_run_phase_completion",
            lambda project_root, step: calls.append((project_root, step)),
        )
        monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_project))
        monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        assert _ghs.main() == 0
        return calls

    def test_driven_config_uses_phase_tasks_current_not_stale_current_step(
        self, tmp_project, monkeypatch,
    ):
        """A driven config whose stale current_step still claims 'project'
        must dispatch on the phase_tasks[]-derived current phase ('build')
        instead. The build config here has no sections yet, so
        _run_phase_completion must NOT be called — whereas the OLD
        current_step ('project') would have fired it, since
        shipwright_project_config.json reports status=complete."""
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps({"status": "complete"}), encoding="utf-8",
        )
        calls = self._call_main(tmp_project, monkeypatch, {
            "pipeline": ["project", "design", "plan", "build", "test"],
            "current_step": "project",
            "completed_steps": [],
            "status": "in_progress",
            "phase_tasks": [
                {"phase": "project", "status": "done"},
                {"phase": "design", "status": "done"},
                {"phase": "plan", "status": "done"},
                {"phase": "build", "status": "in_progress"},
            ],
        })
        assert calls == []

    def test_v1_only_config_uses_one_time_legacy_cutover_fallback(self, tmp_project, monkeypatch):
        """No phase_tasks[] at all: the ONE-TIME legacy cutover (external
        code review, GLM HIGH) reads current_step/completed_steps so this
        detector — the only thing that calls update-step for a standalone
        run — still fires and seeds phase_tasks[] once. Without it the run
        deadlocks forever: nothing else would ever trigger it."""
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps({"status": "complete"}), encoding="utf-8",
        )
        calls = self._call_main(tmp_project, monkeypatch, {
            "current_step": "project",
            "completed_steps": [],
            "status": "in_progress",
        })
        assert calls == [(tmp_project, "project")]

    def test_usable_phase_tasks_never_consults_legacy_fields(self, tmp_project, monkeypatch):
        """A USABLE phase_tasks[] must never fall back to current_step/
        completed_steps — even when it derives 'no current phase' (all
        present entries finished) and the legacy fields disagree in a way
        that WOULD fire if wrongly consulted. Only total absence of usable
        phase_tasks[] triggers the cutover above."""
        (tmp_project / "shipwright_project_config.json").write_text(
            json.dumps({"status": "complete"}), encoding="utf-8",
        )
        calls = self._call_main(tmp_project, monkeypatch, {
            "current_step": "project",
            "completed_steps": [],
            "status": "in_progress",
            "phase_tasks": [{"phase": "project", "status": "done"}],
        })
        assert calls == []

    def test_legacy_cutover_seeds_phase_tasks_for_every_completed_step(
        self, tmp_project, monkeypatch,
    ):
        """Doubt review, sub-iterate s5: the one-time legacy cutover used to
        seed phase_tasks[] for only the ONE phase about to be marked
        complete via update-step, permanently losing every OTHER phase
        recovered from completed_steps the instant the cutover self-disabled
        (phase_tasks[] gaining usable entries). With multiple prior phases
        in completed_steps, all of them must land as 'done' phase_tasks[]
        entries alongside the update-step call for the current phase (which
        also gets its own 'in_progress' seed -- see the orphaning test
        below for why)."""
        (tmp_project / "shipwright_test_results.json").write_text(
            json.dumps({"status": "pass"}), encoding="utf-8",
        )
        calls = self._call_main(tmp_project, monkeypatch, {
            "current_step": "test",
            "completed_steps": ["project", "design", "plan"],
            "status": "in_progress",
        })
        assert calls == [(tmp_project, "test")]

        written = json.loads(
            (tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"),
        )
        seeded = {
            t["phase"]: t["status"]
            for t in written["phase_tasks"]
            if t.get("splitId") is None
        }
        # "test" is also seeded, as 'in_progress' — its own update-step call
        # (stubbed above) would upgrade it to 'done' in a real run; a stub
        # that never touches the file leaves the seed as-is, which is
        # exactly what the orphaning test below exercises deliberately.
        assert seeded == {
            "project": "done", "design": "done", "plan": "done", "test": "in_progress",
        }

    def test_legacy_cutover_seeds_current_phase_to_avoid_orphaning_it(
        self, tmp_project, monkeypatch,
    ):
        """Doubt review round 2: seeding ONLY the historical phases could
        flip phase_tasks_has_usable_entries() True before current_phase
        itself had a phase_tasks[] entry — self-disabling the cutover (it
        never fires twice) and permanently orphaning whatever phase was
        actually in flight at cutover time, the identical deadlock class
        this whole cutover exists to prevent. First Stop event: 'test'
        genuinely isn't done yet — update-step must not fire, but 'test'
        must still land as an 'in_progress' phase_tasks[] entry so a LATER
        Stop event resolves it as current via the ordinary phase_tasks[]
        path (the cutover itself is now permanently disabled)."""
        (tmp_project / "shipwright_run_config.json").write_text(
            json.dumps({
                "current_step": "test",
                "completed_steps": ["project", "design", "plan", "build"],
                "status": "in_progress",
            }),
            encoding="utf-8",
        )
        calls: list[tuple] = []
        monkeypatch.setattr(
            _ghs, "_run_phase_completion",
            lambda project_root, step: calls.append((project_root, step)),
        )
        monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_project))
        monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)

        # Distinct session ids per call: claim_once_for_event dedups
        # same-session Stop-hook fan-out within a 30s TTL, which would
        # otherwise skip the second call's phase-completion fallback
        # entirely — these are meant to model two SEPARATE Stop events.
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        assert _ghs.main() == 0
        assert calls == []

        written = json.loads(
            (tmp_project / "shipwright_run_config.json").read_text(encoding="utf-8"),
        )
        seeded = {
            t["phase"]: t["status"]
            for t in written["phase_tasks"]
            if t.get("splitId") is None
        }
        assert seeded == {
            "project": "done", "design": "done", "plan": "done",
            "build": "done", "test": "in_progress",
        }

        # Second Stop event, later: 'test' has now genuinely finished. The
        # cutover is self-disabled (phase_tasks[] is now usable) — the
        # ordinary phase_tasks[]-derived path must pick 'test' up as
        # current on its own, from the in_progress entry seeded above.
        (tmp_project / "shipwright_test_results.json").write_text(
            json.dumps({"status": "pass"}), encoding="utf-8",
        )
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-2")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        assert _ghs.main() == 0
        assert calls == [(tmp_project, "test")]


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runtime_handoff_path(project_root: Path) -> Path:
    """Helper: the Stop-hook write target after iterate-2026-05-27."""
    return project_root / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md"


def tracked_handoff_path(project_root: Path) -> Path:
    """Helper: the iterate-finalize-only write target."""
    return project_root / ".shipwright" / "agent_docs" / "session_handoff.md"


# The hook script path
HOOK_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "generate_handoff_on_stop.py"


def run_hook(cwd: Path, env_extra: dict | None = None, stdin_data: str = "{}") -> subprocess.CompletedProcess:
    """Run the hook as a subprocess, mimicking Claude Code invocation."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


def test_exits_zero_when_not_shipwright_project(tmp_path):
    """Hook silently exits 0 when no config or agent_docs exist."""
    result = run_hook(tmp_path)
    assert result.returncode == 0
    # No output expected — guard clause skips generation. Post ADR-042
    # the hook does not emit hookSpecificOutput on stdout for any path.
    assert "hookSpecificOutput" not in result.stdout


def test_generates_handoff_with_run_config(tmp_project):
    """Hook writes runtime/session_handoff.md, NOT the tracked path
    (iterate-finalize is the sole producer of the tracked variant)."""
    config = {"scope": "full_app", "profile": "test"}
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={"SHIPWRIGHT_SESSION_ID": "test-session-42"},
    )

    assert result.returncode == 0
    handoff = runtime_handoff_path(tmp_project)
    assert handoff.exists(), (
        f"expected runtime handoff at {handoff}; "
        f"stderr={result.stderr!r}"
    )
    # Tracked path stays absent — only finalize writes it.
    assert not tracked_handoff_path(tmp_project).exists(), (
        "Stop hook wrote tracked session_handoff.md — single-producer "
        "violation. iterate-2026-05-27 regression."
    )
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "test-session-42" in content
    assert "session end" in content


def test_generates_handoff_with_only_agent_docs(tmp_project):
    """Hook generates runtime handoff when only agent_docs/ exists (early phase)."""
    result = run_hook(tmp_project)

    assert result.returncode == 0
    handoff = runtime_handoff_path(tmp_project)
    assert handoff.exists(), (
        f"expected runtime handoff; stderr={result.stderr!r}"
    )
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "not_started" in content


def test_stop_hook_does_not_emit_invalid_stdout_json(tmp_project):
    """Post-ADR-042: Stop hooks must not emit hookSpecificOutput on stdout —
    `additionalContext` (formerly used here) is schema-invalid and triggers
    a JSON validation failure at every session end. Moved to stderr."""
    result = run_hook(tmp_project)

    assert result.returncode == 0
    assert "hookSpecificOutput" not in result.stdout, (
        f"Stop schema violation: stdout = {result.stdout!r}"
    )
    # Stderr carries the relocation diagnostic.
    assert "[shipwright:handoff]" in result.stderr
    assert "session_handoff.md" in result.stderr or "generated" in result.stderr


def test_hook_does_not_touch_compliance_dir(tmp_project):
    """iterate-2026-05-23: Stop hook must NEVER write under .shipwright/compliance/.

    Single-producer invariant: only iterate-finalize writes the tracked
    compliance MDs. The previous mtime-guarded auto-regen block (lines
    283-310 of generate_handoff_on_stop.py) is removed in this iterate
    because it caused dirty-tree noise on out-of-band commits.
    """
    # Seed the same 5 compliance MDs the production audit registers.
    compliance = tmp_project / ".shipwright" / "compliance"
    compliance.mkdir(parents=True, exist_ok=True)
    seeded = {
        "traceability-matrix.md": "# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nRTM body\n",
        "test-evidence.md":       "# Test Evidence\n\nGenerated: 2026-05-23T00:00:00Z\n\nTE body\n",
        "change-history.md":      "# Change Log\n\nGenerated: 2026-05-23T00:00:00Z\n\nCH body\n",
        "sbom.md":                "# SBOM\n\nGenerated: 2026-05-23T00:00:00Z\n\nSBOM body\n",
        "dashboard.md":           "# Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nDash body\n",
    }
    for name, content in seeded.items():
        (compliance / name).write_text(content, encoding="utf-8")

    # Run config exists — this is the case the old auto-regen would fire on.
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"current_step": "iterate"}), encoding="utf-8",
    )

    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes())
              for p in compliance.iterdir() if p.is_file()}

    # Run the hook.
    result = run_hook(
        tmp_project,
        env_extra={"SHIPWRIGHT_SESSION_ID": "iterate-md-single-producer-test"},
    )
    assert result.returncode == 0

    after = {p.name: (p.stat().st_mtime_ns, p.read_bytes())
             for p in compliance.iterdir() if p.is_file()}

    # NOTHING under .shipwright/compliance/ was touched.
    assert set(after.keys()) == set(before.keys())
    for name in before:
        assert before[name][1] == after[name][1], (
            f"Stop hook modified content of .shipwright/compliance/{name}"
        )


def test_idempotent(tmp_project):
    """Running the hook twice produces valid results both times."""
    result1 = run_hook(tmp_project)
    assert result1.returncode == 0

    result2 = run_hook(tmp_project)
    assert result2.returncode == 0

    handoff = runtime_handoff_path(tmp_project)
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content


def test_default_session_id_when_env_not_set(tmp_project):
    """Hook uses 'unknown' when SHIPWRIGHT_SESSION_ID is not set."""
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)

    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env=env,
    )

    assert result.returncode == 0
    handoff = runtime_handoff_path(tmp_project)
    assert handoff.exists()
    assert "unknown" in handoff.read_text(encoding="utf-8")


def test_handles_malformed_stdin(tmp_project):
    """Hook handles malformed stdin gracefully."""
    result = run_hook(tmp_project, stdin_data="not valid json{{{")
    assert result.returncode == 0


def test_canon_marker_same_run_id_skips_regeneration(tmp_project):
    """Iterate 12.1: Stop hook must NOT overwrite a handoff whose canon
    frontmatter matches the current SHIPWRIGHT_RUN_ID."""
    # Seed a pre-existing handoff that was written by a phase's C3 step.
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    handoff = agent_docs / "session_handoff.md"
    canon_body = (
        "---\n"
        "canon_generated: true\n"
        'run_id: "project-20260414-alpha"\n'
        'phase: "project"\n'
        'reason: "project scaffolding complete"\n'
        'timestamp: "2026-04-14T10:00:00Z"\n'
        "---\n"
        "\n# Session Handoff\n\nOriginal canon content.\n"
    )
    handoff.write_text(canon_body, encoding="utf-8")

    # Make this a shipwright project so the hook doesn't hit the guard clause.
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={
            "SHIPWRIGHT_RUN_ID": "project-20260414-alpha",
            "SHIPWRIGHT_SESSION_ID": "test-session",
        },
    )
    assert result.returncode == 0
    # Body must still contain the original canon content — not regenerated.
    assert handoff.read_text(encoding="utf-8") == canon_body
    # Skip diagnostic surfaced on stderr (Post-ADR-042; never on stdout).
    assert "hookSpecificOutput" not in result.stdout
    assert "skipped" in result.stderr.lower()


def test_canon_marker_different_run_id_regenerates(tmp_project):
    """A stale canon frontmatter from a prior run must not prevent
    regeneration when the current run_id differs.

    Post-iterate-2026-05-27: the canon-marker check still inspects the
    TRACKED path (the marker's whole point is to know finalize touched
    that file), but the regenerated content goes to runtime/. The tracked
    file is left alone — iterate-finalize is the sole writer.
    """
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    tracked = tracked_handoff_path(tmp_project)
    tracked.write_text(
        "---\n"
        "canon_generated: true\n"
        'run_id: "project-20260414-old"\n'
        'phase: "project"\n'
        'reason: "stale"\n'
        'timestamp: "2026-04-14T08:00:00Z"\n'
        "---\n"
        "\n# Session Handoff\n\nStale content.\n",
        encoding="utf-8",
    )
    tracked_pre = tracked.read_text(encoding="utf-8")
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={
            "SHIPWRIGHT_RUN_ID": "project-20260414-new",
            "SHIPWRIGHT_SESSION_ID": "test",
        },
    )
    assert result.returncode == 0
    # Tracked path was NOT touched — single-producer.
    assert tracked.read_text(encoding="utf-8") == tracked_pre, (
        "Stop hook modified tracked session_handoff.md; only iterate-"
        "finalize may write the tracked variant."
    )
    # Runtime got the regenerated content.
    runtime = runtime_handoff_path(tmp_project)
    assert runtime.exists(), (
        f"expected runtime regeneration; stderr={result.stderr!r}"
    )
    content = runtime.read_text(encoding="utf-8")
    assert "stale" not in content
    assert "session end" in content


def test_canon_marker_missing_run_id_env_regenerates(tmp_project):
    """When the frontmatter is present but SHIPWRIGHT_RUN_ID is unset,
    the hook must fall through to normal regeneration (safe default).

    Post-iterate-2026-05-27: regenerated content goes to runtime/; tracked
    stays.
    """
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    tracked = tracked_handoff_path(tmp_project)
    tracked.write_text(
        "---\n"
        "canon_generated: true\n"
        'run_id: "project-20260414-alpha"\n'
        'phase: "project"\n'
        'reason: "whatever"\n'
        'timestamp: "2026-04-14T10:00:00Z"\n'
        "---\n"
        "\n# Session Handoff\n\nOld.\n",
        encoding="utf-8",
    )
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )

    env = os.environ.copy()
    env.pop("SHIPWRIGHT_RUN_ID", None)
    env["SHIPWRIGHT_SESSION_ID"] = "test"

    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="{}",
        capture_output=True,
        text=True,
        cwd=tmp_project,
        env=env,
    )
    assert result.returncode == 0
    # Tracked path retains "Old." — single-producer.
    assert "Old." in tracked.read_text(encoding="utf-8")
    # Runtime got the regenerated content.
    runtime = runtime_handoff_path(tmp_project)
    assert runtime.exists()
    content = runtime.read_text(encoding="utf-8")
    assert "Old." not in content
    assert "# Session Handoff" in content


def test_non_canon_handoff_always_regenerates(tmp_project):
    """Plain handoff without frontmatter: regenerate every time, same
    as pre-12.1 behaviour. Regression guard.

    Post-iterate-2026-05-27: regenerated content goes to runtime/; tracked
    plain handoff (no canon marker) stays as seeded.
    """
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    tracked = tracked_handoff_path(tmp_project)
    tracked.write_text(
        "# Session Handoff\n\nOld manual content.\n",
        encoding="utf-8",
    )
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app"}), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={
            "SHIPWRIGHT_RUN_ID": "anything",
            "SHIPWRIGHT_SESSION_ID": "test",
        },
    )
    assert result.returncode == 0
    # Tracked plain content stays (single-producer).
    assert "Old manual content" in tracked.read_text(encoding="utf-8")
    # Runtime got the regenerated content.
    runtime = runtime_handoff_path(tmp_project)
    assert runtime.exists()
    content = runtime.read_text(encoding="utf-8")
    assert "Old manual content" not in content
    assert "session end" in content


def test_with_full_config_set(project_with_configs):
    """Hook generates comprehensive handoff with all configs present."""
    result = run_hook(
        project_with_configs,
        env_extra={"SHIPWRIGHT_SESSION_ID": "full-session"},
    )

    assert result.returncode == 0
    handoff = runtime_handoff_path(project_with_configs)
    content = handoff.read_text(encoding="utf-8")
    assert "full-session" in content
    assert "build" in content  # Phase should be detected as build
    assert "shipwright_run_config.json" in content
