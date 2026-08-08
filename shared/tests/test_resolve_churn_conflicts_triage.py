"""Triage-log-specific cases for the churn-conflict resolver (git integration).

Split out of ``test_resolve_churn_conflicts.py`` when that file crossed the
300-LOC guideline (iterate-2026-08-08-triage-amend-event added an orphan-amend
case). Shares real-git plumbing with the parent module via
``_churn_conflicts_helpers``. The non-triage git-integration cases (preflight,
churn-only merge, events log, regenerate) stay in the parent file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))  # shared/scripts — wins

from lib.churn_merge import TRIAGE_LOG  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402

from _churn_conflicts_helpers import (  # noqa: E402
    TRIAGE_HEADER as _TRIAGE_HEADER,
    git as _git,
    make_conflict_repo as _make_conflict_repo,
)


def test_triage_deduped_and_validated_even_without_conflict(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    dup = '{"event":"append","id":"trg-a"}'
    log.write_text(f"{_TRIAGE_HEADER}\n{dup}\n{dup}\n", encoding="utf-8")  # dup twice
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "triage")

    result = rcc.complete_merge(tmp_path, run_id="iterate-x")

    text = log.read_text(encoding="utf-8")
    assert text.count("trg-a") == 1                 # exact-line dedup ran
    assert "schema" in text.splitlines()[0]          # header preserved
    assert result.status in ("resolved", "clean")


def test_triage_conflict_unions_both_sides(tmp_path: Path) -> None:
    """Codex BLOCKER fix: a hard triage.jsonl conflict UNIONS both sides (keeps
    ours AND theirs items). Target projects lack the merge=union driver, so the
    old `--ours` path would silently drop the other side's backlog items.
    """
    merge = _make_conflict_repo(
        tmp_path,
        {".shipwright/triage.jsonl": (
            f"{_TRIAGE_HEADER}\n",
            f'{_TRIAGE_HEADER}\n{{"event":"append","id":"trg-ours"}}\n',
            f'{_TRIAGE_HEADER}\n{{"event":"append","id":"trg-theirs"}}\n',
        )},
    )
    assert merge.returncode != 0
    result = rcc.complete_merge(tmp_path, run_id=None)
    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []
    assert TRIAGE_LOG in result.resolved
    text = (tmp_path / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert "trg-ours" in text and "trg-theirs" in text  # NEITHER side dropped
    assert text.count("schema") == 1                    # header deduped to one


def test_triage_conflict_unions_non_ascii_byte_identical(tmp_path: Path) -> None:
    """WP6/F22 regression: a hard triage.jsonl conflict whose lines carry
    non-ASCII content (CJK, em-dash, accented) must round-trip BYTE-IDENTICAL
    through ``_union_conflict`` — i.e. ``git show :2:/:3:`` is decoded UTF-8 and
    re-encoded UTF-8, never via the Windows cp1252 locale (which would mojibake
    the tracked log — the sole safety net in repos lacking the merge=union
    driver). Asserts the exact bytes of each side survive in the unioned file.
    """
    ours_line = '{"event":"append","id":"trg-ours","title":"鸢尾花 — café façade"}'
    theirs_line = '{"event":"append","id":"trg-theirs","title":"naïve Москва ☃"}'
    merge = _make_conflict_repo(
        tmp_path,
        {".shipwright/triage.jsonl": (
            f"{_TRIAGE_HEADER}\n",
            f"{_TRIAGE_HEADER}\n{ours_line}\n",
            f"{_TRIAGE_HEADER}\n{theirs_line}\n",
        )},
    )
    assert merge.returncode != 0

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []
    assert TRIAGE_LOG in result.resolved
    # Byte-identity of the CONTENT (external-review code #3): decode strict UTF-8
    # (mojibake would raise here), then assert each line's exact UTF-8 bytes — in
    # exact order, with the header deduped to one. Line endings are compared after
    # universal-newline normalization: `write_text`/`git show` apply the platform
    # newline (CRLF on Windows) and the real merge path re-normalizes via
    # `dedup_triage_lines`/`splitlines()`, so the EOL byte is orthogonal to the
    # F22 encoding contract. What F22 guarantees — and this asserts — is that no
    # character of the multi-byte payload is altered, dropped, or re-encoded.
    raw = (tmp_path / ".shipwright" / "triage.jsonl").read_bytes()
    lines = raw.decode("utf-8").splitlines()  # strict decode; EOL-normalized
    assert lines == [_TRIAGE_HEADER, ours_line, theirs_line], (
        "unioned triage.jsonl content not byte-identical to the UTF-8 source"
    )
    # And the exact raw UTF-8 byte sequence of each non-ASCII payload is on disk.
    assert "鸢尾花 — café façade".encode("utf-8") in raw
    assert "naïve Москва ☃".encode("utf-8") in raw


def test_triage_conflict_non_utf8_byte_returns_triage_invalid_not_traceback(tmp_path: Path) -> None:
    """WP6/F22 hardening (external-review Gemini/OpenAI MED): a triage.jsonl stage
    carrying a legacy non-UTF-8 byte must NOT crash _union_conflict with a bare
    traceback (None.splitlines() on Windows / UnicodeDecodeError on POSIX) — it
    must translate to a structured ``triage_invalid`` status and abort the merge,
    preserving the JSON-status contract. Strict UTF-8 keeps the round-trip
    byte-identical; this is the loud-fail path for genuinely-corrupt input.
    """
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    # base: valid header + one valid line.
    log.write_bytes(f"{_TRIAGE_HEADER}\n".encode("utf-8") + b'{"event":"append","id":"trg-base"}\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "checkout", "-b", "theirs")
    # theirs: append a line with a raw cp1252-undefined byte (0x81) — NOT valid UTF-8.
    log.write_bytes(
        f"{_TRIAGE_HEADER}\n".encode("utf-8")
        + b'{"event":"append","id":"trg-base"}\n'
        + b'{"event":"append","id":"trg-\x81bad"}\n'
    )
    _git(tmp_path, "commit", "-am", "theirs adds non-utf8 byte")
    _git(tmp_path, "checkout", "main")
    _git(tmp_path, "checkout", "-b", "ours")
    log.write_bytes(
        f"{_TRIAGE_HEADER}\n".encode("utf-8")
        + b'{"event":"append","id":"trg-base"}\n'
        + b'{"event":"append","id":"trg-ours"}\n'
    )
    _git(tmp_path, "commit", "-am", "ours")
    merge = _git(tmp_path, "merge", "theirs", "-m", "merge", check=False)
    assert merge.returncode != 0  # conflict

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "triage_invalid"
    assert result.exit_code == 4
    assert any("UTF-8" in e for e in result.errors)
    # Merge aborted: no unmerged paths left wedged.
    assert rcc.conflicted_paths(tmp_path) == []


def test_triage_invalid_when_header_dropped(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('{"event":"append","id":"trg-1"}\n', encoding="utf-8")  # no header
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "triage")

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "triage_invalid"
    assert result.exit_code == 4
    assert any("header" in e for e in result.errors)


def test_triage_invalid_on_orphan_amend_same_as_orphan_status(tmp_path: Path) -> None:
    """iterate-2026-08-08-triage-amend-event, AC11: an `amend` whose id has no
    `append` anywhere surfaces through `_reconcile_triage` the same way an
    orphan `status` already does — `validate_triage_text`'s raw error list
    (which this resolver reads, not the recoverable/`has_non_orphan_error`
    split) is non-empty either way."""
    _git(tmp_path, "init", "-b", "main")
    log = tmp_path / ".shipwright" / "triage.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    orphan_amend = '{"event":"amend","id":"trg-ghost","by":"cli","title":"x"}'
    log.write_text(f"{_TRIAGE_HEADER}\n{orphan_amend}\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "triage")

    result = rcc.complete_merge(tmp_path, run_id=None)

    assert result.status == "triage_invalid"
    assert any("amend" in e and "no append anywhere" in e for e in result.errors)
