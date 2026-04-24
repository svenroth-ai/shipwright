"""Tests for shared/scripts/tools/list_iterate_branches.py.

Unit tests cover pure helpers (parsers, classifiers, schema shape).
Integration tests (marked slow) exercise real git repos in tmp paths.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared" / "scripts" / "tools"))

import list_iterate_branches as lib  # noqa: E402


# =============================================================================
# Unit — parse_worktree_porcelain + WorktreeRecord + _finalize
# =============================================================================


class TestParseWorktreePorcelain:
    def test_single_well_formed_record_with_branch(self) -> None:
        text = (
            "worktree /tmp/repo\n"
            "HEAD abc123\n"
            "branch refs/heads/main\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert errors == []
        assert len(records) == 1
        assert records[0].path == "/tmp/repo"
        assert records[0].head == "abc123"
        assert records[0].branch == "main"
        assert records[0].detached is False

    def test_detached_linked_worktree_is_valid(self) -> None:
        text = (
            "worktree /tmp/repo/linked\n"
            "HEAD abc123\n"
            "detached\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert errors == []
        assert len(records) == 1
        assert records[0].branch is None
        assert records[0].detached is True

    def test_locked_with_reason_vs_bare(self) -> None:
        text_with_reason = (
            "worktree /tmp/a\n"
            "HEAD abc\n"
            "branch refs/heads/a\n"
            "locked pending merge\n"
            "\n"
        )
        text_bare = (
            "worktree /tmp/b\n"
            "HEAD def\n"
            "branch refs/heads/b\n"
            "locked\n"
            "\n"
        )
        recs_a, _ = lib.parse_worktree_porcelain(text_with_reason)
        recs_b, _ = lib.parse_worktree_porcelain(text_bare)
        assert recs_a[0].locked is True
        assert recs_a[0].locked_reason == "pending merge"
        assert recs_b[0].locked is True
        assert recs_b[0].locked_reason is None

    def test_prunable_pragma(self) -> None:
        text = (
            "worktree /tmp/dead\n"
            "HEAD 000\n"
            "branch refs/heads/dead\n"
            "prunable gitdir file points to non-existent location\n"
            "\n"
        )
        records, _ = lib.parse_worktree_porcelain(text)
        assert records[0].prunable is True
        assert records[0].prunable_reason.startswith("gitdir file")

    def test_multiple_records_separated_by_blank(self) -> None:
        text = (
            "worktree /tmp/a\n"
            "HEAD aaa\n"
            "branch refs/heads/a\n"
            "\n"
            "worktree /tmp/b\n"
            "HEAD bbb\n"
            "branch refs/heads/b\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert errors == []
        assert len(records) == 2

    def test_record_missing_path_goes_to_parse_errors(self) -> None:
        text = (
            "HEAD abc\n"
            "branch refs/heads/orphan\n"
            "\n"
            "worktree /tmp/ok\n"
            "HEAD def\n"
            "branch refs/heads/ok\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert len(records) == 1
        assert records[0].path == "/tmp/ok"
        assert len(errors) == 1
        assert "missing path" in errors[0].lower() or "malformed" in errors[0].lower()

    def test_implicit_record_boundary(self) -> None:
        """Two `worktree` keys without a blank separator."""
        text = (
            "worktree /tmp/a\n"
            "HEAD aaa\n"
            "branch refs/heads/a\n"
            "worktree /tmp/b\n"
            "HEAD bbb\n"
            "branch refs/heads/b\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert len(records) == 2
        assert records[0].path == "/tmp/a"
        assert records[1].path == "/tmp/b"
        assert any(
            "implicit boundary" in e or "missing blank-line" in e
            for e in errors
        )

    def test_unknown_key_is_ignored(self) -> None:
        text = (
            "worktree /tmp/x\n"
            "HEAD xxx\n"
            "branch refs/heads/x\n"
            "future-pragma some-value\n"
            "\n"
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert len(records) == 1
        assert errors == []

    def test_eof_without_trailing_blank_finalizes(self) -> None:
        text = (
            "worktree /tmp/x\n"
            "HEAD xxx\n"
            "branch refs/heads/x"  # no trailing newline
        )
        records, errors = lib.parse_worktree_porcelain(text)
        assert len(records) == 1


# =============================================================================
# Unit — run_git + GitError contract
# =============================================================================


class TestRunGit:
    def test_check_true_raises_on_non_zero(self, tmp_path: Path) -> None:
        # Running `git --no-pager -C <tmp> rev-parse HEAD` in a non-git
        # dir returns non-zero. check=True → GitError.
        with pytest.raises(lib.GitError):
            lib.run_git(["rev-parse", "HEAD"], cwd=tmp_path, check=True)

    def test_check_false_returns_completed_process(self, tmp_path: Path) -> None:
        result = lib.run_git(
            ["rev-parse", "HEAD"], cwd=tmp_path, check=False
        )
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode != 0  # non-git dir

    def test_no_pager_flag_prepended(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, Any] = {}

        class FakePopen:
            def __init__(self, args: list[str], **kwargs: Any) -> None:
                captured["args"] = args
                captured["kwargs"] = kwargs
                self.returncode = 0

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                return ("", "")

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        lib.run_git(["status"], cwd=tmp_path, check=False)
        assert captured["args"][0] == "git"
        assert "--no-pager" in captured["args"]
        assert "-C" in captured["args"]
        assert captured["kwargs"].get("shell") is False
        assert captured["kwargs"].get("text") is True
        assert captured["kwargs"].get("encoding") == "utf-8"
        assert captured["kwargs"].get("errors") == "replace"


# =============================================================================
# Unit — detect_main + _branch_exists + _find_branch_ref
# =============================================================================


class TestDetectMain:
    def _fake_run_git(
        self,
        *,
        origin_head: tuple[int, str] | None = None,
        existing_refs: set[str] | None = None,
    ) -> Any:
        """Stub that mimics run_git for detect_main.

        origin_head: (returncode, stdout) for `symbolic-ref refs/remotes/origin/HEAD`.
        existing_refs: set of refs that `show-ref --verify` reports as present.
        """
        existing_refs = existing_refs or set()

        def _inner(args: list[str], *, cwd: Path, check: bool = True, **kw: Any) -> Any:
            if args[0] == "symbolic-ref" and "refs/remotes/origin/HEAD" in args:
                rc, out = origin_head if origin_head else (1, "")
                return subprocess.CompletedProcess(args, rc, out, "")
            if args[0] == "show-ref" and "--verify" in args:
                ref = args[-1]
                rc = 0 if ref in existing_refs else 1
                return subprocess.CompletedProcess(args, rc, "", "")
            raise AssertionError(f"unexpected run_git call: {args}")

        return _inner

    def test_override_exists_local(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(
                existing_refs={"refs/heads/trunk"},
            ),
        )
        name, ref, errors = lib.detect_main(tmp_path, override="trunk")
        assert name == "trunk"
        assert ref == "refs/heads/trunk"
        assert errors == []

    def test_override_not_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(lib, "run_git", self._fake_run_git())
        name, ref, errors = lib.detect_main(tmp_path, override="trunk")
        assert name is None
        assert ref is None
        assert errors and "trunk" in errors[0]

    def test_origin_head_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(
                origin_head=(0, "refs/remotes/origin/develop\n"),
            ),
        )
        name, ref, errors = lib.detect_main(tmp_path, override=None)
        assert name == "develop"
        assert ref == "refs/remotes/origin/develop"
        assert errors == []

    def test_main_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(existing_refs={"refs/heads/main"}),
        )
        name, ref, errors = lib.detect_main(tmp_path, override=None)
        assert name == "main"
        assert ref == "refs/heads/main"

    def test_master_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(existing_refs={"refs/heads/master"}),
        )
        name, _, _ = lib.detect_main(tmp_path, override=None)
        assert name == "master"

    def test_ambiguity_both_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(
                existing_refs={"refs/heads/main", "refs/heads/master"},
            ),
        )
        name, ref, errors = lib.detect_main(tmp_path, override=None)
        assert name is None
        assert ref is None
        assert errors and "ambiguous" in errors[0].lower()

    def test_neither_exists(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(lib, "run_git", self._fake_run_git())
        name, ref, errors = lib.detect_main(tmp_path, override=None)
        assert name is None
        assert ref is None
        assert errors and "no default" in errors[0].lower()

    def test_prefer_remote_over_local(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """R1-H5: when both exist, origin/<name> wins."""
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_run_git(
                existing_refs={
                    "refs/heads/main",
                    "refs/remotes/origin/main",
                },
            ),
        )
        _, ref, _ = lib.detect_main(tmp_path, override=None)
        assert ref == "refs/remotes/origin/main"


# =============================================================================
# Unit — classify_branches (R3-H3 + R3-M4)
# =============================================================================


class TestClassifyBranches:
    def _fake_is_ancestor(self, rc_by_branch: dict[str, int]) -> Any:
        """Stub run_git that returns merge-base --is-ancestor results."""
        def _inner(args: list[str], *, cwd: Path, check: bool = True, **kw: Any) -> Any:
            assert args[0] == "merge-base"
            assert "--is-ancestor" in args
            branch = args[2]  # args = ["merge-base", "--is-ancestor", branch, main_ref]
            rc = rc_by_branch.get(branch, 1)
            return subprocess.CompletedProcess(args, rc, "", "")
        return _inner

    def test_main_unknown_short_circuit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _no_run_git(*a: Any, **kw: Any) -> Any:
            raise AssertionError(
                "no run_git calls expected when main_ref is None"
            )

        monkeypatch.setattr(lib, "run_git", _no_run_git)
        entries, errors = lib.classify_branches(
            tmp_path,
            ["iterate/a", "iterate/b"],
            current_branch="iterate/a",
            branch_to_worktree_path={},
            main_ref=None,
            per_call_timeout=10.0,
        )
        assert entries[0]["status"] == "active"
        assert entries[0]["reason_code"] == "current"
        assert entries[1]["status"] == "active"
        assert entries[1]["reason_code"] == "main_unknown"
        assert entries[1]["confidence"] == "low"

    def test_ancestor_stale_and_active(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_is_ancestor({"iterate/merged": 0, "iterate/open": 1}),
        )
        entries, _ = lib.classify_branches(
            tmp_path,
            ["iterate/merged", "iterate/open"],
            current_branch="main",
            branch_to_worktree_path={},
            main_ref="refs/heads/main",
            per_call_timeout=10.0,
        )
        assert entries[0]["status"] == "stale"
        assert entries[0]["reason_code"] == "ancestor"
        assert entries[1]["status"] == "active"
        assert entries[1]["reason_code"] == "not_ancestor"

    def test_unrelated_history_low_confidence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_is_ancestor({"iterate/orphan": 128}),
        )
        entries, _ = lib.classify_branches(
            tmp_path,
            ["iterate/orphan"],
            current_branch="main",
            branch_to_worktree_path={},
            main_ref="refs/heads/main",
            per_call_timeout=10.0,
        )
        assert entries[0]["reason_code"] == "unrelated_history"
        assert entries[0]["confidence"] == "low"

    def test_locked_with_ancestor_sets_would_be_status(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            lib,
            "run_git",
            self._fake_is_ancestor(
                {"iterate/locked-merged": 0, "iterate/locked-open": 1}
            ),
        )
        entries, _ = lib.classify_branches(
            tmp_path,
            ["iterate/locked-merged", "iterate/locked-open"],
            current_branch="main",
            branch_to_worktree_path={
                "iterate/locked-merged": "/wt/a",
                "iterate/locked-open": "/wt/b",
            },
            main_ref="refs/heads/main",
            per_call_timeout=10.0,
        )
        assert entries[0]["status"] == "locked"
        assert entries[0]["locked_in_worktree"] == "/wt/a"
        assert entries[0]["would_be_status"] == "stale"
        assert entries[1]["status"] == "locked"
        assert entries[1]["would_be_status"] == "active"

    def test_locked_with_main_unknown_sets_would_be_null(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _no_run_git(*a: Any, **kw: Any) -> Any:
            raise AssertionError("no run_git expected")

        monkeypatch.setattr(lib, "run_git", _no_run_git)
        entries, _ = lib.classify_branches(
            tmp_path,
            ["iterate/locked"],
            current_branch=None,
            branch_to_worktree_path={"iterate/locked": "/wt/locked"},
            main_ref=None,
            per_call_timeout=10.0,
        )
        assert entries[0]["status"] == "locked"
        assert entries[0]["would_be_status"] is None
        assert entries[0]["reason_code"] == "locked"

    def test_timeout_on_ancestor_check(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def _raise_timeout(*a: Any, **kw: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="git", timeout=1.0)

        monkeypatch.setattr(lib, "run_git", _raise_timeout)
        entries, _ = lib.classify_branches(
            tmp_path,
            ["iterate/slow"],
            current_branch=None,
            branch_to_worktree_path={},
            main_ref="refs/heads/main",
            per_call_timeout=1.0,
        )
        assert entries[0]["reason_code"] == "timeout"
        assert entries[0]["confidence"] == "low"


# =============================================================================
# Unit — build_branch_to_worktree_map + _normalize_path
# =============================================================================


class TestBranchToWorktreeMap:
    def test_excludes_current_worktree(self) -> None:
        records = [
            lib.WorktreeRecord(
                path="/tmp/main-wt",
                head="a",
                branch="main",
                detached=False,
                locked=False,
                locked_reason=None,
                prunable=False,
                prunable_reason=None,
            ),
            lib.WorktreeRecord(
                path="/tmp/iterate-wt",
                head="b",
                branch="iterate/x",
                detached=False,
                locked=False,
                locked_reason=None,
                prunable=False,
                prunable_reason=None,
            ),
        ]
        mapping = lib.build_branch_to_worktree_map(records, "/tmp/main-wt")
        # Paths are stored normalized — compare via the same normalization
        # so the test is platform-stable (Windows normcase changes case
        # and separators).
        assert list(mapping.keys()) == ["iterate/x"]
        assert mapping["iterate/x"] == lib._normalize_path("/tmp/iterate-wt")

    def test_detached_linked_worktree_has_no_branch(self) -> None:
        records = [
            lib.WorktreeRecord(
                path="/tmp/detached",
                head="a",
                branch=None,
                detached=True,
                locked=False,
                locked_reason=None,
                prunable=False,
                prunable_reason=None,
            ),
        ]
        mapping = lib.build_branch_to_worktree_map(records, "/tmp/other")
        assert mapping == {}


# =============================================================================
# Unit — schema contract
# =============================================================================


class TestSchemaContract:
    VALID_STATUS = {"active", "stale", "locked"}
    VALID_REASON_CODES = {
        "current",
        "locked",
        "ancestor",
        "not_ancestor",
        "unrelated_history",
        "timeout",
        "main_unknown",
    }
    VALID_CONFIDENCE = {"high", "low"}

    def test_entry_shape_exhaustive(self) -> None:
        entry = lib._make_entry(
            "iterate/x",
            status="active",
            reason_code="current",
            confidence="high",
        )
        required = {
            "name",
            "status",
            "reason_code",
            "detail",
            "confidence",
            "locked_in_worktree",
            "would_be_status",
        }
        assert set(entry.keys()) == required

    def test_json_round_trip_with_unicode(self) -> None:
        payload = {
            "version": 1,
            "repo_root": "/tmp",
            "main": "main",
            "main_ref": "refs/heads/main",
            "current": "iterate/ümlaut",
            "branches": [
                lib._make_entry(
                    "iterate/ümlaut",
                    status="active",
                    reason_code="current",
                    confidence="high",
                )
            ],
            "active": ["iterate/ümlaut"],
            "stale": [],
            "locked": [],
            "errors": [],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        restored = json.loads(serialized)
        assert restored == payload
        assert "\\u" not in serialized  # non-ASCII kept raw

    def test_schema_version_is_one(self) -> None:
        assert lib.SCHEMA_VERSION == 1


# =============================================================================
# Integration — slow, real git repos
# =============================================================================


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_commit(cwd: Path, msg: str) -> None:
    _git(cwd, "commit", "--allow-empty", "-m", msg)


def _init_repo(tmp: Path, default_branch: str = "main") -> Path:
    _git(tmp, "init", "-q", "-b", default_branch)
    _git(tmp, "config", "user.email", "test@example.com")
    _git(tmp, "config", "user.name", "Test")
    _git_commit(tmp, "init")
    return tmp


@pytest.mark.slow
class TestIntegration:
    def test_merged_stale_and_unmerged_active(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        # iterate/a: merged via --no-ff → stale/ancestor
        _git(tmp_path, "checkout", "-b", "iterate/a")
        _git_commit(tmp_path, "work on a")
        _git(tmp_path, "checkout", "main")
        _git(tmp_path, "merge", "--no-ff", "iterate/a", "-m", "merge a")
        # iterate/b: unmerged
        _git(tmp_path, "checkout", "-b", "iterate/b")
        _git_commit(tmp_path, "work on b")
        _git(tmp_path, "checkout", "main")

        payload = lib.collect(tmp_path, main_override="main")
        names_by_status = {e["name"]: e["status"] for e in payload["branches"]}
        assert names_by_status["iterate/a"] == "stale"
        assert names_by_status["iterate/b"] == "active"

    def test_squash_merged_stays_active(self, tmp_path: Path) -> None:
        """Freezes the documented limitation — squash-merged is NOT detected."""
        _init_repo(tmp_path)
        _git(tmp_path, "checkout", "-b", "iterate/sq")
        _git_commit(tmp_path, "sq work 1")
        _git_commit(tmp_path, "sq work 2")
        _git(tmp_path, "checkout", "main")
        _git(tmp_path, "merge", "--squash", "iterate/sq")
        _git_commit(tmp_path, "squashed sq")

        payload = lib.collect(tmp_path, main_override="main")
        sq_entry = next(
            e for e in payload["branches"] if e["name"] == "iterate/sq"
        )
        assert sq_entry["status"] == "active", (
            "squash-merge is a known limitation; branch stays active"
        )

    def test_master_only_repo(self, tmp_path: Path) -> None:
        _init_repo(tmp_path, default_branch="master")
        _git(tmp_path, "checkout", "-b", "iterate/x")
        _git_commit(tmp_path, "work")
        _git(tmp_path, "checkout", "master")

        payload = lib.collect(tmp_path)  # no override
        assert payload["main"] == "master"

    def test_main_master_ambiguity(self, tmp_path: Path) -> None:
        _init_repo(tmp_path, default_branch="main")
        _git(tmp_path, "branch", "master")

        payload = lib.collect(tmp_path)  # no override
        assert payload["main"] is None
        assert any(
            "ambiguous" in e.lower() for e in payload["errors"]
        )

    def test_detached_head_current_null(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _git_commit(tmp_path, "second")
        sha = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        _git(tmp_path, "checkout", sha)

        payload = lib.collect(tmp_path, main_override="main")
        assert payload["current"] is None

    def test_worktree_locked_branch(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _git(repo, "checkout", "-b", "iterate/x")
        _git_commit(repo, "work")
        _git(repo, "checkout", "main")
        linked = tmp_path / "linked"
        _git(repo, "worktree", "add", str(linked), "iterate/x")

        payload = lib.collect(repo, main_override="main")
        x_entry = next(
            e for e in payload["branches"] if e["name"] == "iterate/x"
        )
        assert x_entry["status"] == "locked"
        assert x_entry["locked_in_worktree"] is not None
        # Normalized path comparison.
        assert os.path.normcase(os.path.abspath(str(linked))) == os.path.normcase(
            os.path.abspath(x_entry["locked_in_worktree"])
        )

    def test_orphan_branch_unrelated_history(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _git(tmp_path, "checkout", "--orphan", "iterate/orphan")
        subprocess.run(
            ["git", "-C", str(tmp_path), "rm", "-rf", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        _git_commit(tmp_path, "orphan root")
        _git(tmp_path, "checkout", "main")

        payload = lib.collect(tmp_path, main_override="main")
        orphan_entry = next(
            e for e in payload["branches"] if e["name"] == "iterate/orphan"
        )
        # `merge-base --is-ancestor` on unrelated history returns non-0/1.
        assert orphan_entry["status"] == "active"
        assert orphan_entry["reason_code"] in {
            "unrelated_history",
            "not_ancestor",
        }

    def test_unicode_branch_name(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        _git(tmp_path, "checkout", "-b", "iterate/ümlaut-test")
        _git_commit(tmp_path, "work")
        _git(tmp_path, "checkout", "main")

        payload = lib.collect(tmp_path, main_override="main")
        # Serializable as JSON, Unicode preserved raw.
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "ümlaut" in serialized
        names = [e["name"] for e in payload["branches"]]
        assert "iterate/ümlaut-test" in names
