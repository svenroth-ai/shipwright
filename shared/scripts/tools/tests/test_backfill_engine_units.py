"""Unit coverage for the backfill engine's LLM adapter + CLI/report internals (TT6).

Splits the production-path units (the OpenRouter adjudicator, secret redaction,
CLI ``main``, report rendering, spec/test-root discovery) out of the behaviour
suites so each file stays ≤300 LOC and the diff-coverage gate is satisfied
without a live network call (a fake ``openai`` module drives ``_ask``).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backfill_support import backfill_llm, bf, copy_repo  # noqa: E402


# --------------------------------------------------------------------------- #
# backfill_llm — redaction, parsing, adjudicator wiring                       #
# --------------------------------------------------------------------------- #

def test_redact_secrets_scrubs_every_token_shape():
    parts = {
        "gh": "ghp" + "_" + "A" * 30,
        "openai": "sk-" + "B" * 22,
        "aws": "AKIA" + "C" * 16,
        "slack": "xoxb-" + "1234567890-abcdef",
        "bearer": "Bearer " + "z" * 24,
        "jwt": "eyJ" + "a" * 14 + "." + "b" * 14 + "." + "c" * 14,
        "hex": "ab12" * 12,
    }
    for label, token in parts.items():
        title = f"logs in with {token} end"
        out = backfill_llm.redact_secrets(title)
        assert token not in out, label
        assert "[REDACTED]" in out, label
    # an ordinary title is left intact
    assert backfill_llm.redact_secrets("dashboard shows live orders") == "dashboard shows live orders"


def test_null_adjudicator_abstains_and_validates():
    adj = backfill_llm.NullAdjudicator()
    resp = adj.adjudicate({"test_path": "a", "test_title": "b", "candidate_frs": ["FR-01.02"]})
    assert resp == {"proposed_fr": None, "confidence": 0.0, "auto_write": False}
    with pytest.raises(ValueError):
        adj.adjudicate({"test_path": "a", "test_title": "b", "candidate_frs": [], "body": "x"})


def test_build_adjudicator_selects_by_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert isinstance(backfill_llm.build_adjudicator(True, {}, lambda c, k: "m"),
                      backfill_llm.NullAdjudicator)                      # keyed off → null
    assert isinstance(backfill_llm.build_adjudicator(False, {}, lambda c, k: "m"),
                      backfill_llm.NullAdjudicator)                      # use_llm off → null
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-xyz")
    assert isinstance(backfill_llm.build_adjudicator(True, {}, lambda c, k: "m"),
                      backfill_llm.OpenRouterAdjudicator)


@pytest.mark.parametrize("raw,expected", [
    (None, (None, 0.0)),
    ("no json here", (None, 0.0)),
    ('{bad json', (None, 0.0)),
    ('{"proposed_fr": "FR-1.3", "confidence": 0.9}', (None, 0.0)),      # non-canonical
    ('{"proposed_fr": "FR-01.02", "confidence": "high"}', ("FR-01.02", 0.0)),  # bad conf
    ('prefix {"proposed_fr": "FR-01.02", "confidence": 2.0} suffix', ("FR-01.02", 1.0)),  # clamped
])
def test_openrouter_parse(raw, expected):
    assert backfill_llm.OpenRouterAdjudicator._parse(raw) == expected


def _install_fake_openai(monkeypatch, content):
    mod = types.ModuleType("openai")

    class _OpenAI:
        def __init__(self, **kw):
            resp = types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))])
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **k: resp))

    mod.OpenAI = _OpenAI
    monkeypatch.setitem(sys.modules, "openai", mod)


def test_openrouter_adjudicate_consensus_via_fake_openai(monkeypatch):
    _install_fake_openai(monkeypatch, '{"proposed_fr": "FR-01.02", "confidence": 0.7}')
    adj = backfill_llm.OpenRouterAdjudicator("key", {}, lambda config, key: "some/model")
    payload = {"test_path": "t.ts", "test_title": "x", "candidate_frs": ["FR-01.02", "FR-01.03"]}
    resp = adj.adjudicate(payload)     # both models agree on FR-01.02 (in the candidate set)
    assert resp == {"proposed_fr": "FR-01.02", "confidence": 0.7, "auto_write": False}


def test_openrouter_adjudicate_out_of_set_fr_is_dropped(monkeypatch):
    _install_fake_openai(monkeypatch, '{"proposed_fr": "FR-09.09", "confidence": 0.9}')
    adj = backfill_llm.OpenRouterAdjudicator("key", {}, lambda config, key: "some/model")
    payload = {"test_path": "t.ts", "test_title": "x", "candidate_frs": ["FR-01.02"]}
    assert adj.adjudicate(payload)["proposed_fr"] is None      # FR-09.09 not in the candidate set


def test_openrouter_ask_failure_is_swallowed(monkeypatch):
    adj = backfill_llm.OpenRouterAdjudicator("key", {}, lambda config, key: "some/model")
    monkeypatch.setattr(adj, "_ask", lambda k, p: (_ for _ in ()).throw(RuntimeError("boom")))
    payload = {"test_path": "t.ts", "test_title": "x", "candidate_frs": ["FR-01.02"]}
    assert adj.adjudicate(payload)["proposed_fr"] is None


# --------------------------------------------------------------------------- #
# backfill_test_links — discovery, rendering, CLI                             #
# --------------------------------------------------------------------------- #

def test_discover_specs_and_default_test_roots(tmp_path):
    root = tmp_path / "proj"
    (root / ".shipwright/agent_docs").mkdir(parents=True)
    (root / ".shipwright/agent_docs/spec.md").write_text("# top", encoding="utf-8")
    (root / ".shipwright/planning/01-x").mkdir(parents=True)
    (root / ".shipwright/planning/01-x/spec.md").write_text("# split", encoding="utf-8")
    (root / "spec.md").write_text("# root", encoding="utf-8")
    (root / "tests").mkdir()
    specs = bf.discover_specs(root)
    assert (root / ".shipwright/agent_docs/spec.md") in specs
    assert any(p.parent.name == "01-x" for p in specs)
    assert (root / "spec.md") in specs
    roots = bf._default_test_roots(root)
    assert (root / "tests") in roots
    assert bf._default_test_roots(tmp_path / "empty") == [tmp_path / "empty"]   # fallback


def test_render_markdown_none_and_write_failures():
    empty = {
        "engine_version": "v", "generated_at": "t",
        "summary": {"tests": 0, "auto_written": 0, "proposals": 0, "confirmed_orphan": 0,
                    "possible_orphan": 0, "unmapped": 0, "already_tagged": 0, "write_failures": 1},
        "auto_written": [], "proposals": [],
        "orphans": {"confirmed_orphan": [], "possible_orphan": [], "unmapped": []},
        "write_failures": [{"test": "a::b", "fr": "FR-01.02", "reason": "non_utf8_source"}],
    }
    md = bf.render_markdown(empty)
    assert "_none_" in md
    assert "Write failures" in md and "non_utf8_source" in md


def test_main_cli_dry_run_writes_report(tmp_path):
    repo = copy_repo(tmp_path)
    rc = bf.main(["--project-root", str(repo), "--spec-file", "spec.md",
                  "--dry-run", "--repo-follows-split-convention"])
    assert rc == 0
    report = repo / ".shipwright" / "backfill" / "backfill-report.json"
    assert report.exists()
    # dry-run wrote no tag into a file
    dash = repo / "e2e/flows/FR-05.02-dashboard.spec.ts"
    assert "// @covers" not in dash.read_text(encoding="utf-8")
