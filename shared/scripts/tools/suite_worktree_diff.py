"""Build F0's coherent merge-base -> final-working-tree patch.

Kept separate from coverage execution: this module owns Git snapshot semantics;
``suite_coverage`` owns coverage artefacts and the diff-cover verdict.
"""

from __future__ import annotations

import hashlib
import os
import subprocess  # nosec B404 - fixed argv, shell=False
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from scripts.tools.suite_coverage_rules import DATA_DIR


_GIT_CONTEXT_KEYS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
)
_MEASUREMENT_CONFIG_NAMES = frozenset({
    ".coveragerc", ".python-version", "pyproject.toml", "pytest.ini",
    "setup.cfg", "shipwright_test_config.json", "tox.ini", "uv.lock",
})


def controlled_git_env(*, index_file: Path | None = None) -> dict[str, str]:
    """Keep ordinary user settings but refuse inherited repository redirection."""
    env = os.environ.copy()
    for key in _GIT_CONTEXT_KEYS:
        env.pop(key, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if index_file is not None:
        env["GIT_INDEX_FILE"] = str(index_file)
    return env


def source_fingerprint(project_root: Path,
                       runner: Callable[..., Any] = subprocess.run
                       ) -> tuple[str | None, str]:
    """Hash tracked and untracked, non-ignored Python sources in one checkout."""
    root = Path(project_root).resolve()
    argv = ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"]
    try:
        proc = runner(  # nosec B603 - fixed argv, shell=False
            argv, cwd=str(root), env=controlled_git_env(), capture_output=True,
            text=True, errors="replace", shell=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not fingerprint working-tree sources: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return None, f"could not fingerprint working-tree sources: {detail}".rstrip()
    digest = hashlib.sha256()
    for rel in sorted(p for p in (proc.stdout or "").split("\0")
                      if p.endswith((".py", ".pyi"))
                      or Path(p).name in _MEASUREMENT_CONFIG_NAMES):
        path = root / rel
        digest.update(rel.replace("\\", "/").encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        try:
            payload = (os.readlink(path).encode("utf-8", errors="surrogatepass")
                       if path.is_symlink() else path.read_bytes())
        except OSError as exc:
            return None, f"could not fingerprint working-tree source {rel}: {exc}"
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest(), ""


def build_worktree_diff(project_root: Path, branch: str,
                        runner: Callable[..., Any] = subprocess.run
                        ) -> tuple[Path | None, str]:
    """Materialize one coherent merge-base -> working-tree diff.

    diff-cover otherwise unions committed, staged and unstaged hunks whose line
    numbers refer to different file revisions. A private temporary index starts at
    the merge base and stages the final working tree (including untracked, excluding
    ignored), yielding the same single snapshot CI sees after F6. The real index and
    HEAD are never touched.
    """
    root = Path(project_root).resolve()
    data_dir = root / DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    index = data_dir / f"index-{token}"
    output = data_dir / f"worktree-{token}.diff"
    env = controlled_git_env(index_file=index)

    def _git(*args: str) -> subprocess.CompletedProcess | None:
        try:
            return runner(  # nosec B603 - fixed argv, shell=False
                ["git", "-C", str(root), *args], cwd=str(root), env=env,
                capture_output=True,
                text=True, errors="replace", shell=False, timeout=120)
        except (OSError, subprocess.SubprocessError):
            return None

    try:
        base = _git("merge-base", branch, "HEAD")
        if base is None or base.returncode != 0 or not (base.stdout or "").strip():
            return None, (
                f"could not resolve merge base for {branch}; fetch enough history "
                f"(for example: git fetch --deepen=100 origin main) and re-run")
        base_sha = (base.stdout or "").strip()
        for argv in (("read-tree", base_sha), ("add", "-A", "--", ".")):
            proc = _git(*argv)
            if proc is None or proc.returncode != 0:
                detail = "" if proc is None else ((proc.stderr or proc.stdout or "").strip())
                return None, f"git {' '.join(argv)} failed: {detail}".rstrip()
        diff = _git("diff", "--cached", "--no-ext-diff", "--binary",
                    "--full-index", base_sha, "--")
        if diff is None or diff.returncode != 0:
            detail = "" if diff is None else ((diff.stderr or diff.stdout or "").strip())
            return None, f"could not build coherent working-tree diff: {detail}".rstrip()
        output.write_text(diff.stdout or "", encoding="utf-8")
        return output, ""
    finally:
        for path in (index, Path(f"{index}.lock")):
            try:
                path.unlink()
            except OSError:
                pass
