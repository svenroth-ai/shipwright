"""Group G tests (plan v7 Option Z, Step 8) — Sub-Iterate C.

Group G — Agent-docs freshness vs. git activity:

- G2 (detective, MEDIUM): conventional-commit ``type(scope):`` subjects
  must have a scope that resolves against ``g2_alias_map``,
  ``g2_stoplist``, or a known ``shipwright_project_config.json.splits[]``
  entry. Subjects without a conventional prefix are silently skipped.

- G3 (detective, MEDIUM): ADR-N references inside commit BODIES must
  exist in ``.shipwright/agent_docs/decision_log.md``. Subject lines are
  not scanned (Shipwright convention puts ADR refs in the multi-line
  body, never in the conventional-commit subject).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_g  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email",
                    "test@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name",
                    "Test User"], check=True, capture_output=True)


def _git_commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for path, content in files.items():
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg], check=True,
                   capture_output=True)
    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return sha


def _git_tag(repo: Path, tag: str) -> None:
    subprocess.run(["git", "-C", str(repo), "tag", tag], check=True,
                   capture_output=True)


def _default_config() -> dict:
    return {
        "g2_stoplist": ["chore", "ci", "docs"],
        "g2_alias_map": {
            "auth": ["auth", "authn"],
            "billing": ["billing", "payments"],
        },
        "b7_exclusions": {"last_release_tag_pattern": "v*"},
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _decision_log(path: Path, ids: list[str]) -> None:
    body = "# Decision Log\n\n"
    for adr in ids:
        body += f"### {adr}: stub\n\n**Status:** accepted\n\n"
    _write(path, body)


# ---------------------------------------------------------------------------
# G2 — Conventional-commit scope match
# ---------------------------------------------------------------------------


def test_g2_passes_when_every_scope_resolves(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"}, "feat(auth): wire login")
    _git_commit(tmp_path, {"b.txt": "v1"}, "chore: bump deps")

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "pass", g2.detail
    assert g2.source == SOURCE_DETECTIVE_ONLY


def test_g2_resolves_alias_variants(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"}, "fix(authn): bug")
    _git_commit(tmp_path, {"b.txt": "v1"}, "feat(payments): pricing")

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "pass", g2.detail


def test_g2_resolves_split_name_from_project_config(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"}, "feat(02-dashboard): nav")

    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-dashboard", "status": "in_progress"},
        ],
    }))

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "pass", g2.detail


def test_g2_flags_unmatched_scope(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha = _git_commit(tmp_path, {"a.txt": "v2"}, "feat(unknown-thing): x")

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "fail"
    assert g2.severity == "MEDIUM"
    assert sha[:8] in g2.detail
    assert "unknown-thing" in g2.detail


def test_g2_skips_when_no_release_tag(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "skip"


def test_g2_skips_when_no_conventional_subjects(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"}, "ad-hoc one-liner without scope")

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "skip"
    assert "no conventional-commit" in g2.detail


def test_g2_skips_when_not_a_git_repo(tmp_path):
    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "skip"


# ---------------------------------------------------------------------------
# G3 — ADR-ID refs in commit bodies
# ---------------------------------------------------------------------------


def test_g3_passes_when_every_body_ref_is_declared(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _decision_log(tmp_path / ".shipwright" / "agent_docs" / "decision_log.md",
                  ["ADR-001", "ADR-002"])
    _git_commit(tmp_path, {"a.txt": "v2"},
                "feat(auth): wire login\n\nImplements ADR-002.\n")

    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "pass", g3.detail
    assert g3.source == SOURCE_DETECTIVE_ONLY


def test_g3_flags_dangling_adr_ref(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _decision_log(tmp_path / ".shipwright" / "agent_docs" / "decision_log.md",
                  ["ADR-001"])
    sha = _git_commit(
        tmp_path, {"a.txt": "v2"},
        "fix(auth): bug\n\nSupersedes ADR-099.\n",
    )

    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "fail"
    assert g3.severity == "MEDIUM"
    assert sha[:8] in g3.detail
    assert "ADR-099" in g3.detail


def test_g3_does_not_scan_subject_line(tmp_path):
    """ADR refs in commit subjects should NOT be checked — the convention
    puts them in the body. A subject-line reference must not produce a
    finding even when the ADR is undeclared."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _decision_log(tmp_path / ".shipwright" / "agent_docs" / "decision_log.md",
                  ["ADR-001"])
    _git_commit(
        tmp_path, {"a.txt": "v2"},
        # ADR-077 only appears in the subject — empty body.
        "feat(auth): apply ADR-077",
    )

    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    # No body ref → skip (no examined refs), not fail.
    assert g3.status == "skip"


def test_g3_skips_when_no_decision_log(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"},
                "feat(auth): x\n\nADR-001 implementation.\n")

    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "skip"
    assert "decision_log" in g3.detail


def test_g3_skips_when_no_release_tag(tmp_path):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _decision_log(tmp_path / ".shipwright" / "agent_docs" / "decision_log.md",
                  ["ADR-001"])
    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "skip"


def test_g3_skips_when_not_a_git_repo(tmp_path):
    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "skip"


# ---------------------------------------------------------------------------
# Source tagging — every G finding is detective-only
# ---------------------------------------------------------------------------


def test_g_findings_are_detective_only(tmp_path):
    findings = group_g.run(tmp_path, _default_config(), None)
    assert findings  # both G2 + G3 emitted
    for f in findings:
        assert f.source == SOURCE_DETECTIVE_ONLY
        assert f.group == "G"


# ---------------------------------------------------------------------------
# Default-config integration — Step 13 tuning lands in _DEFAULT_CONFIG
# ---------------------------------------------------------------------------


def test_g2_default_config_stoplist_includes_changelog(tmp_path):
    """Step 13 tuning added ``changelog`` to the built-in stoplist after
    a shipwright-monorepo smoke-run flagged ``docs(changelog): ...``
    commits as G2 false-positives.

    Pinning this against ``audit_detector._DEFAULT_CONFIG`` (not the
    ad-hoc ``_default_config()`` fixture) prevents a regression in the
    default tuning from going silently green.
    """
    from scripts.audit import audit_detector

    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"},
                "docs(changelog): backfill release notes")

    # Use the live default config (no project override), not the fixture.
    cfg = audit_detector.load_audit_config(tmp_path)
    findings = group_g.run(tmp_path, cfg, None)
    g2 = next(f for f in findings if f.check_id == "G2")
    assert g2.status == "pass", g2.detail


def test_g2_resolves_uppercase_type_subjects(tmp_path):
    """``Feat(auth): ...`` and ``FIX(auth): ...`` must be parsed the same
    as their lowercase counterparts. Real-world repos vary on type
    casing; G2 silently ignoring them would let unmatched scopes slip
    past the audit (external-review finding 1)."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    _git_commit(tmp_path, {"a.txt": "v2"}, "Feat(auth): wire login")
    sha = _git_commit(tmp_path, {"a.txt": "v3"},
                      "FIX(unknown-x): bad scope")

    findings = group_g.run(tmp_path, _default_config(), None)
    g2 = next(f for f in findings if f.check_id == "G2")
    # The uppercase ``Feat(auth)`` resolves via the alias map; the
    # uppercase ``FIX(unknown-x)`` is parsed but the scope is unknown,
    # so G2 fails on it. Without case-insensitive parsing both subjects
    # would be ignored and G2 would skip rather than fail.
    assert g2.status == "fail"
    assert sha[:8] in g2.detail
    assert "unknown-x" in g2.detail


def test_g3_matches_short_and_long_adr_ids(tmp_path):
    """``ADR-7`` and ``ADR-1234`` must both be recognized — narrow
    digit-count regex would silently miss them (external-review
    finding 2)."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    # decision_log declares ADR-007 (3 digits) and ADR-1234 (4 digits).
    _decision_log(tmp_path / ".shipwright" / "agent_docs" / "decision_log.md",
                  ["ADR-007", "ADR-1234"])
    # Short ref ADR-7 is dangling — declared id is ADR-007. The format
    # mismatch IS the dangling-ref signal we want G3 to surface.
    sha = _git_commit(
        tmp_path, {"a.txt": "v2"},
        "feat(auth): note\n\nReplaces ADR-7. Builds on ADR-1234.\n",
    )

    findings = group_g.run(tmp_path, _default_config(), None)
    g3 = next(f for f in findings if f.check_id == "G3")
    assert g3.status == "fail"
    assert sha[:8] in g3.detail
    assert "ADR-7" in g3.detail  # short form was actually recognized
    # ADR-1234 (long form) IS in the declared set — should NOT be flagged.
    assert "ADR-1234" not in g3.detail
