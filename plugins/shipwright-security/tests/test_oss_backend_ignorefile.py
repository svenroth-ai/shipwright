"""Tests for the Trivy accepted-risk register (``--ignorefile`` wiring).

Split out of test_oss_backend.py so that already-large file does not ratchet
its bloat baseline for new-coverage growth.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scripts/lib is on path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from oss_backend import _resolve_trivy_ignorefile, _run_trivy


class TestTrivyIgnorefile:
    """``_run_trivy`` passes ``--ignorefile`` for a ``.trivyignore.yaml`` /
    ``.trivyignore`` at the SCANNED target root (the accepted-risk register)."""

    @patch("subprocess.run")
    def test_trivy_cmd_passes_ignorefile_when_present(
        self, mock_run, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"Results":[]}', stderr=""
        )
        ignore = tmp_path / ".trivyignore.yaml"
        ignore.write_text("vulnerabilities: []\n", encoding="utf-8")
        _run_trivy(str(tmp_path))
        cmd = mock_run.call_args[0][0]
        assert "--ignorefile" in cmd, f"expected --ignorefile in {cmd}"
        assert cmd[cmd.index("--ignorefile") + 1] == str(ignore)
        # target stays last so the existing positional contract holds
        assert cmd[-1] == str(tmp_path)

    @patch("subprocess.run")
    def test_trivy_cmd_omits_ignorefile_when_absent(
        self, mock_run, monkeypatch, tmp_path
    ):
        monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"Results":[]}', stderr=""
        )
        _run_trivy(str(tmp_path))  # empty dir — no ignore file present
        cmd = mock_run.call_args[0][0]
        assert "--ignorefile" not in cmd

    def test_resolve_prefers_yaml_over_classic(self, tmp_path):
        (tmp_path / ".trivyignore").write_text("CVE-X\n", encoding="utf-8")
        (tmp_path / ".trivyignore.yaml").write_text(
            "vulnerabilities: []\n", encoding="utf-8"
        )
        assert _resolve_trivy_ignorefile(str(tmp_path)) == str(
            tmp_path / ".trivyignore.yaml"
        )

    def test_resolve_returns_none_when_absent(self, tmp_path):
        assert _resolve_trivy_ignorefile(str(tmp_path)) is None
