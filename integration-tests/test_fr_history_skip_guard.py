"""The anti-skip guard in the shallow-clone meta-test, exercised.

``test_an_unreachable_pre_s6_commit_fails_rather_than_skipping`` exists because
a ``pytest.skip`` inside ``pre_s6_sections`` would delete six checks on any
shallow CI clone and report green. Its guard converts that skip into a hard
failure.

Nothing proved the guard actually fires. It cannot be proved from inside the
same session -- ``Skipped`` propagating IS the failure mode, so an in-process
assertion would skip the test that is trying to observe it. So the real test is
run in a child pytest process with ``pre_s6_sections`` replaced by one that
skips, and the child's OUTCOME is the assertion.

This matters because the guard was narrowed in
iterate-2026-07-21-codescanning-alert-cleanup from ``except BaseException`` to
``except pytest.skip.Exception``. That is the correct class, but "the correct
class" is exactly the kind of claim that deserves an executable check rather
than a comment.

@FR-01.10
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ITEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = ITEST_DIR.parent
TARGET = (
    "integration-tests/test_fr_history_recovery_provenance.py"
    "::test_an_unreachable_pre_s6_commit_fails_rather_than_skipping"
)

# Injected via -p. Replaces the helper with one that skips, reproducing the
# regression the guard exists to catch.
_PLUGIN = '''
import sys
import pytest

def pytest_configure(config):
    sys.path.insert(0, {itest!r})
    import _fr_history_docs as docs

    def _reintroduced_skip_hatch(*args, **kwargs):
        pytest.skip("simulated reintroduced skip hatch")

    docs.pre_s6_sections = _reintroduced_skip_hatch
'''


def test_a_reintroduced_skip_makes_the_meta_test_fail_not_skip(tmp_path):
    """A skip inside ``pre_s6_sections`` must turn the meta-test RED.

    The distinction under test is skip-vs-fail, not merely "not passing": a
    skipped test reports green in CI, which is the silent-invisibility failure
    the whole meta-test was written to prevent.
    """
    plugin_dir = tmp_path / "skiphatch"
    plugin_dir.mkdir()
    (plugin_dir / "_skip_hatch_plugin.py").write_text(
        _PLUGIN.format(itest=str(ITEST_DIR)), encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TARGET,
         "-p", "_skip_hatch_plugin", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, encoding="utf-8",
        env={**__import__("os").environ,
             "PYTHONPATH": str(plugin_dir),
             "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )
    out = proc.stdout + proc.stderr

    assert "1 skipped" not in out, (
        "the reintroduced skip propagated and SKIPPED the meta-test — the "
        "guard no longer catches it, so a shallow clone would delete six "
        f"checks and report green:\n{out[-2500:]}"
    )
    assert proc.returncode != 0 and "1 failed" in out, (
        f"expected the meta-test to FAIL on a reintroduced skip, got exit "
        f"{proc.returncode}:\n{out[-2500:]}"
    )
    assert "skip hatch is back" in out, (
        "the meta-test failed, but not through the anti-skip guard — the "
        f"failure message must name the cause:\n{out[-2500:]}"
    )
