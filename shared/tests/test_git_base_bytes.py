"""``lib.git_base`` bytes-mode primitive + characterization of the text mode.

``run_git`` decodes with ``errors="replace"``, which is LOSSY and non-injective:
a byte that is not valid UTF-8 becomes ``U+FFFD``, and two different broken bytes
become the SAME character. Every triage-store comparison reads one side through
git and the other off disk with ``errors="surrogateescape"``, so those two sides
could never agree about a line carrying such a byte
(iterate-2026-08-06-gc-decode-parity).

:func:`lib.git_base.run_git_bytes_soft` is the fix's foundation: the same argv /
timeout / kill-and-reap hygiene as :func:`run_git`, but handing back the blob's
RAW BYTES so the caller applies its own store's decode rule.

The text-mode tests here are characterization, not new behaviour: the bytes
variant was carved out of ``run_git``'s body, and ~133 callers depend on that body
being unchanged. External plan review (openai, high) asked for stdout, stderr,
non-zero exit AND the ``run_git_soft`` timeout mapping to be pinned, not just
``run_git``'s stdout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import git_base  # noqa: E402
from lib.git_base import (  # noqa: E402
    TIMEOUT_RETURNCODE,
    GitError,
    run_git,
    run_git_bytes_soft,
    run_git_soft,
)

#: One raw 0xFF byte spliced into an otherwise-valid JSONL line — what an
#: interrupted multi-byte append leaves behind (``lib.jsonl_records`` names that
#: truncation as an EXPECTED case, so this content is reachable, not contrived).
BROKEN = b'{"event":"status","id":"trg-deadbeef","note":"caf\xff"}\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with BROKEN committed verbatim as ``triage.jsonl``."""
    work = tmp_path / "work"
    work.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "bytes@test.invalid")
    git("config", "user.name", "Bytes Test")
    # write_bytes, NOT write_text: the point is that git stores these exact bytes.
    (work / "triage.jsonl").write_bytes(BROKEN)
    git("add", "--", "triage.jsonl")
    git("commit", "-qm", "seed broken byte")
    return work


class TestBytesMode:
    def test_blob_comes_back_byte_for_byte(self, repo: Path) -> None:
        """AC-1 — the primitive must not decode, replace or normalise anything."""
        proc = run_git_bytes_soft(["show", "HEAD:triage.jsonl"], cwd=repo)
        assert proc.returncode == 0
        assert proc.stdout == BROKEN
        assert isinstance(proc.stdout, bytes)

    def test_stderr_is_bytes_too(self, repo: Path) -> None:
        """Both captured streams are bytes — no mixed typing for a caller that
        formats an error message (external plan review, openai finding 2)."""
        proc = run_git_bytes_soft(["show", "HEAD:nope.jsonl"], cwd=repo)
        assert proc.returncode != 0
        assert isinstance(proc.stderr, bytes)

    def test_a_missing_blob_reports_rather_than_raises(self, repo: Path) -> None:
        """``_soft`` never raises for an expected condition — the GC's fail-safe
        ("could not read origin" => drop nothing) depends on it."""
        proc = run_git_bytes_soft(["show", "HEAD:absent.jsonl"], cwd=repo)
        assert proc.returncode != 0
        assert proc.stdout == b""


class TestNewlineTranslation:
    """The SECOND difference between the modes, which the docstring used to deny.

    Text mode wraps the pipes in ``io.TextIOWrapper`` with ``newline=None``, so it
    performs universal-newline translation: a blob's ``\\r\\n`` — and a lone ``\\r`` —
    arrive as ``\\n``. Binary mode returns what git stored. Pinned because a future
    caller migrating to the bytes helper inherits this silently, and for a lone
    ``\\r`` the byte path is the more faithful of the two (found in Stage-2 review).
    """

    @pytest.fixture
    def crlf_repo(self, tmp_path: Path) -> Path:
        work = tmp_path / "crlf"
        work.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "crlf@test.invalid")
        git("config", "user.name", "CRLF Test")
        # -text keeps git from normalising on the way in, so the blob really holds CRLF.
        (work / ".gitattributes").write_bytes(b"* -text\n")
        (work / "crlf.jsonl").write_bytes(b'{"a":1}\r\n{"a":2}\r\n')
        git("add", "--", ".gitattributes", "crlf.jsonl")
        git("commit", "-qm", "seed crlf")
        return work

    def test_bytes_mode_preserves_crlf(self, crlf_repo: Path) -> None:
        proc = run_git_bytes_soft(["show", "HEAD:crlf.jsonl"], cwd=crlf_repo)
        assert proc.returncode == 0
        assert proc.stdout == b'{"a":1}\r\n{"a":2}\r\n'

    def test_text_mode_translates_crlf_to_lf(self, crlf_repo: Path) -> None:
        proc = run_git(["show", "HEAD:crlf.jsonl"], cwd=crlf_repo)
        assert proc.stdout == '{"a":1}\n{"a":2}\n'
        assert "\r" not in proc.stdout


class TestTimeoutContract:
    """AC-6. A ``TimeoutExpired`` escaping here aborts ``setup_iterate_worktree``
    step 5 AFTER ``git worktree add`` already succeeded, orphaning the worktree —
    the exact regression audit findings 1 and 7 fixed. It must stay fixed on the
    new path too.
    """

    def test_timeout_is_reported_not_raised(self, repo: Path, monkeypatch) -> None:
        def boom(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=0.01, output=b"partial")

        # Patch the module OBJECT, never the "lib.git_base.<name>" string — the
        # string form can bind a DIFFERENT `lib` package (ADR-045).
        monkeypatch.setattr(git_base, "_popen_git", boom)
        proc = run_git_bytes_soft(["show", "HEAD:triage.jsonl"], cwd=repo)

        assert proc.returncode == TIMEOUT_RETURNCODE
        # Partial output is DISCARDED deliberately: half a blob compared against a
        # whole file is a wrong answer, where b"" routes to the fail-safe branch.
        assert proc.stdout == b""
        assert isinstance(proc.stderr, bytes)
        assert b"timed out" in proc.stderr

    def test_text_soft_timeout_mapping_is_unchanged(self, repo: Path, monkeypatch) -> None:
        """Characterization — ``run_git_soft``'s own timeout contract (str streams,
        same return code) must survive the extraction."""
        def boom(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=0.01)

        monkeypatch.setattr(git_base, "_popen_git", boom)
        proc = run_git_soft(["show", "HEAD:triage.jsonl"], cwd=repo)

        assert proc.returncode == TIMEOUT_RETURNCODE
        assert proc.stdout == ""
        assert isinstance(proc.stderr, str)
        assert "timed out" in proc.stderr


class TestTextModeUnchanged:
    """AC-7 — characterization for the ~133 existing ``run_git`` callers."""

    def test_text_mode_still_replaces_the_broken_byte(self, repo: Path) -> None:
        proc = run_git(["show", "HEAD:triage.jsonl"], cwd=repo)
        assert isinstance(proc.stdout, str)
        assert "�" in proc.stdout
        assert "\udcff" not in proc.stdout

    def test_text_mode_stderr_decodes_to_str(self, repo: Path) -> None:
        proc = run_git_soft(["show", "HEAD:absent.jsonl"], cwd=repo)
        assert proc.returncode != 0
        assert isinstance(proc.stderr, str)
        assert proc.stderr.strip()

    def test_check_true_still_raises_giterror(self, repo: Path) -> None:
        with pytest.raises(GitError):
            run_git(["show", "HEAD:absent.jsonl"], cwd=repo)

    def test_check_false_reports_the_exit_code(self, repo: Path) -> None:
        proc = run_git(["show", "HEAD:absent.jsonl"], cwd=repo, check=False)
        assert proc.returncode != 0
        assert proc.stdout == ""
