"""Open-file warning, A7 wording, adopt seeder LF + drop-name parity (events-followups U1).

@FR-01.11
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import events_open_warning as eow  # noqa: E402
from lib.events_layout import events_layout  # noqa: E402
from lib.events_read import DROP_NAME  # noqa: E402
from tools import main_health as tool  # noqa: E402
from tools import main_health_gh as gh  # noqa: E402
from tools.verifiers.adopt_compliance import check_a7_adopted_event  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

REPO_ROOT = Path(__file__).resolve().parents[2]
TIP = "a" * 40


def _tree(root: Path, layout: str, n: int) -> Path:
    (root / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": layout}), encoding="utf-8")
    d = root / "shipwright_events.d"
    d.mkdir()
    for i in range(n):
        (d / f"r{i}--{i:08x}--{i:08x}.jsonl").write_text("{}\n", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _no_layout_override(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_EVENTS_LAYOUT", raising=False)


def test_threshold_is_the_named_constant_150():
    assert eow.OPEN_FILES_WARN_THRESHOLD == 150


def test_at_threshold_warns_with_count_and_fold_hint(tmp_path):
    _tree(tmp_path, "drops", eow.OPEN_FILES_WARN_THRESHOLD)
    line = eow.open_files_warning(tmp_path)
    assert line and line.startswith("WARN") and "150" in line and "fold_events.py" in line and "fold --project-root" in line and Path(eow.__file__).resolve().parents[1].joinpath("tools", "fold_events.py").is_file()
    assert "\n" not in line


def test_below_threshold_is_silent(tmp_path):
    _tree(tmp_path, "drops", eow.OPEN_FILES_WARN_THRESHOLD - 1)
    assert eow.open_files_warning(tmp_path) is None


def test_legacy_layout_is_silent_even_with_many_files(tmp_path):
    _tree(tmp_path, "legacy", eow.OPEN_FILES_WARN_THRESHOLD + 10)
    assert events_layout(tmp_path) == "legacy"  # silence must come from the layout, not a swallowed error
    assert eow.open_files_warning(tmp_path) is None


def test_temp_and_foreign_files_are_not_counted(tmp_path):
    _tree(tmp_path, "drops", 3)
    d = tmp_path / "shipwright_events.d"
    (d / ".x.jsonl.tmp").write_text("x", encoding="utf-8")
    (d / "notes.txt").write_text("x", encoding="utf-8")
    (d / ".hidden.jsonl").write_text("x", encoding="utf-8")
    assert eow.count_open_drop_files(tmp_path) == 3


@pytest.fixture
def host(monkeypatch):
    monkeypatch.setattr(gh, "commit_series", lambda cwd, ref, window: [{"sha": TIP, "subject": "tip (#2)"}])
    monkeypatch.setattr(gh, "workflow_files", lambda cwd: ["ci.yml", "security.yml", "codeql.yml", "bloat-check.yml"])
    run = {"databaseId": 1, "workflowName": "CI", "headSha": TIP, "headBranch": "main", "event": "push",
           "status": "completed", "conclusion": "success", "createdAt": "2026-07-28T10:00:00Z", "url": "https://x/1"}
    monkeypatch.setattr(gh, "list_runs", lambda cwd, b, limit: [run])


def test_main_health_prints_the_line_without_changing_the_exit_code(host, tmp_path, capsys):
    quiet = tmp_path / "quiet"
    loud = tmp_path / "loud"
    quiet.mkdir()
    loud.mkdir()
    _tree(quiet, "drops", 1)
    _tree(loud, "drops", eow.OPEN_FILES_WARN_THRESHOLD + 1)

    code_quiet = tool.main(["--project-root", str(quiet)])
    quiet_err = capsys.readouterr().err
    code_loud = tool.main(["--project-root", str(loud)])
    loud_err = capsys.readouterr().err

    assert code_quiet == code_loud == 0
    assert "WARN" not in quiet_err
    assert "151 event files are open" in loud_err


def test_a_failing_warning_never_breaks_main_health(host, tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(eow, "count_open_drop_files", _boom)
    _tree(tmp_path, "drops", 1)
    assert eow.open_files_warning(tmp_path) is None
    assert tool.main(["--project-root", str(tmp_path)]) == 0


def test_a7_failure_names_both_locations(tmp_path):
    finding = check_a7_adopted_event(tmp_path)
    text = json.dumps(finding)
    assert "shipwright_events.jsonl" in text and "shipwright_events.d/" in text


def _load_seeder():
    path = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "lib" / "event_seeder.py"
    spec = importlib.util.spec_from_file_location("_evt_seeder_u1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _drops_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "drops")
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    return tmp_path


def test_seeder_drop_name_obeys_the_shared_name_rule(tmp_path, monkeypatch):
    root = _drops_root(tmp_path, monkeypatch)
    seeder = _load_seeder()
    log = root / "shipwright_events.jsonl"
    seeder.seed_adopted_event(log, profile="p", scope="s", features_inferred=1, nested_excluded=[],
                              plugin_version="1", commit_sha=None)
    target = seeder.events_target(log)
    m = DROP_NAME.match(target.name)
    assert m, f"seeder name {target.name!r} no longer matches the shared DROP_NAME rule"
    assert m.group("key") == "_adopt" and re.fullmatch(r"[0-9a-f]{8}", m.group("wt8"))


def test_seeder_append_writes_lf_even_when_the_platform_translates_newlines(tmp_path, monkeypatch):
    root = _drops_root(tmp_path, monkeypatch)
    seeder = _load_seeder()
    real_open = Path.open

    def crlf_prone_open(self, mode="r", *args, **kwargs):  # what Windows does when newline is not given
        if "a" in mode and "newline" not in kwargs:
            kwargs["newline"] = "\r\n"
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", crlf_prone_open)
    log = root / "shipwright_events.jsonl"
    seeder.seed_adopted_event(log, profile="p", scope="s", features_inferred=1, nested_excluded=[],
                              plugin_version="1", commit_sha=None)
    seeder.seed_backfill_events(log, [{"sha": "abc", "subject": "x"}])  # the second event is an APPEND
    raw = seeder.events_target(log).read_bytes()
    assert raw.count(b"\n") == 2 and b"\r" not in raw


def test_events_warning_only_flag_prints_the_line_makes_no_gh_call_and_exits_zero(tmp_path, monkeypatch, capsys):
    def _no_gh(*a, **k):
        raise AssertionError("the F0 advisory must not call gh/git")

    for name in ("commit_series", "list_runs", "workflow_files"):
        monkeypatch.setattr(gh, name, _no_gh)
    monkeypatch.setattr(tool, "build_report", _no_gh)
    _tree(tmp_path, "drops", eow.OPEN_FILES_WARN_THRESHOLD)
    assert tool.main(["--events-warning-only", "--project-root", str(tmp_path)]) == 0
    assert "150 event files are open" in capsys.readouterr().err
    quiet = tmp_path / "q"
    quiet.mkdir()
    assert tool.main(["--events-warning-only", "--project-root", str(quiet)]) == 0
    assert capsys.readouterr().err == ""


def test_seeder_legacy_append_also_writes_lf_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "legacy")
    seeder = _load_seeder()
    real_open = Path.open

    def crlf_prone_open(self, mode="r", *args, **kwargs):
        if "a" in mode and "newline" not in kwargs:
            kwargs["newline"] = "\r\n"
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", crlf_prone_open)
    log = tmp_path / "shipwright_events.jsonl"
    seeder.seed_adopted_event(log, profile="p", scope="s", features_inferred=1, nested_excluded=[],
                              plugin_version="1", commit_sha=None)
    seeder.seed_backfill_events(log, [{"sha": "abc", "subject": "x"}])
    raw = log.read_bytes()
    assert raw.count(b"\n") == 2 and b"\r" not in raw
