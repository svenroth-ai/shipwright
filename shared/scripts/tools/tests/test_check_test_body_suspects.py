"""``check_test_body_suspects.py`` — the P3.7 deferred item, advisory-only,
delivered bundled with P3.8. Over a real git repo (``_keystone_repo.py``,
shared with the P3.6/P3.7 keystone tests).

**The one property every test in this module cares about, directly or
indirectly: the CLI never returns a non-zero exit code — not on a clean run,
not on an advisory finding, and not on an infrastructure fault.** That is
the whole point of this check (see the script's own module docstring).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_test_body_suspects as cli  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all as _commit_all  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402

_TOOLS = Path(__file__).resolve().parents[1]
_TEST_FILE = "tests/test_widget.py"
_ORIGINAL_BODY = 'def test_fizz():\n    assert widget.fizz() == "fizz"\n'
_EDITED_BODY = 'def test_fizz():\n    assert widget.fizz() == "fizz"\n    assert True\n'


def _repo_with_test_file(tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / _TEST_FILE).write_text(_ORIGINAL_BODY, encoding="utf-8")
    base_sha = _commit_all(root, "add test file")
    return root, base_sha


def _run(root: Path, head_sha: str, base_sha: str, capsys) -> tuple[int, dict]:
    argv = ["--project-root", str(root), "--head-sha", head_sha, "--base-sha", base_sha]
    code = cli.main(argv)
    payload = json.loads(capsys.readouterr().out)
    return code, payload


def test_a_docs_only_commit_is_clean_and_exits_zero(capsys, tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / "README.md").write_text("hi\n", encoding="utf-8")
    head_sha = _commit_all(root, "docs")

    code, payload = _run(root, head_sha, base_sha, capsys)

    assert code == cli.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["suspects"] == []


def test_a_body_edit_is_advisory_and_still_exits_zero(capsys, tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / _TEST_FILE).write_text(_EDITED_BODY, encoding="utf-8")
    head_sha = _commit_all(root, "edit the test body only")

    code, payload = _run(root, head_sha, base_sha, capsys)

    assert code == cli.EXIT_OK  # advisory means advisory
    assert payload["status"] == "advisory"
    assert payload["suspects"] == [
        {"fr_id": "FR-01.01", "ac_id": "AC01", "test_id": "tests/test_widget.py::test_fizz"},
    ]
    assert "note" in payload


def test_an_unresolvable_base_still_exits_zero(capsys, tmp_path):
    """No merge-base at all (a single-commit repo with no `origin` remote) is
    an infra fault -- reported as `not_evaluated`, never a non-zero exit."""
    root, base_sha = _repo_with_test_file(tmp_path)
    code = cli.main(["--project-root", str(root), "--head-sha", base_sha])
    payload = json.loads(capsys.readouterr().out)

    assert code == cli.EXIT_OK
    assert payload["status"] == "not_evaluated"


def test_an_unreadable_manifest_still_exits_zero(capsys, tmp_path):
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / "README.md").write_text("hi\n", encoding="utf-8")
    head_sha = _commit_all(root, "docs")
    (root / cli.MANIFEST_RELPATH).write_text("not json", encoding="utf-8")

    code, payload = _run(root, head_sha, base_sha, capsys)

    assert code == cli.EXIT_OK
    assert payload["status"] == "not_evaluated"
    assert "error" in payload


def test_the_cli_starts_and_exits_cleanly_as_a_real_subprocess(tmp_path):
    """Deliberately the ONLY subprocess case in this module (house convention,
    ``test_keystone_gate_infra.py``)."""
    root, base_sha = _repo_with_test_file(tmp_path)
    (root / _TEST_FILE).write_text(_EDITED_BODY, encoding="utf-8")
    head = _commit_all(root, "edit the test body only")
    done = subprocess.run(
        [sys.executable, str(_TOOLS / "check_test_body_suspects.py"),
         "--project-root", str(root), "--head-sha", head, "--base-sha", base_sha],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert payload["status"] == "advisory"
