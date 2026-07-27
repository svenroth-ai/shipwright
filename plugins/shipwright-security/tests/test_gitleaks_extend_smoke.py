"""Real-binary proof that the generated gitleaks config EXTENDS the project's.

The external review's HIGH finding: a rendered-TOML unit test proves what we
wrote, not what gitleaks does with it. Whether `[extend] path` merges the
project's rules and allowlist alongside the shipwright path exclusions is
gitleaks' behaviour, and it is version-dependent — so it has to be exercised
against the pinned binary rather than assumed.

Runs wherever gitleaks is installed and HARD-FAILS in CI when it is not
(`skip_or_fail_on_missing_binary`, ADR-044) — CI installs gitleaks 8.21.2 in
`.github/workflows/security.yml`, so a silent skip there would hide exactly the
regression this file exists to catch.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
REPO_ROOT = PLUGIN_ROOT.parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402
from gitleaks_config import PROJECT_CONFIG_NAME  # noqa: E402
from oss_backend import _run_gitleaks  # noqa: E402

_INSTALL_HINT = (
    "Install gitleaks: `winget install Gitleaks.Gitleaks` (Windows), "
    "`brew install gitleaks` (macOS), or see "
    "https://github.com/gitleaks/gitleaks/releases. CI installs it in "
    ".github/workflows/security.yml."
)

# Assembled from fragments so this source file is not itself a gitleaks trigger
# in the parent repo — same technique as test_oss_backend_smoke.py.
_PEM = (
    "-----" + "BEGIN RSA PRIVATE KEY" + "-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDKabcdef==\n"
    "-----" + "END RSA PRIVATE KEY" + "-----\n"
)

_PROJECT_CONFIG = """\
[extend]
useDefault = true

[allowlist]
description = "project accepted findings"
paths = ['''(^|/)accepted/''']
"""


def _git_init_and_commit(repo: Path) -> None:
    """Init a throwaway git repo so ``gitleaks detect`` (history mode) has
    something to scan — without it the leg exits 1 with an empty report and
    the assertions below would fail for the wrong reason."""
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "smoke", "GIT_AUTHOR_EMAIL": "smoke@example.com",
        "GIT_COMMITTER_NAME": "smoke", "GIT_COMMITTER_EMAIL": "smoke@example.com",
    })
    for args in (("init", "-q", "-b", "main"), ("add", "-A"),
                 ("commit", "-q", "-m", "fixture")):
        subprocess.run(["git", *args], cwd=str(repo), env=env, check=True,
                       capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with a real secret in three places: one plain, one under the
    project's own allowlisted path, one under a shipwright-excluded path."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "key.pem").write_text(_PEM, encoding="utf-8")

    (tmp_path / "accepted").mkdir()
    (tmp_path / "accepted" / "known.pem").write_text(_PEM, encoding="utf-8")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "vendor.pem").write_text(_PEM, encoding="utf-8")

    (tmp_path / PROJECT_CONFIG_NAME).write_text(_PROJECT_CONFIG, encoding="utf-8")
    _git_init_and_commit(tmp_path)
    return tmp_path


def _paths(findings: list[dict]) -> list[str]:
    return [
        str(f.get("affected_file") or "").replace("\\", "/") for f in findings
    ]


@pytest.mark.smoke
@pytest.mark.slow
@pytest.mark.covers("FR-01.07")
def test_extend_keeps_default_rules_and_both_allowlists(
    repo: Path, monkeypatch
) -> None:
    """Three properties in one real run, because they can only break together:

    1. the gitleaks DEFAULT rules still fire (the project config's
       ``useDefault`` reaches us through ``[extend] path``) — otherwise the
       plain secret would be missed;
    2. the PROJECT's allowlist applies locally, so the local scan reaches the
       same verdict as the host workflow on the same repo;
    3. the SHIPWRIGHT path exclusions still apply on top of it.
    """
    skip_or_fail_on_missing_binary("gitleaks", _INSTALL_HINT)
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)

    findings = _run_gitleaks(str(repo))
    paths = _paths(findings)

    assert any("src/key.pem" in p for p in paths), (
        "gitleaks default rules did not fire under the generated config — the "
        "project's `[extend] useDefault` did not reach the scan, so the local "
        f"secret scan is running with (almost) no rules. Got: {paths}"
    )
    assert not any("accepted/" in p for p in paths), (
        "the project's own [allowlist] did NOT apply — local and host scans "
        f"disagree on this repo's accepted findings. Got: {paths}"
    )
    assert not any("node_modules" in p for p in paths), (
        f"shipwright path exclusions were lost by extending. Got: {paths}"
    )


@pytest.mark.smoke
@pytest.mark.slow
@pytest.mark.covers("FR-01.07")
def test_generated_config_is_accepted_by_the_real_binary(
    tmp_path: Path, monkeypatch
) -> None:
    """Guards the abort case directly: gitleaks refuses a config that sets both
    `extend.useDefault` and `extend.path`. If the renderer ever emitted both,
    every local secret scan would die — and a dead leg returns no findings."""
    skip_or_fail_on_missing_binary("gitleaks", _INSTALL_HINT)
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)

    (tmp_path / PROJECT_CONFIG_NAME).write_text(_PROJECT_CONFIG, encoding="utf-8")
    (tmp_path / "clean.txt").write_text("nothing to see\n", encoding="utf-8")
    _git_init_and_commit(tmp_path)

    errors: list[dict] = []
    findings = _run_gitleaks(str(tmp_path), errors)
    assert errors == [], f"gitleaks rejected the generated config: {errors}"
    assert findings == []
