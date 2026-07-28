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
from gitleaks_inspect import PROJECT_CONFIG_NAME  # noqa: E402
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
    invocation apart from ``--config``, so a difference in the results is a
    difference the wrapping caused.

    ``cwd=target`` because that is what the host does — `actions/checkout` then
    gitleaks at the repository root. It is not cosmetic: the first CI run of
    this test failed its own fixture guard with an EMPTY host result, which is
    consistent with gitleaks resolving a relative ``extend.path`` against the
    process's working directory rather than against the config's own location.
    Run from the plugin directory, the project's ``gitleaks-base.toml`` is then
    simply not found and the chain brings no rules at all.
    """
    fd, report = tempfile.mkstemp(suffix=".json", prefix="host-gitleaks-")
    os.close(fd)
    try:
        subprocess.run(
            ["gitleaks", "detect", "--report-format", "json", "-s", str(target),
             "--report-path", report, "--config",
             str(target / PROJECT_CONFIG_NAME)],
            cwd=str(target), capture_output=True, text=True, check=False,
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
    3. nothing under a shipwright-excluded path is reported.

    Property 3 is a NON-REGRESSION, not proof that the exclusions work: the
    chained test below measured the host — which has no shipwright exclusions —
    also not reporting `node_modules`, so gitleaks' own defaults already skip
    it and this assertion would hold either way. Read it as "the exclusions did
    not make things worse", and see `test_gitleaks_config.py` for the rendered
    allowlist itself.
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
        "an excluded path was reported. NOTE this cannot distinguish the "
        "shipwright exclusions from gitleaks' own defaults, which already skip "
        f"node_modules — see the docstring. Got: {paths}"
    )


@pytest.mark.smoke
@pytest.mark.slow
@pytest.mark.covers("FR-01.07")
def test_a_project_config_that_is_already_a_chain_keeps_parity(
    chained_repo: Path, monkeypatch
) -> None:
    """The review's HIGH finding, asked as a question the binary answered.

    It answered NO: wrapping a chained config does not survive. Measured on
    gitleaks 8.21.2 with BOTH scans running at the repository root — the host,
    driven by the project's config directly, found the planted secret and the
    wrapped local scan found nothing. Working directory was ruled out first: an
    earlier run had the host leg finding nothing either, which turned out to be
    this test launching gitleaks from the plugin directory. With that fixed the
    host works and only the wrap fails, so the remaining difference is the
    extension level the wrap spends.

    So the wiring changed, exactly as the spec pre-committed: a chained project
    config is handed to gitleaks UNCHANGED and the shipwright exclusions are
    forgone. Parity is the guarantee; the exclusions are a convenience. That is
    why this asserts EXACT equality here — with no wrapper there is nothing left
    to differ — while the unchained case above still asserts the exclusions
    apply.
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
        "PARITY BROKEN on a chained project config: the host scan found "
        f"{sorted(host)} but the local scan found {sorted(local)} — it reports "
        "clean where the host reports a secret. `config_for_scan` is supposed "
        "to detect the chain and hand gitleaks the project's file UNCHANGED; "
        "either that detection stopped firing (check "
        "`gitleaks_inspect.chains_to_another_file`) or something re-introduced "
        "a wrapper. Do not relax this test — a green assertion here IS AC-1."
    )
    assert not any("accepted/" in p for p in local), (
        "the project's own [allowlist] did not apply — local and host disagree "
        f"on this repo's accepted findings. Got: {local}"
    )
    assert set(local) == set(host), (
        "a chained config is passed through unwrapped, so the local scan must "
        f"match the host EXACTLY. host={sorted(host)} local={sorted(local)}"
    )

    # No assertion here that the forgone exclusions are OBSERVABLE. One was
    # written — requiring `node_modules` to appear, to prove the cost was real
    # rather than assumed — and CI refuted it: the HOST leg, which has no
    # shipwright exclusions at all, does not report the planted
    # `node_modules/vendor.pem` either. Gitleaks' own defaults already skip that
    # path, so on this fixture the exclusions change nothing and asserting
    # otherwise would assert something false.
    #
    # The guarantee that a wrapper cannot quietly come back therefore does NOT
    # rest on scan output, where it would be unobservable. It rests on
    # `test_gitleaks_runs_at_the_repo_root.py::TestChainedConfigIsPassedThroughUnwrapped`,
    # which asserts the decision directly and needs no binary.


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
