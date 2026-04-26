"""Regression test for the route_crawler Windows-path bug (sub-iterate G).

`npx playwright test <path>` interprets the path argument as a REGEX.
On Windows, `Path.relative_to(...).str()` returns backslash separators
(`e2e\_shipwright-adopt-crawler.spec.ts`), which Playwright then parses
as a regex containing escape sequences and fails with
"Error: No tests found." Fix: always pass `.as_posix()` so the argument
uses forward slashes — Playwright accepts them on both platforms and
they don't trip the regex parser.

This was caught only by an end-to-end real-Playwright slow test in
sub-iterate F. The unit-test suite never spawned a real `npx playwright
test`, so the bug slept through the entire campaign until manual
verification.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import route_crawler  # noqa: E402


def test_subprocess_invocation_uses_forward_slash_path(tmp_path, monkeypatch):
    """The argv passed to npx must use forward-slash path even on Windows."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["cwd"] = kwargs.get("cwd")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)

    # Plant a routes.json so the parse step doesn't no_output
    out = tmp_path / ".shipwright" / "adopt" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[]", encoding="utf-8")

    route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=out,
        screenshots_dir=tmp_path / ".shipwright" / "adopt" / "screenshots",
        max_depth=1,
        max_pages=10,
        auth_token=None,
    )

    # The spec path argument is the LAST element of the argv. It MUST use
    # forward slashes — backslashes break Playwright's regex matching with
    # "Error: No tests found." (verified in real subprocess against npx
    # playwright on Windows during sub-iterate F manual verification).
    spec_arg = captured["cmd"][-1]
    assert "\\" not in spec_arg, (
        f"spec arg must use forward slashes; got {spec_arg!r}"
    )
    assert spec_arg.startswith("e2e/"), (
        f"spec arg should be relative path under e2e/; got {spec_arg!r}"
    )
    assert spec_arg.endswith(".spec.ts")


def test_subprocess_invocation_with_config_dir_uses_forward_slash(tmp_path, monkeypatch):
    """Multi-service path (config_dir set) — same forward-slash invariant."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)

    client = tmp_path / "client"
    client.mkdir()
    out = tmp_path / ".shipwright" / "adopt" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[]", encoding="utf-8")

    route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=out,
        screenshots_dir=tmp_path / ".shipwright" / "adopt" / "screenshots",
        max_depth=1,
        max_pages=10,
        auth_token=None,
        config_dir=client,
    )

    spec_arg = captured["cmd"][-1]
    assert "\\" not in spec_arg
    assert spec_arg == "e2e/_shipwright-adopt-crawler.spec.ts"
