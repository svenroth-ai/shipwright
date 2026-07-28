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

import json
import os
import subprocess
import sys
import tempfile
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

# A repo whose own config is ALREADY a chain: .gitleaks.toml -> base.toml ->
# the built-in defaults. The host workflow loads `.gitleaks.toml` directly and
# resolves two hops; the local path wraps it, making three. Whether gitleaks
# honours the third hop decides whether wrapping preserves parity at all.
_CHAINED_PROJECT_CONFIG = """\
[extend]
path = "gitleaks-base.toml"

[allowlist]
description = "project accepted findings"
paths = ['''(^|/)accepted/''']
"""

_CHAINED_BASE_CONFIG = """\
[extend]
useDefault = true
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


def _seed_repo(root: Path, configs: dict[str, str]) -> Path:
    """A repo with a real secret in three places: one plain, one under the
    project's own allowlisted path, one under a shipwright-excluded path."""
    for rel, body in configs.items():
        (root / rel).write_text(body, encoding="utf-8")
    for folder, name in (("src", "key.pem"), ("accepted", "known.pem"),
                         ("node_modules", "vendor.pem")):
        (root / folder).mkdir()
        (root / folder / name).write_text(_PEM, encoding="utf-8")
    _git_init_and_commit(root)
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _seed_repo(tmp_path, {PROJECT_CONFIG_NAME: _PROJECT_CONFIG})


@pytest.fixture
def chained_repo(tmp_path: Path) -> Path:
    """The parity-critical shape: the project's config extends a second file."""
    return _seed_repo(tmp_path, {
        PROJECT_CONFIG_NAME: _CHAINED_PROJECT_CONFIG,
        "gitleaks-base.toml": _CHAINED_BASE_CONFIG,
    })


def _host_equivalent_scan(target: Path) -> list[str]:
    """What the HOST workflow sees: gitleaks driven by the project's config
    directly, with no shipwright layer in between. Mirrors ``_run_gitleaks``'
    invocation exactly apart from ``--config``, so a difference in the results
    is a difference the wrapping caused."""
    fd, report = tempfile.mkstemp(suffix=".json", prefix="host-gitleaks-")
    os.close(fd)
    try:
        subprocess.run(
            ["gitleaks", "detect", "--report-format", "json", "-s", str(target),
             "--report-path", report, "--config",
             str(target / PROJECT_CONFIG_NAME)],
            capture_output=True, text=True, check=False,
        )
        raw = Path(report).read_text(encoding="utf-8") or "[]"
    finally:
        try:
            os.unlink(report)
        except OSError:
            pass
    return [
        str(f.get("File") or "").replace("\\", "/") for f in json.loads(raw)
    ]


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
def test_a_project_config_that_is_already_a_chain_keeps_parity(
    chained_repo: Path, monkeypatch
) -> None:
    """The review's HIGH finding, asked as a question the binary answers.

    Wrapping the project's config spends one of gitleaks' extension levels. For
    a repo whose config is already a chain (``.gitleaks.toml`` ->
    ``gitleaks-base.toml`` -> defaults) the host resolves two hops and the local
    path needs three. If gitleaks stops short, the default rules never reach the
    local scan and it reports a clean repo while the host reports the secret —
    the false-clean AC-1 exists to remove.

    So this compares the two directly instead of asserting a depth limit from
    documentation. The only permitted difference is the shipwright path
    exclusions, which the host deliberately does not have.
    """
    skip_or_fail_on_missing_binary("gitleaks", _INSTALL_HINT)
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)

    host = _host_equivalent_scan(chained_repo)
    assert any("src/key.pem" in p for p in host), (
        "the FIXTURE is wrong, not the code: the host-equivalent scan found no "
        f"secret, so this test cannot say anything about parity. Got: {host}"
    )

    local = _paths(_run_gitleaks(str(chained_repo)))

    assert any("src/key.pem" in p for p in local), (
        "PARITY BROKEN by wrapping a chained project config: the host scan "
        f"found {sorted(host)} but the local scan found {sorted(local)}. The "
        "generated config adds an extend level on top of a chain that already "
        "used them, so the built-in rules no longer reach the local scan — it "
        "reports clean where the host reports a secret. Fix the wiring (do not "
        "relax this test): either extend the project's chain target instead of "
        "the project's file, or apply the shipwright exclusions without an "
        "extra extend level."
    )
    assert not any("accepted/" in p for p in local), (
        "the project's own [allowlist] did not survive the chain — local and "
        f"host disagree on this repo's accepted findings. Got: {local}"
    )
    assert not any("node_modules" in p for p in local), (
        f"shipwright path exclusions were lost by extending a chain. Got: {local}"
    )

    expected = {p for p in host if "node_modules" not in p}
    assert set(local) == expected, (
        "the wrapped scan and the host scan disagree beyond the shipwright "
        f"exclusions. host(minus exclusions)={sorted(expected)} "
        f"local={sorted(local)}"
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
