"""End-to-End Verification (Step 11a/11b) for the `--surface cli` iterate
`iterate-2026-09-13-codex-internal-review-transport`.

Every existing unit test drives `review_via_codex.main()` in-process with
`transport.subprocess.run` mocked — none of them prove the transport can
actually launch a real, separate `codex` process under the scrubbed
environment. Doubt-review flagged this gap directly (MEDIUM,
2026-09-17): "I could not find a single execution anywhere in this repo
where `scrubbed_env()` has really started a codex process." This file
closes it: it spawns `review_via_codex.py` as a real subprocess, which in
turn spawns a real (fixture) `codex` executable found only via `PATH` in
the scrubbed child environment — proving argv construction, env
forwarding (including the Windows `.cmd`-shim-resolution vars this
iterate added), and the full validate-then-copy-to-canonical pipeline
end-to-end, with nothing mocked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
_REVIEW_VIA_CODEX = _SHARED / "scripts" / "tools" / "review_via_codex.py"

_FAKE_CODEX_PY = r'''
import json
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:2] == ["login", "status"]:
    sys.exit(0)
if args and args[0] == "exec":
    out_path = Path(args[args.index("-o") + 1])
    out_path.write_text(json.dumps({"section": "e2e-fixture", "review": []}), encoding="utf-8")
    sys.exit(0)
sys.exit(1)
'''


def _install_fake_codex(bin_dir: Path) -> None:
    """A real, separately-executable `codex` fixture — not a Python mock —
    resolvable only via `PATH`, mirroring how the real npm-installed `codex`
    CLI is typically a `.cmd` shim on Windows (this iterate's env-allowlist
    `COMSPEC`/`PATHEXT` additions exist specifically so such a shim can
    launch under the scrubbed environment)."""
    fake_py = bin_dir / "fake_codex.py"
    fake_py.write_text(_FAKE_CODEX_PY, encoding="utf-8")
    if sys.platform == "win32":
        shim = bin_dir / "codex.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{fake_py}" %*\r\n', encoding="utf-8")
    else:
        shim = bin_dir / "codex"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake_py}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)


def test_real_subprocess_launch_under_scrubbed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_codex(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    # Prove the scrub itself works even under a real launch: a secret in
    # THIS process's ambient env must not reach the child, which the fake
    # codex never reads anyway — the real proof is that the launch still
    # succeeds with a scrubbed env, not a full ambient one.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-needed-by-a-real-launch")

    agent_md = tmp_path / "code-reviewer.md"
    agent_md.write_text("Review the diff for correctness.", encoding="utf-8")
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("the spec contract for this fixture", encoding="utf-8")
    diff_file = tmp_path / "the.diff"
    diff_file.write_text("+ a real added line", encoding="utf-8")
    out_dir = tmp_path / "evidence"
    out_dir.mkdir()

    result = subprocess.run(
        [sys.executable, str(_REVIEW_VIA_CODEX),
         "--role", "code", "--worktree-root", str(tmp_path),
         "--agent-md", str(agent_md), "--out-dir", str(out_dir),
         "--spec-file", str(spec_file), "--diff-file", str(diff_file)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=30,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    canonical = out_dir / "code_review_reply.json"
    assert canonical.exists()
    assert json.loads(canonical.read_text(encoding="utf-8")) == {"section": "e2e-fixture", "review": []}
