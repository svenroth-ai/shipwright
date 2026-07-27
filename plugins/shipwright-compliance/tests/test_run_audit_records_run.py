"""The detective audit records its own run — end to end, through the CLI.

Nothing schedules this audit, so it is the only thing that can say it ran.
These tests drive the real ``run_audit.py`` process (not the helper) so the
wiring itself is covered: if the recording call is dropped from the CLI, the
evidence documents silently go back to saying "never run" forever.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.audit import run_audit
from scripts.lib.audit_disclosure import CONFIG_FILE, LAST_AUDIT_KEY

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUN_AUDIT = PLUGIN_ROOT / "scripts" / "audit" / "run_audit.py"


@pytest.fixture
def audited_project(tmp_path: Path) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8",
    )
    return tmp_path


def _run(project_root: Path, *extra: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT), "--project-root", str(project_root),
         *extra],
        capture_output=True, text=True, encoding="utf-8",
    )
    # 0 on all-pass, 1 on any-fail — both mean the audit ran.
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def _recorded(project_root: Path) -> dict:
    doc = json.loads((project_root / CONFIG_FILE).read_text(encoding="utf-8"))
    return doc[LAST_AUDIT_KEY]


def test_a_full_run_is_recorded_in_tracked_state(audited_project: Path):
    payload = _run(audited_project)
    assert payload["last_audit_recorded"]["recorded"] is True

    block = _recorded(audited_project)
    assert block["scope"] == "full"
    assert block["ran_at"]
    assert block["verdict"] == ("fail" if payload["any_fail"] else "pass")
    assert block["checks"]["total"] == len(payload["findings"])


def test_a_partial_run_is_recorded_as_partial(audited_project: Path):
    """``--only`` must never be readable as a full cross-check."""
    _run(audited_project, "--only", "A")
    assert _recorded(audited_project)["scope"] == "A"


def test_a_run_that_executed_no_group_is_not_recorded(audited_project: Path):
    """A typo'd ``--only`` checked nothing — it must not be stored as a PASS.

    An unknown group letter lands in ``groups_skipped`` and ``groups_run`` stays
    empty. Recording that would freshen every document's disclosure on the
    strength of a run that verified nothing, and would store ``verdict: pass``
    to say so. The stored record has to keep meaning "this audit checked
    something".
    """
    payload = _run(audited_project, "--only", "ZZZ")
    assert payload["groups_run"] == []
    assert payload["last_audit_recorded"]["recorded"] is False
    assert payload["last_audit_recorded"]["reason"] == "no_group_ran"
    assert not (audited_project / CONFIG_FILE).exists()


def test_an_empty_run_does_not_displace_an_earlier_real_one(audited_project: Path):
    """The previous answer survives — it is still the last real cross-check."""
    _run(audited_project)
    before = _recorded(audited_project)

    _run(audited_project, "--only", "ZZZ")
    assert _recorded(audited_project) == before


class TestRecordingBranchInProcess:
    """The same three outcomes, driven in-process rather than as a subprocess.

    The subprocess tests above prove the wiring end to end, but coverage cannot
    follow into a child process — the recording branch measured 0% and the
    diff-coverage gate was right to say so. Calling ``main()`` directly exercises
    each arm where it can be seen, and is faster besides.
    """

    def test_an_empty_run_records_nothing_and_says_so(
        self, audited_project: Path, capsys,
    ):
        code = run_audit.main(
            ["--project-root", str(audited_project), "--only", "ZZZ"],
        )
        captured = capsys.readouterr()
        assert code in (0, 1)

        payload = json.loads(captured.out)
        assert payload["last_audit_recorded"] == {
            "recorded": False, "reason": "no_group_ran",
        }
        assert "no audit group ran" in captured.err
        assert "ZZZ" in captured.err
        assert not (audited_project / CONFIG_FILE).exists()

    def test_a_real_run_takes_the_recording_arm(
        self, audited_project: Path, capsys,
    ):
        code = run_audit.main(["--project-root", str(audited_project)])
        payload = json.loads(capsys.readouterr().out)
        assert code in (0, 1)
        assert payload["last_audit_recorded"]["recorded"] is True
        assert _recorded(audited_project)["scope"] == "full"

    def test_an_exploding_recorder_never_changes_the_verdict(
        self, audited_project: Path, capsys, monkeypatch,
    ):
        """The defensive arm: bookkeeping may fail in ways the recorder does not
        anticipate, and the audit's answer to "is this project consistent?" must
        survive all of them."""
        def boom(*_args, **_kwargs):
            raise RuntimeError("recorder exploded")

        monkeypatch.setattr(run_audit, "record_audit_run", boom)

        code = run_audit.main(["--project-root", str(audited_project)])
        captured = capsys.readouterr()

        payload = json.loads(captured.out)
        assert code in (0, 1)
        assert payload["last_audit_recorded"]["recorded"] is False
        assert "recorder exploded" in payload["last_audit_recorded"]["reason"]
        assert "could not be recorded" in captured.err

    def test_a_failed_recording_warns_without_changing_the_verdict(
        self, audited_project: Path, capsys,
    ):
        """Fail-soft, but never silent — the durability half has to be visible."""
        (audited_project / CONFIG_FILE).mkdir()  # a directory where a file belongs

        code = run_audit.main(["--project-root", str(audited_project)])
        captured = capsys.readouterr()

        payload = json.loads(captured.out)
        assert code in (0, 1)  # the audit's own verdict is unchanged
        assert payload["last_audit_recorded"]["recorded"] is False
        assert "could not be recorded" in captured.err


def test_recording_does_not_disturb_an_existing_config(audited_project: Path):
    (audited_project / CONFIG_FILE).write_text(
        json.dumps({"enforcement": {"rtm_coverage_min": 0.7}}, indent=2) + "\n",
        encoding="utf-8",
    )
    _run(audited_project)

    doc = json.loads((audited_project / CONFIG_FILE).read_text(encoding="utf-8"))
    assert doc["enforcement"] == {"rtm_coverage_min": 0.7}
    assert doc[LAST_AUDIT_KEY]["ran_at"]
