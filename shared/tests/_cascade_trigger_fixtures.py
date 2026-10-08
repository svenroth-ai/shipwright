"""Real-git fixtures for the ``check_cascade_trigger`` tests.

Every case runs against a real git repo built in ``tmp_path``: the gate measures
``merge-base..commit`` itself, so a monkeypatched diff would test nothing. By
default the trunk is both ``main`` and ``origin/main`` because
``_branch_base_commit`` needs two names that agree before it trusts a base. Git
runs hermetically: no inherited ``GIT_DIR``-family variable, no commit signing.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from lib.review_record_core import make_entry, new_record, upsert_review
from lib.review_record_schema import RECORDABLE_TYPES
from tools.verifiers.cascade_trigger import check_cascade_trigger

RUN = "iterate-2026-10-08-cascade-probe"
LEAKY_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
REVIEWED = {"status": "completed", "recorded_by": "code-reviewer"}


@pytest.fixture(autouse=True)
def hermetic_git(monkeypatch):
    """The gate's own git calls must not see the enclosing checkout either."""
    for name in LEAKY_GIT_ENV:
        monkeypatch.delenv(name, raising=False)


def git(root: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in LEAKY_GIT_ENV}
    return subprocess.run(["git", "-C", str(root), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


def make_repo(tmp_path: Path, files: dict[str, str], removed: list[str] = (),
              moved: dict[str, str] | None = None, *, origin: bool = True,
              trunk: str = "main") -> tuple[Path, str]:
    """Trunk with ``base.txt`` (200 lines) + a branch commit applying ``files``/``removed``/``moved``."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", trunk)
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
        git(root, "config", key, value)
    (root / "base.txt").write_text("".join(f"b{i}\n" for i in range(200)), encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    if origin:
        git(root, "update-ref", f"refs/remotes/origin/{trunk}", "HEAD")
    git(root, "checkout", "-q", "-b", "iterate/probe")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel in removed:
        (root / rel).unlink()
    for old, new in (moved or {}).items():
        git(root, "mv", old, new)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")
    return root, git(root, "rev-parse", "HEAD")


def lines(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


def write_run(root: Path, *, complexity: str = "small", code: dict | None = None,
              plan_flags: list[str] | None = None, recheck_flags: list[str] | None = None) -> None:
    """Untracked bookkeeping for the run: F5c entry, review record, optional flag sources."""
    iterates = root / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True, exist_ok=True)
    (iterates / f"{RUN}.json").write_text(json.dumps({"run_id": RUN, "complexity": complexity}),
                                          encoding="utf-8")
    if plan_flags is not None:
        (iterates / f"{RUN}.plan.json").write_text(json.dumps({"run_id": RUN, "risk_flags": plan_flags}),
                                                   encoding="utf-8")
    run_dir = root / ".shipwright" / "planning" / "iterate" / RUN
    run_dir.mkdir(parents=True, exist_ok=True)
    if recheck_flags is not None:
        (run_dir / "risk_recheck.json").write_text(json.dumps({
            "schema_version": 1, "run_id": RUN,
            "risk_recheck": {"risk_flags": recheck_flags, "effective_complexity": "small"},
        }), encoding="utf-8")
    code = code or {"status": "not_run", "disposition": "the rule that applies"}
    record = new_record(RUN)
    for review_type in RECORDABLE_TYPES:
        spec = code if review_type == "code" else {"status": "not_run", "disposition": "not part of this probe"}
        entry = make_entry(review_type, spec["status"], disposition=spec.get("disposition"),
                           recorded_by=spec.get("recorded_by"))
        if spec.get("reason_code"):
            entry["reason_code"] = spec["reason_code"]
        record = upsert_review(record, entry, force=True)
    (run_dir / "reviews.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def not_run(code: str) -> dict:
    return {"status": "not_run", "disposition": "the rule that applies", "reason_code": code}


def check(root: Path, commit: str):
    return check_cascade_trigger(root, RUN, commit)
