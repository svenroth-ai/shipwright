"""Adopt goes through the stack-profile resolver (campaign stack-profile-resolver, S3).

Brief S3 acceptance (7): a custom profile is matched from a fixture repo; an unknown
override fails with nothing written; an invalid custom profile is warned about in
discovery but fatal when selected; a same-name shadow never receives a bundled
template (D9); bundled matching is unchanged (see test_profile_matcher.py).
Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import lib.adopt_profile as adopt_profile
from lib.ci_workflow_scaffolder import scaffold_ci_workflow
from lib.codeql_workflow_scaffolder import scaffold_codeql_workflow
from lib.profile_matcher import match_profile
from lib.stack_detector import detect_stack
from tools.analyze_codebase import analyze, main as analyze_main
from tools.generate_adoption_artifacts import generate

pytestmark = pytest.mark.covers("FR-01.06")

_REPO = Path(__file__).resolve().parents[3]
_PY_SIG = {"runtime": {"python": "3"}, "frontend": {}, "backend": {"fastapi": "1"}, "database": {}, "auth": {}}


def _write_profile(root: Path, name: str, data: dict | str | None = None, where: str = ".shipwright/profiles") -> Path:
    path = root / where / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data if data is not None else {"name": name}), encoding="utf-8")
    return path


def _python_stack_profile(name: str) -> dict:
    return {"name": name, "stack": {"runtime": {"python": "3"}, "backend": {"fastapi": "1"}}}


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "p"\ndependencies = ["fastapi"]\n', encoding="utf-8")
    return root


def _snapshot(root: Path, matched: str | None) -> Path:
    snap = root / ".shipwright" / "adopt" / "snapshot.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    body = {"project_root": str(root), "stack": {}, "profile": {"matched": matched or "generic"}}
    snap.write_text(json.dumps(body), encoding="utf-8")
    return snap


def _generate(root: Path, snap: Path, override: str | None = None) -> dict:
    return generate(
        root, snapshot_path=snap, enrichment_path=root / "no-enrichment.json",
        routes_path=root / "no-routes.json", split_name="01-adopted", plugin_version="0.0.0",
        scope_override=None, profile_override=override, write_sync=False, backfill_events=False,
    )


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git/" not in p.as_posix()}


# --- matcher ------------------------------------------------------------------


def test_custom_project_profile_is_matched_and_marked_project(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "my-fastapi", _python_stack_profile("my-fastapi"))
    out = analyze(root, [], None)["profile"]
    assert out["matched"] == "my-fastapi" and out["source"] == "project" and out["confidence"] >= 0.3
    assert out["warnings"] == []
    assert {c["name"] for c in out["candidates"]} >= {"my-fastapi"}


def test_user_level_profile_is_matched(tmp_path):
    root = _repo(tmp_path)
    _write_profile(Path(os.environ["SHIPWRIGHT_USER_PROFILES_DIR"]), "user-fastapi", _python_stack_profile("user-fastapi"), where=".")
    out = analyze(root, [], None)["profile"]
    assert (out["matched"], out["source"]) == ("user-fastapi", "user")


def test_first_directory_owns_a_name_and_an_invalid_owner_blocks_the_lower_one(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "python-plugin-monorepo", "{ not json")  # invalid project file keeps its name
    out = analyze(root, [], None)["profile"]
    assert "python-plugin-monorepo" not in {c["name"] for c in out["candidates"]}
    assert any("python-plugin-monorepo.json" in w and "skipped" in w for w in out["warnings"])


def test_discovery_skips_invalid_candidates_with_warnings_never_fatal(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "broken", "{ nope")
    _write_profile(root, "too-new", {"name": "too-new", "schema_version": 99, "stack": {"runtime": {"python": "3"}}})
    _write_profile(root, "Upper-Case", {"name": "Upper-Case"})
    _write_profile(root, "wrong-name", {"name": "other"})
    clean = analyze(_repo(tmp_path / "clean"), [], None)["profile"]
    out = analyze(root, [], None)["profile"]
    assert (out["matched"], out["source"]) == (clean["matched"], clean["source"])  # bundled matching unchanged
    joined = "\n".join(out["warnings"])
    for stem in ("broken", "too-new", "Upper-Case", "wrong-name"):
        assert f"{stem}.json" in joined


def test_minimal_custom_profile_below_threshold_returns_generic(tmp_path):
    """Documented behaviour: adopt scores metadata keys only; select a minimal profile via --profile."""
    root = _repo(tmp_path)
    _write_profile(root, "minimal", {"name": "minimal"})
    out = analyze(root, [], None)["profile"]
    assert out["matched"] != "minimal"
    sig = detect_stack(root, set())
    only_minimal = match_profile(sig, [("project", str(root / ".shipwright" / "profiles"))])
    assert (only_minimal["matched"], only_minimal["source"]) == ("generic", "builtin")


def test_a_single_directory_is_still_accepted_and_non_profile_files_are_ignored(tmp_path):
    d = tmp_path / "profiles"
    _write_profile(tmp_path, "reducibility-idioms", {"name": "reducibility-idioms", "stack": {"runtime": {"python": "3"}}}, where="profiles")
    _write_profile(tmp_path, "real", _python_stack_profile("real"), where="profiles")
    out = match_profile(_PY_SIG, d)
    assert out["matched"] == "real" and out["source"] == "explicit"


def test_unlistable_directory_is_a_warning(tmp_path, monkeypatch):
    d = tmp_path / "p"
    d.mkdir()
    real = os.listdir
    monkeypatch.setattr(os, "listdir", lambda p=".": (_ for _ in ()).throw(PermissionError(13, "denied")) if str(p) == str(d) else real(p))
    out = match_profile(_PY_SIG, [("project", str(d))])
    assert out["matched"] == "generic" and "cannot list profiles" in out["warnings"][0]


def test_hint_keeps_user_hint_source_and_discovery_warnings(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "broken", "{ nope")
    out = analyze(root, [], "vite-hono")["profile"]
    assert out["source"] == "user-hint" and any("broken.json" in w for w in out["warnings"])


# --- analyze: a missing bundled dir is an error --------------------------------


def test_missing_bundled_dir_is_an_error_not_generic(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _, pr = adopt_profile.load_resolver()
    monkeypatch.setattr(pr, "search_dirs", lambda project_root: [("bundled", str(tmp_path / "gone"))])
    with pytest.raises(FileNotFoundError, match="bundled stack profiles directory or schema not found"):
        analyze(root, [], None)
    monkeypatch.setattr(sys, "argv", ["analyze_codebase.py", "--project-root", str(root)])
    assert analyze_main() == 1
    assert "bundled stack profiles directory or schema not found" in capsys.readouterr().err
    assert not (root / ".shipwright" / "adopt" / "snapshot.json").exists()


# --- generate: effective profile resolved BEFORE any write ---------------------


def test_unknown_override_fails_with_nothing_written(tmp_path, capsys):
    root = _repo(tmp_path)
    snap = _snapshot(root, "vite-hono")
    before = _tree(root)
    with pytest.raises(SystemExit) as exc:
        _generate(root, snap, override="no-such-stack")
    err = capsys.readouterr().err
    assert exc.value.code == 2  # the resolver's not-found exit code survives
    assert "no-such-stack" in err and "nothing was written" in err and "--profile" in err
    assert _tree(root) == before


@pytest.mark.parametrize("bad", ["My_Stack", "../x", "Generic2", "con"])
def test_invalid_override_names_fail_with_nothing_written(tmp_path, bad):
    root = _repo(tmp_path)
    snap = _snapshot(root, None)
    before = _tree(root)
    with pytest.raises(SystemExit):
        _generate(root, snap, override=bad)
    assert _tree(root) == before


def test_snapshot_selected_profile_that_became_invalid_aborts_before_any_write(tmp_path, capsys):
    root = _repo(tmp_path)
    path = _write_profile(root, "my-fastapi", _python_stack_profile("my-fastapi"))
    snap = _snapshot(root, "my-fastapi")  # the snapshot (discovery) saw it valid ...
    path.write_text("{ corrupted", encoding="utf-8")  # ... then it broke before generation
    before = _tree(root)
    with pytest.raises(SystemExit) as exc:
        _generate(root, snap)
    err = capsys.readouterr().err
    assert exc.value.code == 3 and "my-fastapi.json" in err and "snapshot.json" in err
    assert _tree(root) == before
    assert not (root / "shipwright_run_config.json").exists()


def test_schema_drift_in_a_selected_profile_is_fatal(tmp_path, capsys):
    root = _repo(tmp_path)
    _write_profile(root, "future", {"name": "future", "schema_version": 99})
    snap = _snapshot(root, None)
    with pytest.raises(SystemExit):
        _generate(root, snap, override="future")
    assert "schema_version" in capsys.readouterr().err


def test_missing_snapshot_match_means_generic_and_sentinels_resolve_builtin(tmp_path):
    root = _repo(tmp_path)
    res = _generate(root, _snapshot(root, None))
    assert (res["profile"]["name"], res["profile"]["source"]) == ("generic", "builtin")
    assert json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))["profile"] == "generic"
    assert res["ci_workflow"]["reason"] == "no_template_for_profile" and "no CI template" in res["ci_workflow"]["message"]


def test_custom_override_wins_over_the_snapshot_match_and_gets_no_template(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "my-fastapi", _python_stack_profile("my-fastapi"))
    res = _generate(root, _snapshot(root, "vite-hono"), override="my-fastapi")  # snapshot says vite-hono
    assert (res["profile"]["name"], res["profile"]["source"]) == ("my-fastapi", "project")
    assert json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8"))["profile"] == "my-fastapi"
    assert res["ci_workflow"]["reason"] == "no_template_for_profile"
    assert "my-fastapi" in res["ci_workflow"]["message"]
    assert res["codeql_workflow"]["reason"] == "no_codeql_for_profile"
    assert not (root / ".github" / "workflows" / "ci.yml").exists()


def test_bundled_override_wins_over_the_snapshot_match_for_scaffolds(tmp_path):
    root = _repo(tmp_path)
    res = _generate(root, _snapshot(root, "generic"), override="vite-hono")
    assert res["profile"]["source"] == "bundled"
    assert res["ci_workflow"]["reason"] == "scaffolded"
    assert "javascript-typescript" in (root / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")


# --- D9: a same-name shadow never gets a bundled template -----------------------


def test_same_name_shadow_gets_no_bundled_templates(tmp_path):
    root = _repo(tmp_path)
    shadow = _write_profile(root, "supabase-nextjs", {"name": "supabase-nextjs", "testing": {"command": "make test"}})
    res = _generate(root, _snapshot(root, "supabase-nextjs"))
    assert res["profile"]["source"] == "project"
    assert shadow.is_file()
    assert res["ci_workflow"]["reason"] == "no_template_for_profile"
    assert res["codeql_workflow"]["reason"] == "no_codeql_for_profile"
    assert not (root / ".github" / "workflows" / "ci.yml").exists()


def test_scaffolders_key_on_provenance_not_name(tmp_path):
    for source in ("project", "user", "explicit"):
        proj = tmp_path / source
        proj.mkdir()
        assert scaffold_ci_workflow(proj, profile_name="supabase-nextjs", source=source)["reason"] == "no_template_for_profile"
        assert scaffold_codeql_workflow(proj, profile_name="supabase-nextjs", source=source)["reason"] == "no_codeql_for_profile"
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    assert scaffold_ci_workflow(bundled, profile_name="supabase-nextjs", source="bundled")["reason"] == "scaffolded"
    # no provenance (legacy callers): name-keyed lookup as before
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    assert scaffold_codeql_workflow(legacy, profile_name="vite-hono")["reason"] == "scaffolded"


# --- plugin layout (stale-cache rule) ------------------------------------------


def test_adopt_profile_imports_the_resolver_through_the_plugin_layout(tmp_path):
    """adopt_profile.py copied to <root>/<plugin>/<ver>/scripts/lib resolves ../../../../shared (parents[4])."""
    cache = tmp_path / "cache" / "shipwright"
    lib = cache / "shipwright-adopt" / "1.0.0" / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy2(_REPO / "plugins" / "shipwright-adopt" / "scripts" / "lib" / "adopt_profile.py", lib)
    shared = cache / "shared"
    (shared / "scripts").mkdir(parents=True)
    for f in (_REPO / "shared" / "scripts").glob("profile_*.py"):
        shutil.copy2(f, shared / "scripts" / f.name)
    shutil.copytree(_REPO / "shared" / "profiles", shared / "profiles")
    shutil.copytree(_REPO / "shared" / "schemas", shared / "schemas")
    proj = tmp_path / "proj"
    _write_profile(proj, "my-stack", {"name": "my-stack"})
    code = (
        "import json, sys, importlib.util as u\n"
        f"s = u.spec_from_file_location('adopt_profile', r'{lib / 'adopt_profile.py'}')\n"
        "m = u.module_from_spec(s); s.loader.exec_module(m)\n"
        f"d = m.discovery_dirs(r'{proj}')\n"
        f"r = m.resolve_effective(r'{proj}', 'my-stack', {{}})\n"
        "print(json.dumps([[x[0] for x in d], r.source]))\n"
    )
    env = {**os.environ, "SHIPWRIGHT_USER_PROFILES_DIR": str(tmp_path / "u")}
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout.strip().splitlines()[-1]) == [["project", "user", "bundled"], "project"]


# --- review follow-ups ---------------------------------------------------------


def test_provenance_change_between_analysis_and_generation_aborts(tmp_path, capsys):
    """A project 'vite-hono' matched at analysis, deleted before generation: no silent bundled swap."""
    root = _repo(tmp_path)
    path = _write_profile(root, "vite-hono", {"name": "vite-hono", "stack": {"runtime": {"python": "3"}}})
    snap = _snapshot(root, "vite-hono")
    body = json.loads(snap.read_text(encoding="utf-8"))
    body["profile"]["source"] = "project"
    snap.write_text(json.dumps(body), encoding="utf-8")
    path.unlink()
    before = _tree(root)
    with pytest.raises(SystemExit):
        _generate(root, snap)
    assert "now resolves from bundled" in capsys.readouterr().err
    assert _tree(root) == before


def test_shadow_is_reported_in_the_adopt_result(tmp_path):
    root = _repo(tmp_path)
    _write_profile(root, "vite-hono", {"name": "vite-hono"})
    res = _generate(root, _snapshot(root, "vite-hono"))
    assert res["profile"]["source"] == "project" and res["profile"]["shadows"]
    assert any("shadows the bundled" in w for w in res["profile"]["warnings"])


def test_matcher_ignores_non_profile_files_and_case_collisions(tmp_path):
    d = tmp_path / "profiles"
    _write_profile(tmp_path, "reducibility-idioms", {"name": "reducibility-idioms", "stack": {"runtime": {"python": "3"}}}, where="profiles")
    _write_profile(tmp_path, "Mixed-Case", _python_stack_profile("Mixed-Case"), where="profiles")
    out = match_profile(_PY_SIG, [("project", str(d))])
    assert out["matched"] == "generic"
    assert any("Mixed-Case.json" in w for w in out["warnings"])


def test_analyze_cli_prints_discovery_warnings(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _write_profile(root, "broken", "{ nope")
    monkeypatch.setattr(sys, "argv", ["analyze_codebase.py", "--project-root", str(root)])
    assert analyze_main() == 0
    assert "WARNING: stack profile:" in capsys.readouterr().err


@pytest.mark.parametrize("stack", [None, "python", ["python"], 3])
def test_a_profile_with_a_non_object_stack_is_not_a_crash(tmp_path, stack):
    root = _repo(tmp_path)
    _write_profile(root, "odd-stack", {"name": "odd-stack", "stack": stack})
    out = analyze(root, [], None)["profile"]
    assert out["matched"] != "odd-stack"


def test_detecting_is_not_an_adopt_profile(tmp_path, capsys):
    root = _repo(tmp_path)
    with pytest.raises(SystemExit):
        _generate(root, _snapshot(root, None), override="detecting")
    assert "detecting" in capsys.readouterr().err
    assert not (root / "shipwright_run_config.json").exists()


def test_an_unresolvable_hint_is_a_snapshot_warning(tmp_path):
    root = _repo(tmp_path)
    out = analyze(root, [], "no-such-stack")["profile"]
    assert any("--profile-hint 'no-such-stack' does not resolve" in w for w in out["warnings"])
    assert not any("does not resolve" in w for w in analyze(root, [], "vite-hono")["profile"]["warnings"])


def test_an_absent_user_profiles_directory_is_not_a_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_USER_PROFILES_DIR", str(tmp_path / "does-not-exist"))
    assert analyze(_repo(tmp_path), [], None)["profile"]["warnings"] == []


def test_snapshot_profile_deleted_since_analysis_gets_the_drift_message(tmp_path, capsys):
    root = _repo(tmp_path)
    snap = _snapshot(root, "my-fastapi")
    body = json.loads(snap.read_text(encoding="utf-8"))
    body["profile"]["source"] = "project"
    snap.write_text(json.dumps(body), encoding="utf-8")  # matched from the project, file never existed now
    with pytest.raises(SystemExit) as exc:
        _generate(root, snap)
    assert exc.value.code == 2 and "no longer exists" in capsys.readouterr().err


def test_resolver_wording_for_an_absent_user_directory_is_what_the_matcher_filters(tmp_path):
    """profile_matcher drops this one warning by its suffix: pin the resolver's wording."""
    _, pr = adopt_profile.load_resolver()
    listing = pr.list_profiles(search_dirs=[("user", str(tmp_path / "nope"))])
    assert [w for w in listing["warnings"] if w.endswith("user profiles directory does not exist")]


def test_corrupt_or_malformed_snapshot_never_becomes_generic(tmp_path, capsys):
    root = _repo(tmp_path)
    snap = root / ".shipwright" / "adopt" / "snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SystemExit):
        _generate(root, snap)
    assert "unreadable or has no" in capsys.readouterr().err and not (root / "shipwright_run_config.json").exists()
    snap.write_text(json.dumps({"stack": {}, "profile": "vite-hono"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _generate(root, snap)
    assert not (root / "shipwright_run_config.json").exists()


def test_equal_scores_go_to_the_higher_source_whatever_the_name(tmp_path):
    root = _repo(tmp_path)
    for name in ("aaa-copy", "zzz-copy"):
        _write_profile(root, name, _python_stack_profile(name))
    _write_profile(Path(os.environ["SHIPWRIGHT_USER_PROFILES_DIR"]), "aaa-user", _python_stack_profile("aaa-user"), where=".")
    assert analyze(root, [], None)["profile"]["matched"] == "aaa-copy"  # project beats user beats bundled
    (root / ".shipwright" / "profiles" / "aaa-copy.json").unlink()
    (root / ".shipwright" / "profiles" / "zzz-copy.json").unlink()
    assert analyze(root, [], None)["profile"]["source"] == "user"


@pytest.mark.parametrize("body", [{"stack": {}}, {"stack": {}, "profile": None}, {"stack": {}, "profile": {}}, {"profile": {"matched": ""}}, ["x"]])
def test_a_snapshot_without_profile_matched_is_refused_unless_overridden(tmp_path, capsys, body):
    root = _repo(tmp_path)
    snap = root / ".shipwright" / "adopt" / "snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(SystemExit):
        _generate(root, snap)
    assert "profile.matched" in capsys.readouterr().err
    assert not (root / "shipwright_run_config.json").exists()
    if isinstance(body, dict):
        assert _generate(root, snap, override="generic")["profile"]["name"] == "generic"


def test_cli_warning_prefix_is_not_doubled(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _write_profile(root, "vite-hono", {"name": "vite-hono", "stack": {"runtime": {"python": "3"}, "backend": {"fastapi": "1"}}})
    monkeypatch.setattr(sys, "argv", ["analyze_codebase.py", "--project-root", str(root)])
    assert analyze_main() == 0
    err = capsys.readouterr().err
    assert "shadows the bundled" in err and "WARNING: stack profile: WARNING:" not in err
