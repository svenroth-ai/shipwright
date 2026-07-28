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
from gitleaks_config import config_for_scan  # noqa: E402
from gitleaks_inspect import PROJECT_CONFIG_NAME  # noqa: E402


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


@pytest.mark.covers("FR-01.07")
class TestChainedConfigIsPassedThroughUnwrapped:
    """CI measured it against gitleaks 8.21.2: wrapping a config that already
    extends a second file leaves the built-in rules unreachable, so the local
    scan reported a clean repository where the host reported a secret. These
    pin the decision without needing the binary."""

    def _seed(self, root: Path, body: str, base: str | None = None) -> None:
        (root / PROJECT_CONFIG_NAME).write_text(body, encoding="utf-8")
        if base is not None:
            (root / "base.toml").write_text(base, encoding="utf-8")

    def test_a_chained_config_is_handed_over_unchanged(self, tmp_path: Path) -> None:
        self._seed(tmp_path, '[extend]\npath = "base.toml"\n',
                   "[extend]\nuseDefault = true\n")
        path, owned = config_for_scan(str(tmp_path), ("node_modules",))
        assert Path(path) == tmp_path / PROJECT_CONFIG_NAME
        assert owned is False, (
            "the project's own file must never be reported as ours — the "
            "caller unlinks what it owns, and that would delete the "
            "repository's .gitleaks.toml"
        )

    def test_an_unchained_config_is_still_wrapped(self, tmp_path: Path) -> None:
        """The common case keeps BOTH the project's answer and the exclusions."""
        self._seed(tmp_path, "[extend]\nuseDefault = true\n")
        path, owned = config_for_scan(str(tmp_path), ("node_modules",))
        assert owned is True and Path(path) != tmp_path / PROJECT_CONFIG_NAME
        body = Path(path).read_text(encoding="utf-8")
        assert "node_modules" in body and str(tmp_path) in body.replace("\\\\", "\\")
        os.unlink(path)

    def test_no_project_config_still_renders_ours(self, tmp_path: Path) -> None:
        path, owned = config_for_scan(str(tmp_path), ("node_modules",))
        assert owned is True
        assert "useDefault = true" in Path(path).read_text(encoding="utf-8")
        os.unlink(path)

    def test_a_url_extension_counts_as_a_chain_too(self, tmp_path: Path) -> None:
        """Written first expecting the opposite — that a remote hop is "like
        useDefault" and therefore safe to wrap. It is not: `extend.url` spends
        an extension level exactly as `extend.path` does, which is the level CI
        measured us losing. Wrapping it would break parity the same way, and
        unlike the local case nothing here can even be inspected offline."""
        self._seed(tmp_path, '[extend]\nurl = "https://example.invalid/g.toml"\n')
        path, owned = config_for_scan(str(tmp_path), ())
        assert owned is False and Path(path) == tmp_path / PROJECT_CONFIG_NAME

    def test_the_scan_does_not_delete_the_projects_own_config(
        self, captured, tmp_path: Path
    ) -> None:
        """End-to-end on the ownership contract: the `finally` must skip it."""
        self._seed(tmp_path, '[extend]\npath = "base.toml"\n',
                   "[extend]\nuseDefault = true\n")
        oss_backend._run_gitleaks(str(tmp_path))
        assert (tmp_path / PROJECT_CONFIG_NAME).is_file(), (
            "the scan deleted the repository's own .gitleaks.toml"
        )
