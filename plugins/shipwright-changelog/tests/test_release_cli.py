"""L1 tests of ``release.py prepare`` and ``aggregate`` with an injected runner (unit P3, FR-01.09).

No process is started: a fake runner answers by the key of each tool call and records the argv, so the tests prove what the
CLI asks of the existing tools, in which order, with which flags, and what it writes itself (the run state, the upgrade drop).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
pytestmark = pytest.mark.covers("FR-01.09/AC01")  # the tests prove the release steps behave as the requirement says; finer tags where a test names its AC

from lib import release_aggregate, release_prepare, release_runstate
from lib.release_runner import CmdResult, Recorder

NOW = datetime(2026, 11, 23, 9, 30, 0, tzinfo=timezone.utc)
ROWS = [{"gate_id": "changelog.version-suggestion", "policy": "auto-default"},
        {"gate_id": "changelog.entry-preview", "policy": "auto-default"},
        {"gate_id": "changelog.out-of-sequence-continue", "policy": "orchestrator-approve"}]
SETUP = {"success": True, "last_tag": "v1.2.0", "commits_since_tag": 2, "branch": "release/next", "has_unreleased": True,
         "previous_tag_has_release": False, "suggested_version": "1.3.0", "version_reason": "new feature(s)"}


class Fake:
    """A runner that answers by key; ``answers[key]`` is a ``CmdResult`` field dict or a callable ``argv -> dict``."""

    def __init__(self, **answers):
        self.answers, self.calls = answers, []

    def __call__(self, key, argv, cwd):
        self.calls.append((key, list(argv)))
        answer = self.answers.get(key, {})
        fields = answer(argv) if callable(answer) else answer
        return CmdResult(key, tuple(argv), fields.get("exit", 0), fields.get("stdout", ""), fields.get("stderr", ""))

    def keys(self):
        return [k for k, _ in self.calls]

    def argv(self, key):
        return next(a for k, a in self.calls if k == key)


def ok_runner(**over) -> Fake:
    base = {"context": {"stdout": json.dumps({"mode": "standalone", "requires_out_of_sequence_warning": False})},
            "setup": {"stdout": json.dumps(SETUP)}, "gates": {"stdout": json.dumps({"gates": ROWS})},
            "parse-commits": {"stdout": "[]"}, "tag-check": {"exit": 1}, "migration-pages": {"stdout": ""}}
    return Fake(**{**base, **over})


def run_prepare(tmp_path, plugin_root, fake, **kw):
    return release_prepare.prepare(Recorder(fake, tmp_path), plugin_root, clock=lambda: NOW, **kw)


@pytest.mark.covers("FR-01.09/AC01")
def test_prepare_runs_the_prose_steps_in_order_and_returns_what_the_model_used_to_work_out(tmp_path, plugin_root):
    fake = ok_runner()
    code, out = run_prepare(tmp_path, plugin_root, fake)
    assert code == 0 and out["status"] == "ok"
    assert fake.keys()[:5] == ["context", "setup", "gates", "parse-commits", "tag-check"]
    assert fake.argv("parse-commits")[-4:] == ["--since", "v1.2.0", "--format", "json"]
    assert (out["version"], out["suggested"], out["version_reason"], out["mode"]) == ("1.3.0", "1.3.0", "new feature(s)", "standalone")
    assert out["notices"][0].startswith("====") and any("pipeline state will not be updated" in n for n in out["notices"])
    assert any(n.startswith("Notice: v1.2.0 has no GitHub Release") for n in out["notices"])


@pytest.mark.covers("FR-01.09/AC04")
def test_a_custom_version_replaces_the_suggestion_and_the_tag_is_looked_up_for_it(tmp_path, plugin_root):
    fake = ok_runner()
    _, out = run_prepare(tmp_path, plugin_root, fake, version="2.0.0")
    assert out["version"] == "2.0.0" and out["suggested"] == "1.3.0"
    assert fake.argv("tag-check")[-1] == "refs/tags/v2.0.0"


def test_a_token_that_does_not_resolve_stops_before_anything_else_runs(tmp_path, plugin_root):
    fake = ok_runner(context={"exit": 2, "stdout": json.dumps({"mode": "error"})})
    code, out = run_prepare(tmp_path, plugin_root, fake, phase_task_id="stale")
    assert (code, out["status"], out["reason"], out["mode"]) == (2, "stop", "mode_error", "error")
    assert fake.keys() == ["context"] and "--phase-task-id" in fake.argv("context")
    assert not release_runstate.state_path(tmp_path).exists()


def test_a_refused_setup_argument_is_reported_and_writes_nothing(tmp_path, plugin_root):
    fake = ok_runner(setup={"exit": 2, "stderr": "unrecognized arguments: --from v0.1.0"})
    code, out = run_prepare(tmp_path, plugin_root, fake, from_version="v0.1.0")
    assert (code, out["reason"]) == (2, "setup_refused") and "--from" in fake.argv("setup")
    assert not release_runstate.state_path(tmp_path).exists()


@pytest.mark.covers("FR-01.09/AC03")
def test_nothing_unreleased_is_a_result_with_exit_zero_and_no_run_state(tmp_path, plugin_root):
    fake = ok_runner(setup={"stdout": json.dumps({**SETUP, "has_unreleased": False, "commits_since_tag": 0})})
    code, out = run_prepare(tmp_path, plugin_root, fake)
    assert (code, out["status"], out["reason"]) == (0, "stop", "no_unreleased_changes")
    assert "gates" not in fake.keys() and not release_runstate.state_path(tmp_path).exists()


def test_a_missing_gate_catalog_stops_instead_of_guessing_the_answers(tmp_path, plugin_root):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(gates={"exit": 2, "stderr": "gate catalog unavailable"}))
    assert (code, out["reason"]) == (2, "gate_catalog_unavailable")


def test_no_tag_passes_an_empty_since_as_the_prose_does(tmp_path, plugin_root):
    fake = ok_runner(setup={"stdout": json.dumps({**SETUP, "last_tag": None, "suggested_version": "0.1.0"})})
    run_prepare(tmp_path, plugin_root, fake)
    assert fake.argv("parse-commits")[-4:] == ["--since", "", "--format", "json"]


def test_the_out_of_sequence_warning_and_the_gate_answers_are_returned(tmp_path, plugin_root):
    fake = ok_runner(context={"stdout": json.dumps({"mode": "standalone", "requires_out_of_sequence_warning": True,
                                                    "active_phases": ["project"]})})
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({"autonomy": "autonomous"}), encoding="utf-8")
    _, out = run_prepare(tmp_path, plugin_root, fake)
    assert out["out_of_sequence_warning"] is True and out["active_phases"] == ["project"]
    assert out["gates"] == {"version": "auto", "preview": "auto", "out_of_sequence": "ask"}


def test_guided_standalone_asks_and_a_dispatched_run_never_does(tmp_path, plugin_root):
    _, guided = run_prepare(tmp_path, plugin_root, ok_runner())
    assert guided["gates"] == {"version": "ask", "preview": "ask", "out_of_sequence": "ask"}
    piped = ok_runner(context={"stdout": json.dumps({"mode": "pipeline"})})
    (tmp_path / "driven").mkdir()
    _, driven = run_prepare(tmp_path / "driven", plugin_root, piped)
    assert driven["gates"]["version"] == "auto" and driven["gates"]["preview"] == "auto"


@pytest.mark.covers("FR-01.09/AC01")
def test_prepare_stores_the_date_and_run_id_once_and_a_second_prepare_of_the_same_release_keeps_them(tmp_path, plugin_root):
    _, first = run_prepare(tmp_path, plugin_root, ok_runner())
    stored = json.loads(release_runstate.state_path(tmp_path).read_text(encoding="utf-8"))
    assert first["release"] == {"date": "2026-11-23", "run_id": "changelog-v1.3.0-20261123-093000", "reused": False,
                                "state_file": str(release_runstate.state_path(tmp_path))}
    assert (stored["version"], stored["release_date"], stored["run_id"]) == ("1.3.0", "2026-11-23", first["release"]["run_id"])
    later = datetime(2026, 11, 23, 18, 0, 0, tzinfo=timezone.utc)  # the same day, a resumed release
    _, second = release_prepare.prepare(Recorder(ok_runner(), tmp_path), plugin_root, clock=lambda: later)
    assert second["release"]["date"] == "2026-11-23" and second["release"]["run_id"] == first["release"]["run_id"]
    morning = datetime(2026, 11, 24, 8, 0, 0, tzinfo=timezone.utc)  # an abandoned look yesterday must not date today's release
    _, third = release_prepare.prepare(Recorder(ok_runner(), tmp_path), plugin_root, clock=lambda: morning)
    assert third["release"]["date"] == "2026-11-24" and third["release"]["run_id"] == first["release"]["run_id"]


def test_a_released_tag_or_another_version_starts_a_fresh_state(tmp_path, plugin_root):
    run_prepare(tmp_path, plugin_root, ok_runner())
    later = datetime(2026, 12, 1, 8, 0, 0, tzinfo=timezone.utc)
    _, tagged = release_prepare.prepare(Recorder(ok_runner(**{"tag-check": {"exit": 0}}), tmp_path), plugin_root, clock=lambda: later)
    assert tagged["release"]["date"] == "2026-12-01"
    _, other = release_prepare.prepare(Recorder(ok_runner(), tmp_path), plugin_root, version="9.9.9", clock=lambda: later)
    assert other["release"]["run_id"].startswith("changelog-v9.9.9-")


def test_the_run_id_of_the_environment_is_used_only_by_a_dispatched_run(tmp_path, plugin_root, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "given-by-the-orchestrator")
    piped = ok_runner(context={"stdout": json.dumps({"mode": "pipeline"})})
    _, out = run_prepare(tmp_path, plugin_root, piped)
    assert out["release"]["run_id"] == "given-by-the-orchestrator"
    other = tmp_path / "standalone"; other.mkdir()
    _, stale = run_prepare(other, plugin_root, ok_runner())  # a leftover variable is not a run id
    assert stale["release"]["run_id"] == "changelog-v1.3.0-20261123-093000"


def test_an_unfinished_state_older_than_two_days_is_an_abandoned_release_not_an_interrupted_one(tmp_path, plugin_root):
    run_prepare(tmp_path, plugin_root, ok_runner())
    weeks = datetime(2026, 12, 20, 8, 0, 0, tzinfo=timezone.utc)
    _, again = release_prepare.prepare(Recorder(ok_runner(), tmp_path), plugin_root, clock=lambda: weeks)
    assert again["release"]["date"] == "2026-12-20" and again["release"]["reused"] is False


@pytest.mark.parametrize(("over", "reason"), [
    ({"parse-commits": {"exit": 1, "stderr": "bad ref"}}, "parse_commits_failed"),
    ({"setup": {"stdout": json.dumps({**SETUP, "suggested_version": None})}}, "no_version"),
    ({"migration-pages": {"exit": 128, "stderr": "bad revision"}}, "upgrade_notes_query_failed")])
def test_prepare_stops_with_a_named_reason_instead_of_carrying_on_with_missing_facts(tmp_path, plugin_root, over, reason):
    code, out = run_prepare(tmp_path, plugin_root, ok_runner(**over))
    assert code != 0 and out["status"] == "stop" and out["reason"] == reason
    assert not release_runstate.state_path(tmp_path).exists()


def test_a_damaged_state_file_is_never_trusted(tmp_path):
    path = release_runstate.state_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert release_runstate.load(tmp_path) is None
    path.write_text(json.dumps({"schema": 1, "version": "1.0.0"}), encoding="utf-8")
    assert release_runstate.load(tmp_path) is None
    for bad in ({"release_date": "tomorrow", "run_id": "ok"}, {"release_date": "2026-11-23", "run_id": "../../etc"}):
        path.write_text(json.dumps({"schema": 1, "version": "1.0.0", **bad}), encoding="utf-8")
        assert release_runstate.load(tmp_path) is None  # the shape is checked on read: no path built from an unchecked id


# ---- aggregate -------------------------------------------------------------------------------

AGG_OK = {"stdout": json.dumps({"version": "1.3.0", "section_action": "inserted", "changelog_updated": True, "section_written": "## [1.3.0]",
                                "legacy_unreleased_bullets": 0, "legacy_unreleased_bullet_texts": []})}


def run_aggregate(tmp_path, plugin_root, fake, **kw):
    return release_aggregate.aggregate(Recorder(fake, tmp_path), plugin_root, clock=lambda: NOW, **kw)


@pytest.mark.covers("FR-01.09/AC10")
def test_the_preview_passes_dry_run_never_fail_if_empty_and_writes_no_state(tmp_path, plugin_root):
    fake = Fake(**{"aggregate-dry": AGG_OK, "tag-check": {"exit": 1}})
    code, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0", dry_run=True)
    argv = fake.argv("aggregate-dry")
    assert code == 0 and "--dry-run" in argv and "--fail-if-empty" not in argv
    assert fake.keys() == ["tag-check", "aggregate-dry"] and not release_runstate.state_path(tmp_path).exists()


@pytest.mark.covers("FR-01.09/AC03")
def test_the_real_run_always_passes_fail_if_empty_then_numbers_the_decisions_and_stores_the_state(tmp_path, plugin_root):
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}, "decisions": {}})
    code, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0")
    argv = fake.argv("aggregate")
    assert code == 0 and "--fail-if-empty" in argv and "--dry-run" not in argv
    assert fake.keys() == ["tag-check", "aggregate", "decisions"] and out["decisions"] == {"exit": 0}
    assert release_runstate.load(tmp_path)["release_date"] == "2026-11-23"


@pytest.mark.covers("FR-01.09/AC07")
def test_every_call_reads_the_stored_date_and_an_explicit_date_overrides_it(tmp_path, plugin_root):
    release_runstate.save(tmp_path, {"schema": 1, "version": "1.3.0", "release_date": "2026-01-15", "run_id": "r1",
                                    "created_at": "2026-11-23T08:00:00+00:00"})
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}})
    run_aggregate(tmp_path, plugin_root, fake, version="1.3.0")
    assert fake.argv("aggregate")[fake.argv("aggregate").index("--release-date") + 1] == "2026-01-15"
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}})
    _, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0", release_date="2026-02-01")
    assert out["release"]["date"] == "2026-02-01" and release_runstate.load(tmp_path)["release_date"] == "2026-02-01"
    assert release_runstate.load(tmp_path)["run_id"] == "r1"


@pytest.mark.covers("FR-01.09/AC08")
def test_a_refused_rerun_keeps_the_aggregators_exit_code_and_does_nothing_after_it(tmp_path, plugin_root):
    fake = Fake(aggregate={"exit": 1, "stderr": "ERROR: the section on record disagrees"}, **{"tag-check": {"exit": 1}})
    code, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0", fallback_entries=[("Fixed", "x")])
    assert code == 1 and out["status"] == "failed" and out["reason"] == "aggregator_refused"
    assert "decisions" not in fake.keys() and not release_runstate.state_path(tmp_path).exists()
    assert out["commands"][-1]["stderr"] == "ERROR: the section on record disagrees"


@pytest.mark.covers("FR-01.09/AC05")
def test_cherry_picked_bullets_are_written_before_the_aggregator_and_only_on_a_real_run(tmp_path, plugin_root):
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}})
    run_aggregate(tmp_path, plugin_root, fake, version="1.3.0", fallback_entries=[("Fixed", "A cherry-picked fix")])
    keys = fake.keys()
    assert keys.index("fallback-append") < keys.index("aggregate")
    argv = fake.argv("fallback-append")
    assert argv[argv.index("--category") + 1] == "Fixed" and argv[argv.index("--entry") + 1] == "A cherry-picked fix"
    dry = Fake(**{"aggregate-dry": AGG_OK, "tag-check": {"exit": 1}})
    run_aggregate(tmp_path, plugin_root, dry, version="1.3.0", dry_run=True, fallback_entries=[("Fixed", "x")])
    assert "fallback-append" not in dry.keys()


def test_a_failed_fallback_append_or_decision_numbering_stops_the_release(tmp_path, plugin_root):
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}, "fallback-append": {"exit": 2}})
    code, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0", fallback_entries=[("Fixed", "x")])
    assert code == 1 and out["reason"] == "fallback_entry_failed" and "aggregate" not in fake.keys()
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}, "decisions": {"exit": 3}})
    code, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0")
    assert code == 3 and out["status"] == "failed" and out["reason"] == "decisions_numbering_failed"


def test_aggregate_reads_an_old_unfinished_state_of_its_own_version_prepare_alone_starts_a_release(tmp_path, plugin_root):
    release_runstate.save(tmp_path, {"schema": 1, "version": "1.3.0", "release_date": "2026-10-01", "run_id": "r-old",
                                    "created_at": "2026-10-01T08:00:00+00:00"})
    fake = Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}})
    _, out = run_aggregate(tmp_path, plugin_root, fake, version="1.3.0")
    assert out["release"]["date"] == "2026-10-01" and out["release"]["run_id"] == "r-old"  # aggregate keeps what prepare stored, even across midnight


def test_a_malformed_fallback_entry_is_refused_not_dropped(tmp_path):
    import release
    with pytest.raises(SystemExit):
        release.main(["aggregate", "--project-root", str(tmp_path), "--version", "1.3.0", "--fallback-entry", "no-colon"],
                     runner=Fake())


def test_the_cli_main_prints_json_and_returns_the_exit_code(tmp_path, capsys):
    import release
    fake = Fake(aggregate={"exit": 1, "stderr": "boom"}, **{"tag-check": {"exit": 1}})
    code = release.main(["aggregate", "--project-root", str(tmp_path), "--version", "1.3.0"], runner=fake)
    captured = capsys.readouterr()
    assert code == 1 and json.loads(captured.out)["status"] == "failed" and "boom" in captured.err
    code = release.main(["aggregate", "--project-root", str(tmp_path), "--version", "1.3.0", "--fallback-entry", "Fixed:a:b"],
                        runner=Fake(aggregate=AGG_OK, **{"tag-check": {"exit": 1}}))
    assert code == 0
    assert Path(release.__file__).name == "release.py"


def test_a_new_dispatch_names_its_own_run_and_bad_version_or_date_arguments_are_refused(tmp_path, plugin_root, monkeypatch):
    import release
    run_prepare(tmp_path, plugin_root, ok_runner())
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "second-dispatch")
    _, out = run_prepare(tmp_path, plugin_root, ok_runner(context={"stdout": json.dumps({"mode": "pipeline"})}))
    assert out["release"]["run_id"] == "second-dispatch" and out["release"]["reused"] is True
    for bad in (["--version", "v1.3.0"], ["--version", "1.3.0", "--release-date", "2026-1-5"]):
        with pytest.raises(SystemExit):
            release.main(["aggregate", "--project-root", str(tmp_path), *bad], runner=Fake())
