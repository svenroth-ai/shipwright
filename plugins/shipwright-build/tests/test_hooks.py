"""Tests for shipwright-build hooks (plugin-specific only).

The SessionStart capture_session_id.py hook is shared across all
plugins and tested in shared/tests/test_capture_session_id.py.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


def _bash() -> str:
    """Find the Bash paired with Git when Windows exposes only git.exe."""
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(variable, "")) / "Git" / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    resolved = shutil.which("bash")
    if resolved:
        return resolved
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("bash is required to exercise shell hook behavior; install Git Bash / bash")
    pytest.skip("bash is required to exercise shell hook behavior")
    raise AssertionError("pytest.skip() must not return")


def test_validate_command_allows_normal():
    """Normal commands should pass."""
    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "npm test"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_validate_command_blocks_force_push():
    """git push --force should be blocked."""
    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "git push --force origin main"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stdout


def test_validate_command_allows_force_push_to_feature():
    """git push --force to feature branch should be allowed."""
    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "git push --force origin my-app/01-auth"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_validate_command_blocks_rm_rf_root():
    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "rm -rf /"}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2


def _validate(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, encoding="utf-8",
    )


ALLOWED_COMMANDS = [
    # "-f" only inside a branch name, "main" elsewhere in the string
    "git push origin feature/lint-fail && git checkout master",
    "git push -u origin fix/lint-fail",
    # chained command passes --notes-file to another tool; checkout master elsewhere
    "git push origin my-branch && gh release create v1 --notes-file n.md; git checkout master",
    "git push origin my-branch; gh release create v1 --notes-file n.md && git checkout master",
    # separators inside quotes do not start a new push segment
    'git commit -m "docs: git push -f origin main" && git status',
    # force flag belongs to another command, not the push
    "git push origin my-branch && rm -f x.txt main",
    # plain push to the protected branch is fine
    "git push origin main",
    # force toward a feature branch is fine
    "git push --force-with-lease origin feature/x",
    "git push -f origin HEAD:feature/x",
    # attached push-option value is not a flag cluster; redirect target is not a refspec
    "git push -ofast-forward origin main",
    "git push -f origin feature/x > main",
    # non-ASCII text must not crash the inspector into a false block
    'git commit -m "Änderung Ðx" && git status',
    # the words are data, not a command: argument of echo, heredoc body
    "echo git push -f origin main",
    # inline comment is not part of the push
    "git push -f origin feature/x # fix main",
    "git commit -F - <<EOF\nnever run git push -f origin main\nEOF",
    # only the + refspec is forced, and it is not the protected branch
    "git push origin +feature/x main",
]


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_validate_command_allows_false_positives(command):
    result = _validate(command)
    assert result.returncode == 0, result.stdout


BLOCKED_COMMANDS = [
    "git push -f origin main",
    "git push origin main --force",
    "git push --force-with-lease origin master",
    "git push --force-with-lease=main:abc origin main",
    "git push -uf origin main",
    "git push origin +main",
    "git push -f origin HEAD:refs/heads/main",
    "git -C repo push --force origin main",
    "git fetch && git push -f origin master",
    "echo ok; git push --force origin main",
    # multi-line commands: every line is its own segment
    "git fetch origin\ngit push -f origin main",
    "cd repo\ngit push --force origin master",
    "git commit -F - <<EOF\nmsg\nEOF\ngit push -f origin main",
    # a mid-word # is not a comment in bash
    "echo issue#42 && git push -f origin main",
    "curl http://host/#x && git push -f origin main",
    # wrappers and shell keywords in front of the push
    "sudo git push -f origin main",
    "env git push -f origin main",
    "time git push -f origin main",
    "{ git push -f origin main; }",
    "if true; then git push -f origin main; fi",
    "bash -c 'git push -f origin main'",
    "xargs git push -f origin main",
    # pushing every branch force-pushes main too
    "git push --all -f origin",
    "git push --mirror --force origin",
    # nested shell command is not the last segment of the line
    "bash -c 'git push -f origin main'; echo done",
    "bash -c 'git push -f origin main' && echo done",
    # a + refspec forces its own destination
    "git push origin +feature/x +main",
    # value-taking letter in a cluster does not swallow the refspec
    "git push -fo value origin main",
    "git push -f main",
    "sudo -u bob git push -f origin main",
    "timeout 10 git push -f origin main",
    "echo $(git push -f origin main)",
    "echo `git push -f origin master`",
    # nested shell: other forms; backslash continuation
    "eval \"git push --force origin master\"; echo ok",
    "bash -lc 'git push -f origin main'",
    "git push --force \\\n  origin main",
    "git push origin main \\\n  --force",
    # non-cp1252 characters in the same command must not blank the guard
    'git commit -m "✅ done" && git push -f origin main',
]


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_validate_command_still_blocks_real_force_push(command):
    result = _validate(command)
    assert result.returncode == 2, command
    assert "BLOCKED" in result.stdout


def _load_guard():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "force_push_guard", HOOKS_DIR / "force_push_guard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _guard_exit(guard, monkeypatch, command, branch="feature/x"):
    import io

    monkeypatch.setattr(guard, "checked_out_destinations", lambda cwd: [branch])
    monkeypatch.setattr(guard.sys, "stdin", type("S", (), {"buffer": io.BytesIO(command.encode())})())
    return guard.main()


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_force_push_guard_allows_in_process(monkeypatch, command):
    assert _guard_exit(_load_guard(), monkeypatch, command) == 0


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_force_push_guard_blocks_in_process(monkeypatch, command):
    assert _guard_exit(_load_guard(), monkeypatch, command) == 3, command


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command,branch,expected", [
    ("git push -f", "main", 3),
    ("git push --force origin", "master", 3),
    ("git push --force origin HEAD", "main", 3),
    ("git push -f", "feature/x", 0),
    ("git push origin", "main", 0),  # not forced
    # redirects must not become refspecs
    ("git push -f origin 2>&1", "main", 3),
    ("git push --force 2>&1 | tail -5", "main", 3),
    ("git push -f &>/dev/null", "master", 3),
    ("git push -f origin HEAD 2>&1", "main", 3),
    ("git push -f origin 2>&1", "feature/x", 0),
])
def test_force_push_guard_without_explicit_branch_uses_checked_out_branch(
    monkeypatch, command, branch, expected
):
    guard = _load_guard()
    monkeypatch.setattr(guard, "checked_out_destinations", lambda cwd: [branch])
    monkeypatch.setattr(
        guard.sys, "stdin", type("S", (), {"buffer": __import__("io").BytesIO(command.encode())})()
    )
    assert guard.main() == expected


@pytest.mark.covers("FR-01.05/AC08")
def test_force_push_guard_reports_undecided_on_internal_error(monkeypatch):
    guard = _load_guard()

    def boom(_cmd):
        raise RuntimeError("boom")

    monkeypatch.setattr(guard, "segments", boom)
    monkeypatch.setattr(
        guard.sys, "stdin", type("S", (), {"buffer": __import__("io").BytesIO(b"git push -f origin main")})()
    )
    assert guard.main() == guard.UNDECIDED_EXIT


def _hook_copy(tmp_path, guard_body=None, real_guard=False):
    """A private copy of the hook dir, optionally with a replacement/real guard."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    shutil.copy(HOOKS_DIR / "validate_command.sh", hooks / "validate_command.sh")
    if real_guard:
        shutil.copy(HOOKS_DIR / "force_push_guard.py", hooks / "force_push_guard.py")
    if guard_body is not None:
        (hooks / "force_push_guard.py").write_text(guard_body, encoding="utf-8")
    return hooks / "validate_command.sh"


def _run_hook(script, command, env=None):
    return subprocess.run(
        [_bash(), str(script)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


FALLBACK_CASES = [
    ("git push -f origin main", 2),
    ("git push --force origin master", 2),
    ("rm -rf /", 2),
    # forms the first coarse version let through
    ("git -C . push -f origin main", 2),
    ("git push -f origin HEAD:main", 2),
    ("git push origin +main", 2),
    ("git push\t-f origin main", 2),
    ('git commit -m "x" && git push -f origin main', 2),
    ("echo hi\ngit push --force origin master", 2),
    ("git push origin feature/lint-fail", 0),
    ("npm test", 0),
]


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("guard_body", [
    None,  # guard file missing
    "import sys\nsys.exit(4)\n",  # guard cannot decide
    "raise SystemExit(127)\n",  # guard unrunnable
])
@pytest.mark.parametrize("command,expected", FALLBACK_CASES)
def test_hook_degrades_to_coarse_check_when_guard_cannot_decide(tmp_path, guard_body, command, expected):
    result = _run_hook(_hook_copy(tmp_path, guard_body), command)
    assert result.returncode == expected, (command, result.stdout, result.stderr)
    assert "coarse fallback" in result.stderr


@pytest.mark.covers("FR-01.05/AC08")
def test_hook_still_checks_when_python_cannot_extract_the_command():
    """A lone surrogate makes the Python extractor fail; sed must still find the command."""
    result = _run_hook(
        HOOKS_DIR / "validate_command.sh", "git push -f origin main #\ud800"
    )
    assert result.returncode == 2, (result.stdout, result.stderr)


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("command,expected", FALLBACK_CASES)
def test_hook_still_guards_when_no_python_interpreter_is_found(tmp_path, command, expected):
    """Every interpreter candidate fails its probe -> sed/grep path, never a silent allow."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("python3", "python", "py"):
        stub = stubs / name
        stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": str(stubs) + os.pathsep + os.environ.get("PATH", "")}
    # the REAL guard is present: only the missing interpreter can cause the fallback
    result = _run_hook(_hook_copy(tmp_path, real_guard=True), command, env=env)
    assert result.returncode == expected, (command, result.stdout, result.stderr)
    assert "coarse fallback" in result.stderr


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


@pytest.mark.covers("FR-01.05/AC08")
@pytest.mark.parametrize("branch,expected", [("main", 2), ("feature/x", 0)])
def test_registered_hook_judges_a_bare_force_push_by_the_real_checkout(tmp_path, branch, expected):
    """Integration: hooks.json -> validate_command.sh -> force_push_guard.py -> a real git checkout."""
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required for this integration test")
        pytest.skip("git is required for this integration test")
    registered = json.loads((HOOKS_DIR.parent.parent / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in registered["hooks"]["PreToolUse"]
        for hook in group["hooks"]
    ]
    assert any("scripts/hooks/validate_command.sh" in c for c in commands)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    if branch != "main":
        _git(repo, "checkout", "-q", "-b", branch)
    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "validate_command.sh")],
        input=json.dumps({"tool_input": {"command": "git push --force 2>&1 | tail -5"}}),
        capture_output=True, text=True, encoding="utf-8", cwd=repo,
    )
    assert result.returncode == expected, result.stdout


def test_check_destructive_migration_clean(tmp_path):
    """Non-destructive SQL should pass."""
    sql = tmp_path / "supabase" / "migrations" / "001_create.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text("CREATE TABLE users (id UUID PRIMARY KEY);\n")

    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(sql)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_check_destructive_migration_drop_table(tmp_path):
    """DROP TABLE should trigger warning."""
    sql = tmp_path / "supabase" / "migrations" / "002_drop.sql"
    sql.parent.mkdir(parents=True)
    sql.write_text("DROP TABLE users;\n")

    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(sql)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
    # WP4: the block reason is delivered on STDERR (the channel Claude reads on
    # a PostToolUse exit-2 soft block), not the stdout that exit-2 discards.
    assert "DROP TABLE" in result.stderr


def test_check_destructive_non_sql(tmp_path):
    """Non-SQL files should pass without checking."""
    ts = tmp_path / "src" / "app.ts"
    ts.parent.mkdir(parents=True)
    ts.write_text("console.log('hello');\n")

    result = subprocess.run(
        [_bash(), str(HOOKS_DIR / "check_destructive_migration.sh")],
        input=json.dumps({"tool_input": {"file_path": str(ts)}}),
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
