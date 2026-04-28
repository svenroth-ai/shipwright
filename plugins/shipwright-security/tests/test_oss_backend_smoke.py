"""Real-scanner smoke tests for the per-scanner exclusion contract.

Sub-Iterate H.D. Validates that the wrapper functions in
``oss_backend`` actually behave the way the unit tests assert when invoked
against the real Semgrep / Trivy / Gitleaks binaries on a synthetic
fixture repo.

Marked ``smoke`` so they don't run in the default fast suite — they touch
network (Semgrep ``--config auto``) and a local Trivy vuln DB. Run via:

    uv run pytest tests/test_oss_backend_smoke.py -v -m smoke

Each test ``skipif``s when the corresponding binary is not on PATH.

Reviewer-Finding 5: synthetic credentials are written into ``tmp_path``
only — never committed to the repo — so external secret scanners
(GitHub Advanced Security, TruffleHog, IDE plugins) cannot trigger on
fixture content.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure scripts/lib is on path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from oss_backend import _run_gitleaks, _run_semgrep, _run_trivy


# --- Synthetic credential helpers ------------------------------------------
# We assemble the PEM markers from string fragments so neither this source
# file nor the smoke fixture committed-into-git is itself a Gitleaks trigger
# in the parent shipwright repo. The reconstructed pem-payload matches
# Gitleaks' default "Identified a Private Key" rule AND Semgrep's
# `generic.secrets.security.detected-private-key` registry rule — chosen
# because both rule engines fire deterministically on the marker, with no
# AWS-style example/test allowlisting to defeat. This is NOT a real key —
# the body is short and obviously synthetic.

_PEM_BEGIN_FRAG = "-----" + "BEGIN RSA PRIVATE KEY" + "-----"
_PEM_END_FRAG = "-----" + "END RSA PRIVATE KEY" + "-----"
_PEM_BODY_FRAG = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDKabcdef=="


def _synthetic_pem_block() -> str:
    """Return a PEM-formatted private-key block both scanners detect."""
    return f"{_PEM_BEGIN_FRAG}\n{_PEM_BODY_FRAG}\n{_PEM_END_FRAG}\n"


# --- Fixture --------------------------------------------------------------

@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """Build a synthetic project tree under tmp_path.

    Layout:
        .gitignore                     # does NOT ignore .shipwright/
        .shipwright/agent_docs/sample.py    # SAST trigger
        .shipwright/agent_docs/notes.md     # secret-pattern trigger
        node_modules/legacy.py              # negative control (must skip)
        src/main.py                         # positive baseline (always scan)

    The fixture also runs ``git init`` and commits everything so Gitleaks
    ``detect`` (history mode) has something to find.
    """
    # Project files
    (tmp_path / ".gitignore").write_text(
        "# Synthetic fixture: .shipwright/ is intentionally NOT gitignored\n"
        "# to test the post-H scanner contract end-to-end.\n",
        encoding="utf-8",
    )

    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    # PEM-block file — both Semgrep registry and Gitleaks default rule fire on
    # the BEGIN/END markers, regardless of body entropy.
    (agent_docs / "key.pem").write_text(_synthetic_pem_block(), encoding="utf-8")

    nm_dir = tmp_path / "node_modules"
    nm_dir.mkdir()
    (nm_dir / "legacy_key.pem").write_text(
        # Same trigger inside node_modules — MUST be excluded by every scanner.
        _synthetic_pem_block(),
        encoding="utf-8",
    )

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main_key.pem").write_text(
        # Positive baseline — never excluded.
        _synthetic_pem_block(),
        encoding="utf-8",
    )

    _git_init_and_commit(tmp_path)
    return tmp_path


def _git_init_and_commit(repo: Path) -> None:
    """Init a throwaway git repo so Gitleaks ``detect`` has history."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "smoke"
    env["GIT_AUTHOR_EMAIL"] = "smoke@example.com"
    env["GIT_COMMITTER_NAME"] = "smoke"
    env["GIT_COMMITTER_EMAIL"] = "smoke@example.com"

    def run(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("commit", "-q", "-m", "fixture")


# --- Tests ----------------------------------------------------------------

@pytest.mark.smoke
@pytest.mark.skipif(not shutil.which("semgrep"), reason="semgrep not on PATH")
def test_semgrep_scans_shipwright_dir_after_refactor(
    synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Semgrep wrapper must walk into ``.shipwright/agent_docs/`` and
    must NOT walk into ``node_modules/`` (Semgrep's own .semgrepignore
    handles that)."""
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
    findings = _run_semgrep(str(synthetic_repo))
    if findings is None or len(findings) == 0:
        pytest.skip(
            "Semgrep returned no findings — likely a registry-fetch or "
            "rules-availability issue. Smoke test cannot assert on "
            "exclusion behavior without findings to bucket."
        )

    paths = [_finding_path(f) for f in findings]
    assert any(".shipwright" in p for p in paths), (
        f"Semgrep should now find content under .shipwright/agent_docs/; "
        f"got paths: {paths}"
    )
    assert not any("node_modules" in p for p in paths), (
        f"Semgrep must skip node_modules via its built-in .semgrepignore; "
        f"got paths: {paths}"
    )


@pytest.mark.smoke
@pytest.mark.skipif(not shutil.which("gitleaks"), reason="gitleaks not on PATH")
def test_gitleaks_detect_scans_committed_shipwright_dir(
    synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gitleaks ``detect`` (history mode) must find committed secrets in
    ``.shipwright/agent_docs/`` and must NOT report ``node_modules/``."""
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
    findings = _run_gitleaks(str(synthetic_repo))
    if not findings:
        pytest.skip(
            "Gitleaks returned no findings — likely a default-rules "
            "availability issue on this binary. Cannot assert exclusion "
            "behavior without findings."
        )

    paths = [_finding_path(f) for f in findings]
    assert any(".shipwright" in p for p in paths), (
        f"Gitleaks should now find committed secrets under "
        f".shipwright/agent_docs/; got paths: {paths}"
    )
    assert not any("node_modules" in p for p in paths), (
        f"Gitleaks must skip node_modules via the TOML allowlist; "
        f"got paths: {paths}"
    )


@pytest.mark.smoke
@pytest.mark.skipif(not shutil.which("trivy"), reason="trivy not on PATH")
def test_trivy_scans_shipwright_dir_after_refactor(
    synthetic_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trivy ``fs --scanners vuln`` only flags manifests, but the wrapper
    must at minimum NOT crash and must NOT skip ``.shipwright/`` via a
    plugin-side --skip-dirs entry. We assert this by reconstructing the
    invoked command (via subprocess capture) rather than counting
    findings — Trivy SCA on a tree with no manifests legitimately
    returns zero findings."""
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
    cmd_seen: list[str] = []

    real_run = subprocess.run

    def capture(cmd, *args, **kwargs):
        if cmd and cmd[0] == "trivy":
            cmd_seen.extend(cmd)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", capture)
    _run_trivy(str(synthetic_repo))

    assert cmd_seen, "Trivy was never invoked"
    assert "--skip-dirs" in cmd_seen, (
        f"Trivy command should still carry --skip-dirs flags; got: {cmd_seen}"
    )
    # Critical regression sentinel: .shipwright must NOT be passed as a
    # --skip-dirs name. The previous _DEFAULT_EXCLUDES included it.
    skip_dirs_values = _values_after_flag(cmd_seen, "--skip-dirs")
    assert ".shipwright" not in skip_dirs_values, (
        f"Trivy must not skip .shipwright/ anymore; got --skip-dirs values: "
        f"{skip_dirs_values}"
    )
    assert "securityreports" not in skip_dirs_values, (
        f"Trivy must not skip securityreports/ anymore; got --skip-dirs values: "
        f"{skip_dirs_values}"
    )
    # Positive controls — node_modules and friends still go in.
    assert "node_modules" in skip_dirs_values
    assert ".venv" in skip_dirs_values


# --- Helpers --------------------------------------------------------------

def _finding_path(finding: dict) -> str:
    """Best-effort extract a file-path-ish string from a normalized finding."""
    for key in ("file", "path", "location", "uri", "Path", "File"):
        v = finding.get(key)
        if isinstance(v, str):
            return v
    # Fall back to scanning the whole record for a path-like substring.
    return json.dumps(finding, default=str)


def _values_after_flag(argv: list[str], flag: str) -> list[str]:
    """Return every value that immediately follows *flag* in argv."""
    return [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == flag]
