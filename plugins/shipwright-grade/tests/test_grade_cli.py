"""Tests for the grade.py CLI wrapper (deterministic, non-interactive)."""

from __future__ import annotations

import json
from pathlib import Path

import clone
import grade
from clone import _run_clone
from grade import run


class TestGradeCli:
    def test_terminal_format_default(self, well_run_repo: Path, capsys):
        rc = run([str(well_run_repo)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Control Grade: A" in out
        assert "controls measured" in out  # A can't be quoted without the caveat
        assert "Controls Shipwright would light up" in out

    def test_markdown_format(self, well_run_repo: Path, capsys):
        rc = run([str(well_run_repo), "--format", "markdown"])
        assert rc == 0
        assert "# Control Grade: A" in capsys.readouterr().out

    def test_json_format_is_valid_and_stable(self, well_run_repo: Path, capsys):
        rc = run([str(well_run_repo), "--format", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["grade"] == "A"
        assert payload["mode"] == "heuristic"
        assert isinstance(payload["dimensions"], list)
        # n/a dimension carries provenance + None score in the schema.
        na = [d for d in payload["dimensions"] if d["score"] is None]
        assert na and na[0]["provenance"]["mode"] == "unavailable"

    def test_html_format_emits_self_contained_document(self, well_run_repo: Path, capsys):
        rc = run([str(well_run_repo), "--format", "html"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.lstrip().lower().startswith("<!doctype html>")
        assert "Content-Security-Policy" in out
        assert "Control Grade" in out
        # No external-request surface leaked through the CLI path: zero scripts,
        # no auto-fetch src, and the only link is the static CTA.
        assert "<script" not in out.lower()
        assert 'src="http' not in out.lower()
        import re as _re
        assert _re.findall(r'href="([^"]*)"', out) == ["https://svenroth.ai/shipwright"]

    def test_output_is_utf8_encodable(self, well_run_repo: Path, capsys):
        # The card carries em dashes / ellipses; every format must be UTF-8
        # encodable (the CLI forces UTF-8 stdio so a cp1252 console can't crash).
        for fmt in ("terminal", "markdown", "json", "html"):
            run([str(well_run_repo), "--format", fmt])
            out = capsys.readouterr().out
            out.encode("utf-8")  # raises if any surrogate/unencodable char

    def test_non_git_dir_exits_2(self, non_git_dir: Path, capsys):
        assert run([str(non_git_dir)]) == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_url_with_no_clone_exits_2_without_network(self, capsys):
        # Hermetic: --no-clone rejects a URL with a clean error, no network.
        assert run(["https://github.com/x/y", "--no-clone"]) == 2
        assert "requires cloning" in capsys.readouterr().err

    def test_url_is_cloned_and_graded(self, well_run_repo: Path, monkeypatch, capsys):
        # Clone-by-default: a URL grades. Cloning is redirected to a local repo
        # (allow_local) so the test stays offline.
        def fake_clone(raw, dest, **kwargs):
            _run_clone(str(well_run_repo), dest, allow_local=True)
            return dest
        monkeypatch.setattr(clone, "clone_repo", fake_clone)
        rc = run(["https://github.com/o/r", "--format", "json"])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["grade"] == "A"

    def test_standalone_never_blocks_on_input(self, well_run_repo: Path, monkeypatch):
        # AC4: the standalone CLI is non-interactive — prove it at RUNTIME by
        # replacing stdin with a guard that raises on ANY read; a real grade run
        # must complete without ever touching it.
        import sys

        class _NoStdin:
            def __getattr__(self, name):
                # Raise AttributeError (the __getattr__ contract — satisfies
                # CodeQL py/unexpected-raise-in-special-method); any real stdin
                # access still propagates out of run() and errors the test.
                raise AttributeError(
                    f"standalone CLI must never read stdin (touched sys.stdin.{name})")

        monkeypatch.setattr(sys, "stdin", _NoStdin())
        assert run([str(well_run_repo), "--format", "json"]) == 0

    def test_grade_module_has_no_input_call(self):
        # Belt-and-suspenders: no interactive prompt in the CLI source either.
        src = Path(grade.__file__).read_text(encoding="utf-8")
        assert "input(" not in src and "stdin.read" not in src

    def test_json_carries_g2_network_and_maintainability(self, well_run_repo: Path, capsys):
        rc = run([str(well_run_repo), "--format", "json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["network_enabled"] is False
        assert payload["network_enrichments"] == []
        maint = [d for d in payload["dimensions"] if d["key"] == "maintainability"][0]
        assert maint["score"] is not None            # G2 lights it locally
        assert "source files over 300 LOC" in maint["detail"]

    def test_allow_network_without_remote_stays_local_only(self, well_run_repo: Path, capsys):
        # The fixture has no remote, so --allow-network cannot enrich and must
        # NOT attempt any network call — it degrades to local-only, no crash.
        rc = run([str(well_run_repo), "--allow-network"])
        assert rc == 0
        assert "no GitHub remote" in capsys.readouterr().out
