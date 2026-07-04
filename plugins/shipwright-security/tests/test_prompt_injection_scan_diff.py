"""Regression for PR #125: the ``--diff`` scan path must apply the same
``SKIP_DIRS`` / ``SELF_REFERENCE_PATHS`` exclusion as the full-tree walk.

Since ``scan_python`` became string-literal aware (it blanks STRING / COMMENT
token spans before matching), the scanner's own source/tests — which carry
dynamic-execution pattern literals by design — no longer self-flag on a raw
scan. The ``SELF_REFERENCE_PATHS`` exclusion is retained as belt-and-suspenders
for the ``--diff`` path. Kept in its own file so the heavily-baselined
``test_prompt_injection_scan.py`` is not grown.
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

    def test_self_reference_files_no_longer_self_flag_but_stay_excluded(self):
        # The literal-aware scan_python means the scanner's own source/tests —
        # whose dynamic-exec patterns are all STRING LITERALS — no longer
        # self-flag on a raw scan (a revert of that fix would re-break this).
        # The SELF_REFERENCE exclusion is kept as belt-and-suspenders anyway.
        for rel in scanner.SELF_REFERENCE_PATHS:
            target = REPO_ROOT / rel
            assert scanner.scan_file(target, REPO_ROOT) == [], f"{rel} should not self-flag"
            assert scanner._is_excluded(target, REPO_ROOT), rel
