"""End-to-end tests for the section file-attribution checker.

Covers the boundary the pure parser cannot: a real commit range, the rename and
deletion cases external review flagged, and the interaction with a recorded
declaration's attributed extras.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))

from check_section_file_attribution import main  # noqa: E402
from record_requirement_impact import main as record_main  # noqa: E402

SECTION_FILE = ".shipwright/planning/03-auth/sections/01-auth.md"
SECTION_DOC = """# Section: 01-auth

## Files to Create/Modify
- `src/auth/login.ts` — the login handler
- `src/auth/logout.ts` — the logout handler

## Verification
- [ ] All tests pass
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SECTION_FILE, SECTION_DOC)
    _write(tmp_path, "src/lib/http.ts", "export const get = () => {};\n")
    _write(tmp_path, "src/legacy.ts", "export const old = 1;\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def _declare(repo: Path, *extra: str) -> None:
    """The declaration every section must record — the checker now requires it."""
    record_main([
        "--project-root", str(repo), "--run-id", "run-a", "--phase", "build",
        "--scope", "01-auth", "--impact", "none",
        "--reason", "section implemented as specified", *extra,
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ])


def _check(repo: Path, capsys) -> tuple[int, dict]:
    code = main(["--project-root", str(repo), "--section-file", SECTION_FILE,
                 "--run-id", "run-a", "--scope", "01-auth",
                 "--base-ref", "HEAD~1", "--head-ref", "HEAD"])
    return code, json.loads(capsys.readouterr().out)


def test_section_touching_only_declared_files_passes(repo, capsys):
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _write(repo, "src/auth/logout.ts", "export const logout = () => {};\n")
    _commit(repo, "section 01-auth")
    _declare(repo)
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 0
    assert payload["success"] is True
    assert payload["unattributed"] == []


def test_undeclared_shared_touch_fails(repo, capsys):
    """The case the rule is aimed at: shared code changed with no record of why."""
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _write(repo, "src/lib/http.ts", "export const get = () => 'retried';\n")
    _commit(repo, "section 01-auth + a silent shared change")

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["unattributed"] == ["src/lib/http.ts"]
    assert "record_requirement_impact.py" in payload["detail"]


def test_recorded_attributed_extra_makes_the_same_touch_pass(repo, capsys):
    """Part (3): the section MAY touch shared code when it records why."""
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _write(repo, "src/lib/http.ts", "export const get = () => 'retried';\n")
    _commit(repo, "section 01-auth + an attributed shared change")

    record_main([
        "--project-root", str(repo), "--run-id", "run-a", "--phase", "build",
        "--scope", "01-auth", "--impact", "none",
        "--reason", "section matched both the spec and the mockup",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
        "--extra", "src/lib/http.ts=login needed a retry helper on the shared client",
    ])
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 0
    assert payload["declaration_found"] is True
    assert payload["attributed_extras"] == ["src/lib/http.ts"]


def test_declaration_from_another_run_does_not_excuse_the_touch(repo, capsys):
    """A stale extra must not license this run's undeclared change (GPT-1)."""
    _write(repo, "src/lib/http.ts", "export const get = () => 'retried';\n")
    _commit(repo, "shared change")

    record_main([
        "--project-root", str(repo), "--run-id", "SOME-OTHER-RUN", "--phase", "build",
        "--scope", "01-auth", "--impact", "none", "--reason", "old run",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
        "--extra", "src/lib/http.ts=stale attribution",
    ])
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["declaration_found"] is False
    assert payload["unattributed"] == ["src/lib/http.ts"]


def test_none_impact_section_editing_requirements_is_flagged(repo, capsys):
    """Claiming no requirement impact while editing a spec is a real divergence."""
    _write(repo, ".shipwright/planning/01-adopted/spec.md", "# Spec\n\n| FR-01.05 | x |\n")
    _commit(repo, "section 01-auth quietly editing requirements")

    record_main([
        "--project-root", str(repo), "--run-id", "run-a", "--phase", "build",
        "--scope", "01-auth", "--impact", "none", "--reason", "nothing changed",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ])
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["unattributed"] == [".shipwright/planning/01-adopted/spec.md"]


def test_spec_attribution_requires_the_declaration_to_cover_this_range(repo, capsys):
    """A declaration recorded over a DIFFERENT range must not attribute this one.

    Otherwise a broad or older range containing some spec edit would launder an
    unrelated spec change in a later section.
    """
    spec = ".shipwright/planning/01-adopted/spec.md"
    _write(repo, spec, "# Spec\n\n| FR-01.05 | v2 |\n")
    _commit(repo, "an earlier commit that touched the spec")
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _write(repo, spec, "# Spec\n\n| FR-01.05 | v3 |\n")
    _commit(repo, "section 01-auth")

    # Declared over HEAD~2..HEAD — wider than the section's own range.
    record_main([
        "--project-root", str(repo), "--run-id", "run-a", "--phase", "build",
        "--scope", "01-auth", "--impact", "modify", "--fr", "FR-01.05",
        "--base-ref", "HEAD~2", "--head-ref", "HEAD",
    ])
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 1
    assert spec in payload["unattributed"]


def test_deleting_an_undeclared_file_fails(repo, capsys):
    """Removing something out of scope needs the same record as changing it.

    An earlier version reported every deletion and failed none, so
    `git rm shared/lib/legacy_client.py` passed clean — arguably the most
    destructive out-of-scope change was the one class needing no record at all.
    """
    (repo / "src/legacy.ts").unlink()
    _commit(repo, "drop the legacy module")
    _declare(repo)
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["unattributed_deletions"] == ["src/legacy.ts"]


def test_deleting_a_declared_file_passes(repo, capsys):
    """What a section file does not list is the removal of a file it DID declare."""
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _commit(repo, "add the declared file")
    (repo / "src/auth/login.ts").unlink()
    _commit(repo, "and remove it again")
    _declare(repo)
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 0
    assert payload["deleted"] == ["src/auth/login.ts"]
    assert payload["unattributed_deletions"] == []


def test_a_section_with_no_declaration_fails(repo, capsys):
    """The build side had no equivalent of the design gate; now it does."""
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _commit(repo, "section 01-auth, declaring nothing")

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["declaration_found"] is False
    assert "recorded no requirement-impact declaration" in payload["detail"]


def test_rename_source_is_reported_but_the_destination_must_be_accounted_for(repo, capsys):
    """A `git mv` + rewrite of a shared file must not escape the check.

    Git reports that as one `R` record. Excluding BOTH paths — as an earlier
    version did — let the destination through unexamined, so a section could move
    a shared file, rewrite it, and be reported clean. Only the source is
    informational; the destination is a path that now exists and is the
    section's to declare.
    """
    _git(repo, "mv", "src/legacy.ts", "src/renamed.ts")
    _commit(repo, "rename the legacy module")

    code, payload = _check(repo, capsys)

    assert code == 1
    assert payload["renamed"] == ["src/legacy.ts"]
    assert payload["unattributed"] == ["src/renamed.ts"]


def test_a_declared_rename_destination_passes(repo, capsys):
    (repo / "src" / "auth").mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", "src/legacy.ts", "src/auth/login.ts")
    _commit(repo, "move the module into the section's declared path")
    _declare(repo, "--extra", "src/legacy.ts=moved into the section's own module")
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 0
    assert payload["unattributed"] == []


def test_bad_ref_is_a_request_error_not_a_violation(repo, capsys):
    code = main(["--project-root", str(repo), "--section-file", SECTION_FILE,
                 "--run-id", "run-a", "--scope", "01-auth",
                 "--base-ref", "no-such-ref", "--head-ref", "HEAD"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "evidence_unusable"


def test_missing_section_file_is_a_request_error(repo, capsys):
    code = main(["--project-root", str(repo), "--section-file", "nope.md",
                 "--run-id", "run-a", "--scope", "01-auth",
                 "--base-ref", "HEAD~1", "--head-ref", "HEAD"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "section_file_unreadable"


def test_non_repository_is_skipped_and_says_so(tmp_path, capsys):
    _write(tmp_path, SECTION_FILE, SECTION_DOC)
    code = main(["--project-root", str(tmp_path), "--section-file", SECTION_FILE,
                 "--run-id", "run-a", "--scope", "01-auth",
                 "--base-ref", "HEAD~1", "--head-ref", "HEAD"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "skipped"


def test_declaration_file_is_not_itself_flagged(repo, capsys):
    """Step 10 records AFTER the Step 8 commit, so the log is never in range."""
    _write(repo, "src/auth/login.ts", "export const login = () => {};\n")
    _commit(repo, "section 01-auth")

    record_main([
        "--project-root", str(repo), "--run-id", "run-a", "--phase", "build",
        "--scope", "01-auth", "--impact", "none", "--reason", "matched",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ])
    capsys.readouterr()

    code, payload = _check(repo, capsys)

    assert code == 0
    assert not any("requirement-impact" in p for p in payload["unattributed"])
