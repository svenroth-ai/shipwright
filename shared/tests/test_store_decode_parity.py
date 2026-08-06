"""The triage store's two sides must decode a byte the SAME way — the seam itself.

A triage line is compared across a seam: one side is a git blob, the other is the
file on disk. Both sides used to pick their own decode error handler —
``lib.git_base.run_git`` is fixed on ``errors="replace"`` (a bad byte becomes
``U+FFFD``), while ``lib.sweep_text.read_text_verbatim`` uses
``errors="surrogateescape"`` (the same byte becomes ``U+DCFF``). For any line
carrying a byte that is not valid UTF-8 the two sides therefore produced DIFFERENT
strings for IDENTICAL bytes, and no comparison built on them could ever match again
(iterate-2026-08-06-gc-decode-parity).

This module pins the seam and the one shared decode rule. The three CONSUMERS whose
behaviour the asymmetry broke — the delivered-line GC, the drift plan, the reconcile
fold count — live in ``test_sweep_store_decode_parity.py``, which needs the real
git/worktree/origin plumbing this module deliberately does without.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib.git_base import run_git_bytes_soft  # noqa: E402
from lib.sweep_text import decode_store_text, read_text_verbatim  # noqa: E402


class TestDecodeParity:
    """AC-2 — the seam itself, independent of any consumer.

    Note what carries the weight here. ``read_text_verbatim`` IS
    ``decode_store_text(path.read_bytes())`` now, so the equality below is
    STRUCTURAL — one function, so it cannot disagree with itself, which is the
    point of the design. The two codepoint assertions are the real pin: they fail
    if either side is reverted to ``errors="replace"``. A future caller that
    reintroduces the text-mode helper on the BLOB side is caught by the consumer
    tests in ``test_sweep_store_decode_parity.py``, not here
    (Stage-3 doubt review).
    """

    def test_git_blob_and_file_read_agree_on_a_broken_byte(self, tmp_path: Path) -> None:
        work = tmp_path / "work"
        work.mkdir()

        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "parity@test.invalid")
        git("config", "user.name", "Parity Test")
        path = work / "triage.jsonl"
        path.write_bytes(h.broken_bytes(h.spliceable_status("trg-parity1")) + b"\n")
        git("add", "--", "triage.jsonl")
        git("commit", "-qm", "seed")

        blob = run_git_bytes_soft(["show", "HEAD:triage.jsonl"], cwd=work)
        assert blob.returncode == 0

        from_git = decode_store_text(blob.stdout)
        from_disk = read_text_verbatim(path)

        assert from_git == from_disk
        # And specifically: the SURROGATE form on both sides, never the lossy one.
        assert "\udcff" in from_git and "\udcff" in from_disk
        assert "�" not in from_git


class TestDecodeStoreText:
    """Characterization of the one decode rule (external plan review, finding 4).

    ``read_text_verbatim`` now routes through ``decode_store_text``; these pin the
    properties callers already relied on, so the rewiring cannot quietly change
    ordinary reads.
    """

    def test_plain_utf8_is_unaffected(self, tmp_path: Path) -> None:
        p = tmp_path / "a.jsonl"
        p.write_bytes('{"note":"café ✓"}\n'.encode("utf-8"))
        assert read_text_verbatim(p) == '{"note":"café ✓"}\n'

    @pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
    def test_line_endings_survive_verbatim(self, tmp_path: Path, eol: bytes) -> None:
        """No newline translation, either way — a CRLF log must not silently become
        LF (that is what the old ``newline=""`` bought)."""
        p = tmp_path / "b.jsonl"
        p.write_bytes(b'{"a":1}' + eol + b'{"a":2}' + eol)
        assert read_text_verbatim(p) == ('{"a":1}' + eol.decode() + '{"a":2}' + eol.decode())

    def test_surrogateescape_round_trips_to_the_original_bytes(self, tmp_path: Path) -> None:
        """The property that makes this fix lossless where ``replace`` is not."""
        p = tmp_path / "c.jsonl"
        raw = h.broken_bytes(h.spliceable_status("trg-round1")) + b"\n"
        p.write_bytes(raw)
        assert read_text_verbatim(p).encode("utf-8", errors="surrogateescape") == raw

    def test_a_bom_is_preserved_not_stripped(self, tmp_path: Path) -> None:
        """Plan-review finding 7, checked rather than assumed: only ``utf-8-sig``
        strips a BOM, so byte-reading changes nothing here."""
        p = tmp_path / "d.jsonl"
        p.write_bytes(b"\xef\xbb\xbf" + b'{"a":1}\n')
        assert read_text_verbatim(p) == "﻿" + '{"a":1}\n'

    def test_missing_file_is_empty_string(self, tmp_path: Path) -> None:
        assert read_text_verbatim(tmp_path / "nope.jsonl") == ""
