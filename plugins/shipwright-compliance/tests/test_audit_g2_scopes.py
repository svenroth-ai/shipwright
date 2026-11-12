"""G2 judges each comma-joined scope part on its own; docs promise no auto-skip."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_g  # noqa: E402
from scripts.audit.g2_scopes import scope_parts, unknown_scope_parts  # noqa: E402
from tests.test_audit_group_g import (  # noqa: E402
    _default_config,
    _git_commit,
    _git_init,
    _git_tag,
)

REPO_ROOT = PLUGIN_ROOT.parent.parent

pytestmark = pytest.mark.covers("FR-01.10")


@pytest.mark.parametrize("scope,parts", [
    ("daemon,lib", ["daemon", "lib"]),
    (" daemon , lib ", ["daemon", "lib"]),
    ("a,,b,", ["a", "b"]),
    ("a, b,,", ["a", "b"]),
    ("auth", ["auth"]),
    (",", []),
])
def test_scope_parts(scope, parts):
    assert scope_parts(scope) == parts


def test_unknown_scope_parts_reports_only_the_unknown():
    known = {"auth", "ci"}
    assert unknown_scope_parts("auth,ci", known) == []
    assert unknown_scope_parts("auth,daemon,lib", known) == ["daemon", "lib"]
    assert unknown_scope_parts(",", known) == [","]


def test_whole_string_stoplist_entry_still_matches():
    assert unknown_scope_parts("daemon,lib", {"daemon,lib"}) == []
    assert unknown_scope_parts(" daemon,lib ", {"daemon,lib"}) == []
    assert unknown_scope_parts("daemon,lib,x", {"daemon,lib"}) == ["daemon", "lib", "x"]


def _g2(tmp_path, subject):
    _git_init(tmp_path)
    _git_commit(tmp_path, {"a.txt": "v1"}, "initial")
    _git_tag(tmp_path, "v0.1.0")
    sha = _git_commit(tmp_path, {"a.txt": "v2"}, subject)
    g2 = next(f for f in group_g.run(tmp_path, _default_config(), None)
              if f.check_id == "G2")
    return sha, g2


def test_known_plus_known_passes(tmp_path):
    _, g2 = _g2(tmp_path, "feat(auth,ci): both known")
    assert g2.status == "pass", g2.detail


def test_known_plus_unknown_flags_only_the_unknown_part(tmp_path):
    sha, g2 = _g2(tmp_path, "feat(auth,daemon): half known")
    assert g2.status == "fail"
    assert sha[:8] in g2.detail
    assert "scope='daemon'" in g2.detail
    assert "auth" not in g2.detail


def test_every_unknown_part_is_listed(tmp_path):
    _, g2 = _g2(tmp_path, "feat(daemon, lib): both unknown")
    assert g2.status == "fail"
    assert "scope='daemon,lib'" in g2.detail


def test_docs_promise_no_automatic_skip():
    detector = (PLUGIN_ROOT / "scripts/audit/audit_detector.py").read_text(
        encoding="utf-8")
    skill = (PLUGIN_ROOT / "skills/compliance/SKILL.md").read_text(
        encoding="utf-8")
    hooks = (REPO_ROOT / "docs/hooks-and-pipeline.md").read_text(encoding="utf-8")
    for name, text in (("detector", detector), ("skill", skill), ("hooks doc", hooks)):
        assert "skip the match check" not in text, name
        assert "never skipped automatically" in text, name
    assert "disabled_checks" in detector and "g2_alias_map" in detector
