"""S5 (issue 978): conventions / architecture bullets as per-run drop files.

Kill criterion 7: two branches adding bullets are clean under ``merge-tree``; old consumers never
see a bullet as an ADR; render identical pending vs folded; budget/shape read folded + pending;
cap overflow warns; fold order (bullets before ADRs).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.11")

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import doc_bullets  # noqa: E402
from lib.agent_doc_budget import ENTRY_MAX_CHARS  # noqa: E402
from tools.write_doc_bullet import DocBulletError, main as write_main, write_doc_bullet  # noqa: E402

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


def test_writer_names_content_and_idempotence(repo: Path) -> None:
    p = _bullet(repo, "iterate-2026-11-06-a")
    assert p.parent == doc_bullets.bullets_dir(repo) and p.suffix == ".md"
    assert doc_bullets._NAME.match(p.name) and "--iterate-2026-11-06-a--" in p.name
    raw = p.read_bytes()
    assert raw.endswith(b"\n") and b"\r" not in raw
    assert raw.decode().startswith("- **iterate-2026-11-06-a** (2026-11-06): Convention — new rule. → decision_log")
    assert _bullet(repo, "iterate-2026-11-06-a") == p  # identical retry = same file
    with pytest.raises(DocBulletError):  # a different bullet for the same anchor is refused
        _bullet(repo, "iterate-2026-11-06-a", summary="other")


@pytest.mark.parametrize("kw", [
    {"text": "- **iterate-2026-11-06-a** (2026-11-06): Convention — x.\nsecond", "impact": ""},
    {"text": "not a bullet"},
    {"text": "- free text anchor"},
    {"impact": "component", "summary": "x"},
    {"impact": "convention", "summary": "y" * (ENTRY_MAX_CHARS + 1)},
])
def test_writer_rejects_bad_input(repo: Path, kw: dict) -> None:
    with pytest.raises(DocBulletError):
        write_doc_bullet(repo, "conventions", "iterate-2026-11-06-a", **kw)
    assert not list(doc_bullets.bullets_dir(repo).glob("*")) if doc_bullets.bullets_dir(repo).exists() else True


def test_learnings_target_takes_free_date_first_line(repo: Path) -> None:
    p = write_doc_bullet(repo, "learnings", "iterate-2026-11-06-a", text="- (2026-11-06) build — gotcha. → x")
    assert p.name.startswith("learnings--")


def test_cli_prints_relative_path(repo: Path, capsys: pytest.CaptureFixture) -> None:
    rc = write_main(["--project-root", str(repo), "--target", "architecture", "--run-id", "iterate-2026-11-06-c",
                     "--impact", "component", "--summary", "s"])
    assert rc == 0
    assert capsys.readouterr().out.strip().startswith(".shipwright/agent_docs/decision-drops/bullets/architecture--")
    assert write_main(["--project-root", str(repo), "--target", "architecture", "--run-id", "r", "--impact", "convention",
                       "--summary", "s"]) == 1


def test_bad_names_are_skipped_not_raised(repo: Path) -> None:
    bd = doc_bullets.bullets_dir(repo)
    bd.mkdir(parents=True)
    (bd / "junk.md").write_text("- x\n", encoding="utf-8")
    (bd / ".gitkeep").write_text("", encoding="utf-8")
    (bd / "conventions--k--aaaaaaaa--bbbbbbbb.md").write_text("no bullet\n", encoding="utf-8")
    bullets, skipped = doc_bullets.pending(repo)
    assert bullets == [] and sorted(skipped) == ["conventions--k--aaaaaaaa--bbbbbbbb.md", "junk.md"]


def test_render_identical_pending_vs_folded(repo: Path) -> None:
    for i, run in enumerate(("iterate-2026-11-05-z", "iterate-2026-11-06-a", "iterate-2026-11-06-b")):
        _bullet(repo, run, "conventions", f"rule {i}")
    _bullet(repo, "iterate-2026-11-06-a", "architecture", "arch")
    write_doc_bullet(repo, "learnings", "iterate-2026-11-06-a", text="- (2026-11-06) build — gotcha. → x")
    docs = repo / ".shipwright" / "agent_docs"
    pend = {n: doc_bullets.effective_text(docs, n) for n in ("architecture.md", "conventions.md")}
    assert pend["conventions.md"] != CONV
    res = doc_bullets.fold(repo)
    assert res["folded"] == 5 and not res["errors"]
    for n, text in pend.items():
        assert (docs / n).read_bytes().decode() == text  # byte-identical
    assert not list(doc_bullets.bullets_dir(repo).glob("*.md"))
    assert doc_bullets.fold(repo)["folded"] == 0  # idempotent
    arch = (docs / "architecture.md").read_text(encoding="utf-8")
    assert arch.index("iterate-2026-11-06-a") > arch.index("old") and arch.index("## Other") > arch.index("iterate-2026-11-06-a")
    conv = (docs / "conventions.md").read_text(encoding="utf-8")
    assert conv.index("rule 0") < conv.index("rule 1") < conv.index("rule 2") < conv.index("## Learnings") < conv.index("gotcha")


def test_fold_creates_a_missing_section_and_dedups_identical_text(repo: Path) -> None:
    docs = repo / ".shipwright" / "agent_docs"
    (docs / "architecture.md").write_text("# A" + chr(10), encoding="utf-8")  # no section at all
    p = _bullet(repo, "iterate-2026-11-06-a", "architecture")
    twin = p.with_name(p.name[:-11] + "ffffffff.md")
    twin.write_bytes(p.read_bytes())  # same text, other file (e.g. a retried writer)
    res = doc_bullets.fold(repo)
    text = (docs / "architecture.md").read_text(encoding="utf-8")
    assert text.startswith("# A" + chr(10) * 2 + "## Architecture Updates" + chr(10) * 2 + "- **iterate-2026-11-06-a**")
    assert text.count("- **iterate-2026-11-06-a**") == 1 and res["conflicts"] == []
    assert not list(doc_bullets.bullets_dir(repo).glob("*.md"))


def test_same_anchor_different_text_is_kept_not_deleted(repo: Path) -> None:
    docs = repo / ".shipwright" / "agent_docs"
    p = _bullet(repo, "iterate-2026-11-06-a", "architecture", "first")
    with pytest.raises(DocBulletError):  # the writer refuses a second, different bullet for the same anchor
        _bullet(repo, "iterate-2026-11-06-a", "architecture", "second")
    other = p.with_name(p.name[:-11] + "ffffffff.md")
    other.write_bytes(p.read_bytes().replace(b"first", b"second"))  # but a hand-added/merged one can exist
    res = doc_bullets.fold(repo)
    assert res["folded"] == 1 and res["conflicts"] == [other.name] and other.exists() and not res["errors"]
    assert "second" not in (docs / "architecture.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("sep", [chr(13), chr(11), chr(0x85), chr(0x2028)])
def test_a_bullet_is_exactly_one_line(repo: Path, sep: str) -> None:
    with pytest.raises(DocBulletError):
        write_doc_bullet(repo, "learnings", "iterate-2026-11-06-a", text="- (2026-11-06) p " + sep + "## Heading")
    bd = doc_bullets.bullets_dir(repo)
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "learnings--k--aaaaaaaa--bbbbbbbb.md").write_bytes(("- ok" + chr(10) + chr(10) + "## Heading" + chr(10) + "prose").encode())
    assert doc_bullets.pending(repo)[0] == []


def test_text_must_be_anchored_on_the_run(repo: Path) -> None:
    other = "- **iterate-2026-11-06-zz** (2026-11-06): Convention — x. → decision_log (y)"
    with pytest.raises(DocBulletError):
        write_doc_bullet(repo, "conventions", "iterate-2026-11-06-a", text=other)


def test_crlf_doc_keeps_its_line_endings(repo: Path) -> None:
    docs = repo / ".shipwright" / "agent_docs"
    (docs / "conventions.md").write_bytes(CONV.replace("\n", "\r\n").encode())
    _bullet(repo, "iterate-2026-11-06-a")
    doc_bullets.fold(repo)
    raw = (docs / "conventions.md").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")


def test_missing_doc_and_no_bullets_are_inert(tmp_path: Path) -> None:
    docs = tmp_path / ".shipwright" / "agent_docs"
    assert doc_bullets.effective_text(docs, "conventions.md") == ""
    assert doc_bullets.render_pending_summary(tmp_path) == ""
    assert doc_bullets.fold(tmp_path)["folded"] == 0


def test_context_cap_20_newest_then_n_more_then_warning(repo: Path) -> None:
    for i in range(45):
        write_doc_bullet(repo, "learnings", f"iterate-2026-11-06-r{i:02d}", text=f"- (2026-11-{1 + i // 2:02d}) p — rule {i}. → x")
    out = doc_bullets.render_pending_summary(repo).splitlines()
    assert sum(1 for ln in out if ln.startswith("- [")) == 20
    assert "rule 44" in out[0] and "25 more pending" in out[20]
    assert out[21].startswith("WARNING: 45 pending bullets (> 40)")
    few = doc_bullets.render_pending_summary(repo, limit=100, warn_above=100)
    assert "more pending" not in few and "WARNING" not in few


@pytest.mark.parametrize(
    "summary", ["see planning/iterate/ for it", "reads shared/profiles/python.json", "uses agent_docs/ files"],  # artifact-path-canon: legacy
)
def test_writer_rejects_text_that_repo_wide_prose_guards_would_flag(repo: Path, summary: str) -> None:
    with pytest.raises(DocBulletError):
        _bullet(repo, "iterate-2026-11-06-a", summary=summary)
    assert _bullet(repo, "iterate-2026-11-06-a", summary="see .shipwright/planning/iterate/ and shared/profiles/deploy-x").exists()
