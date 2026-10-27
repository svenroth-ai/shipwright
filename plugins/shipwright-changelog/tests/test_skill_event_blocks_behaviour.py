"""Run the changelog skill's Step 7 event blocks for real.

The text-order pins in ``test_skill_event_ships_in_release_pr.py`` would still
pass if a command were wrong but in the right place. Here the fenced ``bash``
blocks are extracted from SKILL.md and executed against a throw-away clone with
a bare remote, so what is asserted is what git actually did: the PR-flow block
commits only the events file and pushes the branch; the on-main block commits
but pushes nothing; a failing ``record_event.py`` stops the chain.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
)
_FENCE = re.compile(r"```bash\n(.*?)```", re.S)


def _find_bash() -> str | None:
    found = shutil.which("bash")
    if os.name == "nt" and found and "system32" in found.lower():
        # The WSL launcher, not a shell that understands C:/ paths: use Git's bash.
        git = shutil.which("git")
        cand = Path(git).resolve().parent.parent / "bin" / "bash.exe" if git else None
        found = str(cand) if cand and cand.exists() else None
    return found


_BASH = _find_bash()

if _BASH is None:
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("bash is required to run the SKILL.md command blocks; install it")
    pytest.skip("bash not available", allow_module_level=True)


def _event_blocks() -> tuple[str, str]:
    """(PR-flow block, on-main block) of Step 7, as written in SKILL.md."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    step = text[text.index("## Step 7: Create PR"):]
    blocks = [b for b in _FENCE.findall(step) if "record_event.py" in b]
    assert len(blocks) == 2, "expected one PR-flow and one on-main event block"
    pr_flow = [b for b in blocks if "git push" in b]
    on_main = [b for b in blocks if "git push" not in b]
    assert len(pr_flow) == 1 and len(on_main) == 1
    return pr_flow[0], on_main[0]


def _git(cwd: Path, env: dict, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path):
    """A clone on ``main`` with a bare ``origin``, a stub ``uv`` and a stub record_event."""
    shared = tmp_path / "shared"
    tool = shared / "scripts" / "tools"
    tool.mkdir(parents=True)
    (tool / "record_event.py").write_text(
        "import os, sys\n"
        "if os.environ.get('STUB_FAIL'):\n"
        "    sys.exit(1)\n"
        "if os.environ.get('STUB_NOOP'):  # real tool: duplicate phase_completed -> exit 0, no write\n"
        "    sys.exit(0)\n"
        "with open('shipwright_events.jsonl', 'a', encoding='utf-8') as f:\n"
        "    f.write('{\"event\": \"phase_completed\"}\\n')\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(f'#!/bin/sh\nshift\nexec "{Path(sys.executable).as_posix()}" "$@"\n')
    uv.chmod(0o755)
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n"
        "[init]\n\tdefaultBranch = main\n",
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "PYTHONUTF8": "1",
    }
    env.pop("STUB_FAIL", None)

    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, env=env,
                   capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, env=env,
                   capture_output=True)
    (work / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    _git(work, env, "add", "CHANGELOG.md")
    _git(work, env, "commit", "-m", "init")
    _git(work, env, "push", "origin", "main")
    return work, shared, env, remote


def _run(block: str, work: Path, shared: Path, env: dict, **extra: str):
    script = (
        block.replace("{shared_root}", shared.as_posix())
        .replace("{version}", "1.2.3")
        .replace("{PR_URL}", "https://example.invalid/pr/1")
    )
    return subprocess.run(
        [_BASH, "-c", script], cwd=work, env={**env, **extra},
        capture_output=True, text=True,
    )


@pytest.mark.covers("FR-01.09/AC01")
def test_pr_flow_commits_only_the_events_file_and_pushes_the_branch(repo):
    work, shared, env, remote = repo
    pr_flow, _ = _event_blocks()
    _git(work, env, "checkout", "-b", "release/v1.2.3")
    (work / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    _git(work, env, "add", "shipwright_events.jsonl")
    _git(work, env, "commit", "-m", "events file exists")
    # An unrelated uncommitted edit must stay out of the event commit.
    (work / "CHANGELOG.md").write_text("# Changelog\n\n## 1.2.3\n", encoding="utf-8")

    proc = _run(pr_flow, work, shared, env)

    assert proc.returncode == 0, proc.stderr
    touched = _git(work, env, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    assert touched == "shipwright_events.jsonl"
    assert "record changelog event for v1.2.3" in _git(work, env, "log", "-1", "--format=%s")
    assert _git(work, env, "status", "--porcelain") == "M CHANGELOG.md"
    assert _git(remote, env, "rev-parse", "release/v1.2.3") == _git(work, env, "rev-parse", "HEAD")


@pytest.mark.covers("FR-01.09/AC01")
def test_pr_flow_handles_a_first_release_with_an_untracked_events_file(repo):
    work, shared, env, remote = repo
    pr_flow, _ = _event_blocks()
    _git(work, env, "checkout", "-b", "release/v1.2.3")

    proc = _run(pr_flow, work, shared, env)

    assert proc.returncode == 0, proc.stderr
    assert _git(work, env, "ls-tree", "--name-only", "HEAD").split() == [
        "CHANGELOG.md", "shipwright_events.jsonl",
    ]
    assert _git(remote, env, "rev-parse", "release/v1.2.3")


@pytest.mark.covers("FR-01.09/AC01")
def test_on_main_block_commits_but_pushes_nothing(repo):
    work, shared, env, remote = repo
    _, on_main = _event_blocks()
    before = _git(remote, env, "rev-parse", "main")

    proc = _run(on_main, work, shared, env)

    assert proc.returncode == 0, proc.stderr
    assert _git(work, env, "rev-parse", "HEAD") != before
    assert "record changelog event for v1.2.3" in _git(work, env, "log", "-1", "--format=%s")
    assert _git(remote, env, "rev-parse", "main") == before


@pytest.mark.covers("FR-01.09/AC01")
@pytest.mark.parametrize("which", [0, 1], ids=["pr-flow", "on-main"])
def test_a_failing_record_event_stops_before_commit_and_push(repo, which):
    work, shared, env, remote = repo
    block = _event_blocks()[which]
    if which == 0:
        _git(work, env, "checkout", "-b", "release/v1.2.3")
    head = _git(work, env, "rev-parse", "HEAD")
    remote_main = _git(remote, env, "rev-parse", "main")

    proc = _run(block, work, shared, env, STUB_FAIL="1")

    assert proc.returncode != 0
    assert _git(work, env, "rev-parse", "HEAD") == head
    assert _git(work, env, "diff", "--cached", "--name-only") == ""
    assert "release/v1.2.3" not in _git(remote, env, "branch", "--list")
    assert _git(remote, env, "rev-parse", "main") == remote_main


@pytest.mark.covers("FR-01.09/AC01")
def test_pr_flow_retries_the_push_when_record_event_records_nothing(repo):
    # record_event.py exits 0 without writing when the phase event already exists
    # (dedup). That is a re-run after a push that did not land: the block must not
    # stop at "nothing to commit" - it has to push what is already committed.
    work, shared, env, remote = repo
    pr_flow, _ = _event_blocks()
    _git(work, env, "checkout", "-b", "release/v1.2.3")
    first = _run(pr_flow, work, shared, env)
    assert first.returncode == 0, first.stderr
    _git(remote, env, "update-ref", "-d", "refs/heads/release/v1.2.3")  # the push is lost
    head = _git(work, env, "rev-parse", "HEAD")

    proc = _run(pr_flow, work, shared, env, STUB_NOOP="1")

    assert proc.returncode == 0, proc.stderr
    assert _git(work, env, "rev-parse", "HEAD") == head
    assert _git(remote, env, "rev-parse", "release/v1.2.3") == head


@pytest.mark.covers("FR-01.09/AC01")
def test_on_main_block_succeeds_when_record_event_records_nothing(repo):
    work, shared, env, remote = repo
    _, on_main = _event_blocks()
    (work / "shipwright_events.jsonl").write_text("{}\n", encoding="utf-8")  # already recorded
    _git(work, env, "add", "shipwright_events.jsonl")
    _git(work, env, "commit", "-m", "event recorded earlier")
    head = _git(work, env, "rev-parse", "HEAD")

    proc = _run(on_main, work, shared, env, STUB_NOOP="1")

    assert proc.returncode == 0, proc.stderr
    assert _git(work, env, "rev-parse", "HEAD") == head
