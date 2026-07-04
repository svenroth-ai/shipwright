"""git_exec — the single hardened, read-only git runner for the grader.

Every git call in the grader goes through here (untrusted-repo threat model):

- **list-arg, ``shell=False``** — never string-concatenated.
- **repo-config neutralised** — ``-c`` flags disable the target repo's fsmonitor,
  pager and hooks, and set ``safe.directory=*`` so grading a repo owned by
  another user does not fail on "dubious ownership". Read-only porcelain
  (``log``/``rev-parse``/``remote``) doesn't run hooks today, but this keeps the
  hostile-input posture consistent and safe when index-touching/clone commands
  arrive (G4).
- **bounded output** — ``max_bytes`` reads at most N bytes then terminates the
  process, so a hostile repo with multi-MB commit bodies cannot buffer GBs.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_HARDENING = [
    "-c", "core.fsmonitor=false",
    "-c", "core.pager=cat",
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "safe.directory=*",
]


def _noninteractive_env() -> dict[str, str]:
    """Env that makes every git call strictly non-interactive.

    Without this, a clone of a private/404 HTTPS remote prompts
    ``Username for 'https://…':`` and an ``ssh://git@…`` remote prompts for a
    host-key/passphrase — both **block on the inherited TTY until the timeout**,
    which would violate the standalone CLI's "never blocks" contract. We disable
    the terminal prompt, neutralise the credential/askpass helpers, and force SSH
    batch mode with a short connect timeout so an unreachable remote fails fast.
    """
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "echo",
        "GCM_INTERACTIVE": "never",
        "GIT_SSH_COMMAND": (
            "ssh -oBatchMode=yes -oStrictHostKeyChecking=accept-new "
            "-oConnectTimeout=10"
        ),
    }


def run_git(
    args: list[str], cwd: Path, *, timeout: int = 30, max_bytes: int | None = None,
) -> tuple[int, str]:
    """Run a read-only git command. Returns ``(returncode, stdout)``.

    With ``max_bytes`` set, reads at most that many bytes of stdout and then
    terminates the child (deterministic truncation of a hostile stream). Always
    runs with ``stdin`` closed and a non-interactive env so no git call can block
    on a prompt.
    """
    cmd = ["git", *_HARDENING, *args]
    env = _noninteractive_env()
    try:
        if max_bytes is None:
            result = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
                stdin=subprocess.DEVNULL, env=env,
            )
            return result.returncode, result.stdout
        return _run_bounded(cmd, cwd, timeout=timeout, max_bytes=max_bytes, env=env)
    except (subprocess.SubprocessError, FileNotFoundError, OSError, ValueError):
        return 1, ""


def remote_url(cwd: Path, remote: str = "origin") -> str:
    """The configured URL of ``remote`` (``""`` when absent). Read-only."""
    rc, out = run_git(["remote", "get-url", remote], cwd, timeout=10)
    return out.strip() if rc == 0 else ""


def _run_bounded(
    cmd: list[str], cwd: Path, *, timeout: int, max_bytes: int,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    proc = subprocess.Popen(
        cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, env=env,
    )
    try:
        assert proc.stdout is not None
        raw = proc.stdout.read(max_bytes)
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
    text = raw.decode("utf-8", errors="replace") if raw else ""
    return (0 if raw else 1), text
