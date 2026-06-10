"""The generated agent-doc trio (ADR-089 single-producer caches) is exempt from
the artifact-path-canon lint in EVERY migration (trg-6ed063ae).

These caches render arbitrary text — triage finding detail/launchPayload, iterate
and build context — that may legitimately quote any bare legacy path, and they are
regenerated each iterate, so a legacy reference cannot be "fixed" in place. Same
exempt class as change-history.md / shipwright_test_results.json prose. This test
locks the exemption so a future allowlist edit can't silently drop one and reopen
the recurring CI false-fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

from artifact_migrations import ALLOWLIST  # noqa: E402

_GENERATED_AGENT_DOC_CACHES = (
    ".shipwright/agent_docs/triage_inbox.md",
    ".shipwright/agent_docs/session_handoff.md",
    ".shipwright/agent_docs/build_dashboard.md",
)


def test_generated_agent_doc_caches_exempt_in_every_migration() -> None:
    for migration, allow in ALLOWLIST.items():
        for cache in _GENERATED_AGENT_DOC_CACHES:
            assert cache in allow, (
                f"{cache!r} (a regenerated agent-doc cache) is not exempt in the "
                f"{migration!r} migration — a finding/handoff quoting a bare legacy "
                "path would false-fail the artifact-path-canon lint (trg-6ed063ae)."
            )
