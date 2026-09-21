"""Unit tests for ``lib.loop_state`` (campaign-dag-scheduler R1):
``_load_units_from`` (both kinds), the terminal-status mapping + ancestry
verification, ``is_unit_ready``, and ``describe_blocker``.
"""

from __future__ import annotations

import json

from lib import loop_state
from lib.loop_state import (
    _load_units_from,
    describe_blocker,
    is_unit_ready,
    verify_merged_commit_ancestry,
)

#: A syntactically valid 40-char hex SHA for tests exercising the real
#: `verify_merged_commit_ancestry` (its `_SHA_RE` guard rejects "deadbeef"
#: on its own — only 8 chars).
_FAKE_SHA = "deadbeef" * 5


class TestLoadUnitsFromSection:
    def test_section_kind_unchanged_drops_complete(self):
        # kind == "section" regression: unchanged — a completed section is
        # still dropped, every unit still starts "pending". Proves the
        # sub_iterate fixes did not leak into shipwright-build's loop.
        data = json.dumps({"sections": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-api", "status": "not_started"},
        ]})
        units = _load_units_from(None, "section", text=data)
        assert len(units) == 1
        assert units[0]["id"] == "02-api"
        assert units[0]["status"] == "pending"
        assert "depends_on" not in units[0]


class TestLoadUnitsFromSubIterate:
    def test_retains_every_unit_never_drops(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [
            {"id": "A", "status": "complete", "commit": "sha-a"},
            {"id": "B", "status": "pending", "depends_on": ["A"]},
            {"id": "C", "status": "failed"},
        ]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert [u["id"] for u in units] == ["A", "B", "C"]  # none dropped

    def test_depends_on_carried_into_key_set(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [{"id": "B", "status": "pending", "depends_on": ["A", "C"]}]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["depends_on"] == ["A", "C"]

    def test_missing_depends_on_defaults_empty(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [{"id": "A", "status": "pending"}]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["depends_on"] == []

    def test_complete_maps_to_merged_with_verified_commit(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)  # always verifies
        data = json.dumps({"sub_iterates": [{"id": "A", "status": "complete", "commit": "sha-a"}]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["status"] == "merged"
        assert units[0]["merged_commit"] == "sha-a"

    def test_complete_unverified_ancestry_yields_no_merged_commit(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: None)  # never verifies
        data = json.dumps({"sub_iterates": [{"id": "A", "status": "complete", "commit": "sha-a"}]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["status"] == "merged"
        assert units[0]["merged_commit"] is None  # status says merged, but NOT is_unit_ready-satisfying

    def test_done_maps_to_merged_same_as_complete(self, monkeypatch):
        # Code review finding (medium regression): the pre-R1 loader dropped
        # "complete" AND "done" rows identically for kind == "sub_iterate";
        # this rewrite must keep recognizing "done" as finished, or a
        # "done" row gets silently re-claimed and rebuilt from scratch.
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [{"id": "A", "status": "done", "commit": "sha-a"}]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["status"] == "merged"
        assert units[0]["merged_commit"] == "sha-a"

    def test_prefers_durable_merged_commit_over_legacy_commit_field(self, monkeypatch):
        # Code review finding (medium, forward-looking): once a later
        # sub-iterate's step 3h writes the real post-merge SHA into
        # status.json's own `merged_commit` field, it must be verified —
        # not the stale pre-merge `commit` field.
        seen = []
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: seen.append(c) or c)
        data = json.dumps({"sub_iterates": [
            {"id": "A", "status": "complete", "commit": "sha-a-premerge", "merged_commit": "sha-a-postmerge"},
        ]})
        _load_units_from(None, "sub_iterate", text=data)
        assert seen == ["sha-a-postmerge"]

    def test_failed_and_escalated_map_to_failed(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [
            {"id": "A", "status": "failed"}, {"id": "B", "status": "escalated"},
        ]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert units[0]["status"] == "failed"
        assert units[1]["status"] == "failed"

    def test_pending_and_in_progress_stay_pending(self, monkeypatch):
        monkeypatch.setattr(loop_state, "verify_merged_commit_ancestry", lambda c: c)
        data = json.dumps({"sub_iterates": [
            {"id": "A", "status": "pending"}, {"id": "B", "status": "in_progress"},
            {"id": "C"},
        ]})
        units = _load_units_from(None, "sub_iterate", text=data)
        assert [u["status"] for u in units] == ["pending", "pending", "pending"]


class TestVerifyMergedCommitAncestry:
    def test_no_commit_returns_none(self):
        assert verify_merged_commit_ancestry(None) is None
        assert verify_merged_commit_ancestry("") is None

    def test_non_str_commit_returns_none(self, monkeypatch):
        # Doubt review (low): `commit` is operator-editable status.json
        # data — a truthy non-str previously reached `_SHA_RE.fullmatch`
        # and raised TypeError, escaping the "any failure yields None"
        # contract.
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry(123) is None  # type: ignore[arg-type]

    def test_resolve_default_branch_self_bootstraps(self):
        # Doubt review (high, campaign-dag-scheduler R1): every test below
        # monkeypatches `resolve_default_branch`, so a broken import (the
        # bare `from branch_base import ...` silently swallowed to `None`
        # when `shared/scripts/lib` isn't already on sys.path — true for
        # every `lib.loop_state` importer except `autonomous_loop.py`) was
        # invisible to this whole suite. This module must self-bootstrap
        # its own directory rather than depend on its importer.
        assert loop_state.resolve_default_branch is not None

    def test_ancestor_found_returns_commit(self, monkeypatch):
        calls = []

        class FakeResult:
            def __init__(self, returncode):
                self.returncode = returncode

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "merge-base"]:
                return FakeResult(0)
            return FakeResult(0)

        monkeypatch.setattr(loop_state.subprocess, "run", fake_run)
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry(_FAKE_SHA) == _FAKE_SHA
        assert any(c[:2] == ["git", "fetch"] for c in calls)

    def test_ancestor_not_found_returns_none(self, monkeypatch):
        class FakeResult:
            def __init__(self, returncode):
                self.returncode = returncode

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["git", "merge-base"]:
                return FakeResult(1)  # not an ancestor
            return FakeResult(0)

        monkeypatch.setattr(loop_state.subprocess, "run", fake_run)
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry(_FAKE_SHA) is None

    def test_git_failure_returns_none_never_crashes(self, monkeypatch):
        import subprocess as _subprocess

        def fake_run(cmd, **kwargs):
            raise _subprocess.TimeoutExpired(cmd, 60)

        monkeypatch.setattr(loop_state.subprocess, "run", fake_run)
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry(_FAKE_SHA) is None

    def test_no_resolve_default_branch_returns_none(self, monkeypatch):
        monkeypatch.setattr(loop_state, "resolve_default_branch", None)
        assert verify_merged_commit_ancestry(_FAKE_SHA) is None

    def test_non_hex_sha_rejected_before_any_subprocess_call(self, monkeypatch):
        # External code review finding (medium, security): `commit` is
        # operator-editable (status.json) and flows unquoted into `git
        # merge-base` argv — a value git would parse as an option (e.g. a
        # leading "-") must never reach that call.
        calls = []
        monkeypatch.setattr(loop_state.subprocess, "run", lambda *a, **k: calls.append(a))
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry("--upload-pack=evil") is None
        assert verify_merged_commit_ancestry("deadbeef") is None  # too short, not 40 hex chars
        assert calls == []  # never reached subprocess at all

    def test_failed_fetch_returns_none_never_trusts_stale_local_ref(self, monkeypatch):
        # Code review finding (high): a failed `git fetch` must not fall
        # through to merge-base against a possibly-stale local origin/<default>
        # — that could verify a commit whose remote history was rewritten
        # while offline/network-down.
        calls = []

        class FakeResult:
            def __init__(self, returncode):
                self.returncode = returncode

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "fetch"]:
                return FakeResult(1)  # fetch failed
            return FakeResult(0)  # merge-base would say "verified" if reached

        monkeypatch.setattr(loop_state.subprocess, "run", fake_run)
        monkeypatch.setattr(loop_state, "resolve_default_branch", lambda: "main")
        assert verify_merged_commit_ancestry(_FAKE_SHA) is None
        assert not any(c[:2] == ["git", "merge-base"] for c in calls)  # never reached


class TestIsUnitReady:
    def test_no_dependencies_is_ready(self):
        assert is_unit_ready({"id": "A", "depends_on": []}, [])

    def test_merged_and_verified_dependency_is_ready(self):
        all_units = [{"id": "A", "status": "merged", "merged_commit": "sha"}]
        assert is_unit_ready({"id": "B", "depends_on": ["A"]}, all_units)

    def test_merged_but_unverified_dependency_blocks(self):
        all_units = [{"id": "A", "status": "merged", "merged_commit": None}]
        assert not is_unit_ready({"id": "B", "depends_on": ["A"]}, all_units)

    def test_pending_dependency_blocks(self):
        all_units = [{"id": "A", "status": "pending"}]
        assert not is_unit_ready({"id": "B", "depends_on": ["A"]}, all_units)

    def test_missing_dependency_blocks(self):
        assert not is_unit_ready({"id": "B", "depends_on": ["ZZZ"]}, [])

    def test_independent_unit_unaffected_by_others_blocking(self):
        all_units = [
            {"id": "A", "status": "pending"},
            {"id": "B", "depends_on": ["A"]},
            {"id": "C", "depends_on": []},
        ]
        assert is_unit_ready({"id": "C", "depends_on": []}, all_units)

    def test_case_mismatched_dependency_resolves_not_a_deadlock(self):
        # External code review finding (high): validate_dependency_graph
        # resolves depends_on existence case-insensitively at write time, so
        # a case-mismatched edge is write-time VALID. is_unit_ready's lookup
        # must resolve it too, or the dependent blocks forever.
        all_units = [{"id": "R0", "status": "merged", "merged_commit": "sha"}]
        assert is_unit_ready({"id": "B", "depends_on": ["r0"]}, all_units)


class TestDescribeBlocker:
    def test_ready_unit_has_no_blocker(self):
        all_units = [{"id": "A", "status": "merged", "merged_commit": "sha"}]
        assert describe_blocker({"id": "B", "depends_on": ["A"]}, all_units) == ""

    def test_names_the_unmerged_dependency(self):
        all_units = [{"id": "A", "status": "pending"}]
        msg = describe_blocker({"id": "B", "depends_on": ["A"]}, all_units)
        assert "B" in msg and "A" in msg

    def test_names_the_missing_dependency(self):
        msg = describe_blocker({"id": "B", "depends_on": ["ZZZ"]}, [])
        assert "ZZZ" in msg

    def test_names_the_unverified_dependency(self):
        all_units = [{"id": "A", "status": "merged", "merged_commit": None}]
        msg = describe_blocker({"id": "B", "depends_on": ["A"]}, all_units)
        assert "ancestry" in msg
