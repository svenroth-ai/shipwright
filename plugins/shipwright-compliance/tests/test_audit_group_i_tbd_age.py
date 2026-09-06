"""I8 — stale TBD acceptance-criteria placeholder (iterate-2026-09-06-fr-hygiene-touched-rows).

Real git via a tmp_path repo: `git blame` needs actual commit history, so this
cannot be a pure in-memory test the way I6/I7 are.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_i  # noqa: E402
from scripts.audit.group_i_tbd_age import TBD_MARKER  # noqa: E402

_SPEC_REL = ".shipwright/planning/01-adopted/spec.md"

_ENV = {
    "GIT_AUTHOR_NAME": "Adopt Test", "GIT_AUTHOR_EMAIL": "adopt@test.invalid",
    "GIT_COMMITTER_NAME": "Adopt Test", "GIT_COMMITTER_EMAIL": "adopt@test.invalid",
}


def _git(cwd: Path, *args: str, when: str | None = None) -> None:
    import os
    env = os.environ.copy()
    env.update(_ENV)
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "-C", str(cwd), *args], env=env, capture_output=True,
                    text=True, check=True)


def _write(root: Path, content: str) -> None:
    p = root / _SPEC_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _spec(fr_id: str, name: str, tbd: bool) -> str:
    body = TBD_MARKER if tbd else "- (E) Given x, when y, then z."
    return (
        "## 2. Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {fr_id} | Core | {name} | Must | The system does {name}. | code | unit |\n\n"
        f"### {fr_id} — {name}\n\n{body}\n"
    )


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    return root


def test_old_tbd_is_flagged_stale(tmp_path: Path):
    root = _repo(tmp_path)
    _write(root, _spec("FR-01.01", "Login", tbd=True))
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "adopt: seed spec", when="2020-01-01T00:00:00")
    findings = {f.check_id: f for f in group_i.run(root, None, None)}
    f = findings["I8"]
    assert f.status == "pass"  # advisory — never fails
    assert "FR-01.01" in f.detail


def test_fresh_tbd_is_not_flagged(tmp_path: Path):
    root = _repo(tmp_path)
    _write(root, _spec("FR-01.01", "Login", tbd=True))
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "adopt: seed spec")  # today
    findings = {f.check_id: f for f in group_i.run(root, None, None)}
    assert "FR-01.01" not in findings["I8"].detail


def test_row_with_real_criteria_never_flagged(tmp_path: Path):
    root = _repo(tmp_path)
    _write(root, _spec("FR-01.01", "Login", tbd=False))
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "adopt: seed spec", when="2020-01-01T00:00:00")
    findings = {f.check_id: f for f in group_i.run(root, None, None)}
    assert "no FR(s) with a TBD placeholder" in findings["I8"].detail


def test_i8_is_registered():
    ids = {cid for cid, _name, _sev in group_i._CHECKS}
    assert "I8" in ids
