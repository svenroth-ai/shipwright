"""Mixed versions of the event-log layout (issue 978, campaign S7, kill criterion 3 mixed-version cases)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.events_gitignore import apply_reinclude, reinclude_lines  # noqa: E402
from lib.events_layout import resolve_events_write_path  # noqa: E402
from lib.events_layout_ci import check_layout_ci  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402
from lib.events_sentinel import (  # noqa: E402
    UnsupportedEventsLayout, ensure_layout_key, evidence_refusal, require_writable_layout, unsupported_layout,
)
from tools import record_event  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def _cfg(root: Path, value) -> None:
    body = {"mappings": []} if value is None else {"mappings": [], "events_layout": value}
    (root / "shipwright_sync_config.json").write_text(json.dumps(body), encoding="utf-8")


def _ev(eid: str) -> dict:
    return {"v": 1, "id": eid, "ts": "2026-11-06T10:00:00+00:00", "type": "task_created", "description": "d"}


@pytest.fixture(name="repo")
def _repo(tmp_path, monkeypatch):
    for var in ("SHIPWRIGHT_EVENTS_LAYOUT", "SHIPWRIGHT_EVENTS_LAYOUT_TEST", "SHIPWRIGHT_RUN_ID"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", k, v)
    (root / "README.md").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _commit(root: Path, msg: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


# --- old writer + new reader --------------------------------------------------------------------------


def test_old_writer_appends_legacy_and_new_reader_reads_both(repo):
    _cfg(repo, "drops")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "r1--00000000--00000000.jsonl").write_text(json.dumps(_ev("a" * 16)) + "\n", encoding="utf-8")
    # a pre-S2 plugin knows no drops folder: it appends to the legacy file by hand
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("b" * 8)) + "\n", encoding="utf-8")
    ids = {e["id"] for e in read_events_assembled(repo).records}
    assert ids == {"a" * 16, "b" * 8}


# --- new plugin on an unknown layout fails closed -----------------------------------------------------


@pytest.mark.parametrize("value", ["drops2", 3, ["drops"], ""])
def test_unknown_layout_refuses_event_writes(repo, value):
    _cfg(repo, value)
    assert unsupported_layout(repo) == repr(value)
    with pytest.raises(UnsupportedEventsLayout, match="Update the Shipwright plugins"):
        record_event.append_event(repo, _ev("c" * 8))
    assert not (repo / "shipwright_events.jsonl").exists()


def test_unknown_layout_refuses_legacy_amend(repo):
    _cfg(repo, "v9")
    with pytest.raises(UnsupportedEventsLayout):
        record_event.attach_commit_to_event(repo, "x", "deadbeef")


@pytest.mark.parametrize("value", [None, "legacy", "drops"])
def test_supported_or_absent_layout_is_a_noop(repo, value):
    _cfg(repo, value)
    assert unsupported_layout(repo) is None
    assert evidence_refusal(repo, "p") is None
    resolve_events_write_path(repo)  # does not raise


def test_missing_or_corrupt_config_is_not_an_unknown_layout(repo):
    assert unsupported_layout(repo) is None
    (repo / "shipwright_sync_config.json").write_text("{not json", encoding="utf-8")
    assert unsupported_layout(repo) is None


def test_env_override_cannot_hide_an_unknown_declaration(repo, monkeypatch):
    _cfg(repo, "drops2")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "legacy")
    with pytest.raises(UnsupportedEventsLayout):
        resolve_events_write_path(repo)


# --- legacy write over an existing drops folder -------------------------------------------------------


def test_legacy_write_refused_while_drop_files_exist_and_key_absent(repo):
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "r1--00000000--00000000.jsonl").write_text(json.dumps(_ev("a" * 16)) + "\n", encoding="utf-8")
    with pytest.raises(UnsupportedEventsLayout, match="split the log"):
        require_writable_layout(repo, "legacy")
    with pytest.raises(UnsupportedEventsLayout):
        record_event.append_event(repo, _ev("d" * 8))
    require_writable_layout(repo, "drops")  # the drops layout itself is fine


def test_explicit_legacy_key_is_a_deliberate_rollback_even_with_leftover_drops(repo):
    _cfg(repo, "legacy")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "bad--00000000--00000000.jsonl").write_text("{torn", encoding="utf-8")
    require_writable_layout(repo, "legacy")
    record_event.append_event(repo, _ev("1" * 8))
    assert (repo / "shipwright_events.jsonl").exists()


def test_legacy_write_allowed_when_folder_is_empty_or_only_keep(repo):
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / ".keep").write_text("", encoding="utf-8")
    require_writable_layout(repo, "legacy")
    record_event.append_event(repo, _ev("e" * 8))
    assert (repo / "shipwright_events.jsonl").exists()


# --- release evidence refused --------------------------------------------------------------------------


def test_refresh_compliance_docs_refuses_unknown_layout(repo):
    _cfg(repo, "drops2")
    proc = subprocess.run([sys.executable, str(SCRIPTS / "tools" / "refresh_compliance_docs.py"),
                           "--project-root", str(repo), "--stage"], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 1, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "refused_unsupported_events_layout" and out["producer"] == "refresh_compliance_docs"


def test_update_compliance_gate_refuses_unknown_layout(repo):
    gate = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-compliance" / "scripts" / "tools" / "events_sentinel_gate.py"
    import importlib.util
    spec = importlib.util.spec_from_file_location("_gate_under_test", gate)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.evidence_refusal(repo, "update_compliance") is None
    _cfg(repo, "drops2")
    assert mod.evidence_refusal(repo, "update_compliance")["status"] == "refused_unsupported_events_layout"


# --- init / adopt write the key explicitly --------------------------------------------------------------


def test_ensure_layout_key_writes_once_and_never_overwrites(repo):
    assert ensure_layout_key(repo) is True
    assert json.loads((repo / "shipwright_sync_config.json").read_text(encoding="utf-8")) == {"events_layout": "legacy"}
    assert ensure_layout_key(repo) is False
    _cfg(repo, "drops")
    assert ensure_layout_key(repo) is False
    assert json.loads((repo / "shipwright_sync_config.json").read_text(encoding="utf-8"))["events_layout"] == "drops"


def test_ensure_layout_key_keeps_other_keys_and_skips_unparsable(repo):
    _cfg(repo, None)
    assert ensure_layout_key(repo) is True
    cfg = json.loads((repo / "shipwright_sync_config.json").read_text(encoding="utf-8"))
    assert cfg == {"mappings": [], "events_layout": "legacy"}
    (repo / "shipwright_sync_config.json").write_text("{nope", encoding="utf-8")
    assert ensure_layout_key(repo) is False


def _adopt_sync(root: Path) -> dict:
    """Run adopt's ``write_sync_config`` in a fresh interpreter (its ``lib`` would collide with shared's)."""
    adopt = Path(__file__).resolve().parents[2] / "plugins" / "shipwright-adopt" / "scripts"
    code = ("import sys, json; sys.path.insert(0, sys.argv[1]); from lib.config_writer import write_sync_config; "
            "from pathlib import Path; write_sync_config(Path(sys.argv[2]))")
    subprocess.run([sys.executable, "-I", "-c", code, str(adopt), str(root)], check=True, capture_output=True, timeout=120)
    return json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8"))


def test_adopt_sync_config_writes_the_key_and_keeps_an_existing_value(tmp_path):
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert _adopt_sync(fresh)["events_layout"] == "legacy"
    for value in ("drops", "", "v9"):
        root = tmp_path / f"r{len(value)}"
        root.mkdir()
        _cfg(root, value)
        assert _adopt_sync(root)["events_layout"] == value


def test_adopt_sync_config_never_writes_legacy_over_live_drops(tmp_path):
    (tmp_path / ".shipwright/events/drops").mkdir(parents=True)
    (tmp_path / ".shipwright/events/drops" / "r--00000000--00000000.jsonl").write_text("{}\n", encoding="utf-8")
    assert "events_layout" not in _adopt_sync(tmp_path)



# --- conditional gitignore re-include -------------------------------------------------------------------


def test_reinclude_noop_when_nothing_is_ignored(repo):
    _cfg(repo, "drops")
    assert reinclude_lines(repo) == []


def test_reinclude_when_jsonl_ignored_and_drops_adopted(repo):
    (repo / ".gitignore").write_text("*.jsonl\n", encoding="utf-8")
    _cfg(repo, "drops")
    lines = reinclude_lines(repo)
    assert "!/.shipwright/events/drops/*.jsonl" in lines and "!/.shipwright/events/archive/*.jsonl" in lines
    text, added = apply_reinclude((repo / ".gitignore").read_text(encoding="utf-8"), lines)
    (repo / ".gitignore").write_text(text, encoding="utf-8")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "x.jsonl").write_text("{}\n", encoding="utf-8")
    assert subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", ".shipwright/events/drops/x.jsonl"]).returncode == 1
    assert reinclude_lines(repo) == []  # healed: a second run has nothing to add
    assert added


def test_reinclude_skips_a_legacy_repo_without_tracked_drops(repo):
    (repo / ".gitignore").write_text("*.jsonl\n", encoding="utf-8")
    _cfg(repo, "legacy")
    assert reinclude_lines(repo) == []


def test_reinclude_tracked_legacy_log_only_in_a_drops_repo(repo):
    (repo / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    _commit(repo, "log")
    (repo / ".gitignore").write_text("*.jsonl\n", encoding="utf-8")
    assert reinclude_lines(repo) == []  # legacy layout: nothing to heal, no commit
    _cfg(repo, "drops")
    assert reinclude_lines(repo)[0] == "!/shipwright_events.jsonl"


# --- consumer CI check, judged at the merge-base ---------------------------------------------------------


def _branch_with(repo: Path, *, base_layout, head_layout, touch_legacy: bool):
    _cfg(repo, base_layout)
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("f" * 8)) + "\n", encoding="utf-8")
    _commit(repo, "base state")
    _git(repo, "branch", "base-ref")
    _git(repo, "checkout", "-q", "-b", "pr")
    if head_layout != base_layout:
        _cfg(repo, head_layout)
    if touch_legacy:
        with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(_ev("9" * 8)) + "\n")
    else:
        (repo / ".shipwright/events/drops").mkdir(parents=True)
        (repo / ".shipwright/events/drops" / "r--00000000--00000000.jsonl").write_text(
            json.dumps(_ev("8" * 16)) + "\n", encoding="utf-8")
    _commit(repo, "pr change")


def test_ci_check_legacy_append_after_flip_fails(repo):
    _branch_with(repo, base_layout="drops", head_layout="drops", touch_legacy=True)
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["legacy_write_after_flip"]


def test_ci_check_pr_in_flight_at_the_flip_is_not_failed(repo):
    _branch_with(repo, base_layout="legacy", head_layout="drops", touch_legacy=True)
    assert check_layout_ci(repo, "base-ref") == []


def test_ci_check_absent_key_at_base_passes(repo):
    _branch_with(repo, base_layout=None, head_layout=None, touch_legacy=True)
    assert check_layout_ci(repo, "base-ref") == []


def test_ci_check_drops_without_legacy_touch_passes_and_full_fold_is_allowed(repo):
    _branch_with(repo, base_layout="drops", head_layout="drops", touch_legacy=False)
    assert check_layout_ci(repo, "base-ref") == []
    _git(repo, "checkout", "-q", "-b", "fold")
    (repo / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")
    _commit(repo, "full fold")
    assert check_layout_ci(repo, "base-ref")
    assert check_layout_ci(repo, "base-ref", allow_full_fold=True) == []


def test_ci_check_declared_rollback_to_legacy_passes(repo):
    _branch_with(repo, base_layout="drops", head_layout="legacy", touch_legacy=True)
    assert check_layout_ci(repo, "base-ref") == []


def test_ci_check_unknown_layout_fails_closed_at_head(repo):
    _branch_with(repo, base_layout="legacy", head_layout="drops9", touch_legacy=False)
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["unsupported_layout"]


def test_ci_check_cli_exit_codes(repo):
    _branch_with(repo, base_layout="drops", head_layout="drops", touch_legacy=True)
    cmd = [sys.executable, str(SCRIPTS / "checks" / "check_events_layout_ci.py"), "--project-root", str(repo)]
    bad = subprocess.run([*cmd, "--base-ref", "base-ref"], capture_output=True, text=True, encoding="utf-8")
    assert bad.returncode == 1 and json.loads(bad.stdout)["status"] == "violations"
    err = subprocess.run([*cmd, "--base-ref", "no-such-ref"], capture_output=True, text=True, encoding="utf-8")
    assert err.returncode == 2


def test_ensure_layout_key_never_writes_legacy_over_live_drops(repo):
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "r--00000000--00000000.jsonl").write_text(json.dumps(_ev("a" * 16)) + "\n", encoding="utf-8")
    assert ensure_layout_key(repo) is False
    with pytest.raises(UnsupportedEventsLayout):
        require_writable_layout(repo, "legacy")


def test_ci_check_layout_key_removed_is_a_violation(repo):
    _branch_with(repo, base_layout="legacy", head_layout=None, touch_legacy=False)
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["layout_key_removed"]


def test_ci_check_judges_the_pr_tip_behind_a_synthetic_merge_commit(repo):
    # a PR opened while the base was still legacy; the base then flipped; CI checks out refs/pull/N/merge
    _cfg(repo, "legacy")
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("f" * 8)) + "\n", encoding="utf-8")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "pr")
    with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(_ev("9" * 8)) + "\n")
    _commit(repo, "pr appends legacy")
    _git(repo, "checkout", "-q", "main")
    _cfg(repo, "drops")
    _commit(repo, "flip")
    _git(repo, "checkout", "-q", "-b", "merge-ref")
    _git(repo, "merge", "-q", "--no-ff", "-m", "synthetic merge", "pr")
    assert check_layout_ci(repo, "main", "HEAD") == []


def test_ci_check_head_legacy_with_drop_files_left_is_not_a_rollback(repo):
    _branch_with(repo, base_layout="drops", head_layout="legacy", touch_legacy=True)
    (repo / ".shipwright/events/drops").mkdir(parents=True, exist_ok=True)
    (repo / ".shipwright/events/drops" / "r--00000000--00000000.jsonl").write_text(json.dumps(_ev("7" * 16)) + "\n", encoding="utf-8")
    _commit(repo, "legacy key but drops left")
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["legacy_write_after_flip"]


def test_ci_check_real_merge_commit_is_judged_as_given(repo):
    _branch_with(repo, base_layout="drops", head_layout="drops", touch_legacy=True)  # PR appends legacy
    _git(repo, "checkout", "-q", "-b", "side", "base-ref")
    (repo / "other.txt").write_text("x\n", encoding="utf-8")
    _commit(repo, "side")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge side into pr", "side")  # HEAD^1 is the PR, not the base
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["legacy_write_after_flip"]


def test_explicit_json_null_is_an_unknown_declaration(repo):
    (repo / "shipwright_sync_config.json").write_text('{"events_layout": null}', encoding="utf-8")
    assert unsupported_layout(repo) == "None"
    with pytest.raises(UnsupportedEventsLayout):
        require_writable_layout(repo, "legacy")
    assert ensure_layout_key(repo) is False


def test_reinclude_is_reappended_when_a_later_rule_overrides_an_earlier_one(repo):
    (repo / ".gitignore").write_text("!/.shipwright/events/drops/*.jsonl\n*.jsonl\n", encoding="utf-8")
    _cfg(repo, "drops")
    lines = reinclude_lines(repo)
    text, added = apply_reinclude((repo / ".gitignore").read_text(encoding="utf-8"), lines)
    (repo / ".gitignore").write_text(text, encoding="utf-8")
    assert added and reinclude_lines(repo) == []


def test_ci_check_two_commit_split_cannot_hide_a_legacy_append_behind_a_legacy_key(repo):
    # commit 1 only flips the key to legacy; commit 2 appends the legacy log (its parent is "legacy"), drops stay at the head
    _cfg(repo, "drops")
    (repo / ".shipwright/events/drops").mkdir(parents=True)
    (repo / ".shipwright/events/drops" / "r--00000000--00000000.jsonl").write_text(json.dumps(_ev("6" * 16)) + "\n", encoding="utf-8")
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("f" * 8)) + "\n", encoding="utf-8")
    _commit(repo, "base state")
    _git(repo, "branch", "base-ref")
    _git(repo, "checkout", "-q", "-b", "pr")
    _cfg(repo, "legacy")
    _commit(repo, "key only")
    with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(_ev("9" * 8)) + "\n")
    _commit(repo, "legacy append")
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["legacy_write_after_flip"]


def test_ci_check_a_pr_that_took_main_in_after_the_flip_is_judged_per_commit(repo):
    _cfg(repo, None)
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("f" * 8)) + "\n", encoding="utf-8")
    _commit(repo, "legacy base")
    _git(repo, "checkout", "-q", "-b", "pr")
    with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(_ev("9" * 8)) + "\n")
    _commit(repo, "legacy append before the flip")
    _git(repo, "checkout", "-q", "main")
    _cfg(repo, "drops")
    _commit(repo, "flip")
    _git(repo, "checkout", "-q", "pr")
    _git(repo, "merge", "-q", "--no-edit", "main")
    assert check_layout_ci(repo, "main") == []
    with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(_ev("a" * 8)) + "\n")
    _commit(repo, "legacy append after the flip")
    assert [v.code for v in check_layout_ci(repo, "main")] == ["legacy_write_after_flip"]


def test_ci_check_key_flipped_to_legacy_and_back_cannot_excuse_a_legacy_append(repo):
    _cfg(repo, "drops")
    (repo / "shipwright_events.jsonl").write_text(json.dumps(_ev("f" * 8)) + "\n", encoding="utf-8")
    _commit(repo, "base state")
    _git(repo, "branch", "base-ref")
    _git(repo, "checkout", "-q", "-b", "pr")
    _cfg(repo, "legacy")
    _commit(repo, "key to legacy")
    with (repo / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(_ev("9" * 8)) + "\n")
    _commit(repo, "legacy append")
    _cfg(repo, "drops")
    _commit(repo, "key back to drops")
    assert [v.code for v in check_layout_ci(repo, "base-ref")] == ["legacy_write_after_flip"]
