"""Adopt writes the profile's architecture rules into conventions.md (one marked block)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.generate_adoption_artifacts import generate

pytestmark = pytest.mark.covers("FR-01.01/AC17")

BEGIN = "<!-- shipwright:architecture-rules:begin"
RULE = {"id": "thin-routes", "text": "Keep routes thin.", "why": "Logic belongs in lib.",
        "enforcement": "prompt-only (judgement)"}


def _project(tmp_path: Path, rules) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    profile = {"name": "rules-stack", "description": "d"}
    if rules is not None:
        profile["architecture_rules"] = rules
    pdir = root / ".shipwright" / "profiles"
    pdir.mkdir(parents=True)
    (pdir / "rules-stack.json").write_text(json.dumps(profile), encoding="utf-8")
    snap = root / ".shipwright" / "adopt" / "snapshot.json"
    snap.parent.mkdir(parents=True)
    snap.write_text(json.dumps({"project_root": str(root), "stack": {}, "profile": {"matched": "rules-stack"}}),
                    encoding="utf-8")
    return root


def _generate(root: Path) -> dict:
    return generate(
        root, snapshot_path=root / ".shipwright" / "adopt" / "snapshot.json",
        enrichment_path=root / "no-enrichment.json", routes_path=root / "no-routes.json",
        split_name="01-adopted", plugin_version="0.0.0", scope_override=None, profile_override=None,
        write_sync=False, backfill_events=False,
    )


def _conventions(root: Path) -> str:
    return (root / ".shipwright" / "agent_docs" / "conventions.md").read_text(encoding="utf-8")


def test_adopt_on_a_profile_with_rules_gets_the_block(tmp_path):
    root = _project(tmp_path, [RULE])
    _generate(root)
    text = _conventions(root)
    assert text.count(BEGIN) == 1 and "**thin-routes** - Keep routes thin." in text
    assert "## Architecture Rules" in text
    assert "## Linter / Formatter" in text  # adopt's own sections are still there


def test_adopt_twice_gives_the_same_conventions(tmp_path):
    root = _project(tmp_path, [RULE])
    _generate(root)
    first = _conventions(root)
    _generate(root)
    assert _conventions(root) == first


def test_adopt_on_a_profile_without_rules_says_none_declared(tmp_path):
    root = _project(tmp_path, None)
    _generate(root)
    assert "_No architecture rules declared by stack profile `rules-stack`._" in _conventions(root)


def test_bad_rule_is_reported_in_the_result_not_fatal(tmp_path):
    root = _project(tmp_path, [RULE, {"id": "bad", "text": "x", "why": "y", "enforcement": "nonsense"}])
    result = _generate(root)
    assert any("rule bad" in n for n in result["architecture_rules_notes"])
    assert "**thin-routes**" in _conventions(root) and "**bad**" not in _conventions(root)


def test_unwritable_conventions_is_a_note_not_a_crash(tmp_path):
    from lib.adopt_profile import write_rules_block

    class _Res:
        name = "rules-stack"
        data = {"architecture_rules": [RULE]}

    notes = write_rules_block(tmp_path / "missing" / "conventions.md", _Res())
    assert any("NOT written" in n for n in notes)
    damaged = tmp_path / "c.md"
    damaged.write_text(BEGIN + " (x) -->\nno end marker\n", encoding="utf-8")
    assert any("NOT written" in n for n in write_rules_block(damaged, _Res()))
    assert damaged.read_text(encoding="utf-8") == BEGIN + " (x) -->\nno end marker\n"


def test_missing_shared_tool_is_a_note(tmp_path, monkeypatch):
    import lib.adopt_profile as ap

    monkeypatch.setattr(ap, "_SHARED_SCRIPTS", str(tmp_path / "nowhere"))
    monkeypatch.setattr(ap, "load_resolver", lambda: None)
    assert any("missing" in n for n in ap.write_rules_block(tmp_path / "c.md", object()))
