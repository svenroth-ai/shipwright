"""Unit tests for adr_seeding (split out of test_artifact_writer for the
same bloat-ceiling reason lib/adr_seeding.py was split out of
lib/artifact_writer.py)."""

import json
import re
import subprocess
from pathlib import Path

import pytest

import lib.adr_seeding as adr_seeding
from lib.artifact_writer import (
    ADR_SPEC_FOLDER,
    _derive_commit_subject,
    _render_decision_log,
    _resolve_retroactive_adrs,
    write_agent_docs,
)
from tools.generate_adoption_artifacts import generate


def test_render_decision_log_imported_section_names_the_adr_folder() -> None:
    """trg-50efc4c8: the pointer sentence must name the canonical ADR-spec
    folder, not merely say "above this section" — a reader has no way to
    know `.shipwright/planning/adr/` is where decisions actually accrue
    otherwise."""
    body = _render_decision_log(
        project_name="Demo", profile="x", scope="full_app",
        commit_sha="abc1234", features_count=0,
        retroactive_adrs=[], start_adr_number=1,
        harvested_decisions=("Some harvested content", "docs/adr"),
    )
    assert f"{ADR_SPEC_FOLDER}/" in body
    assert f"{ADR_SPEC_FOLDER}/INDEX.md" in body


def test_write_agent_docs_seeds_adr_spec_folder(tmp_path: Path) -> None:
    """trg-50efc4c8: adopt must seed the canonical ADR-spec folder with its
    own minted ADRs so INDEX.md has something to index from day one."""
    paths = write_agent_docs(
        tmp_path,
        project_name="Demo", profile="supabase-nextjs", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=1, commits_total=5, contributors_total=1,
        nested_excluded=[], commit_sha="abc1234",
        retroactive_adrs=[],
    )
    adr_dir = tmp_path / ".shipwright" / "planning" / "adr"
    seed = adr_dir / "001-adopt-this-repository-into-the-shipwright-sdlc.md"
    assert seed in paths
    content = seed.read_text(encoding="utf-8")
    assert content.startswith("# ADR-001 — Adopt this repository into the Shipwright SDLC")
    assert "abc1234" in content
    index = (adr_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "ADR-001" in index


def test_write_agent_docs_seeds_retroactive_adr_specs_too(tmp_path: Path) -> None:
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=1, contributors_total=1,
        nested_excluded=[], commit_sha=None,
        retroactive_adrs=[
            {"sha": "abc1234", "subject": "Switch to vite",
             "context": "ctx", "decision": "dec", "consequences": "csq"},
        ],
    )
    adr_dir = tmp_path / ".shipwright" / "planning" / "adr"
    seed = adr_dir / "002-switch-to-vite.md"
    assert seed.is_file()
    assert "# ADR-002 — Switch to vite" in seed.read_text(encoding="utf-8")


def test_derive_commit_subject_reads_a_real_commit(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "switch to vite"], cwd=tmp_path, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert _derive_commit_subject(tmp_path, sha) == "switch to vite"


def test_derive_commit_subject_unresolvable_sha_returns_empty(tmp_path: Path) -> None:
    """No repo at all — a well-formed but unresolvable sha must not raise,
    only return "" so the caller fails closed instead of crashing."""
    assert _derive_commit_subject(tmp_path, "0000000") == ""


def test_derive_commit_subject_rejects_malformed_sha(tmp_path: Path) -> None:
    assert _derive_commit_subject(tmp_path, "not a sha!") == ""


def test_resolve_retroactive_adrs_derives_subject_from_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trg-6b59524b: prefer deriving over failing where the data exists."""
    monkeypatch.setattr(
        adr_seeding, "_derive_commit_subject",
        lambda root, sha: "Derived subject" if sha == "abc1234" else "",
    )
    resolved = _resolve_retroactive_adrs(tmp_path, [
        {"sha": "abc1234", "context": "ctx", "decision": "dec"},
    ])
    assert resolved[0]["subject"] == "Derived subject"


def test_resolve_retroactive_adrs_fails_closed_without_subject_or_sha(tmp_path: Path) -> None:
    """trg-6b59524b: a hollow entry — no subject, nothing to derive it
    from — must not silently render as adoption success."""
    with pytest.raises(ValueError, match="missing subject"):
        _resolve_retroactive_adrs(tmp_path, [
            {"context": "ctx", "decision": "dec"},
        ])


def test_resolve_retroactive_adrs_fails_closed_on_missing_context(tmp_path: Path) -> None:
    """trg-6b59524b broadened beyond subject: context/decision fall back to
    a placeholder the same way and must fail closed too."""
    with pytest.raises(ValueError, match="missing context"):
        _resolve_retroactive_adrs(tmp_path, [
            {"subject": "Has a subject", "decision": "dec"},
        ])


def test_resolve_retroactive_adrs_derives_subject_from_commit_sha_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`commit_sha` (not `sha`) is the documented Layer-2 enrichment key
    (step-b8-semantic-enrichment.md) — the whole enrichment.json shape Step
    E actually produces has no `sha` key at all. Code review caught that
    the original fix read only `sha`, so derivation never fired on real
    data and every documented-shape enrichment.json hard-aborted Step E."""
    monkeypatch.setattr(
        adr_seeding, "_derive_commit_subject",
        lambda root, sha: "Derived subject" if sha == "def5678" else "",
    )
    resolved = _resolve_retroactive_adrs(tmp_path, [
        {"commit_sha": "def5678", "context": "ctx", "decision": "dec"},
    ])
    assert resolved[0]["subject"] == "Derived subject"
    assert resolved[0]["sha"] == "def5678"


def test_write_agent_docs_fails_closed_before_writing_anything(tmp_path: Path) -> None:
    """Code review: the original fail-closed call sat AFTER architecture.md
    and conventions.md were already backed up and overwritten, so a hollow
    retroactive ADR left the target repo half-migrated. The check must run
    before the first write."""
    with pytest.raises(ValueError, match="missing subject"):
        write_agent_docs(
            tmp_path,
            project_name="Demo", profile="vite-hono", scope="full_app",
            stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
            layers=[], loc_by_layer={},
            architecture_diagram="```\n```", data_flow_description="",
            conventions={}, conventions_prose="",
            features_count=0, commits_total=1, contributors_total=1,
            nested_excluded=[], commit_sha=None,
            retroactive_adrs=[{"context": "ctx", "decision": "dec"}],
        )
    assert not (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").exists()
    assert not (tmp_path / ".shipwright" / "agent_docs" / "conventions.md").exists()


def test_write_agent_docs_no_sha_renders_the_same_unknown_fallback_everywhere(
    tmp_path: Path,
) -> None:
    """A subject-only retroactive ADR (no sha) is legal. decision_log.md and
    the seeded .shipwright/planning/adr/ spec file must agree on the commit
    fallback — code review caught them rendering empty backticks vs.
    `unknown`, which made the density check flag its own output as hollow."""
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=1, contributors_total=1,
        nested_excluded=[], commit_sha=None,
        retroactive_adrs=[
            {"subject": "No commit known", "context": "ctx", "decision": "dec"},
        ],
    )
    dec = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    seed = (tmp_path / ".shipwright" / "planning" / "adr" / "002-no-commit-known.md").read_text(
        encoding="utf-8"
    )
    assert "**Commit**: `unknown`" in dec
    assert "**Commit**: `unknown`" in seed


def test_adr_spec_folder_agrees_with_shared_adr_index() -> None:
    """Doubt-reviewer (round 4): adopt duplicates ADR_SPEC_FOLDER rather than
    importing shared/scripts/lib/adr_index.py (ADR-045 — adopt's `lib`
    package would collide). Nothing pinned the two copies together, so the
    canonical folder could move in shared and adopt would keep seeding into
    the abandoned path with no test anywhere failing. Regex over the shared
    file's source (no import, so no `lib` collision) instead of an import."""
    shared_root = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib" / "adr_index.py"
    source = shared_root.read_text(encoding="utf-8")
    match = re.search(r'^ADR_SPEC_FOLDER = "([^"]+)"', source, re.MULTILINE)
    assert match is not None, f"could not find ADR_SPEC_FOLDER in {shared_root}"
    assert match.group(1) == adr_seeding.ADR_SPEC_FOLDER


def test_resolve_retroactive_adrs_normalizes_consequences_fallback(tmp_path: Path) -> None:
    """Round-4 code review: decision_log.md defaulted a MISSING consequences
    key to em-dash while the seed file defaulted an EMPTY-STRING value the
    same way — a schema-valid ``""`` rendered differently in each."""
    resolved = _resolve_retroactive_adrs(tmp_path, [
        {"subject": "s", "context": "ctx", "decision": "dec", "consequences": ""},
    ])
    assert resolved[0]["consequences"] == "—"


def test_next_adr_start_number_avoids_seed_folder_collision(tmp_path: Path) -> None:
    """A Step E re-run must not reissue a number the ADR-spec folder already
    has, even when decision_log.md doesn't know about it yet (code review:
    numbering was decision_log-only)."""
    adr_dir = tmp_path / ".shipwright" / "planning" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "005-something-already-seeded.md").write_text("# ADR-005 — x\n", encoding="utf-8")
    write_agent_docs(
        tmp_path,
        project_name="Demo", profile="vite-hono", scope="full_app",
        stack={"runtime": {}, "frontend": {}, "backend": {}, "database": {}, "auth": {}},
        layers=[], loc_by_layer={},
        architecture_diagram="```\n```", data_flow_description="",
        conventions={}, conventions_prose="",
        features_count=0, commits_total=1, contributors_total=1,
        nested_excluded=[], commit_sha=None,
        retroactive_adrs=[],
    )
    assert (adr_dir / "006-adopt-this-repository-into-the-shipwright-sdlc.md").is_file()


def test_generate_fails_closed_before_writing_claude_md(tmp_path: Path) -> None:
    """Code review (round 3): the fail-closed check was insufficient inside
    write_agent_docs alone — generate() calls write_claude_md BEFORE it. A
    hollow retroactive ADR (schema-valid, no subject, unresolvable
    commit_sha) must abort generate() before ANY artifact is written."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "init"], cwd=tmp_path, check=True,
    )

    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    snapshot_path = snap_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps({
        "stack": {"primary_language": "typescript"},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [],
        "git": {"commits_total": 1, "contributors_total": 1, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": None},
        "excludes": [],
    }), encoding="utf-8")
    enrichment_path = snap_dir / "enrichment.json"
    enrichment_path.write_text(json.dumps({
        "product_description": "x", "features": [],
        "architecture_prose": "x", "architecture_diagram": "```\n```",
        "conventions_prose": "x",
        "adrs": [
            {"commit_sha": "0000000", "context": "ctx",
             "decision": "dec", "consequences": "csq"},
        ],
    }), encoding="utf-8")
    routes_path = snap_dir / "routes.json"

    with pytest.raises(ValueError, match="missing subject"):
        generate(
            tmp_path,
            snapshot_path=snapshot_path, enrichment_path=enrichment_path,
            routes_path=routes_path,
            split_name="01-adopted", plugin_version="0.2.0",
            scope_override=None, profile_override=None,
            write_sync=False, backfill_events=False,
        )
    assert not (tmp_path / "CLAUDE.md").exists()
