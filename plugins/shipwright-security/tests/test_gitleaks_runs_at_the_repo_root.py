"""gitleaks runs AT the scanned repository, like the host workflow does.

Found by the first CI run of `test_a_project_config_that_is_already_a_chain_keeps_parity`,
which failed its own fixture guard with an EMPTY host result. A relative
`extend.path` resolves against the *process's* working directory, not against the
config file that contains it — so a project whose `.gitleaks.toml` extends a
sibling file had that sibling silently unreachable when the scan was launched
from anywhere but the repository root. The generated config's own extend path is
absolute and was never the problem; the project's INTERNAL chain was.

That is AC-1's failure mode exactly: the same repository yielding a different
verdict depending on who asked. These are mock-based, so they pin the invocation
everywhere rather than only where a scanner binary exists — the real-binary
consequence is covered by `test_gitleaks_extend_smoke.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import oss_backend  # noqa: E402


@pytest.fixture
def captured(monkeypatch) -> dict:
    """Capture `_run_tool`'s kwargs without launching anything."""
    seen: dict = {}

    def fake_run_tool(cmd, **kwargs):
        seen["cmd"] = cmd
        seen.update(kwargs)
        return []

    monkeypatch.setattr(oss_backend, "_run_tool", fake_run_tool)
    monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
    return seen


@pytest.mark.covers("FR-01.07")
class TestGitleaksRunsAtTheTarget:
    def test_cwd_is_the_scanned_target(self, captured, tmp_path: Path) -> None:
        oss_backend._run_gitleaks(str(tmp_path))
        assert captured.get("cwd") == os.path.abspath(str(tmp_path)), (
            "gitleaks must run AT the scanned repository — the host workflow "
            "does, and a relative `extend.path` in the project's own config "
            "resolves against the process cwd. Got: "
            f"{captured.get('cwd')!r}"
        )

    def test_cwd_is_absolute_even_for_a_relative_target(
        self, captured, tmp_path: Path, monkeypatch
    ) -> None:
        """A relative target plus a changed cwd must not send the subprocess
        somewhere else entirely."""
        (tmp_path / "sub").mkdir()
        monkeypatch.chdir(tmp_path)
        oss_backend._run_gitleaks("sub")
        cwd = captured.get("cwd")
        assert cwd and os.path.isabs(cwd), f"not absolute: {cwd!r}"
        assert Path(cwd).resolve() == (tmp_path / "sub").resolve()

    def test_a_nonexistent_target_does_not_break_the_invocation(
        self, captured, tmp_path: Path
    ) -> None:
        """`cwd` pointing at a missing directory makes `subprocess.run` raise
        instead of running the scan, which would turn a bad path into a crash
        rather than a degraded leg. Fall back to the inherited cwd."""
        oss_backend._run_gitleaks(str(tmp_path / "gone"))
        assert captured.get("cwd") is None

    def test_the_target_still_reaches_gitleaks_as_the_source(
        self, captured, tmp_path: Path
    ) -> None:
        """Setting cwd must not be mistaken for passing the target: `-s` still
        carries it, so a scan launched at the root does not silently widen."""
        oss_backend._run_gitleaks(str(tmp_path))
        cmd = captured["cmd"]
        assert "-s" in cmd
        assert cmd[cmd.index("-s") + 1] == str(tmp_path)
