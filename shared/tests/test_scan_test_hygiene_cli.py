"""CLI-level tests for shared/scripts/tools/scan_test_hygiene.py (TT4).

Exercises ``main()`` end-to-end in ``--files`` mode (no git needed): the exit
codes (0 pass / 1 findings / 2 usage), the Python+TS/JS routing, and the
``xfail`` skip form the core parametrization does not cover. The ``--diff``
git line-scoping is covered by ``added_lines_from_diff`` +
``filter_to_changed`` unit tests in ``test_ts_test_hygiene.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CLI_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "tools" / "scan_test_hygiene.py"
)
_spec = importlib.util.spec_from_file_location("scan_test_hygiene_cli", _CLI_PATH)
assert _spec and _spec.loader
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def _write(tmp_path: Path, name: str, body: str) -> str:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_clean_quarantined_spec_exits_zero(tmp_path: Path) -> None:
    body = (
        "// @quarantine\n// reason: flaky\n// owner: @o\n// ticket: T\n"
        "// expires: 2026-12-31\ntest.skip('a', () => {})\n"
    )
    f = _write(tmp_path, "a.spec.ts", body)
    assert cli.main(["--files", f]) == 0


def test_focused_test_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    f = _write(tmp_path, "a.spec.ts", "test.only('a', () => {})\n")
    assert cli.main(["--files", f]) == 1
    assert "js.only" in capsys.readouterr().out


def test_bare_xfail_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    f = _write(tmp_path, "a.spec.ts", "xfail('a', () => {})\n")
    assert cli.main(["--files", f]) == 1
    assert "js.skip.no_quarantine" in capsys.readouterr().out


def test_unsupported_suffix_exits_two(tmp_path: Path) -> None:
    f = _write(tmp_path, "notes.md", "test.only(x)\n")
    assert cli.main(["--files", f]) == 2


def test_python_and_ts_routed_together(tmp_path: Path) -> None:
    py = _write(tmp_path, "test_x.py", "import pytest\npytest.skip('x')\n")
    ts = _write(tmp_path, "x.spec.ts", "test.only('a', () => {})\n")
    # Both legs must report; a single finding is enough to fail the gate.
    assert cli.main(["--files", py, ts]) == 1


def test_json_output_is_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    import json

    f = _write(tmp_path, "a.spec.ts", "test.only('a', () => {})\n")
    assert cli.main(["--files", f, "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings_count"] == 1
    assert payload["findings"][0]["pattern"] == "js.only"
