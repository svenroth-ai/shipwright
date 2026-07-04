"""Regression: the Python scanner matches executable *code*, not token text
that merely appears inside string literals, docstrings, or inline comments.

Covers the false-positive class in prompt_risks.json (CI run 28686996368): a
security-audit test that lists ``"os.system("`` / ``"eval("`` / ``"exec("`` as
forbidden STRING LITERALS was reported as high-severity "dangerous Python
pattern" findings although it contains no such calls. Kept in its own file so
the heavily-baselined ``test_prompt_injection_scan.py`` is not grown.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import prompt_injection_scan as scanner  # noqa: E402
from py_token_filter import blank_noncode_spans  # noqa: E402


class TestPythonScannerIgnoresStringsAndComments:

    def test_string_literal_tokens_not_flagged(self, tmp_path):
        # Mirrors plugins/shipwright-grade/tests/test_reused_collector_audit.py:
        # a tuple of forbidden tokens used for a negative assertion.
        content = (
            '_FORBIDDEN = ("os.system(", "eval(", "exec(", "pickle.loads(")\n'
            "\n"
            "def check(src):\n"
            "    for token in _FORBIDDEN:\n"
            "        assert token not in src\n"
        )
        p = tmp_path / "audit.py"
        p.write_text(content, encoding="utf-8")
        assert scanner.scan_python(p, "audit.py") == []

    def test_docstring_tokens_not_flagged(self, tmp_path):
        content = (
            "def f():\n"
            '    """Prose mentioning os.system( and eval( must not trip."""\n'
            "    return 1\n"
        )
        p = tmp_path / "doc.py"
        p.write_text(content, encoding="utf-8")
        assert scanner.scan_python(p, "doc.py") == []

    def test_inline_trailing_comment_not_flagged(self, tmp_path):
        content = "x = 1  # eval( example, os.system( too\n"
        p = tmp_path / "inline.py"
        p.write_text(content, encoding="utf-8")
        assert scanner.scan_python(p, "inline.py") == []

    def test_real_calls_still_flagged(self, tmp_path):
        content = "import os\nos.system(cmd)\neval(expr)\nexec(code)\n"
        p = tmp_path / "real.py"
        p.write_text(content, encoding="utf-8")
        rules = {f["rule"] for f in scanner.scan_python(p, "real.py")}
        assert "PY_OS_SYSTEM" in rules
        assert "PY_EVAL" in rules
        assert "PY_EXEC" in rules

    def test_subprocess_shell_true_with_string_arg_still_flagged(self, tmp_path):
        # The string arg is neutralized, but the multi-token shell=True pattern
        # must still match across the blanked span (positions preserved).
        content = 'import subprocess\nsubprocess.run("rm -rf /", shell=True)\n'
        p = tmp_path / "shell.py"
        p.write_text(content, encoding="utf-8")
        findings = scanner.scan_python(p, "shell.py")
        assert any(f["rule"] == "PY_SHELL_TRUE" for f in findings)

    def test_affected_line_survives_preceding_multiline_string(self, tmp_path):
        # A multiline string precedes a real call; blanking preserves line
        # structure so the reported line stays accurate.
        content = (
            'BANNER = """\n'
            "line two mentions eval( but is data\n"
            "line three\n"
            '"""\n'
            "os.system(cmd)\n"
        )
        p = tmp_path / "multiline.py"
        p.write_text(content, encoding="utf-8")
        os_findings = [
            f for f in scanner.scan_python(p, "multiline.py") if f["rule"] == "PY_OS_SYSTEM"
        ]
        assert len(os_findings) == 1
        assert os_findings[0]["affected_line"] == 5

    def test_invalid_python_falls_back_to_line_scan(self, tmp_path):
        # tokenize raises on invalid Python (unterminated string) → the scan must
        # fail safe to the line-based path so a real dangerous call is still seen.
        content = 'x = "unterminated\nos.system(cmd)\n'
        p = tmp_path / "broken.py"
        p.write_text(content, encoding="utf-8")
        findings = scanner.scan_python(p, "broken.py")
        assert any(f["rule"] == "PY_OS_SYSTEM" for f in findings)


class TestBlankNoncodeSpans:

    def test_blanks_string_content_but_keeps_code(self):
        out = blank_noncode_spans('x = "eval("\nos.system(y)\n')
        assert "eval(" not in out            # string content blanked
        assert "os.system(y)" in out         # executable code kept verbatim

    def test_preserves_newline_count(self):
        src = 'a = """\ntwo\nthree\n"""\nb = 1\n'
        assert blank_noncode_spans(src).count("\n") == src.count("\n")

    def test_invalid_python_returns_original_verbatim(self):
        src = 'x = "unterminated\n'
        assert blank_noncode_spans(src) == src
