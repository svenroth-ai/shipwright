"""The finalization verifier and the release-notes tools declare their own packages.

They are started as ``uv run <script>`` from whatever folder the operator is in
(a consumer project, a plugin dir, an empty temp dir). Under a plain
``uv run`` that is NOT this repo's root project, so a package only the root
``pyproject.toml`` supplied is silently missing: the condenser answered
"openai package not installed" and the verifier's jsonschema-backed checks
degraded. A PEP 723 ``# /// script`` header makes the script carry its own
dependencies on every uv version, in any working directory (the same rule the
hook scripts follow, ``test_hooks_pep723_isolation.py``).

``publish_release_notes.py`` is the release entry point and imports the
condenser as a module (a module's own header is not read), so it carries the
header too. The compliance script that ``finalize_iterate.py`` launches is the other half of
the one rule (packages from the project the script runs under, ``uv run --project``):
it keeps that form on purpose, because the SBOM licence scan reads the plugin's
``.venv`` and its lock pins the versions; a second source would drift.

The slow tests need network access (uv resolves the packages) and are excluded from
the default run (`-m slow`).

The "package not installed" fallback itself stays covered by
``test_condense_release_notes.py`` — release notes remain best-effort.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "shared" / "scripts" / "tools"
pytestmark = pytest.mark.covers("FR-01.11")
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")

# script -> distribution names it must declare (what its code path imports).
_DECLARED = {
    "verify_iterate_finalization.py": {"jsonschema", "pyyaml"},
    "condense_release_notes.py": {"openai"},
    "publish_release_notes.py": {"openai"},
}


def _declared_names(script: Path) -> set[str]:
    text = script.read_text(encoding="utf-8")
    match = _BLOCK.search(text)
    assert match, f"{script.name} has no PEP 723 `# /// script` header"
    body = "".join(
        line[2:] if line.startswith("# ") else line[1:]
        for line in match.group("content").splitlines(keepends=True)
    )
    deps = tomllib.loads(body).get("dependencies", [])
    return {re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", d).group(0).lower() for d in deps}


def _uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    return uv


@pytest.mark.parametrize("name", sorted(_DECLARED))
def test_script_header_declares_its_packages(name):
    assert _DECLARED[name] <= _declared_names(TOOLS / name)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(_DECLARED))
def test_header_resolves_in_a_clean_directory(name, tmp_path):
    """uv resolves the header's packages from an empty directory (no project in reach)."""
    proc = subprocess.run(
        [_uv(), "export", "--script", str(TOOLS / name), "--no-hashes"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    resolved = {ln.split("==")[0].strip().lower() for ln in proc.stdout.splitlines() if "==" in ln}
    assert _DECLARED[name] <= resolved


@pytest.mark.slow
def test_condenser_runs_bare_from_an_unrelated_directory(tmp_path):
    """The real command, bare `uv run`, no project: it must reach the provider call (one outbound
    request to openrouter.ai with a fake key), not answer "not installed"."""
    section = tmp_path / "section.md"
    prompt = tmp_path / "prompt.md"
    section.write_text("### Added\n- a thing\n", encoding="utf-8")
    prompt.write_text("Summarise {version}: {section}\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "VIRTUAL_ENV"}}
    env["OPENROUTER_API_KEY"] = "sk-or-not-a-real-key"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [_uv(), "run", str(TOOLS / "condense_release_notes.py"), "--section-file", str(section),
         "--prompt-file", str(prompt), "--version", "1.0.0", "--project-root", str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", env=env, timeout=170,
    )
    assert proc.stdout.strip(), proc.stderr  # empty stdout = uv could not resolve the packages
    out = json.loads(proc.stdout)
    assert out["status"] == "error" and out["reason"] != "openai package not installed", out


@pytest.mark.slow
def test_verifier_runs_bare_from_an_unrelated_directory(tmp_path):
    """The real command, bare `uv run`, no project in reach: it starts and prints its report."""
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [_uv(), "run", str(TOOLS / "verify_iterate_finalization.py"), "--run-id", "iterate-x",
         "--project-root", str(tmp_path), "--commit", "0" * 40],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", env=env, timeout=170,
    )
    assert "ModuleNotFoundError" not in proc.stderr, proc.stderr
    assert proc.returncode == 1, proc.stdout + proc.stderr  # the empty project has no artifacts: a real FAIL, not a crash
    assert "ok," in proc.stdout and "error(s)" in proc.stdout, proc.stdout + proc.stderr
