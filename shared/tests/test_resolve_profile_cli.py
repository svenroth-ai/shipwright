"""``resolve_profile.py`` CLI (S1 items 3-6, 9, 12, 13): in-process plus one subprocess smoke.

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))
import resolve_profile as cli  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")
_CLI = Path(cli.__file__)


def _run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_resolve_json_stdout_clean_provenance_on_stderr(project, capsys):
    write_profile(proj_dir(project), "vite-hono")
    code, out, err = _run(capsys, "resolve", "--project-root", str(project),
                          "--name", "vite-hono", "--json")
    assert code == 0
    data = json.loads(out)  # stdout is pure JSON (no provenance line)
    assert data["source"] == "project" and data["name"] == "vite-hono"
    assert "source=project" in err and "shadows:" in err and "WARNING" in err


def test_path_only_prints_path_and_sentinel_prints_nothing(project, capsys):
    code, out, _ = _run(capsys, "resolve", "--project-root", str(project),
                        "--name", "vite-hono", "--path-only")
    assert code == 0 and out.strip().endswith("vite-hono.json")
    for sentinel in ("generic", "detecting"):
        code, out, err = _run(capsys, "resolve", "--project-root", str(project),
                              "--name", sentinel, "--path-only")
        assert (code, out) == (0, "") and "builtin" in err


def test_exit_codes(project, capsys):
    d = proj_dir(project)
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{", encoding="utf-8")
    write_profile(d, "new", schema_version=99)
    root = ["--project-root", str(project)]
    code, out, err = _run(capsys, "resolve", *root, "--name", "missing")
    assert code == 2 and out == "" and "Searched" in err
    code, out, err = _run(capsys, "resolve", *root, "--name", "bad")
    assert code == 3 and "bad.json" in err
    code, out, err = _run(capsys, "resolve", *root, "--name", "new")
    assert code == 3 and "schema_version 99" in err and "copy the bundled profile" in err
    code, out, err = _run(capsys, "resolve", *root, "--name", "../x")
    assert code == 3


@pytest.mark.parametrize("argv", [[], ["bogus"], ["resolve"], ["validate"],
                                  ["validate", "--name", "a", "--file", "b"],
                                  ["resolve", "--name", "x", "--nope"]])
def test_usage_errors_exit_4_not_argparse_2(argv, capsys):
    assert cli.main(argv) == 4
    assert capsys.readouterr().out == ""


def test_list_json_contract_pinned(project, user_dir, capsys):
    write_profile(proj_dir(project), "mine")
    (proj_dir(project) / "broken.json").write_text("{", encoding="utf-8")
    code, out, _ = _run(capsys, "list", "--project-root", str(project), "--json")
    data = json.loads(out)
    assert code == 0 and data["contract_version"] == 1
    assert set(data) == {"contract_version", "profiles", "warnings", "searched"}
    by = {r["name"]: r for r in data["profiles"]}
    assert by["mine"]["valid"] and by["broken"]["valid"] is False
    assert {"supabase-nextjs", "vite-hono", "python-plugin-monorepo"} <= set(by)
    code, text, _ = _run(capsys, "list", "--project-root", str(project))
    assert "INVALID" in text and "mine\tproject" in text


def test_validate_by_name_and_file(project, tmp_path, capsys):
    root = ["--project-root", str(project)]
    code, out, _ = _run(capsys, "validate", *root, "--name", "vite-hono")
    assert code == 0 and out.startswith("ok: vite-hono")
    f = write_profile(tmp_path / "x", "anything")
    code, out, err = _run(capsys, "validate", *root, "--file", str(f), "--json")
    assert code == 0 and json.loads(out)["source"] == "explicit"


def test_list_and_validate_are_read_only(project, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("must not spawn")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    assert _run(capsys, "list", "--project-root", str(project))[0] == 0
    assert _run(capsys, "validate", "--project-root", str(project), "--name", "vite-hono")[0] == 0
    assert not hasattr(cli, "_expand_env")


def test_utf8_output_for_non_ascii_description(project, capsys):
    write_profile(proj_dir(project), "umlaut", description="Stärke – 日本")
    code, out, _ = _run(capsys, "list", "--project-root", str(project), "--json")
    assert code == 0 and "Stärke" in out


def test_subprocess_smoke(project, tmp_path, isolate_user_profiles_dir):
    done = subprocess.run(
        [sys.executable, str(_CLI), "resolve", "--project-root", str(project),
         "--name", "vite-hono", "--path-only"],
        capture_output=True, text=True, encoding="utf-8", check=False)
    assert done.returncode == 0
    assert done.stdout.strip().endswith("vite-hono.json")
    assert "source=bundled" in done.stderr


def _contract_view(out: dict, project: Path) -> dict:
    """Shape-only view of ``list --json`` (paths and prose normalised away)."""
    return {
        "contract_version": out["contract_version"],
        "top_level_keys": sorted(out),
        "row_keys": sorted(out["profiles"][0]),
        # shape sample of ONE bundled row; adding a bundled profile is not a contract change
        "profiles": [{"name": r["name"], "source": r["source"], "valid": r["valid"],
                      "kind": r["kind"], "schema_version": r["schema_version"]}
                     for r in out["profiles"]
                     if r["source"] != "bundled" or r["name"] == "vite-hono"],
        "warnings": len(out["warnings"]),
    }


def test_list_json_matches_checked_in_contract_fixture(project, user_dir, capsys):
    write_profile(proj_dir(project), "mine")
    (proj_dir(project) / "broken.json").write_text("{", encoding="utf-8")
    _, out, _ = _run(capsys, "list", "--project-root", str(project), "--json")
    fixture = Path(__file__).parent / "fixtures" / "profile_list_contract_v1.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    assert _contract_view(json.loads(out), project) == expected, (
        "list --json is a cross-repo contract (WebUI): a shape change is a major bump")
