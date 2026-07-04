"""Tests for the grade.py CLI wrapper (deterministic, non-interactive)."""

from __future__ import annotations

import json
from pathlib import Path

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

    def test_output_is_utf8_encodable(self, well_run_repo: Path, capsys):
        # The card carries em dashes / ellipses; every format must be UTF-8
        # encodable (the CLI forces UTF-8 stdio so a cp1252 console can't crash).
        for fmt in ("terminal", "markdown", "json"):
            run([str(well_run_repo), "--format", fmt])
            out = capsys.readouterr().out
            out.encode("utf-8")  # raises if any surrogate/unencodable char

    def test_non_git_dir_exits_2(self, non_git_dir: Path, capsys):
        assert run([str(non_git_dir)]) == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_url_exits_2(self, capsys):
        assert run(["https://github.com/x/y"]) == 2

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
