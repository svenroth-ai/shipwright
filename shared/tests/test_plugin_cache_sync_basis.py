"""How the repo side of the comparison is ESTABLISHED, before anything is read.

The cache is synced from ``~/.claude/plugins/marketplaces/shipwright``, a
``git reset --hard origin/main`` clone. So "what git tracks" is exactly "what
can ever reach the cache", and the repo side asks git rather than walking the
filesystem. Two measured failures drove that:

- a worked-in checkout carries files the clone can never hold
  (``shared/.coverage``, four ``.shipwright_toolcall_count``, one more — all
  gitignored). Walking them made each a permanent phantom "missing from cache"
  and turned the ``--strict`` run ``writing-plugin.md`` calls mandatory
  permanently red;
- and no exclusion list stays correct as directories are added: a bare
  ``build`` component hid all 29 tracked files of
  ``plugins/shipwright-build/skills/build/``, ``SKILL.md`` included.

The cache side still walks — it is not a git tree. That asymmetry is what
``TestTheTwoBasesCannotDisagree`` exists to keep honest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling cache_sync_fixtures module
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the module under test: prepending would let scripts/'s
    # top-level module names win resolution for the whole pytest process
    # (ADR-045 lib-collision, one directory over). Nothing here needs
    # precedence — no other `check_plugin_cache_sync` exists on any path.
    sys.path.append(str(_SCRIPTS))

from cache_tree_compare import SKIP_DIRS  # noqa: E402
from check_plugin_cache_sync import check_sync  # noqa: E402
from cache_sync_fixtures import seed_repo_and_cache as _seed  # noqa: E402


class TestTheRepoSideBasisIsGit:
    """What git tracks IS what can reach the cache — nothing else can.

    The cache is synced from a ``git reset --hard origin/main`` clone, so a
    worked-in checkout carries files the clone can never hold. Measured on the
    main checkout: ``shared/.coverage``, ``shared/.shipwright_toolcall_count``
    and four more, all gitignored, all absent from the cache. Walking the
    filesystem made each a permanent phantom "missing from cache" and turned
    the mandatory ``--strict`` run permanently red — the surest way to train
    an operator to ignore a detective check.
    """

    def _git(self, repo: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True)

    def _init(self, repo: Path) -> None:
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "t")

    def test_a_gitignored_generated_file_is_not_phantom_drift(
            self, tmp_path: Path):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        self._init(repo)
        (repo / ".gitignore").write_text(".coverage\n", encoding="utf-8")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")
        # Exactly the state of a checkout that has run pytest.
        (repo / "shared" / ".coverage").write_text("data", encoding="utf-8")

        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["basis"] == "git"
        assert result["status"] == "ok", "an untrackable file is not drift"
        assert result["shared"]["missing_in_cache_count"] == 0

    def test_a_tracked_file_still_drifts_under_the_git_basis(
            self, tmp_path: Path):
        repo, cache = _seed(tmp_path, shared={"scripts/lib/a.py": "new = 1\n"},
                            cache_shared={"scripts/lib/a.py": "old = 1\n"})
        self._init(repo)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["basis"] == "git"
        assert result["status"] == "drift"

    def test_a_non_git_tree_falls_back_and_says_so(self, tmp_path: Path):
        """The fallback must be visible, never a silent change of meaning."""
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["basis"].startswith("walk")
        assert result["status"] == "ok"

    def test_a_repo_that_tracks_nothing_here_is_not_a_green_over_zero_files(
            self, tmp_path: Path):
        """``git ls-files`` exits 0 and prints nothing — a refusal, not agreement.

        Reachable after ``git init`` on an unzipped download, or for a copy of
        ``plugins/`` dropped inside an unrelated checkout. Read as success it
        yields ``ok`` over zero files at ``--strict`` exit 0 — the same
        confident-green-over-nothing the unreadable ``plugins/`` dir produced.
        """
        repo, cache = _seed(tmp_path, shared={"scripts/lib/a.py": "new = 1\n"},
                            cache_shared={"scripts/lib/a.py": "old = 1\n"})
        self._init(repo)  # initialised, nothing added

        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["basis"].startswith("walk")
        assert "tracks nothing" in result["shared"]["basis"]
        assert result["status"] == "drift", "the real drift must still surface"
        assert result["shared"]["tracked_count"] == 1

    def test_nothing_readable_over_a_non_empty_listing_is_a_refusal(
            self, tmp_path: Path):
        """The same rule as the empty listing, at the OTHER place zero enters.

        Git lists files, none of them can be read (offline cloud placeholders,
        a disconnected mount, an AV quarantine, an all-gitlink tree). Left
        unguarded that is an empty hash set compared against the cache, which
        agrees with everything: ``ok`` at ``--strict`` exit 0.
        """
        files = {"scripts/lib/a.py": "a = 1\n", "scripts/lib/b.py": "b = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        self._init(repo)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")
        for name in ("a.py", "b.py"):
            (repo / "shared" / "scripts" / "lib" / name).unlink()

        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["state"] == "unreadable"
        assert result["shared"]["unhashable_count"] == 2
        assert result["status"] == "drift", "a refusal must not read as in sync"
        # ...and the machine-readable claim must not cover it either.
        assert "shared" not in result["verified"]

    def test_a_cache_absent_tree_still_counts_as_verified(self, tmp_path: Path):
        """`not_in_cache` is a finding, not a refusal — the basis WAS established."""
        repo, cache = _seed(tmp_path, shared={"scripts/lib/a.py": "a = 1\n"})
        self._init(repo)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["state"] == "not_in_cache"
        assert "shared" in result["verified"]

    def test_a_tracked_file_that_cannot_be_read_is_counted_not_dropped(
            self, tmp_path: Path):
        """Git says how many files should be here; silence would shrink to fit.

        A gitlink, a partial checkout, an AV lock or a cloud-storage
        placeholder all hash to None. Dropping them shrinks ``tracked_count``
        so the record self-consistently reports ``ok`` over a partial basis.
        """
        files = {"scripts/lib/a.py": "a = 1\n", "scripts/lib/b.py": "b = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        self._init(repo)
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "init")
        # Tracked, committed, then removed from disk — git still lists it.
        (repo / "shared" / "scripts" / "lib" / "b.py").unlink()

        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["shared"]["basis"] == "git"
        assert result["shared"]["unhashable_count"] == 1
        assert result["shared"]["tracked_count"] == 1


class TestTheTwoBasesCannotDisagree:
    """The asymmetry's load-bearing invariant, pinned instead of asserted.

    The repo side asks git; the cache side applies SKIP_DIRS. While the two
    used the same rule, a SKIP_DIRS name could only cause a symmetric blind
    spot — bad, as ``build`` proved, but never a false alarm. Now, if any file
    under one of those components ever becomes tracked, the repo side includes
    it, the cache side skips it, and it becomes permanent unclearable drift.
    """

    def test_skip_dirs_hide_nothing_git_tracks(self):
        proc = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "ls-files", "-z"],
            capture_output=True, timeout=120, check=True,
        )
        tracked = [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]
        assert tracked, "sanity: the repo tracks files"
        offenders = [p for p in tracked
                     if SKIP_DIRS & set(PurePosixPath(p).parts)]
        assert offenders == [], (
            "these tracked paths would be seen on the repo side and skipped on "
            f"the cache side, i.e. permanent unclearable drift: {offenders[:5]}"
        )
