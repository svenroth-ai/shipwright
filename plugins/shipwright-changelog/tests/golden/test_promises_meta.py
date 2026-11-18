"""The promise list, the promise tests' interface rule and the judgement scenarios, checked (programme P18, P19, P21).

* ``promise_list.json``: every entry has the shape of ``trace.json`` of ``shipwright-skill-check`` (id, sentence, source
  anchor with a content hash, class, check, status, decision), the six statuses only, and the claimed status agrees with
  what exists: a named test that is not there is ``dangling``, never ``passing``.
* the promise tests call the driver interface and the oracle only, and each carries the ``covers`` tag of its entry.
* ``scenarios.json``: the schema of ``compare_runs.py`` (id, seeds, title, setup, ask, expected.decision, expected.note).
* the promise lock's fingerprint (``shared/testkit/promise_hash.py``) is computed for every promise test, follows its
  helpers and the ``conftest.py`` fixtures, and resolves AC ids through the spec's ``## AC-Move-Map``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re

import pytest

import promise_hash as ph
import promise_lock as pl

from . import coverage
from .conftest import GOLDEN_DIR, REPO_ROOT

PROMISES = GOLDEN_DIR / "promise_list.json"
SCENARIOS = GOLDEN_DIR / "scenarios.json"
STATUSES = {"passing", "failing", "dangling", "proposed", "not-run", "gap"}
CLASSES = {"ask", "mechanic", "judgement", "outward command", "text"}
KINDS = {"test", "text", "scenario"}  # the kinds of check of trace.json
DECISIONS = {"block", "proceed", "ask", "do"}  # compare_runs.py
ORACLES = {"test", "trace", "scenario"}
# what a promise test may import from this package: the driver interface and the independent oracle (and the set-up helpers)
ALLOWED_LOCAL = {"oracle", "scenario_support", "driver_replay", "scenario_core"}
ALLOWED_MODULES = {"__future__", "pytest", "json"}  # an allow-list: nothing else may be imported
FORBIDDEN_TEXT = ("SKILL.md", "subprocess", "sys.executable", "scripts/", "git_utils", "aggregate_changelog", "setup-changelog")


def _doc():
    return json.loads(PROMISES.read_text(encoding="utf-8"))


def _entries():
    return _doc()["promises"]


def _promise_files():
    return sorted(GOLDEN_DIR.glob("test_promise_*.py"))


def _checks(entry):
    return [c for c in [entry["check"], *entry.get("more_checks", [])] if c is not None]


def _test_defs(path):
    return {n.name for n in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)}


def _spec_texts():
    block = coverage.SPEC.read_text(encoding="utf-8").split("### FR-01.09 —", 1)[1].split("\n### FR-", 1)[0]
    return {m.group(1): " ".join(m.group(2).split()) for m in re.finditer(r"\(E\) \[(AC\d+)\] (.*?)(?=\n- \(|\Z)", block, re.S)}


def _section_text(text, heading):
    """The section whose heading starts with ``heading``: from its line to the next heading of the same or a higher level."""
    lines = text.replace("\r\n", "\n").split("\n")
    start = level = None
    for n, line in enumerate(lines):
        found = re.match(r"^(#+)\s+(.*)$", line)
        if found and start is None and found.group(2).strip().startswith(heading):
            start, level = n, len(found.group(1))
        elif found and start is not None and len(found.group(1)) <= level:
            return "\n".join(lines[start:n]).strip()
    return "\n".join(lines[start:]).strip() if start is not None else None


def _located(check):
    """``(file, name)`` of a ``test`` check ``path::name``; the file must be inside the repository."""
    path, _, name = check["id"].partition("::")
    assert (REPO_ROOT / path).resolve().is_relative_to(REPO_ROOT.resolve()), check["id"]
    return REPO_ROOT / path, name


@pytest.mark.covers("FR-01.09/AC01")
def test_every_entry_has_the_shape_of_the_trace_record_and_one_of_the_six_statuses():
    ids = []
    for e in _entries():
        assert {"id", "sentence", "source", "class", "check", "status", "decision", "oracle"} <= set(e), e["id"]
        assert e["status"] in STATUSES and e["class"] in CLASSES and e["oracle"] in ORACLES | {"none"}, e["id"]
        assert e["sentence"].strip() and e["decision"].strip() and {"file", "heading_path", "content_hash"} == set(e["source"]), e["id"]
        assert all(c["kind"] in KINDS for c in _checks(e)), e["id"]
        ids.append(e["id"])
    assert len(ids) == len(set(ids))


@pytest.mark.covers("FR-01.09/AC01")
def test_no_entry_calls_a_missing_script_name_uncovered():
    text = PROMISES.read_text(encoding="utf-8").lower()
    assert "uncovered" not in text
    assert any(e["status"] == "gap" and "not obviously covered" in e.get("note", "").lower() for e in _entries())


@pytest.mark.covers("FR-01.09/AC01")
def test_a_claimed_status_agrees_with_what_exists():
    for e in _entries():
        checks, tests = _checks(e), [c for c in _checks(e) if c["kind"] == "test"]
        for c in tests:
            path, name = _located(c)
            present = path.is_file() and name in _test_defs(path)
            assert present == (e["status"] in ("passing", "failing")), f"{e['id']}: {c['id']} is {'there' if present else 'dangling'}, status {e['status']}"
        if e["status"] == "gap" or e["status"] == "proposed":
            assert not tests, e["id"]  # a gap or a proposal names no check (a proposal is never counted as proof)
        if e["status"] == "not-run":
            assert checks and all(c["kind"] == "scenario" for c in checks), e["id"]
        if e["oracle"] == "scenario":
            assert e["status"] == "not-run", e["id"]


@pytest.mark.covers("FR-01.09/AC01")
def test_the_source_anchor_hashes_the_acceptance_criterion_it_names_and_other_anchors_exist():
    texts = _spec_texts()
    for e in _entries():
        file = REPO_ROOT / e["source"]["file"]
        assert file.is_file(), e["id"]
        if e["source"]["file"] == str(coverage.SPEC.relative_to(REPO_ROOT).as_posix()):
            ac = e["source"]["heading_path"][-1]
            assert ac in texts, f"{e['id']}: the spec has no {ac} any more"
            assert e["source"]["content_hash"] == hashlib.sha256(texts[ac].encode()).hexdigest(), f"{e['id']}: the spec text of {ac} changed, review the sentence and re-hash"
        else:
            body = _section_text(file.read_text(encoding="utf-8"), e["source"]["heading_path"][-1])
            assert body, f"{e['id']}: the heading {e['source']['heading_path'][-1]!r} is gone from {e['source']['file']}"
            assert e["source"]["content_hash"] == hashlib.sha256(body.encode("utf-8")).hexdigest(), f"{e['id']}: the section changed, review the sentence and re-hash"


@pytest.mark.covers("FR-01.09/AC01")
def test_every_ac_of_the_requirement_has_an_entry_and_the_replay_only_parts_are_marked_oracle_trace():
    entries = {e["id"]: e for e in _entries()}
    assert set(coverage.spec_acs()) <= set(entries)
    assert {i for i, e in entries.items() if e["status"] == "gap"} == {"FR-01.09/AC11"}  # a full pass must be a deliberate edit
    assert entries["FR-01.09/AC11"]["status"] == "gap" and entries["FR-01.09/AC11/aggregation"]["status"] == "passing"
    traced = {i for i, e in entries.items() if e["oracle"] == "trace"}
    assert traced == {"FR-01.09/AC01/request", "FR-01.09/AC15/no-backfill"}  # parts seen only in the stub's state or log, entries of their own
    assert {i for i, e in entries.items() if e["oracle"] == "none"} == {i for i, e in entries.items() if e["status"] in ("gap", "proposed")}


@pytest.mark.covers("FR-01.09/AC01")
def test_every_promise_test_is_bound_by_an_entry_and_carries_that_entrys_covers_tag():
    bound = {}
    for e in _entries():
        for c in _checks(e):
            if c["kind"] == "test":
                bound[c["id"]] = re.match(r"FR-\d{2}\.\d{2}/AC\d{2,}", e["id"]).group(0)
    found = {}
    for path in _promise_files():
        source = path.read_text(encoding="utf-8")
        for name in ph.tests_in(source):
            found[f"{path.relative_to(REPO_ROOT).as_posix()}::{name}"] = ph.covers_of(name, source)
    assert set(found) == set(bound), sorted(set(found) ^ set(bound))
    for check, ids in found.items():
        assert ids == [bound[check]], f"{check} is tagged {ids}, its entry says {bound[check]}"


@pytest.mark.covers("FR-01.09/AC01")
def test_promise_tests_go_through_the_driver_interface_and_the_oracle_only():
    assert _promise_files()
    for path in _promise_files():
        source = path.read_text(encoding="utf-8")
        assert not [w for w in FORBIDDEN_TEXT if w in source.replace("`SKILL.md`", "")], path.name
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):  # an alias would let one module pose as another: the fingerprint hashes the binding, this refuses it
                assert all(x.asname in (None, x.name) for x in node.names), f"{path.name} imports {[(x.name, x.asname) for x in node.names]} under another name"
            if isinstance(node, ast.ImportFrom):
                local = node.level == 1 and (node.module is None and {x.name for x in node.names} <= ALLOWED_LOCAL
                                             or node.module in ALLOWED_LOCAL)
                assert local or (node.level == 0 and node.module in ALLOWED_MODULES), f"{path.name} imports {node.module}"
            elif isinstance(node, ast.Import):
                assert {x.name for x in node.names} <= ALLOWED_MODULES, f"{path.name} imports {[x.name for x in node.names]}"
        for stmt in ast.parse(source).body:  # a statement that binds nothing runs at import and is invisible to the fingerprint: refuse it
            plain = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)) \
                or isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef)) \
                or (isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and all(isinstance(t, ast.Name) for t in ([stmt.target] if not isinstance(stmt, ast.Assign) else stmt.targets))
                                                                      and not any(isinstance(n, ast.Call) for n in ast.walk(stmt)))  # a call at import can rewire the oracle unseen
            assert plain, f"{path.name}:{stmt.lineno} is a module-level statement the fingerprint cannot see"
        assert "ReplayDriver" in source, path.name
        assert len(source.splitlines()) <= 300, path.name
        for name in ph.tests_in(source):  # every promise test reaches the oracle through its own closure, not through a neighbour's use of it
            assert "oracle" in ph.closure(name, source, [_golden_sources()]), f"{path.name}::{name} never reaches the oracle"


@pytest.mark.covers("FR-01.09/AC01")
def test_scenarios_json_is_valid_in_the_schema_of_the_comparison_tool_and_covers_the_three_questions():
    doc = json.loads(SCENARIOS.read_text(encoding="utf-8"))  # compare_runs.check_scenarios, restated
    items = doc["scenarios"]
    assert isinstance(items, list) and items
    known, seen = set(coverage.all_scenarios()), set()
    for s in items:
        for key in ("id", "setup", "ask", "expected"):
            assert key in s, f"scenario {s.get('id', '?')} lacks {key!r}"
        assert s["id"] not in seen
        seen.add(s["id"])
        assert s["expected"]["decision"] in DECISIONS and s["expected"]["note"].strip(), s["id"]
        assert s["title"].strip() and s["seeds"] and set(s["seeds"]) <= known, s["id"]
    for question in ("version", "preview", "out-of-sequence"):
        assert any(i.startswith(question) for i in seen), question
    assert {c["id"] for e in _entries() for c in _checks(e) if c["kind"] == "scenario"} == seen  # every scenario is bound to a promise


def _golden_sources():
    return (GOLDEN_DIR / "conftest.py").read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.09/AC01")
def test_the_fingerprint_is_stable_for_every_promise_test_follows_the_conftest_fixtures_and_differs_per_test():
    conftest, prints = _golden_sources(), {}
    for path in _promise_files():
        source = path.read_text(encoding="utf-8")
        for name in ph.tests_in(source):
            first = ph.fingerprint(name, source, [conftest])
            assert first == ph.fingerprint(name, source, [conftest]) and len(first) == 64
            key = pl.lock_key(path.relative_to(REPO_ROOT).as_posix(), name)  # a lock entry is keyed path::name: a bare name is not unique
            assert key not in prints, key
            prints[key] = first
    assert len(set(prints.values())) == len(prints) >= 20
    source = (GOLDEN_DIR / "test_promise_aggregate.py").read_text(encoding="utf-8")
    parts = ph.closure("test_ac06_the_new_section_goes_above_the_latest_release_and_older_text_stays", source, [conftest])
    assert {"make_project@1", "make_scratch@1", "warm_uv@1", "_project", "HISTORY", "VERSION", "NEW", "_aggregate"} <= set(parts)


@pytest.mark.covers("FR-01.09/AC01")
def test_the_lock_entry_of_a_promise_test_names_its_acceptance_criterion_through_the_move_map():
    spec = coverage.SPEC.read_text(encoding="utf-8")
    source = (GOLDEN_DIR / "test_promise_release.py").read_text(encoding="utf-8")
    entry = pl.lock_entry("test_ac13_a_version_written_in_several_places_of_one_manifest_is_written_in_all_together", source, spec, [_golden_sources()])
    assert entry["acs"] == ["FR-01.09/AC13"] and len(entry["hash"]) == 64
    moved = pl.lock_entry("test_ac13_a_version_written_in_several_places_of_one_manifest_is_written_in_all_together", source,
                          spec + "\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.09/AC13` | `FR-01.40/AC13` |\n", [_golden_sources()])
    assert moved["acs"] == ["FR-01.40/AC13"] and moved["hash"] == entry["hash"]
