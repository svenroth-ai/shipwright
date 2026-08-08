"""Smoke tests for the check_mandated_load_coverage.py CLI wrapper.

Logic is unit-tested in test_mandated_load_coverage.py. The subprocess tests
below check the real process contract (argv parsing, stdout, exit code); the
``test_cli_*`` tests call ``main()`` in-process so ``check_mandated_load_
coverage.py``'s own lines register on diff coverage -- a subprocess child
runs outside the parent's coverage instrumentation, same pattern as
test_check_agent_doc_shape.py's ``test_cli_*`` tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "tools"
_SCRIPT = _TOOLS_ROOT / "check_mandated_load_coverage.py"
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

from tools.check_mandated_load_coverage import main  # noqa: E402


def _run(project_root: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-root", str(project_root), *extra_args],
        capture_output=True, text=True, check=False,
    )


def test_glob_expands_and_reports_each_match(tmp_path: Path) -> None:
    for split in ("01-a", "02-b"):
        d = tmp_path / ".shipwright" / "planning" / split
        d.mkdir(parents=True)
        (d / "spec.md").write_text("one line\n", encoding="utf-8")

    proc = _run(tmp_path, "--glob", ".shipwright/planning/*/spec.md")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert len(payload["files"]) == 2
    assert payload["any_exceeds_cap"] is False
    assert all(f["exists"] and f["total_lines"] == 1 for f in payload["files"])


def test_no_glob_matches_reports_empty_not_an_error(tmp_path: Path) -> None:
    proc = _run(tmp_path, "--glob", ".shipwright/planning/*/spec.md")
    assert proc.returncode == 0
    assert json.loads(proc.stdout) == {"files": [], "any_exceeds_cap": False, "escaped_project_root": []}


def test_absolute_path_is_reported_escaped_not_followed(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("shh\n", encoding="utf-8")
    project_root = tmp_path / "proj"
    project_root.mkdir()

    proc = _run(project_root, "--path", str(outside))
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["files"] == []
    assert payload["escaped_project_root"] == [str(outside)]


def test_dotdot_traversal_path_is_reported_escaped_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("shh\n", encoding="utf-8")
    project_root = tmp_path / "proj"
    project_root.mkdir()

    proc = _run(project_root, "--path", "../outside-secret.txt")
    payload = json.loads(proc.stdout)
    assert payload["files"] == []
    assert payload["escaped_project_root"] == ["../outside-secret.txt"]


def test_in_root_path_is_unaffected_by_containment_check(tmp_path: Path) -> None:
    (tmp_path / "spec.md").write_text("one line\n", encoding="utf-8")
    proc = _run(tmp_path, "--path", "spec.md")
    payload = json.loads(proc.stdout)
    assert payload["escaped_project_root"] == []
    assert payload["files"][0]["exists"] is True


def test_explicit_path_over_cap_lines_flag_exceeds(tmp_path: Path) -> None:
    f = tmp_path / "spec.md"
    f.write_text("\n".join(str(i) for i in range(20)) + "\n", encoding="utf-8")
    proc = _run(tmp_path, "--path", "spec.md", "--cap-lines", "5")
    payload = json.loads(proc.stdout)
    assert payload["files"][0]["exceeds_cap"] is True
    assert payload["any_exceeds_cap"] is True


def test_cli_glob_via_main_prints_report_and_returns_0(tmp_path, monkeypatch, capsys) -> None:
    d = tmp_path / ".shipwright" / "planning" / "01-a"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("one line\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "check_mandated_load_coverage.py", "--project-root", str(tmp_path),
        "--glob", ".shipwright/planning/*/spec.md",
    ])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["any_exceeds_cap"] is False
    assert payload["files"][0]["total_lines"] == 1


def test_cli_explicit_path_via_main_joins_project_root(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "spec.md").write_text("\n".join(str(i) for i in range(20)) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "check_mandated_load_coverage.py", "--project-root", str(tmp_path),
        "--path", "spec.md", "--cap-lines", "5",
    ])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"][0]["exists"] is True
    assert payload["files"][0]["exceeds_cap"] is True


def test_cli_via_main_reports_escaped_path_instead_of_following_it(tmp_path, monkeypatch, capsys) -> None:
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("shh\n", encoding="utf-8")
    project_root = tmp_path / "proj"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "check_mandated_load_coverage.py", "--project-root", str(project_root),
        "--path", "../outside-secret.txt",
    ])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["files"] == []
    assert payload["escaped_project_root"] == ["../outside-secret.txt"]
