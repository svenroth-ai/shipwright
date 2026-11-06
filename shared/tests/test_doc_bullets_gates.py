"""S5 gates over bullet drops: budget, shape, documented, conventions-reviewed, committed, aggregate, merge-tree."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.11")

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import architecture_doc, doc_bullets  # noqa: E402
from tools import aggregate_decisions, check_agent_doc_budget, check_agent_doc_shape  # noqa: E402
from tools.write_doc_bullet import write_doc_bullet  # noqa: E402

ARCH = (
    "# Architecture\n\n## Data Flow\n\nprose\n\n## Architecture Updates\n\n"
    "- **iterate-2026-06-01-old** (2026-06-01): Component — old. → decision_log (x)\n\n## Other\n\nz\n"
)
CONV = "# Conventions\n\n## Convention Updates\n\n- **iterate-2026-06-01-old** (2026-06-01): Convention — old. → archive\n\n## Learnings\n\n- (2026-06-01) build — rule. → x\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    docs = root / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True)
    (docs / "architecture.md").write_bytes(ARCH.encode())
    (docs / "conventions.md").write_bytes(CONV.encode())
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "-u", "origin", "main")
    return root


def _bullet(root: Path, run: str, target: str = "conventions", summary: str = "new rule") -> Path:
    impact = "convention" if target == "conventions" else "component"
    return write_doc_bullet(root, target, run, impact=impact, summary=summary, entry_date="2026-11-06")


def test_budget_and_shape_read_folded_plus_pending(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feat")
    good = _bullet(repo, "iterate-2026-11-06-a")
    v, base = check_agent_doc_budget.find_violations(repo, base_ref="main")
    assert base and v == []
    assert check_agent_doc_shape.find_violations(repo, base_ref="main")[0] == []
    # an over-long / non-canonical PENDING bullet is judged exactly like a folded one
    long_bullet = "- **iterate-2026-11-06-big** (2026-11-06): Convention — " + "x" * 700 + ". → decision_log (y)"
    (good.parent / "conventions--iterate-2026-11-06-big--aaaaaaaa--bbbbbbbb.md").write_text(long_bullet + "\n", encoding="utf-8")
    (good.parent / "architecture--camp--aaaaaaaa--cccccccc.md").write_text("- **Campaign foo** (2026-11-06): Component — x. → decision_log (y)\n", encoding="utf-8")
    budget = check_agent_doc_budget.find_violations(repo, base_ref="main")[0]
    shape = check_agent_doc_shape.find_violations(repo, base_ref="main")[0]
    assert [f for f, _, _ in budget] == ["conventions.md"]
    assert [f for f, _, _ in shape] == ["architecture.md"]
    full_pend = check_agent_doc_budget.find_violations(repo, full_corpus=True)[0]
    doc_bullets.fold(repo)
    assert check_agent_doc_budget.find_violations(repo, full_corpus=True)[0] == full_pend  # folded == pending


def test_architecture_documented_gate_sees_pending_bullet(repo: Path) -> None:
    _bullet(repo, "iterate-2026-11-06-a", "architecture")
    texts = architecture_doc.read_target_texts(repo / ".shipwright" / "agent_docs")
    rec = architecture_doc.DropRecord("x.json", "iterate-2026-11-06-a", "component")
    assert architecture_doc.missing_entries([rec], texts) == []
    assert architecture_doc.missing_entries([architecture_doc.DropRecord("y.json", "iterate-2026-11-06-zz", "component")], texts)


def test_old_consumers_see_no_bullet_as_an_adr(repo: Path) -> None:
    _bullet(repo, "iterate-2026-11-06-a")
    _bullet(repo, "iterate-2026-11-06-a", "architecture")
    dd = aggregate_decisions.drop_dir(repo)
    assert dd.joinpath("bullets").is_dir()
    assert aggregate_decisions._snapshot_drops(dd) == []  # the OLD aggregator's file listing
    assert architecture_doc.scan_drops(dd) == ([], [])  # the OLD *.json scan
    assert list(dd.glob("*.json")) == [] and [p for p in dd.iterdir() if p.is_file()] == []  # old WebUI glob shape


def test_aggregate_folds_bullets_before_adrs_without_duplicating(repo: Path) -> None:
    run = "iterate-2026-11-06-a"
    _bullet(repo, run, "architecture")
    dd = aggregate_decisions.drop_dir(repo)
    (dd / f"{run}_001.json").write_text(json.dumps({
        "run_id": run, "date": "2026-11-06", "section": "S", "title": "T", "decision": "D",
        "architecture_impact": "component"}), encoding="utf-8")
    res = aggregate_decisions.aggregate(repo)
    assert res["aggregated"] == 1 and res["bullets_folded"] == 1 and not res["errors"]
    arch = (repo / ".shipwright" / "agent_docs" / "architecture.md").read_text(encoding="utf-8")
    assert arch.count(f"- **{run}**") == 1  # the ADR fallback bullet did not duplicate it
    assert not list((dd / "bullets").glob("*.md"))


def test_two_branches_adding_bullets_are_clean_under_merge_tree(repo: Path, tmp_path: Path) -> None:
    wts = {}
    for name in ("a", "b"):
        wts[name] = tmp_path / f"wt-{name}"
        _git(repo, "worktree", "add", "-q", "-b", name, str(wts[name]), "main")
        _bullet(wts[name], f"iterate-2026-11-06-{name}", "conventions", f"rule {name}")
        _bullet(wts[name], f"iterate-2026-11-06-{name}", "architecture", f"arch {name}")
        _git(wts[name], "add", "-A")
        _git(wts[name], "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", name)
    clean = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", "a", "b"], capture_output=True, text=True)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    # contrast: editing the shared section directly is the conflict this removes
    for name in ("c", "d"):
        _git(repo, "checkout", "-q", "-b", name, "main")
        f = repo / ".shipwright" / "agent_docs" / "conventions.md"
        line = f"- **iterate-2026-11-06-{name}** (2026-11-06): Convention — {name}. → archive" + chr(10)
        old = "→ archive" + chr(10)
        f.write_text(f.read_text(encoding="utf-8").replace(old, old + line, 1), encoding="utf-8")
        _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", name)
    bad = subprocess.run(["git", "-C", str(repo), "merge-tree", "--write-tree", "c", "d"], capture_output=True, text=True)
    assert bad.returncode == 1


def test_conventions_reviewed_accepts_the_runs_own_pending_bullet(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.verifiers import iterate_checks

    ref = (repo / ".shipwright" / "agent_docs" / "conventions.md").stat().st_mtime + 100
    monkeypatch.setattr(iterate_checks, "find_entry_by_run_id", lambda *_: {"intent": "feature"})
    monkeypatch.setattr(iterate_checks, "_freshness_mtime_reference", lambda *_: ref)
    assert iterate_checks.check_conventions_reviewed(repo, "iterate-2026-11-06-a").ok is False
    _bullet(repo, "iterate-2026-11-06-other")  # someone else's bullet does not count
    _bullet(repo, "iterate-2026-11-06-a", "architecture")  # nor does another target
    assert iterate_checks.check_conventions_reviewed(repo, "iterate-2026-11-06-a").ok is False
    _bullet(repo, "iterate-2026-11-06-a")
    assert iterate_checks.check_conventions_reviewed(repo, "iterate-2026-11-06-a").ok is True


def test_failed_fold_keeps_the_drops_and_a_second_fold_is_a_noop(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from lib import atomic_write

    _bullet(repo, "iterate-2026-11-06-a")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_write, "durable_atomic_write", boom)
    res = doc_bullets.fold(repo)
    assert res["errors"] and res["folded"] == 0
    assert len(list(doc_bullets.bullets_dir(repo).glob("*.md"))) == 1
    monkeypatch.undo()
    assert doc_bullets.fold(repo)["folded"] == 1 and doc_bullets.fold(repo)["folded"] == 0


def test_display_order_is_independent_of_discovery_order_and_mtime(repo: Path) -> None:
    import os

    paths = [write_doc_bullet(repo, "learnings", f"iterate-2026-11-06-r{i}", text=f"- (2026-11-0{i + 1}) p — rule {i}. → x")
             for i in range(3)]
    before = doc_bullets.render_pending_summary(repo)
    for n, p in enumerate(reversed(paths)):
        os.utime(p, (1_000_000 + n, 1_000_000 + n))
    assert doc_bullets.render_pending_summary(repo) == before


def test_committed_check_covers_the_runs_bullets(repo: Path) -> None:
    from tools.verifiers.decision_log_gate import check_decision_drop_committed

    _git(repo, "checkout", "-q", "-b", "feat")
    p = _bullet(repo, "iterate-2026-11-06-a")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-qm", "empty")
    head = _git(repo, "rev-parse", "HEAD").strip()
    bad = check_decision_drop_committed(repo, "iterate-2026-11-06-a", head)
    assert bad.ok is False and p.name in bad.detail
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "bullet")
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert check_decision_drop_committed(repo, "iterate-2026-11-06-a", head).ok is True


def test_base_side_includes_bullets_pending_at_the_base(repo: Path) -> None:
    """A non-compliant bullet already pending on main must not read as NEW in every later PR."""
    bd = doc_bullets.bullets_dir(repo)
    bd.mkdir(parents=True)
    long_bullet = "- **iterate-2026-11-05-big** (2026-11-05): Convention — " + "x" * 700 + ". → decision_log (y)"
    (bd / "conventions--iterate-2026-11-05-big--aaaaaaaa--bbbbbbbb.md").write_text(long_bullet + "\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pending bullet on main")
    _git(repo, "push", "-q", "origin", "main")
    _git(repo, "checkout", "-q", "-b", "feat")
    pend = check_agent_doc_budget.find_violations(repo, base_ref="main")[0]
    assert pend == []  # at the base it is already pending, so it is not new here
    doc_bullets.fold(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "fold")
    assert check_agent_doc_budget.find_violations(repo, base_ref="main")[0] == pend  # folded == pending


def test_crlf_doc_pending_render_equals_folded_bytes(repo: Path) -> None:
    docs = repo / ".shipwright" / "agent_docs"
    (docs / "conventions.md").write_bytes(CONV.replace("\n", "\r\n").encode())
    _bullet(repo, "iterate-2026-11-06-a")
    pend = doc_bullets.effective_text(docs, "conventions.md")
    doc_bullets.fold(repo)
    assert (docs / "conventions.md").read_bytes().decode() == pend


def test_aggregate_does_not_fold_adrs_over_a_failed_bullet_fold(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = "iterate-2026-11-06-a"
    _bullet(repo, run, "architecture")
    dd = aggregate_decisions.drop_dir(repo)
    (dd / f"{run}_001.json").write_text(json.dumps({"run_id": run, "section": "S", "decision": "D"}), encoding="utf-8")
    monkeypatch.setattr(doc_bullets, "fold", lambda *_a, **_k: {"folded": 0, "conflicts": [], "errors": ["architecture.md: disk full"]})
    res = aggregate_decisions.aggregate(repo)
    assert res["aggregated"] == 0 and res["bullets_failed"] and (dd / f"{run}_001.json").exists()
    assert aggregate_decisions.main(["--project-root", str(repo)]) == 1


def test_budget_read_ignores_other_files_bullets(repo: Path) -> None:
    (repo / ".shipwright" / "agent_docs" / "architecture.md").unlink()
    _bullet(repo, "iterate-2026-11-06-a")  # a conventions bullet only
    assert check_agent_doc_budget._read(repo, "architecture.md") is None
    assert "iterate-2026-11-06-a" in check_agent_doc_budget._read(repo, "conventions.md")


def test_release_path_reports_a_kept_conflict(repo: Path) -> None:
    p = _bullet(repo, "iterate-2026-11-06-a", "architecture", "first")
    other = p.with_name(p.name[:-11] + "ffffffff.md")
    other.write_bytes(p.read_bytes().replace(b"first", b"second"))
    res = aggregate_decisions.aggregate(repo)
    assert any(other.name in e and "kept" in e for e in res["errors"]) and not res.get("bullets_failed") and other.exists()


def test_architecture_doc_loaded_by_path_still_reads_pending_bullets(repo: Path) -> None:
    """The compliance Group F5 loads architecture_doc by file path (no parent package)."""
    import importlib.util

    _bullet(repo, "iterate-2026-11-06-a", "architecture")
    src = _SCRIPTS / "lib" / "architecture_doc.py"
    spec = importlib.util.spec_from_file_location("_sentinel_architecture_doc", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_sentinel_architecture_doc"] = mod
    try:
        spec.loader.exec_module(mod)
        texts = mod.read_target_texts(repo / ".shipwright" / "agent_docs")
    finally:
        sys.modules.pop("_sentinel_architecture_doc", None)
    assert "iterate-2026-11-06-a" in texts["architecture.md"]


def test_arch_impact_repo_state_test_accepts_a_run_documented_only_by_a_pending_bullet(repo: Path) -> None:
    run = "iterate-2026-11-06-a"
    _bullet(repo, run, "architecture")
    _bullet(repo, run, "conventions")
    texts = architecture_doc.read_target_texts(repo / ".shipwright" / "agent_docs")
    recs = [architecture_doc.DropRecord("a.json", run, "component"), architecture_doc.DropRecord("b.json", run, "convention")]
    assert architecture_doc.missing_entries(recs, texts) == []
