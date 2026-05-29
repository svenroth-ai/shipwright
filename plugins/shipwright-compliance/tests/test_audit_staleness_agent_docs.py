"""Audit_staleness DOC_REGISTRY now covers the agent-doc trio.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
extended the single-producer snapshot pattern from the 5 compliance MDs to
the 3 agent-doc MDs (session_handoff, build_dashboard, triage_inbox).

Drift protection:
1. ``DOC_REGISTRY`` contains both sets.
2. ``find_snapshot_commit`` accepts commits modifying either dir.
3. ``compare_doc`` returns ``stale=False, error="not-in-snapshot"`` when a
   doc was added after the snapshot commit (the agent-doc trio scenario
   on pre-2026-05-27 history). External review OpenAI #8.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the audit dir to sys.path for direct module import (mirrors the
# pattern in test_audit_staleness.py).
_AUDIT_DIR = (
    Path(__file__).resolve().parents[1] / "scripts" / "audit"
)
sys.path.insert(0, str(_AUDIT_DIR))

from audit_staleness import (  # noqa: E402
    AGENT_DOCS_DIR,
    COMPLIANCE_DIR,
    DOC_REGISTRY,
    SNAPSHOT_PATH_FILTERS,
    DocInfo,
    compare_doc,
)


def test_doc_registry_includes_compliance_set() -> None:
    keys = {d.key for d in DOC_REGISTRY}
    assert {"rtm", "test_evidence", "change_history", "sbom", "dashboard"} <= keys


def test_doc_registry_includes_agent_docs_trio() -> None:
    """The 3 agent-doc MDs joined the registry in iterate-2026-05-27."""
    keys = {d.key for d in DOC_REGISTRY}
    assert {"session_handoff", "build_dashboard", "triage_inbox"} <= keys


def test_agent_doc_paths_are_anchored_under_agent_docs_dir() -> None:
    """Path correctness — each agent-doc entry uses the AGENT_DOCS_DIR root."""
    by_key = {d.key: d for d in DOC_REGISTRY}
    for key in ("session_handoff", "build_dashboard", "triage_inbox"):
        info = by_key[key]
        assert info.rel_path.startswith(f"{AGENT_DOCS_DIR}/"), (
            f"{key} rel_path {info.rel_path!r} not under {AGENT_DOCS_DIR}"
        )


def test_snapshot_path_filters_widen_to_both_dirs() -> None:
    """``find_snapshot_commit`` queries both compliance/ and agent_docs/."""
    assert COMPLIANCE_DIR in SNAPSHOT_PATH_FILTERS
    assert AGENT_DOCS_DIR in SNAPSHOT_PATH_FILTERS


def test_compare_doc_handles_missing_on_both_sides(tmp_path: Path, monkeypatch) -> None:
    """A doc added to the registry after the snapshot commit is benign.

    Scenario: agent-doc trio added in iterate-2026-05-27. An earlier
    snapshot commit (compliance-only) won't have any agent-doc files.
    Pre-fix: ``compare_doc`` would emit ``stale=True, error="snapshot side
    missing"`` because the snapshot ``git show`` failed. Post-fix
    (external review OpenAI #8): when BOTH on-disk and snapshot side are
    missing, return ``stale=False, error="not-in-snapshot"``.
    """
    # Build a doc that doesn't exist on disk.
    doc = DocInfo("phantom", ".shipwright/compliance/phantom.md")

    # Patch git invocation to simulate "snapshot side missing".
    def fake_read_snapshot_text(project_root, snapshot_sha, rel_path):
        return None, "fatal: pathspec didn't match"

    import audit_staleness as mod

    monkeypatch.setattr(mod, "_read_snapshot_text", fake_read_snapshot_text)

    result = compare_doc(tmp_path, doc, "abc123")
    assert result.exists is False
    assert result.stale is False, (
        f"new doc absent from earlier snapshot should NOT be stale; "
        f"got stale=True with error={result.error!r}"
    )
    assert result.error == "not-in-snapshot"


def test_compare_doc_on_disk_exists_but_snapshot_missing(
    tmp_path: Path, monkeypatch
) -> None:
    """Post-merge state: on-disk has the file, pre-2026-05-27 snapshot doesn't.

    Realistic scenario after this iterate lands: agent-doc trio's tracked
    files are present on disk (finalize wrote them on the iterate branch),
    but the *previous* single-producer snapshot commit was pre-registry-
    extension and won't have those paths. The audit should NOT flag this
    as stale — there's no canonical version to diff against. The next
    finalize commit will become the new snapshot baseline and subsequent
    audits compare against it normally.

    Pre-fix (code-reviewer HIGH #1, 2026-05-27): this branch fell through
    to ``stale=True, error=snapshot_err``, generating 3 false-positive
    Group E entries until the next iterate finalize.
    """
    doc = DocInfo("new_doc", ".shipwright/agent_docs/new_doc.md")

    # On-disk exists with realistic content.
    on_disk = tmp_path / ".shipwright" / "agent_docs" / "new_doc.md"
    on_disk.parent.mkdir(parents=True, exist_ok=True)
    on_disk.write_text("# Tracked content\n", encoding="utf-8")

    # Snapshot side is missing (old commit didn't have this doc).
    def fake_read_snapshot_text(project_root, snapshot_sha, rel_path):
        return None, "fatal: pathspec didn't match"

    import audit_staleness as mod

    monkeypatch.setattr(mod, "_read_snapshot_text", fake_read_snapshot_text)

    result = compare_doc(tmp_path, doc, "abc123")
    assert result.exists is True, "on-disk side IS present"
    assert result.stale is False, (
        f"newly-registered doc absent from earlier snapshot must not be "
        f"flagged stale; got stale=True with error={result.error!r}"
    )
    assert result.error == "not-in-snapshot"
