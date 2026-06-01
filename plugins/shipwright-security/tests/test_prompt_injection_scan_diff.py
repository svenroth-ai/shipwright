"""Regression for PR #125: the ``--diff`` scan path must apply the same
``SKIP_DIRS`` / ``SELF_REFERENCE_PATHS`` exclusion as the full-tree walk.

Without it, a PR whose diff touches the scanner's own source/tests — which
carry dynamic-execution pattern literals by design — yields false-positive
PY_EVAL / PY_EXEC findings (the noise seen on PR #125). Kept in its own file so
the heavily-baselined ``test_prompt_injection_scan.py`` is not grown.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import prompt_injection_scan as scanner  # noqa: E402

REPO_ROOT = PLUGIN_ROOT.parents[1]


class TestDiffModeExclusion:
    def test_self_reference_files_are_excluded(self):
        for rel in scanner.SELF_REFERENCE_PATHS:
            assert scanner._is_excluded(REPO_ROOT / rel, REPO_ROOT), rel

    def test_skip_dir_file_excluded(self):
        p = REPO_ROOT / "plugins/shipwright-security/tests/fixtures/x.py"
        assert scanner._is_excluded(p, REPO_ROOT)

    def test_ordinary_file_not_excluded(self):
        p = REPO_ROOT / "plugins/shipwright-security/scripts/tools/scan.py"
        assert not scanner._is_excluded(p, REPO_ROOT)

    def test_self_reference_test_file_would_flag_but_is_excluded(self):
        # scan_file DOES flag this file's dynamic-exec fixtures; the exclusion
        # is precisely what keeps diff-mode from reporting them.
        target = REPO_ROOT / "plugins/shipwright-security/tests/test_prompt_injection_scan.py"
        assert scanner.scan_file(target, REPO_ROOT), "raw scan_file should flag the fixtures"
        assert scanner._is_excluded(target, REPO_ROOT)
