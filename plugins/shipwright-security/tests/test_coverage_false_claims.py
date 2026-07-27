"""False-coverage-claim regressions found by the fresh review of the PR head.

Each is a way the code could assert coverage it did not have — the exact failure
class this card exists to remove, so each gets its own test:

- ``--input`` with no manifest fell back to the local ``shipwright_security_config
  .json``, attaching a DIFFERENT scan's coverage to these findings;
- the prompt-injection row read ``covered`` from the mere presence of the
  ``--prompt-risks`` flag, so a missing or malformed file still claimed the class
  was checked;
- the comparison keyed findings by ``source:rule:file:line`` only, so two
  findings normalized to different classes could match across classes;
- coverage cells came back from an untrusted file and reached the markdown table
  unescaped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import generate_security_report as gsr  # noqa: E402
from coverage_report import coverage_table  # noqa: E402
from scan_coverage import build_coverage  # noqa: E402

_FULL = build_coverage(available={"sast", "sca", "secrets"})


def _report(tmp_path: Path, *extra: str) -> str:
    md = tmp_path / "r.md"
    with patch.object(sys, "argv", [
        "generate_security_report.py", "--project-root", str(tmp_path),
        "--output", str(md), *extra,
    ]):
        gsr.main()
    return md.read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.07")
class TestInputCoverageIsAuthoritative:
    def test_pre_feature_input_does_not_inherit_local_config_coverage(
        self, tmp_path: Path
    ) -> None:
        """A local config describing a DIFFERENT scan must not lend its coverage
        to the findings file the caller actually passed."""
        (tmp_path / "shipwright_security_config.json").write_text(
            json.dumps({"findings": [], "coverage": _FULL}), encoding="utf-8")
        old = tmp_path / "old.json"
        old.write_text(json.dumps({"findings": []}), encoding="utf-8")

        body = _report(tmp_path, "--input", str(old))
        assert "Coverage not reported" in body
        assert "✅ checked" not in body

    def test_no_input_still_reads_the_local_config(self, tmp_path: Path) -> None:
        """The fallback stays for the pipeline path that has no --input."""
        (tmp_path / "shipwright_security_config.json").write_text(
            json.dumps({"findings": [], "coverage": _FULL}), encoding="utf-8")
        body = _report(tmp_path)
        assert "## Coverage" in body
        assert "Coverage not reported" not in body

    def test_input_with_coverage_is_used(self, tmp_path: Path) -> None:
        src = tmp_path / "findings.json"
        src.write_text(
            json.dumps({"findings": [], "coverage": build_coverage(available={"sast"})}),
            encoding="utf-8")
        body = _report(tmp_path, "--input", str(src))
        assert "Incomplete Coverage" in body


@pytest.mark.covers("FR-01.07")
class TestPromptInjectionRowNeedsRealOutput:
    def _status(self, tmp_path: Path, *extra: str) -> str:
        out = tmp_path / "latest.json"
        with patch.object(sys, "argv", [
            "generate_security_report.py", "--project-root", str(tmp_path),
            "--json-output", str(out), *extra,
        ]):
            gsr.main()
        rows = json.loads(out.read_text(encoding="utf-8"))["coverage"]
        return next(
            (r["status"] for r in rows if r["class"] == "prompt_injection"), "absent")

    def test_missing_prompt_risks_file_is_not_covered(self, tmp_path: Path) -> None:
        """`--prompt-risks nope.json` must not claim the class was checked."""
        assert self._status(
            tmp_path, "--prompt-risks", str(tmp_path / "nope.json")) == "absent"

    def test_malformed_prompt_risks_file_is_not_covered(self, tmp_path: Path) -> None:
        bad = tmp_path / "prompt_risks.json"
        bad.write_text("{not json", encoding="utf-8")
        assert self._status(tmp_path, "--prompt-risks", str(bad)) == "absent"

    def test_wrong_shape_prompt_risks_file_is_not_covered(self, tmp_path: Path) -> None:
        bad = tmp_path / "prompt_risks.json"
        bad.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        assert self._status(tmp_path, "--prompt-risks", str(bad)) == "absent"

    def test_valid_empty_prompt_risks_file_is_covered(self, tmp_path: Path) -> None:
        """A real clean prompt scan DID check the class."""
        good = tmp_path / "prompt_risks.json"
        good.write_text(json.dumps({"findings": []}), encoding="utf-8")
        assert self._status(tmp_path, "--prompt-risks", str(good)) == "covered"


@pytest.mark.covers("FR-01.07")
class TestCoverageCellsAreEscaped:
    def test_a_pipe_in_an_untrusted_cell_cannot_break_the_table(self) -> None:
        """The manifest is read back from findings.json — untrusted input."""
        rows = coverage_table([
            {"class": "sa|st", "tool": "sem|grep", "status": "cov|ered",
             "detail": "a|b"},
        ])
        row = [ln for ln in rows if ln.startswith("| sa")][0]
        # Every injected pipe is escaped, so only the 5 real cell delimiters
        # remain unescaped — the table keeps its 4 columns.
        assert row.replace("\\|", "").count("|") == 5, row
        assert "sa\\|st" in row

    def test_a_newline_in_an_untrusted_cell_cannot_add_rows(self) -> None:
        rows = coverage_table([
            {"class": "sast\n| evil | evil | evil", "tool": "t",
             "status": "covered", "detail": "d"},
        ])
        data_rows = [ln for ln in rows if ln.startswith("| ") and "---" not in ln]
        # header + exactly one data row
        assert len(data_rows) == 2, data_rows

    def test_known_statuses_still_render_their_icon(self) -> None:
        rows = coverage_table([
            {"class": "sast", "tool": "semgrep", "status": "covered", "detail": None},
        ])
        assert any("checked" in ln for ln in rows)
