"""F1 artifact-drift detection: a git FAILURE must never read as a clean tree.

AC-7 of iterate-2026-07-31-triage-store-failsafe. Split out of
``test_triage_delivery_failsafe.py`` when that module crossed the 300-line
guideline; the CI-routing / retry-counter halves stayed behind.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import artifact_sync  # noqa: E402


def _sync_config(root: Path) -> None:
    (root / "shipwright_sync_config.json").write_text(
        json.dumps({"mappings": [{"pattern": "src/**", "artifacts": ["d.md"],
                                  "frs": ["FR-01.01"], "category": "x"}]}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# AC-7 — a git failure must not read as a clean tree
# ---------------------------------------------------------------------------

def test_git_failure_reports_error_not_clean(tmp_path: Path) -> None:
    """``detect_drift`` in a NON-repo must say it could not look, not "no drift".

    Before: ``git diff`` exited non-zero, stdout was empty, and the empty
    changed-files list fell through to ``drift_detected: False`` / "No changes
    detected" — indistinguishable from a genuinely clean tree.
    """
    _sync_config(tmp_path)
    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")

    assert result["error"], f"a git failure was reported as a clean tree: {result}"
    assert result["drift_detected"] is False
    assert result["affected"] == []


def test_error_result_keeps_the_published_shape(tmp_path: Path) -> None:
    """The error path must not drop keys other readers rely on."""
    _sync_config(tmp_path)
    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")
    assert {"drift_detected", "message", "affected"} <= set(result)


def test_missing_sync_config_is_not_an_error(tmp_path: Path) -> None:
    """"No config" is a legitimate no-op, NOT a failure — it must stay distinct."""
    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")
    assert result["drift_detected"] is False
    assert not result.get("error")


def test_git_diff_is_routed_through_run_git_with_check_false(tmp_path, monkeypatch) -> None:
    """Asserts on the OUTBOUND call: the argv shape and `check=False`.

    Deliberately NOT named "bounded and utf8" any more — it stubs `run_git` out, so
    it cannot observe either property. Those belong to `run_git` itself and are
    covered where they live (`test_store_git_timeout_paths.py` for the bound,
    `git_base.run_git`'s own `encoding="utf-8"` for the decode). Claiming them here
    was the pass-through-that-is-never-used shape this repo has been bitten by.
    """
    _sync_config(tmp_path)
    seen: dict = {}

    def fake_run_git(args, *, cwd, timeout=None, check=True):
        seen["args"] = args
        seen["check"] = check
        return subprocess.CompletedProcess(["git", *args], 0, "src/a.py\n", "")

    monkeypatch.setattr(artifact_sync, "run_git", fake_run_git)
    artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")

    assert seen["args"][:2] == ["diff", "--name-only"]
    assert seen["check"] is False, "check=True would raise GitError past the handler"


def test_git_diff_decodes_a_non_latin1_path_for_real(tmp_path) -> None:
    """REAL git, REAL non-Latin-1 filename, NO stub — the decode must happen here.

    An earlier version of this test stubbed `run_git` to return an already-decoded
    `str`, which meant the decode never ran inside the test at all: it was green
    against fixed AND unfixed code, i.e. the exact defect the sibling test above was
    renamed for. The decode lives in `git_base.run_git`'s `Popen(encoding="utf-8")`,
    so the stub replaced the very statement under test.
    """
    _sync_config(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    # MEASURED, not assumed: at git's DEFAULT `core.quotepath=true` the diff emits
    # `"src/caf\303\251/..."` — pure ASCII — so the non-Latin-1 bytes never reach the
    # decoder and this test would pass on cp1252 too, exercising nothing. quotepath
    # is off in plenty of real setups, and it is the only way to get raw UTF-8 out.
    subprocess.run(["git", "config", "core.quotepath", "false"], cwd=tmp_path, check=True)
    # The FILENAME is chosen, not decorative. `café/日本.py` was the first pick and it
    # does not discriminate: every byte of its UTF-8 form is DEFINED in cp1252
    # (measured), so the pre-fix locale decode produced mojibake — one non-empty line,
    # no exception — and both assertions below still passed. `Ё` is U+0401 = `d0 81`,
    # and 0x81 is one of cp1252's five UNDEFINED slots, so the pre-fix decode RAISES
    # `UnicodeDecodeError` there. That is a `ValueError`, not a `SubprocessError`, so
    # it escapes detect_drift's handler — the test now fails against unfixed code on
    # the exact platform the defect was reported from, and passes everywhere fixed.
    src = tmp_path / "src" / "Ёж"
    src.mkdir(parents=True)
    target = src / "Ёж.py"
    target.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=tmp_path, check=True)
    # Modify it so `git diff --name-only HEAD` actually EMITS the non-Latin-1 path —
    # on a clean tree the diff is empty and detect_drift early-returns before the
    # decode, which would make this test vacuous in a second way.
    target.write_text("x = 2\n", encoding="utf-8")

    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD")

    assert not result.get("error"), result
    assert result["changed_files_total"] == 1, result


def test_main_exits_2_when_it_could_not_determine_drift(tmp_path, monkeypatch, capsys) -> None:
    """The CLI's exit code is its own contract — asserted directly, not inferred.

    ``finalize_bundle._f1_record`` reads stdout and ignores the exit code, so this
    boundary cannot inherit coverage from that consumer. It matters for anyone
    invoking the script directly, which is how F1 documents running it.
    """
    _sync_config(tmp_path)  # tmp_path is not a git repo -> git diff fails
    monkeypatch.setattr(sys, "argv",
                        ["artifact_sync.py", "--project-root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        artifact_sync.main()
    assert exc.value.code == 2, "a git failure must be distinct from clean(0) and drift(1)"
    assert json.loads(capsys.readouterr().out)["error"]


def test_main_still_exits_0_on_a_clean_run(tmp_path, monkeypatch) -> None:
    """The opposite direction: exit 2 must not swallow the ordinary clean exit."""
    _sync_config(tmp_path)
    monkeypatch.setattr(artifact_sync, "run_git",
                        lambda *a, **k: subprocess.CompletedProcess(["git"], 0, "", ""))
    monkeypatch.setattr(sys, "argv",
                        ["artifact_sync.py", "--project-root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        artifact_sync.main()
    assert exc.value.code == 0


def test_main_exits_1_on_real_drift(tmp_path, monkeypatch) -> None:
    """And a genuine drift still exits 1, so the three states stay distinguishable."""
    _sync_config(tmp_path)
    monkeypatch.setattr(artifact_sync, "run_git",
                        lambda *a, **k: subprocess.CompletedProcess(
                            ["git"], 0, "src/auth/login.py\n", ""))
    monkeypatch.setattr(sys, "argv",
                        ["artifact_sync.py", "--project-root", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        artifact_sync.main()
    assert exc.value.code == 1


def test_import_error_from_the_lazy_seam_reaches_the_structured_result(tmp_path, monkeypatch) -> None:
    """Row 49's real pin. The lazy import exists to survive an ADR-045 `lib` shadow,
    so the failure it was built for must not escape as a bare traceback.

    `ModuleNotFoundError` derives from `ImportError`, not `OSError`, so before this it
    slipped past a handler listing only `SubprocessError`/`FileNotFoundError`.
    """
    _sync_config(tmp_path)

    def shadowed(*_a, **_k):
        raise ModuleNotFoundError("No module named 'lib.git_base'")

    monkeypatch.setattr(artifact_sync, "run_git", shadowed)
    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")

    assert result["error"], result
    assert "ModuleNotFoundError" in result["error"], result


def test_a_one_commit_repo_is_a_no_op_not_a_finalization_abort(tmp_path) -> None:
    """`HEAD~1..HEAD` cannot resolve on a repo with ONE commit — greenfield's first
    iterate, or a shallow CI checkout.

    Doubt review caught this: adding the returncode check turned that into
    `error` -> F1 `failed` -> `finalize_bundle` aborts the WHOLE bundle, for a repo
    whose only sin is being new. It must stay non-blocking (no `error` key), just no
    longer silent about why.
    """
    _sync_config(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "only commit"], cwd=tmp_path, check=True)

    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")

    assert not result.get("error"), f"a one-commit repo aborts finalization: {result}"
    assert result["drift_detected"] is False
    assert "not enough history" in result["message"], result


def test_a_real_git_failure_is_still_an_error(tmp_path) -> None:
    """The opposite direction: the unresolvable-ref escape must not swallow a genuine
    failure, or AC-7's whole point is undone."""
    _sync_config(tmp_path)
    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")  # not a repo
    assert result["error"], result


def test_an_unknown_ref_is_an_error_not_missing_history(tmp_path) -> None:
    """A typo'd ref must stay LOUD, not be downgraded to a no-op.

    External review (GPT) caught this in the first cut of the escape hatch: treating
    every unresolved endpoint as "not enough history" reintroduces exactly the
    false-clean AC-7 exists to close. A real multi-commit repo plus a bad name is the
    discriminating case — `HEAD` resolves, so the HEAD-first guard does not catch it;
    only the base-resolution check does.
    """
    _sync_config(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    for n in (1, 2):
        (tmp_path / f"f{n}.py").write_text(f"x = {n}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", f"c{n}"], cwd=tmp_path, check=True)

    result = artifact_sync.detect_drift(str(tmp_path), ref="no-such-ref..HEAD")

    assert result["error"], f"a bad ref was downgraded to a no-op: {result}"


def test_enough_history_still_compares_normally(tmp_path) -> None:
    """The control: with two commits the default ref resolves and the check RUNS."""
    _sync_config(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    src = tmp_path / "src"
    src.mkdir()
    for n in (1, 2):
        (src / "a.py").write_text(f"x = {n}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", f"c{n}"], cwd=tmp_path, check=True)

    result = artifact_sync.detect_drift(str(tmp_path), ref="HEAD~1..HEAD")

    assert not result.get("error"), result
    assert result["drift_detected"] is True, result


@pytest.mark.parametrize("bad_ref", ["HEAD~bogus..HEAD", "HEAD@{bogus}..HEAD"])
def test_a_malformed_revision_expression_is_an_error(tmp_path, bad_ref) -> None:
    """The follow-up external review found: a malformed SUFFIX on a resolvable base.

    `HEAD~bogus`'s base is `HEAD`, which resolves — so the base-resolution check alone
    classified it as missing history and returned a clean no-op. Only accepting a
    well-formed ancestry suffix (`~`, `~N`, `^`, `^N`) keeps it loud.
    """
    _sync_config(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    for n in (1, 2):
        (tmp_path / f"f{n}.py").write_text(f"x = {n}\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", f"c{n}"], cwd=tmp_path, check=True)

    result = artifact_sync.detect_drift(str(tmp_path), ref=bad_ref)

    assert result["error"], f"{bad_ref} was downgraded to a no-op: {result}"


def test_ancestry_forms_are_recognised_but_junk_is_not() -> None:
    """Unit-level guard on the discriminator itself, both directions."""
    for good in ("HEAD", "HEAD~1", "HEAD~", "HEAD^", "HEAD~2^", "main~10"):
        assert artifact_sync._ANCESTRY_REF.fullmatch(good), good
    for bad in ("HEAD~bogus", "HEAD@{bad}", "HEAD~1~x"):
        assert not artifact_sync._ANCESTRY_REF.fullmatch(bad), bad
