"""Guard: no module names a root ``shipwright_*`` file except through the resolver.

Campaign root-files-into-config, R0b (BRIEF 4.6 / 11.9). The resolver
(``shared/scripts/lib/shipwright_paths.py``) is the only place allowed to know where these
files live; moving them (R1-R3) is then one edit plus this guard. Scope: Python (AST, so
f-strings, concatenations and ``.lock`` construction are seen), bash, YAML, deploy-profile
JSON and SKILL/agent/reference markdown (carriers, held to a ratchet because they cannot call
Python - they flip with the plugin version in R3).

**Allowlists are explicit and reasoned.** A new entry needs a reason a reviewer can disagree
with. Test files and fixtures are exempt wholesale: they write the root layout on purpose
until R3. The resolver and (from R2) the migration tool, the R3 hard-abort code and the
class-8 persisted-provenance regexes are the only product code that may name the files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # for _shipwright_paths_scan

import _shipwright_paths_scan as scan  # noqa: E402

# --- explicit allowlists: file -> why -------------------------------------------------------
#: Locks beside files that are NOT moved data files (the resolver owns only data-file locks).
LOCK_ALLOWED = {
    "plugins/shipwright-compliance/scripts/lib/compliance_override.py": "override log lock, not a moved file",
    "plugins/shipwright-deploy/scripts/lib/rollback_audit.py": "rollback audit log lock",
    "shared/scripts/lib/_host_resource_locking.py": "host resource lease locks",
    "shared/scripts/lib/doc_bullets.py": "doc file lock",
    "shared/scripts/lib/host_resource_lease.py": "host resource lease locks",
    "shared/scripts/lib/iterate_timings.py": "timings file lock",
    "shared/scripts/lib/layer_promotion_ledger.py": "ledger lock",
    "shared/scripts/tools/aggregate_decisions.py": "decision log lock",
    "shared/scripts/tools/append_changelog_entry.py": "CHANGELOG lock",
    "shared/scripts/tools/brief_project_mode.py": "CONTEXT.md lock",
    "shared/scripts/tools/suite_worktree_diff.py": "diff-index lock",
    "shared/scripts/tools/write_context_term.py": "CONTEXT.md lock",
    "shared/scripts/tools/write_grill_trace.py": "grill-trace lock",
    "shared/scripts/triage.py": "triage.jsonl lock",
}
#: Rules that cover the whole ``.shipwright/`` tree. Name-based scans miss them (BRIEF 11.9 6c);
#: each must be decided at R3 (is ``.shipwright/config/`` exempt?). R0b inventories, never decides.
PREFIX_RULE_ALLOWED = {
    "plugins/shipwright-design/scripts/checks/check-design-gates.py": "R3: decide config/ exemption",
    "plugins/shipwright-plan/scripts/checks/check-plan-gates.py": "R3: decide config/ exemption",
    "plugins/shipwright-security/scripts/lib/scan_gitignore.py": "R3: decide config/ exemption",
    "shared/scripts/lib/ac_surface.py": "R3: decide config/ exemption",
    "shared/scripts/lib/change_type_paths.py": "R3: bookkeeping rule must learn .shipwright/config/ (BRIEF 4.1)",
    "shared/scripts/lib/review_attestation.py": "R3: decide config/ exemption",
    "shared/scripts/lib/review_diff_threshold.py": "R3: decide config/ exemption",
    "shared/scripts/lib/worktree_isolation.py": "R3: decide config/ exemption",
    "shared/scripts/tools/verifiers/_baseline_b_packs.py": "R3: _OMIT regex (BRIEF 11.9 6c)",
    "shared/scripts/tools/write_decision_log.py": "decides the drops path only; unaffected",
}
#: Names that must stay literal. Degraded-import fallbacks cannot depend on the resolver (they run
#: exactly when shared/scripts/lib is missing); persisted-provenance regexes (test_results_backfill_check, 11.9 6b) contain spaces, so the prose rule skips them.
LITERAL_ALLOWED = {
    "plugins/shipwright-changelog/scripts/lib/release_event.py": "the changelog plugin has a lib package of its own and cannot import the shared resolver; the name is a pathspec for git (P4)",
    "plugins/shipwright-changelog/scripts/lib/release_verify.py": "same: the plugin cannot import the shared resolver; the name is a search path (P4)",
    "shared/scripts/hooks/track_tool_calls.py": "degraded-import fallback: must not depend on shared lib (R1 item, BRIEF 4.7.1)",
    "shared/scripts/hooks/check_required_checks_hook.py": "degraded-import fallback: must not depend on shared lib (R1 item, BRIEF 4.7.1)",
    "plugins/shipwright-iterate/scripts/hooks/iterate_worktree_gate.py": "fail-open fallback when the resolver cannot be imported",
    "plugins/shipwright-run/scripts/hooks/master_stop_check.py": "observational hook: must still run when the shared cache is stale",
    "plugins/shipwright-compliance/scripts/lib/security_gate.py": "fail-closed deploy gate must not depend on a possibly stale shared tree",
    "plugins/shipwright-compliance/scripts/lib/rtm_gate_support.py": "commit gate must keep evaluating when the shared tree is stale",
    "plugins/shipwright-grade/scripts/lib/routing.py": "grade stays usable without shared (lazy/soft-fail design)",
    "plugins/shipwright-grade/scripts/lib/authoritative.py": "grade stays usable without shared (lazy/soft-fail design)",
    "shared/scripts/hooks/session_start_using_shipwright.py": "session hook: must still run when the shared cache is stale",
    "shared/scripts/hooks/suggest_iterate.py": "hook must not crash when the shared cache is stale: guarded import with a literal fallback (Tier-3 review, PR 1089)",
    "shared/scripts/hooks/check_file_size.py": "hook must not crash when the shared cache is stale: guarded import with a literal fallback (Tier-3 review, PR 1089)",
    "shared/scripts/hooks/required_checks_state.py": "hook must not crash when the shared cache is stale: guarded import with a literal fallback (Tier-3 review, PR 1089)",
}
ALLOWED = {"lock-construction": LOCK_ALLOWED, "shipwright-prefix-rule": PREFIX_RULE_ALLOWED, "literal": LITERAL_ALLOWED}


def _violations():
    out = []
    for rel in scan.production_py():
        for rule, line, text in scan.scan_python(rel):
            if rel not in ALLOWED.get(rule, {}):
                out.append(f"{rel}:{line}: [{rule}] {text}")
    return out


@pytest.mark.covers("FR-01.11")
def test_python_goes_through_the_resolver():
    found = _violations()
    assert not found, (
        "name a root file through shared/scripts/lib/shipwright_paths.py "
        "(rel / path / rel_at / lock_for / lock_beside), or add a REASONED allowlist entry:\n" + "\n".join(found)
    )


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("rule", sorted(ALLOWED))
def test_allowlists_have_no_stale_entries(rule):
    """An entry whose file no longer trips the rule is dead weight that would hide a regression."""
    live = {(rule, rel) for rel in scan.production_py() for rule, _, _ in scan.scan_python(rel)}
    stale = [rel for rel in ALLOWED[rule] if (rule, rel) not in live]
    assert not stale, f"remove from the allowlist: {stale}"


@pytest.mark.covers("FR-01.11")
def test_carriers_do_not_grow():
    """bash / YAML / deploy-profile JSON / md / templates: per-file, per-name count of root names is a ratchet."""
    baseline, now = scan.load_baseline(), scan.carrier_counts()
    grown = [f"{p}: {name} x{n} > {baseline.get(p, {}).get(name, 0)}"
             for p, names in sorted(now.items()) for name, n in names.items()
             if n > baseline.get(p, {}).get(name, 0)]
    assert not grown, (
        "a carrier names more root shipwright_* files than the ratchet allows. Prose cannot call the "
        "resolver; keep the count, or lower it, or (new file) regenerate with "
        "`uv run python shared/tests/_shipwright_paths_scan.py --write` and justify it in review:\n" + "\n".join(grown)
    )


@pytest.mark.covers("FR-01.11")
def test_carrier_scan_covers_every_carrier_kind():
    """The scan must actually see bash, YAML, deploy-profile JSON and SKILL/agent md."""
    seen = set(scan.carrier_files())
    assert "scripts/hooks/pre-commit" in seen
    assert ".github/workflows/bloat-check.yml" in seen
    assert any(p.startswith("shared/profiles/deploy/") and p.endswith(".json") for p in seen)
    assert any(p.endswith("SKILL.md") for p in seen)
    assert any("/agents/" in p and p.endswith(".md") for p in seen)


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("snippet,rule", [
    ('p = root / f"shipwright_{name}.json"\n', "constructed-name"),
    ('p = root / ("shipwright_" + name + ".json")\n', "constructed-name"),
    ('lock = Path(str(reg) + ".lock")\n', "lock-construction"),
    ('lock = reg.with_suffix(".json.lock")\n', "lock-construction"),
    ('p = root / "shipwright_run_config.json"\n', "literal"),
    ('RX = r"^(a|shipwright_bloat_baseline\\.json)"\n', "literal"),
    ('ok = path.startswith((".shipwright/", "docs/"))\n', "shipwright-prefix-rule"),
    ('def f(r, c):\n    return git("show", c + ":" + _sp.rel("test_results"))\n', "class8-uses-rel"),
])
def test_scanner_catches_each_reference_shape(tmp_path, monkeypatch, snippet, rule):
    f = tmp_path / "mod.py"
    f.write_text(snippet, encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    assert rule in {r for r, _, _ in scan.scan_python("mod.py")}


@pytest.mark.covers("FR-01.11")
def test_scanner_ignores_prose_docstrings_and_resolver_calls(tmp_path, monkeypatch):
    f = tmp_path / "mod.py"
    f.write_text('"""Reads shipwright_run_config.json."""\nmsg = "no shipwright_run_config.json found"\n'
                 'p = root / _sp.rel("run_config")\nq = _sp.rel_at("test_results", sha)\n', encoding="utf-8")
    monkeypatch.setattr(scan, "REPO", tmp_path)
    assert scan.scan_python("mod.py") == []
