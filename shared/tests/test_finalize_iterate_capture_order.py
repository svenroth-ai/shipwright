"""``finalize_iterate`` captures dirtiness BEFORE Step 1 writes (``trg-f5ae5371``).

The reproduced chain: `finalize()` appends ``work_completed`` to the TRACKED
``shipwright_events.jsonl``, then spawns the compliance regen, which rewrites six
more tracked documents and only then emits the ``grade_snapshot``. Anything asking
git at that point reads ``dirty=true`` on a pristine tree.

The compliance end of this is proven end-to-end in
``plugins/shipwright-compliance/tests/test_grade_snapshot_dirty.py``. What is pinned
HERE is the half that lives in this module and that no compliance test can see: that
the capture happens **before** Step 1, and that the run id which makes the captured
value readable is actually forwarded to the subprocess. Both are ordering claims, so
both are tested by observing order rather than by inspecting the source.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from source_state_capture import ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN  # noqa: E402
from tools import finalize_iterate  # noqa: E402

RUN = "iterate-2026-08-01-grade-snapshot-dirty-capture"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """The capture reads real ``os.environ``; a developer's own export must not
    decide whether these pass."""
    for name in (ENV_DIRTY, ENV_DIRTY_ROOT, ENV_DIRTY_RUN, "SHIPWRIGHT_RUN_ID"):
        monkeypatch.setenv(name, "sentinel")
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A pristine repo whose event log is TRACKED, so Step 1's append is real dirt."""
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True, text=True, timeout=30)

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True,
                   capture_output=True, text=True, timeout=30)
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "fixture")
    git("config", "commit.gpgsign", "false")
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('committed')\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "pristine")
    return tmp_path


def test_capture_happens_before_step_1_writes(repo: Path, monkeypatch):
    """The ordering claim, observed rather than asserted about the source.

    ``_record_event`` is the FIRST writer in ``finalize()``. If the capture had not
    already run by the time it is called, the environment would still be empty here
    — and the later regen would measure a tree this very call is about to dirty.
    """
    observed: dict = {}

    def spy_record_event(project_root, commit, run_id, description,
                         event_extras=None):
        import os
        observed["dirty"] = os.environ.get(ENV_DIRTY)
        observed["run"] = os.environ.get(ENV_DIRTY_RUN)
        return "evt-test0001"

    monkeypatch.setattr(finalize_iterate, "_record_event", spy_record_event)
    monkeypatch.setattr(finalize_iterate, "_update_compliance",
                        lambda pr, run_id=None: [])
    monkeypatch.setattr(finalize_iterate, "_update_dashboard",
                        lambda pr, sid, rid: None)
    monkeypatch.setattr(finalize_iterate, "_generate_handoff",
                        lambda pr, sid, rid, reason: None)

    finalize_iterate.run(repo, run_id=RUN)

    assert observed["run"] == RUN, "the capture had not run before Step 1 wrote"
    assert observed["dirty"] == "0", (
        f"captured {observed['dirty']!r} on a pristine tree — expected clean")


def test_the_run_id_is_forwarded_to_the_compliance_subprocess(repo: Path, monkeypatch):
    """Without this the child cannot read the parent's capture: the value is
    honoured only when the run ids match, so an unforwarded id silently reverts the
    regen to measuring a tree Step 1 already dirtied."""
    seen: dict = {}

    def spy_update_compliance(project_root, run_id=None):
        seen["run_id"] = run_id
        return []

    monkeypatch.setattr(finalize_iterate, "_record_event",
                        lambda *a, **k: "evt-test0001")
    monkeypatch.setattr(finalize_iterate, "_update_compliance", spy_update_compliance)
    monkeypatch.setattr(finalize_iterate, "_update_dashboard",
                        lambda pr, sid, rid: None)
    monkeypatch.setattr(finalize_iterate, "_generate_handoff",
                        lambda pr, sid, rid, reason: None)

    finalize_iterate.run(repo, run_id=RUN)

    assert seen.get("run_id") == RUN


def test_the_subprocess_argv_actually_carries_run_id(repo: Path, monkeypatch):
    """One level deeper than the call above: the flag reaches the real argv, not
    just the Python signature."""
    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(finalize_iterate.subprocess, "run", fake_run)
    finalize_iterate._update_compliance(repo, RUN)

    cmd = captured.get("cmd") or []
    assert "--run-id" in cmd, f"run id never reached argv: {cmd}"
    assert cmd[cmd.index("--run-id") + 1] == RUN


def test_no_run_id_means_no_flag(repo: Path, monkeypatch):
    """With no run id the flag is omitted rather than passed empty.

    An empty ``--run-id`` would be pure noise: ``safe_run_id`` refuses a blank token
    anyway, so it could never bind a capture — it would only make the argv lie about
    carrying an identity.
    """
    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(finalize_iterate.subprocess, "run", fake_run)
    finalize_iterate._update_compliance(repo, None)

    assert "--run-id" not in (captured.get("cmd") or [])


def test_update_compliance_runs_in_the_compliance_plugins_own_environment(
    repo: Path, monkeypatch,
):
    """``update_compliance.py`` needs ``jsonschema``/``pyyaml``, declared ONLY in
    ``plugins/shipwright-compliance/pyproject.toml``. Launching it with
    ``sys.executable`` runs it under WHICHEVER interpreter is executing
    ``finalize_iterate.py`` — typically another plugin's own ``uv``-managed venv,
    which carries no such dependency — and fails with
    ``ModuleNotFoundError: No module named 'jsonschema'`` (reproduced live on
    macOS, trg-jsonschema-interpreter-mismatch). The call must instead route
    through the compliance plugin's OWN environment, mirroring the pattern
    already used for the same class of problem in
    ``shared/scripts/tools/ci_manifest_drift_check.py`` and
    ``plugins/shipwright-adopt/tests/test_seed_traceability_baseline.py``:
    ``["uv", "run", "--project", <compliance_plugin_dir>, "python", <script>, ...]``.
    """
    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(finalize_iterate.subprocess, "run", fake_run)
    finalize_iterate._update_compliance(repo, RUN)

    cmd = captured.get("cmd") or []
    assert cmd[:2] == ["uv", "run"], (
        f"must launch via `uv run`, not the caller's bare interpreter: {cmd}")
    assert "--project" in cmd, f"must pin the compliance plugin's own venv: {cmd}"
    plugin_dir = Path(cmd[cmd.index("--project") + 1])
    assert plugin_dir.name == "shipwright-compliance", (
        f"--project must point at the compliance plugin, not the caller's own "
        f"plugin: {plugin_dir}")
    assert sys.executable not in cmd, (
        f"the caller's own interpreter must not appear in the argv: {cmd}")
