"""Regression: phase_from_plugin_root must resolve a VERSIONED CLAUDE_PLUGIN_ROOT.

Claude Code's installed_plugins.json uses installPath=.../<plugin>/<version>
(e.g. .../shipwright-iterate/0.4.1), so the basename is the *version*. Before
iterate-2026-05-30 the resolver only matched the basename and returned None,
silently no-opping EVERY phase-keyed Stop hook (phase_quality,
audit_compliance_on_stop, the capture_session_id injection guard) under a
versioned install. Verified empirically that the cached
audit_phase_quality_on_stop.py wrote no finding under the real versioned root.

Lives in its own file (not test_audit_phase_quality.py) to respect that file's
bloat baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402

_BASE = "C:/Users/x/.claude/plugins/cache/shipwright"


def test_versioned_install_resolves_to_phase():
    assert pq.phase_from_plugin_root(f"{_BASE}/shipwright-iterate/0.4.1") == "iterate"
    assert pq.phase_from_plugin_root(f"{_BASE}/shipwright-changelog/0.2.1") == "changelog"
    assert pq.phase_from_plugin_root(f"{_BASE}/shipwright-compliance/0.2.2") == "compliance"


def test_unversioned_mirror_still_resolves_directly():
    assert pq.phase_from_plugin_root(f"{_BASE}/plugins/shipwright-iterate") == "iterate"


def test_version_dir_under_unknown_plugin_does_not_spoof():
    assert pq.phase_from_plugin_root(f"{_BASE}/not-a-plugin/1.0.0") is None
    assert pq.phase_from_plugin_root("/x/y/shipwright-iterate/0.4.1/extra/deep") is None
