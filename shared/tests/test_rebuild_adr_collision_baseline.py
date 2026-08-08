"""CLI coverage for ``scripts/tools/rebuild_adr_collision_baseline.py``.

Calls ``main()`` in-process (never via ``subprocess``) — a subprocess-invoked
CLI test is invisible to this repo's diff-coverage gate (a documented
landmine: the child interpreter's coverage never merges back into the
parent's measurement).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.rebuild_adr_collision_baseline import main


def _adr(root: Path, name: str, body: str) -> Path:
    folder = root / ".shipwright" / "planning" / "adr"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def test_no_adr_folder_is_a_no_op(tmp_path, capsys):
    assert main(["--project-root", str(tmp_path)]) == 0
    assert not (tmp_path / "shipwright_adr_collision_baseline.json").exists()
    assert "nothing to do" in capsys.readouterr().out


def test_regenerates_the_baseline_at_the_project_root(tmp_path, capsys):
    _adr(tmp_path, "500-a.md", "# A\n")
    _adr(tmp_path, "500-b.md", "# B\n")
    _adr(tmp_path, "501-solo.md", "# Solo\n")  # not a collision — excluded

    assert main(["--project-root", str(tmp_path)]) == 0

    baseline_path = tmp_path / "shipwright_adr_collision_baseline.json"
    assert baseline_path.is_file()
    doc = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert doc == {"version": 1, "entries": {"500": ["500-a.md", "500-b.md"]}}
    assert "regenerated" in capsys.readouterr().out


def test_output_has_lf_line_endings_only(tmp_path):
    _adr(tmp_path, "500-a.md", "# A\n")
    _adr(tmp_path, "500-b.md", "# B\n")
    main(["--project-root", str(tmp_path)])
    raw = (tmp_path / "shipwright_adr_collision_baseline.json").read_bytes()
    assert b"\r" not in raw
