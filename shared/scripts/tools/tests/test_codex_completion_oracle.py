"""Tests for the read-only Codex completion oracle."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools import codex_completion_oracle as oracle
from tools import watch_pr_delivery


def _write_events(root, *events):
    (root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(event) for event in events) + "\n",
        encoding="utf-8",
    )


_REQUIRED_C1_PHASES = {"changelog", "deploy", "design", "plan", "project", "test"}


@pytest.mark.parametrize("phase", sorted(_REQUIRED_C1_PHASES))
def test_each_c1_phase_verdict_is_session_scoped(tmp_path, phase):
    _write_events(
        tmp_path,
        {"type": "phase_completed", "phase": phase, "session": "sid"},
        {"type": "phase_completed", "phase": phase, "session": "other"},
    )

    assert oracle.evaluate(tmp_path, phase, session="sid")["verdict"] == "done"
    assert oracle.evaluate(tmp_path, phase, session="missing")["verdict"] == "not_done"


def test_c1_phase_set_matches_the_completion_oracle_contract():
    assert oracle._C1_PHASES == _REQUIRED_C1_PHASES


def test_build_verdict_is_session_scoped(tmp_path):
    _write_events(
        tmp_path,
        {"type": "work_completed", "source": "build", "session": "other"},
        {"type": "work_completed", "source": "build", "session": "sid"},
    )

    assert oracle.evaluate(tmp_path, "build", session="sid")["verdict"] == "done"
    assert oracle.evaluate(tmp_path, "build", session="missing")["verdict"] == "not_done"


def test_c1_since_fallback_certifies_only_events_after_the_boundary(tmp_path):
    _write_events(
        tmp_path,
        {
            "type": "phase_completed", "phase": "plan",
            "ts": "2026-09-15T10:00:00Z",
        },
        {
            "type": "phase_completed", "phase": "plan",
            "ts": "2026-09-15T10:00:00.001Z",
        },
    )

    assert oracle.evaluate(
        tmp_path, "plan", session="missing", since="2026-09-15T10:00:00Z",
    )["verdict"] == "done"

    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps({
            "type": "phase_completed", "phase": "plan",
            "ts": "2026-09-15T10:00:00Z",
        }) + "\n",
        encoding="utf-8",
    )
    assert oracle.evaluate(
        tmp_path, "plan", session="missing", since="2026-09-15T10:00:00Z",
    )["verdict"] == "not_done"


def test_c1_exact_session_evidence_blocks_a_newer_since_fallback(tmp_path):
    _write_events(
        tmp_path,
        {"type": "phase_started", "phase": "plan", "session": "sid"},
        {
            "type": "phase_completed", "phase": "plan",
            "ts": "2026-09-15T10:01:00Z",
        },
    )

    result = oracle.evaluate(
        tmp_path, "plan", session="sid", since="2026-09-15T10:00:00Z",
    )

    assert result["verdict"] == "not_done"
    assert result["evidence"]["completion_scope"] == "exact"


def test_no_oracle_is_explicit_and_uses_the_documented_exit_code(tmp_path, capsys):
    code = oracle.main(["--project-root", str(tmp_path), "--phase", "security", "--session", "sid"])

    assert code == oracle.EXIT_NO_ORACLE
    assert json.loads(capsys.readouterr().out)["verdict"] == "no_oracle"


def test_main_runs_a_real_c1_oracle_path(tmp_path, capsys):
    _write_events(tmp_path, {"type": "phase_completed", "phase": "plan", "session": "sid"})

    code = oracle.main(["--project-root", str(tmp_path), "--phase", "plan", "--session", "sid"])

    assert code == oracle.EXIT_DONE
    assert json.loads(capsys.readouterr().out)["verdict"] == "done"


def test_main_runs_a_real_not_done_oracle_path(tmp_path, capsys):
    code = oracle.main(["--project-root", str(tmp_path), "--phase", "plan", "--session", "sid"])

    assert code == oracle.EXIT_NOT_DONE
    assert json.loads(capsys.readouterr().out)["verdict"] == "not_done"


def test_main_runs_a_real_delivery_pending_oracle_path(tmp_path, monkeypatch, capsys):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": "pending"}), returncode=4),
    )

    code = oracle.main(["--project-root", str(tmp_path), "--phase", "iterate", "--session", "sid"])

    assert code == oracle.EXIT_DELIVERY_PENDING
    assert json.loads(capsys.readouterr().out)["verdict"] == "delivery_pending"


@pytest.mark.parametrize("since", ["not-a-time", "2026-09-15T10:00:00"])
def test_main_reports_invalid_since_values_as_json_not_done(tmp_path, since, capsys):
    code = oracle.main(
        ["--project-root", str(tmp_path), "--phase", "plan", "--session", "sid", "--since", since]
    )

    assert code == oracle.EXIT_NOT_DONE
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "not_done"
    assert payload["evidence"]["since_parse_failed"] is True


def test_evaluate_marks_an_invalid_since_value_as_fail_safe_not_done(tmp_path):
    result = oracle.evaluate(tmp_path, "plan", session="sid", since="not-a-time")

    assert result["verdict"] == "not_done"
    assert result["evidence"]["since_parse_failed"] is True


@pytest.mark.parametrize(
    ("verdict", "exit_code"),
    [
        ("done", oracle.EXIT_DONE),
        ("not_done", oracle.EXIT_NOT_DONE),
        ("delivery_pending", oracle.EXIT_DELIVERY_PENDING),
    ],
)
def test_main_maps_every_active_verdict_to_its_documented_exit_code(
    tmp_path, monkeypatch, capsys, verdict, exit_code,
):
    monkeypatch.setattr(
        oracle,
        "evaluate",
        lambda _root, _phase, *, session, since=None: {
            "verdict": verdict, "phase": _phase, "session": session, "evidence": {},
        },
    )

    code = oracle.main(["--project-root", str(tmp_path), "--phase", "plan", "--session", "sid"])

    assert code == exit_code
    assert json.loads(capsys.readouterr().out)["verdict"] == verdict


def test_iterate_delivery_pending_uses_read_only_watch_once(tmp_path, monkeypatch):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example", "ts": "2026-09-15T10:00:00Z",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps({"status": "pending"}), returncode=4)

    monkeypatch.setattr(oracle.subprocess, "run", fake_run)
    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "delivery_pending"
    assert calls[0][0][-3:] == ["--pr", "iterate/example", "--once"]
    assert "deliver_pr.py" not in " ".join(calls[0][0])


@pytest.mark.parametrize("status", sorted(oracle._WATCHER_STATUS_CODES))
def test_iterate_watcher_status_contract_matches_the_real_watcher(status):
    assert watch_pr_delivery._exit_code(status) == oracle._WATCHER_STATUS_CODES[status]


def test_iterate_merged_is_done(tmp_path, monkeypatch):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": "merged"}), returncode=0),
    )

    assert oracle.evaluate(tmp_path, "iterate", session="sid")["verdict"] == "done"


def test_iterate_does_not_trust_a_merged_payload_with_the_wrong_exit_code(tmp_path, monkeypatch):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": "merged"}), returncode=4),
    )

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "not_done"
    assert result["evidence"]["delivery_state"] == "indeterminate"


def test_iterate_uses_the_latest_event_by_utc_instant(tmp_path, monkeypatch):
    _write_events(
        tmp_path,
        {
            "type": "work_completed", "source": "iterate", "session": "sid",
            "adr_id": "iterate-2026-09-15-older", "ts": "2026-09-15T10:30:00+01:00",
        },
        {
            "type": "work_completed", "source": "iterate", "session": "sid",
            "adr_id": "iterate-2026-09-15-newer", "ts": "2026-09-15T10:00:00.001+00:00",
        },
    )
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-older.json").write_text(json.dumps({"branch": "iterate/older"}))
    (entry / "iterate-2026-09-15-newer.json").write_text(json.dumps({"branch": "iterate/newer"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": "merged"}), returncode=0),
    )

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "done"
    assert result["evidence"]["run_id"] == "iterate-2026-09-15-newer"


def test_iterate_rejects_an_unsafe_run_id_before_reading_files(tmp_path, monkeypatch):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid", "adr_id": "../other",
    })
    monkeypatch.setattr(oracle, "_iterate_branch", lambda *_args: pytest.fail("must not read an unsafe path"))

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "not_done"
    assert "unsafe" in result["evidence"]["reason"]


def test_iterate_rejects_a_branch_that_would_be_parsed_as_an_option(tmp_path, monkeypatch):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "--help"}))
    monkeypatch.setattr(oracle, "_delivery_status", lambda *_args: pytest.fail("must not invoke watcher"))

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "not_done"
    assert "unsafe branch" in result["evidence"]["reason"]


@pytest.mark.parametrize(("status", "returncode"), [("checks_failed", 2), ("closed", 3)])
def test_iterate_confirmed_delivery_errors_are_pending_not_agent_not_done(tmp_path, monkeypatch, status, returncode):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": status}), returncode=returncode),
    )

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "delivery_pending"
    assert result["evidence"]["delivery_state"] == "error"
    assert result["evidence"]["delivery"]["status"] == status


@pytest.mark.parametrize(
    "failure",
    [OSError(), oracle.subprocess.TimeoutExpired("watch_pr_delivery", 70), json.JSONDecodeError("bad", "x", 0)],
)
def test_iterate_unreadable_delivery_remains_nudgeable_until_pr_exists(tmp_path, monkeypatch, failure):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(oracle.subprocess, "run", fail)
    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "not_done"
    assert result["evidence"]["delivery_state"] == "indeterminate"


@pytest.mark.parametrize("status", ["gh_error", "unknown"])
def test_iterate_unrecognized_delivery_remains_nudgeable_until_pr_exists(tmp_path, monkeypatch, status):
    _write_events(tmp_path, {
        "type": "work_completed", "source": "iterate", "session": "sid",
        "adr_id": "iterate-2026-09-15-example",
    })
    entry = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    entry.mkdir(parents=True)
    (entry / "iterate-2026-09-15-example.json").write_text(json.dumps({"branch": "iterate/example"}))
    monkeypatch.setattr(
        oracle.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps({"status": status}), returncode=1),
    )

    result = oracle.evaluate(tmp_path, "iterate", session="sid")

    assert result["verdict"] == "not_done"
    assert result["evidence"]["delivery_state"] == "indeterminate"
