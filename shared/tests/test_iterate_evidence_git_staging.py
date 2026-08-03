"""F6 must never stage crash residue from immutable-evidence publication."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGED_GITIGNORE = REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"
RUN_ID = "iterate-2026-08-03-temp-ignore"


def test_directory_level_f6_add_excludes_evidence_install_temporary(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_bytes(MANAGED_GITIGNORE.read_bytes())
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    canonical = iterates / f"{RUN_ID}.test-results.json"
    temporary = iterates / f"{canonical.name}.crash-residue.tmp"
    canonical.write_text("{}\n", encoding="utf-8")
    temporary.write_text("partial or linked bytes", encoding="utf-8")

    subprocess.run(
        ["git", "-C", str(tmp_path), "add", ".gitignore", str(iterates)],
        check=True,
    )
    staged = subprocess.check_output(
        ["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
        text=True,
    ).splitlines()

    assert canonical.relative_to(tmp_path).as_posix() in staged
    assert temporary.relative_to(tmp_path).as_posix() not in staged
    assert subprocess.run(
        ["git", "-C", str(tmp_path), "check-ignore", "-q", str(temporary)]
    ).returncode == 0
