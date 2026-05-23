"""Tests for the Stop hook that generates session_handoff.md."""

import json
import os
import subprocess
import sys
from pathlib import Path


def _agent_docs_root(tmp: Path) -> Path:
    """Return canonical agent_docs subdir under tmp, creating parents."""
    p = tmp / ".shipwright" / "agent_docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


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
    """Hook generates session_handoff.md when shipwright_run_config.json exists."""
    config = {"scope": "full_app", "profile": "test"}
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )

    result = run_hook(
        tmp_project,
        env_extra={"SHIPWRIGHT_SESSION_ID": "test-session-42"},
    )

    assert result.returncode == 0
    handoff = tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "test-session-42" in content
    assert "session end" in content


def test_generates_handoff_with_only_agent_docs(tmp_project):
    """Hook generates handoff when only agent_docs/ exists (early phase)."""
    result = run_hook(tmp_project)

    assert result.returncode == 0
    handoff = tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md"
    assert handoff.exists()
    content = handoff.read_text(encoding="utf-8")
    assert "# Session Handoff" in content
    assert "not_started" in content


def test_stop_hook_does_not_emit_invalid_stdout_json(tmp_project):
    """Post-ADR-042: Stop hooks must not emit hookSpecificOutput on stdout.

    Claude Code's Stop event schema only permits `hookEventName` inside
    `hookSpecificOutput`; `additionalContext` (formerly used here) is
    schema-invalid and triggers
    "Hook JSON output validation failed — (root): Invalid input" at every
    session end. Diagnostic moved to stderr.
    """
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

    handoff = tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md"
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
    handoff = tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md"
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
    regeneration when the current run_id differs."""
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    handoff = agent_docs / "session_handoff.md"
    handoff.write_text(
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
    content = handoff.read_text(encoding="utf-8")
    # The regenerated handoff has the "session end" reason; the old
    # "stale" reason is gone.
    assert "stale" not in content
    assert "session end" in content


def test_canon_marker_missing_run_id_env_regenerates(tmp_project):
    """When the frontmatter is present but SHIPWRIGHT_RUN_ID is unset,
    the hook must fall through to normal regeneration (safe default)."""
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    (agent_docs / "session_handoff.md").write_text(
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
    content = (tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(encoding="utf-8")
    # Should be regenerated — old content gone.
    assert "Old." not in content
    assert "# Session Handoff" in content


def test_non_canon_handoff_always_regenerates(tmp_project):
    """Plain handoff without frontmatter: regenerate every time, same
    as pre-12.1 behaviour. Regression guard."""
    agent_docs = tmp_project / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    (agent_docs / "session_handoff.md").write_text(
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
    content = (tmp_project / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(encoding="utf-8")
    assert "Old manual content" not in content
    assert "session end" in content


def test_with_full_config_set(project_with_configs):
    """Hook generates comprehensive handoff with all configs present."""
    result = run_hook(
        project_with_configs,
        env_extra={"SHIPWRIGHT_SESSION_ID": "full-session"},
    )

    assert result.returncode == 0
    handoff = project_with_configs / ".shipwright" / "agent_docs" / "session_handoff.md"
    content = handoff.read_text(encoding="utf-8")
    assert "full-session" in content
    assert "build" in content  # Phase should be detected as build
    assert "shipwright_run_config.json" in content
