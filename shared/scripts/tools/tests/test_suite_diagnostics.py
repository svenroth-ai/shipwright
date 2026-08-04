"""Run-scoped F0 diagnostic evidence is bounded, redacted, and atomic."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_diagnostics import write_attempt_evidence


def test_failure_evidence_round_trips_redacted_and_untrusted(tmp_path):
    secret = "sk-" + "a" * 24
    rel = write_attempt_evidence(
        tmp_path, run_id=f"run/{secret}/../München",
        unit_id=f"shared/{secret}\nnext", phase=f"initial-{secret}",
        rc=1, seconds=1.25,
        tail=f"prefix {secret} suffix", truncated=True, pytest_ran=True,
    )
    assert rel.as_posix().startswith(".shipwright/runs/")
    path = tmp_path / rel
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["untrusted"] is True and payload["truncated"] is True
    assert secret not in json.dumps(payload)
    assert "[REDACTED]" in payload["tail"]
    assert "[REDACTED]" in payload["run_id"]
    assert "[REDACTED]" in payload["unit_id"]
    assert "[REDACTED]" in payload["phase"]
    assert ".." not in rel.parts and not list(path.parent.glob("*.tmp"))
    assert len(str(rel)) <= 112


def test_attempt_evidence_has_deterministic_byte_cap(tmp_path):
    terminal = "terminal-failure-message"
    rel = write_attempt_evidence(
        tmp_path, run_id="r", unit_id="u", phase="retry", rc=2,
        seconds=.1, tail="é" * 100_000 + terminal,
        truncated=False, pytest_ran=False,
        max_tail_bytes=127,
    )
    payload = json.loads((tmp_path / rel).read_text(encoding="utf-8"))
    assert len(payload["tail"].encode("utf-8")) <= 127
    assert payload["truncated"] is True
    assert payload["tail"].endswith(terminal)


def test_same_run_unit_and_phase_never_overwrite_prior_evidence(tmp_path):
    kwargs = dict(
        run_id="same", unit_id="u", phase="initial", rc=1, seconds=.1,
        truncated=False, pytest_ran=True)
    first = write_attempt_evidence(tmp_path, tail="first", **kwargs)
    first_bytes = (tmp_path / first).read_bytes()
    second = write_attempt_evidence(tmp_path, tail="second", **kwargs)
    assert first != second
    assert (tmp_path / first).read_bytes() == first_bytes
    assert b"second" in (tmp_path / second).read_bytes()


def test_deep_windows_fixture_keeps_atomic_evidence_path_compact(tmp_path):
    deep = tmp_path.joinpath(*(["pytest-fixture-segment"] * 5))
    deep.mkdir(parents=True)
    rel = write_attempt_evidence(
        deep, run_id="iterate-" + "r" * 300,
        unit_id="integration/tests/" + "u" * 300,
        phase="authoritative-serial-" + "p" * 300,
        rc=1, seconds=.2, tail="bounded", truncated=False, pytest_ran=True,
    )
    assert len(str(rel)) <= 112
    target = (deep / rel).resolve()
    if sys.platform == "win32":
        target = Path("\\\\?\\" + str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["run_id"].startswith("iterate-")
    assert payload["unit_id"].startswith("integration/tests/")


def test_linked_worktree_evidence_survives_in_the_main_repo_store(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=main, check=True)
    (main / "seed").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "seed"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=main, check=True)
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "diagnostics-test",
         str(linked), "HEAD"],
        cwd=main, check=True)

    rel = write_attempt_evidence(
        linked, run_id="durable", unit_id="u", phase="initial", rc=1,
        seconds=.1, tail="failure", truncated=False, pytest_ran=True)

    assert (main / rel).is_file()
    assert not (linked / rel).exists()
