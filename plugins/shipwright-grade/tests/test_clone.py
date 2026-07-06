"""Tests for clone + open_target — the URL clone-and-grade seam (G4).

Covers the scheme allowlist, an offline real shallow clone (from a local repo via
the test-only ``allow_local`` transport relaxation), the size cap, remote-vs-local
detection, and — critically — that the throwaway tempdir is purged even when the
clone crashes mid-flight.
"""

from __future__ import annotations

from pathlib import Path

import clone
import pytest
from clone import (
    MAX_CLONE_BYTES,
    _dir_size_over,
    _run_clone,
    clone_repo,
    normalize_url,
)
from resolve_target import TargetError, is_remote_target, open_target


class TestNormalizeUrl:
    @pytest.mark.parametrize("raw, expected", [
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("https://gitlab.com/o/r.git", "https://gitlab.com/o/r.git"),
        ("git@github.com:o/r.git", "git@github.com:o/r.git"),
        ("ssh://git@github.com/o/r", "ssh://git@github.com/o/r"),
        ("octocat/Hello-World", "https://github.com/octocat/Hello-World"),
        ("octocat/Hello-World.git", "https://github.com/octocat/Hello-World.git"),
    ])
    def test_accepts_allowlisted(self, raw, expected):
        assert normalize_url(raw) == expected

    @pytest.mark.parametrize("raw", [
        "http://github.com/o/r",            # insecure scheme
        "git://github.com/o/r",             # unauthenticated git protocol
        "file:///etc/passwd",               # local file exfiltration
        "ext::sh -c 'id'",                  # arbitrary command transport (RCE)
        "ftp://host/x",
        "../../../etc",                     # traversal shorthand
        "not a url at all",
        "",
        "git@-oProxyCommand=x:o/r",         # ssh option-injection (leading-dash host)
        "ssh://git@-evil/o/r",              # ssh option-injection via ssh:// form
        "https://-evil/o/r",                # leading-dash host over https
    ])
    def test_rejects_everything_else(self, raw):
        with pytest.raises(TargetError):
            normalize_url(raw)


class TestNonInteractive:
    def test_git_runner_env_disables_prompts(self):
        # The clone runner must never block on a credential/host-key prompt.
        from git_exec import _noninteractive_env
        env = _noninteractive_env()
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert "BatchMode=yes" in env["GIT_SSH_COMMAND"]
        assert env.get("GIT_ASKPASS")  # neutralised askpass helper


class TestRealClone:
    """A real, offline shallow clone from a local source (allow_local=True)."""

    def test_run_clone_checks_out_working_tree(self, well_run_repo: Path, tmp_path: Path):
        dest = tmp_path / "cloned"
        _run_clone(str(well_run_repo), dest, allow_local=True)
        assert (dest / ".git").is_dir()
        assert (dest / "app" / "api.py").is_file()      # working tree checked out
        # (A network clone also writes .git/shallow for --depth 1; git skips the
        # shallow file for a same-filesystem local clone, so we don't assert it.)

    def test_run_clone_rejects_unreachable(self, tmp_path: Path):
        with pytest.raises(TargetError, match="clone failed"):
            _run_clone(str(tmp_path / "nope"), tmp_path / "d", allow_local=True)

    def test_run_clone_fetches_history_not_depth_one(self, tmp_path: Path, monkeypatch):
        # A URL grade must fetch enough history for the projector (>= Caps.max_commits),
        # not `--depth 1` (which starved events_total to 1 and mis-graded every URL).
        captured: dict = {}

        def fake_run_git(args, *, cwd=None, timeout=None):
            captured["args"] = list(args)
            (tmp_path / "d" / ".git").mkdir(parents=True, exist_ok=True)
            return 0, ""
        monkeypatch.setattr(clone, "run_git", fake_run_git)
        _run_clone("https://github.com/o/r", tmp_path / "d")
        args = captured["args"]
        assert "1" not in args[args.index("--depth"):args.index("--depth") + 2]
        depth = int(args[args.index("--depth") + 1])
        # Couple to the source of truth: the clone must fetch at least the history
        # window the projector reads, so a URL grade equals a local-clone grade.
        from repo_context import Caps
        assert depth >= Caps().max_commits

    def test_dir_size_over_short_circuits(self, well_run_repo: Path):
        assert _dir_size_over(well_run_repo, 0) is True          # any content > 0
        assert _dir_size_over(well_run_repo, 10**12) is False    # under a huge cap

    def test_clone_repo_enforces_size_cap(self, tmp_path: Path, monkeypatch):
        # A valid URL passes normalize_url; a fake clone drops >0 bytes; the
        # 0-byte cap then trips the guard (the real wiring, no network).
        def fake_run(url, dest, **kwargs):
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir()
            (dest / "big").write_text("x" * 1000, encoding="utf-8")
        monkeypatch.setattr(clone, "_run_clone", fake_run)
        with pytest.raises(TargetError, match="size cap"):
            clone_repo("o/r", tmp_path / "d", max_bytes=0)


class TestIsRemoteTarget:
    def test_url_is_remote(self):
        assert is_remote_target("https://github.com/o/r") is True
        assert is_remote_target("git@github.com:o/r.git") is True

    def test_shorthand_is_remote_when_no_local_path(self):
        assert is_remote_target("octocat/Hello-World") is True

    def test_existing_local_path_wins_over_shorthand(self, tmp_path: Path, monkeypatch):
        (tmp_path / "o").mkdir()
        (tmp_path / "o" / "r").mkdir()
        monkeypatch.chdir(tmp_path)
        assert is_remote_target("o/r") is False  # a real local dir → not remote

    def test_absolute_local_path_is_not_remote(self, well_run_repo: Path):
        assert is_remote_target(str(well_run_repo)) is False


class TestOpenTarget:
    def test_local_path_resolves_without_cloning(self, well_run_repo: Path):
        with open_target(str(well_run_repo)) as target:
            assert target.is_git is True
            assert target.local_path == well_run_repo.resolve()

    def test_remote_is_cloned_and_resolved(
        self, well_run_repo: Path, monkeypatch
    ):
        def fake_clone(raw, dest, **kwargs):
            _run_clone(str(well_run_repo), dest, allow_local=True)
            return dest
        monkeypatch.setattr(clone, "clone_repo", fake_clone)
        with open_target("https://github.com/o/r") as target:
            assert target.is_git is True
            assert (target.local_path / "app" / "api.py").is_file()

    def test_no_clone_forbids_remote(self):
        with pytest.raises(TargetError, match="requires cloning"):
            with open_target("https://github.com/o/r", allow_clone=False):
                pass

    def test_tempdir_purged_even_when_clone_crashes(self, monkeypatch):
        seen: dict[str, Path] = {}

        def boom(raw, dest, **kwargs):
            seen["tmp"] = dest.parent
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "marker").write_text("x", encoding="utf-8")
            raise TargetError("boom mid-clone")

        monkeypatch.setattr(clone, "clone_repo", boom)
        with pytest.raises(TargetError, match="boom mid-clone"):
            with open_target("https://github.com/o/r"):
                pass
        # The TemporaryDirectory was purged during exception unwinding.
        assert seen["tmp"].exists() is False


def test_max_clone_bytes_is_bounded():
    assert 0 < MAX_CLONE_BYTES <= 2_000_000_000
