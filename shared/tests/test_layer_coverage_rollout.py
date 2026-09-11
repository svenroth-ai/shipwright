"""Real-git tests for the trg-aedcfe7b transition rule's rollout resolution
(:mod:`_layer_coverage_rollout`): ``resolve_rollout_commit`` and
``rollout_manifest`` against actual git history, since the module's whole
purpose is asking a repo's OWN git ancestry a wall-clock question — a purely
synthetic manifest test (as in ``test_layer_coverage_binding_transition.py``)
cannot exercise the git resolution itself.

Commit dates are pinned via ``GIT_AUTHOR_DATE``/``GIT_COMMITTER_DATE`` with an
explicit UTC offset (never a bare local-time string) so the test is immune to
the runner's timezone; ``commit.gpgsign=false`` is set per-repo so a
developer machine with commit signing enabled cannot hang or fail these
commits (opus internal plan review, low-severity finding).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_regen import _load_collector  # noqa: E402
from tools.verifiers._layer_coverage_rollout import (  # noqa: E402
    GATE_ROLLOUT_AT_EPOCH,
    clear_rollout_cache,
    resolve_rollout_commit,
    rollout_manifest,
)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit_at(root: Path, msg: str, iso_date: str) -> str:
    """Commit with an explicit, offset-qualified author/committer date — never
    the ambient clock — so the test's pass/fail cannot depend on when it runs."""
    _git(root, "add", "-A")
    proc = subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", msg],
        capture_output=True, text=True,
        env={
            **__import__("os").environ,
            "GIT_AUTHOR_DATE": iso_date,
            "GIT_COMMITTER_DATE": iso_date,
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git commit failed: {proc.stderr}")
    return _git(root, "rev-parse", "HEAD")


_BEFORE_ROLLOUT = "2026-09-06T00:00:00+00:00"
_AT_ROLLOUT = "2026-09-07T16:09:19+00:00"  # == GATE_ROLLOUT_AT_EPOCH, to the second
_AFTER_ROLLOUT = "2026-09-08T00:00:00+00:00"

_SPEC_PRE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-09.30 | Pre-rollout requirement | Should | unit |\n"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_rollout_cache()
    yield
    clear_rollout_cache()


def test_resolve_rollout_commit_finds_a_commit_strictly_before_cutoff(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    pre_sha = _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    resolved = resolve_rollout_commit(root, head_sha)
    assert resolved == pre_sha


def test_resolve_rollout_commit_accepts_a_commit_exactly_at_the_boundary_instant(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    boundary_sha = _commit_at(root, "at boundary", _AT_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    resolved = resolve_rollout_commit(root, head_sha)
    assert resolved == boundary_sha


def test_resolve_rollout_commit_none_when_repo_born_entirely_after_rollout(tmp_path):
    # The greenfield case: every commit postdates the cutoff -> no snapshot, no grace.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    head_sha = _commit_at(root, "born after rollout", _AFTER_ROLLOUT)

    assert resolve_rollout_commit(root, head_sha) is None


def test_resolve_rollout_commit_none_for_a_shallow_clone(tmp_path):
    origin = tmp_path / "origin"
    _init(origin)
    _write(origin, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    _commit_at(origin, "pre-rollout", _BEFORE_ROLLOUT)
    _write(origin, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    _commit_at(origin, "post-rollout", _AFTER_ROLLOUT)

    # `--depth` is a no-op for a same-machine PATH clone (git takes the local-clone
    # fast path and copies full history regardless) — only a `file://` URL forces
    # git through the real network-clone code path that actually honours `--depth`
    # (external code review, P3.3 follow-up, openai, medium). Asserted below rather
    # than assumed, so a future git/platform behaviour change fails loudly here
    # instead of silently turning this into a no-op full-clone test.
    shallow = tmp_path / "shallow"
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", origin.as_uri(), str(shallow)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    is_shallow = _git(shallow, "rev-parse", "--is-shallow-repository")
    assert is_shallow == "true", "clone did not actually produce a shallow repository"
    head_sha = _git(shallow, "rev-parse", "HEAD")

    assert resolve_rollout_commit(shallow, head_sha) is None


def test_resolve_rollout_commit_none_for_empty_commit_hash(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)

    assert resolve_rollout_commit(root, "") is None


def test_rollout_manifest_builds_a_snapshot_from_the_resolved_pre_rollout_commit(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    manifest = rollout_manifest(root, head_sha)
    assert manifest is not None
    # v3 manifest keys derive from the FR id alone (``<group digits>::<id>``), not from
    # the spec's directory — look the node up by its ``id`` rather than assuming the
    # exact key shape, so this test does not silently pin an internal collector detail.
    node = next(
        (n for n in manifest["requirements"].values() if n.get("id") == "FR-09.30"), None,
    )
    assert node is not None
    # The PRE-rollout value (unit only) — not head's widened (unit, e2e) — since the
    # snapshot is built from the resolved pre-rollout commit, not from head.
    assert node["required_layers"] == ["unit"]


def test_rollout_build_is_evidence_independent_for_required_layers(tmp_path):
    # External code review (P3.3 follow-up, glm, medium): rollout_manifest passes
    # `evidence={}` to `_build`, claimed equivalent to `with_evidence=False` (never
    # affecting required_layers/required_layers_source, only coverage). Pin that
    # directly: build the SAME tree with empty vs. non-empty evidence and assert the
    # two required_layers/source fields are byte-identical while coverage differs.
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "app").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "app" / "spec.md").write_text(
        "# Spec\n\n## Functional Requirements\n\n"
        "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
        "| FR-09.31 | Evidence-independence check | Should | unit |\n",
        encoding="utf-8",
    )
    test_id = "tests/test_evidence_independence.py::test_x"
    (root / "tests" / "test_evidence_independence.py").write_text(
        'import pytest\n\n\n@pytest.mark.covers("FR-09.31")\ndef test_x():\n    assert True\n',
        encoding="utf-8",
    )

    test_links, io, _evio = _load_collector()
    no_evidence = test_links.build_manifest(
        root, spec_files=io.discover_specs(root), test_roots=[root / "tests"], evidence={},
    )
    with_evidence = test_links.build_manifest(
        root, spec_files=io.discover_specs(root), test_roots=[root / "tests"],
        evidence={test_id: {"status": "enabled", "executed": "pass"}},
    )

    node_no_ev = next(n for n in no_evidence["requirements"].values() if n.get("id") == "FR-09.31")
    node_with_ev = next(n for n in with_evidence["requirements"].values() if n.get("id") == "FR-09.31")

    assert node_no_ev["required_layers"] == node_with_ev["required_layers"]
    assert node_no_ev["required_layers_source"] == node_with_ev["required_layers_source"]
    # Coverage DOES differ — proving the evidence dict was actually consulted for
    # coverage, so the required_layers/source equality above is a real pin, not a
    # fixture that never exercised the evidence path at all.
    assert node_no_ev["coverage"] != node_with_ev["coverage"]
    assert node_with_ev["coverage"].get("unit") == "ok"


def test_rollout_manifest_none_when_no_rollout_commit_resolves(tmp_path):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    head_sha = _commit_at(root, "born after rollout", _AFTER_ROLLOUT)

    assert rollout_manifest(root, head_sha) is None


def test_rollout_manifest_caches_by_root_and_commit(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE)
    _commit_at(root, "pre-rollout", _BEFORE_ROLLOUT)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PRE.replace("unit", "unit, e2e"))
    head_sha = _commit_at(root, "post-rollout", _AFTER_ROLLOUT)

    first = rollout_manifest(root, head_sha)
    assert first is not None

    import tools.verifiers._layer_coverage_rollout as _rollout_mod
    def _boom(*_a, **_kw):
        raise AssertionError("resolve_rollout_commit should not run again on a cache hit")
    monkeypatch.setattr(_rollout_mod, "resolve_rollout_commit", _boom)

    second = rollout_manifest(root, head_sha)
    assert second is first
