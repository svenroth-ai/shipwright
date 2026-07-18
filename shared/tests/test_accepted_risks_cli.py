"""The accepted-risk reconciler CLI — operator-facing behaviour.

Split out of ``test_accepted_risks_register.py`` when that file crossed the
300-line guideline. That file owns the GATE (live guards + drift negative
controls); this one owns the CLI surface an operator actually reads.

Both halves matter for a different reason. The in-process tests assert on the
wording a human is shown and are what coverage sees; the subprocess tests prove
the real entry point — argument wiring, exit codes, stderr channel — works when
invoked the way CI and a maintainer invoke it. A child process contributes
nothing to coverage, so keeping only those would leave every reporting branch
looking untested while actually being exercised.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import accepted_risks as ar  # noqa: E402
from tools import accepted_risks_cli as cli  # noqa: E402

_CLI = REPO_ROOT / "shared" / "scripts" / "tools" / "accepted_risks_cli.py"

# Negative controls — prove each guard fires
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path, *, register: str | None, workflow_env: str = "",
          trivy: str | None = None) -> Path:
    if register is not None:
        (tmp_path / ar.REGISTER_NAME).write_text(register, encoding="utf-8")
    if trivy is not None:
        (tmp_path / ".trivyignore.yaml").write_text(trivy, encoding="utf-8")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "security.yml").write_text(
        "jobs:\n  scan:\n    steps:\n      - env:\n" + workflow_env, encoding="utf-8"
    )
    return tmp_path


def _register(rule: str, target: str, expires: str = "2099-01-01") -> str:
    return (
        "schema: 1\nacceptances:\n"
        f"  - id: ar-test-entry\n    target: {target}\n    rule: {rule}\n"
        f"    expires: {expires}\n    rationale_ref: ADR-271\n"
        "    statement: >-\n      A sufficiently long justification for the test.\n"
    )

# ---------------------------------------------------------------------------
# Drive main() — the arg wiring is real logic and is otherwise untested
# ---------------------------------------------------------------------------


def _run(root: Path, command: str) -> subprocess.CompletedProcess:
    # Force UTF-8 on the child: a Windows console/pipe defaults to cp1252, and a
    # single non-ASCII byte in the gate's output would otherwise blow up the
    # reader thread instead of failing the assertion under test.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(_CLI), command, "--project-root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )


class TestCliInProcess:
    """Drive the CLI in-process.

    The subprocess tests below prove the real entry point works end to end, but a
    child process contributes nothing to coverage — so every reporting branch
    would look untested while actually being exercised. These call the same
    functions directly and assert on what an operator would read.
    """

    def test_check_reports_clean_repo(self, capsys):
        assert cli.cmd_check(REPO_ROOT) == 0
        out = capsys.readouterr().out
        assert "no drift" in out
        assert "register entr" in out

    def test_check_without_register_is_a_noop(self, tmp_path, capsys):
        assert cli.cmd_check(_repo(tmp_path, register=None)) == 0
        assert "nothing to reconcile" in capsys.readouterr().out

    def test_check_reports_stale_entry(self, tmp_path, capsys):
        root = _repo(tmp_path, register=_register("gone.rule.id",
                                                  ar.TARGET_SEMGREP_RULE))
        assert cli.cmd_check(root) == 1
        out = capsys.readouterr().out
        assert "STALE" in out and "gone.rule.id" in out
        assert "remove the register entry" in out

    def test_check_reports_unrecorded_suppression(self, tmp_path, capsys):
        root = _repo(
            tmp_path,
            register="schema: 1\nacceptances: []\n",
            workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
        )
        assert cli.cmd_check(root) == 1
        out = capsys.readouterr().out
        assert "UNRECORDED" in out and "some.rule.id" in out

    def test_check_names_what_it_did_not_check(self, tmp_path, capsys):
        root = _repo(tmp_path, register=_register("py/some-query",
                                                  ar.TARGET_GITHUB_DISMISSAL))
        assert cli.cmd_check(root) == 0
        # Silence here would read as "checked and clean" — it must say otherwise.
        assert "UNCHECKED" in capsys.readouterr().out

    def test_expire_clean(self, tmp_path, capsys):
        root = _repo(tmp_path, register=_register("some.rule.id",
                                                  ar.TARGET_SEMGREP_RULE))
        assert cli.cmd_expire(root) == 0
        assert "none past due" in capsys.readouterr().out

    def test_expire_without_register_is_a_noop(self, tmp_path, capsys):
        assert cli.cmd_expire(_repo(tmp_path, register=None)) == 0
        assert "no register" in capsys.readouterr().out

    def test_expire_reports_overdue_entry(self, tmp_path, capsys):
        yesterday = ar.today_utc() - timedelta(days=1)
        root = _repo(tmp_path, register=_register(
            "some.rule.id", ar.TARGET_SEMGREP_RULE, expires=yesterday.isoformat()))
        assert cli.cmd_expire(root) == 1
        out = capsys.readouterr().out
        assert "EXPIRED" in out and "ar-test-entry" in out
        assert "renew `expires`" in out

    def test_main_dispatches_both_commands(self, tmp_path):
        root = _repo(tmp_path, register=_register("some.rule.id",
                                                  ar.TARGET_SEMGREP_RULE))
        assert cli.main(["expire", "--project-root", str(root)]) == 0
        assert cli.main(["check", "--project-root", str(root)]) == 1  # stale

    def test_main_fails_closed_in_process(self, tmp_path, capsys):
        root = _repo(tmp_path, register="schema: 1\nacceptances: [broken\n")
        assert cli.main(["check", "--project-root", str(root)]) == 2
        assert "invalid" in capsys.readouterr().err.lower()


def test_main_check_passes_on_this_repo():
    proc = _run(REPO_ROOT, "check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_main_expire_passes_on_this_repo():
    assert _run(REPO_ROOT, "expire").returncode == 0


def test_main_exits_nonzero_on_drift(tmp_path):
    root = _repo(tmp_path, register=_register("gone.rule.id", ar.TARGET_SEMGREP_RULE))
    proc = _run(root, "check")
    assert proc.returncode == 1
    assert "STALE" in proc.stdout


def test_main_fails_closed_on_a_malformed_register(tmp_path):
    root = _repo(tmp_path, register="schema: 1\nacceptances: [broken\n")
    proc = _run(root, "check")
    assert proc.returncode == 2, "a malformed register must never read as 'no drift'"
    assert "invalid" in proc.stderr.lower()


def test_main_is_a_noop_without_a_register(tmp_path):
    proc = _run(_repo(tmp_path, register=None), "check")
    assert proc.returncode == 0, "an absent register is a legacy repo, not an error"


@pytest.mark.parametrize("command", ["check", "expire"])
def test_main_reports_expiry_and_drift_separately(tmp_path, command):
    yesterday = ar.today_utc() - timedelta(days=1)
    root = _repo(
        tmp_path,
        register=_register("some.rule.id", ar.TARGET_SEMGREP_RULE,
                           expires=yesterday.isoformat()),
        workflow_env="          SHIPWRIGHT_SEMGREP_EXCLUDE_RULES: some.rule.id\n",
    )
    proc = _run(root, command)
    # The register agrees with reality, so `check` is clean while `expire` fails.
    assert proc.returncode == (0 if command == "check" else 1), proc.stdout


# ---------------------------------------------------------------------------
# Discovery error branches. Each returns "nothing found" — which, paired with a
# register entry, surfaces as STALE rather than silently as clean. Worth pinning
# so a future refactor cannot turn one into a swallowed exception.
# ---------------------------------------------------------------------------


def test_unreadable_workflow_yields_no_env(tmp_path, monkeypatch):
    root = _repo(tmp_path, register=None)

    def _boom(*_a, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _boom)
    assert cli.read_workflow_env(root) == {}


def test_absent_workflow_yields_no_env(tmp_path):
    assert cli.read_workflow_env(tmp_path) == {}


def test_malformed_trivyignore_yaml_yields_nothing(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text("[oops\n  - broken", encoding="utf-8")
    assert cli.read_trivyignore_ids(tmp_path) == set()


def test_non_mapping_trivyignore_yields_nothing(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text("- a\n- b\n", encoding="utf-8")
    assert cli.read_trivyignore_ids(tmp_path) == set()


def test_trivyignore_entry_without_id_is_skipped(tmp_path):
    (tmp_path / ".trivyignore.yaml").write_text(
        "vulnerabilities:\n  - paths: [a]\n  - id: CVE-OK\n", encoding="utf-8")
    assert cli.read_trivyignore_ids(tmp_path) == {"CVE-OK"}


def test_unreadable_flat_trivyignore_yields_nothing(tmp_path, monkeypatch):
    (tmp_path / ".trivyignore").write_text("CVE-1\n", encoding="utf-8")

    def _boom(*_a, **_kw):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _boom)
    assert cli.read_trivyignore_ids(tmp_path) == set()
