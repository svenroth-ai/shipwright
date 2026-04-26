"""Verify playwright_setup surfaces non-zero npm/npx exit codes (sub-iterate F).

External review caught a false-success bug: the original code didn't check
`subprocess.run(...).returncode`, so a failed `npm install` still produced
`success: True` with the misleading action `"Installed @playwright/test"`.
This test pins the corrected behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import playwright_setup  # noqa: E402


def _make_minimal_pkg(root: Path) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {}}), encoding="utf-8"
    )


def test_npm_install_failure_returns_success_false_with_stderr_tail(tmp_path, monkeypatch):
    _make_minimal_pkg(tmp_path)

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = "npm warn audit something"
            stderr = "npm ERR! 404 Not Found - GET https://registry.example/foo — package missing"

        return _R()

    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(playwright_setup, "resolve_executable", lambda n: n)

    result = playwright_setup.setup(tmp_path)

    assert result["success"] is False
    assert "404" in result["error"] or "ERR" in result["error"]
    # The setup_dir is still surfaced for diagnostics
    assert result.get("setup_dir") == str(tmp_path)


def test_npx_install_failure_returns_success_false(tmp_path, monkeypatch):
    """Same false-success surface for `npx playwright install chromium`."""
    # Pretend @playwright/test + tsx are already installed, so we skip the npm
    # install loop and only npx playwright install runs.
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "devDependencies": {
            "@playwright/test": "1.0.0", "tsx": "4.0.0"
        }}), encoding="utf-8"
    )

    def fake_run(cmd, **kwargs):
        # Identify by argv[0]: real `npx playwright install chromium` should fail.
        cmd_str = " ".join(cmd)
        rc = 1 if "playwright" in cmd_str else 0

        class _R:
            returncode = rc
            stdout = ""
            stderr = "Failed to download Chromium: ENOSPC" if rc else ""

        return _R()

    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(playwright_setup, "resolve_executable", lambda n: n)

    result = playwright_setup.setup(tmp_path)
    assert result["success"] is False
    assert "ENOSPC" in result["error"] or "playwright install" in result["error"]


def test_tsx_install_failure_is_non_critical(tmp_path, monkeypatch):
    """tsx is documented as non-critical — a tsx install failure must NOT fail
    the whole setup. The action log should carry a WARN entry though."""
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "devDependencies": {"@playwright/test": "1.0.0"}}),
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        # tsx install fails; everything else succeeds
        rc = 1 if "tsx" in cmd_str else 0

        class _R:
            returncode = rc
            stdout = ""
            stderr = "tsx install fail"

        return _R()

    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(playwright_setup, "resolve_executable", lambda n: n)

    result = playwright_setup.setup(tmp_path)
    assert result["success"] is True
    assert any("tsx" in a and "WARN" in a for a in result["actions"])


def test_npm_install_success_appends_action(tmp_path, monkeypatch):
    """Sanity: when subprocess returncode is 0, we still emit the success action."""
    _make_minimal_pkg(tmp_path)

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(playwright_setup, "resolve_executable", lambda n: n)

    result = playwright_setup.setup(tmp_path)
    assert result["success"] is True
    assert any("Installed @playwright/test" in a for a in result["actions"])
