"""Capstone: the golden manifest MATCHES the reference parser + evidence (property 4).

Schema-validity (compliance suite) proves the golden is well-shaped; this proves it
is *correct* — i.e. it is exactly what the reference @FR grammar over the mini-repo
plus the execution-evidence would produce. A golden with a wrong test→FR mapping,
a missing/extra hit, a wrong tag_source, a wrong orphan, or coverage that disagrees
with the evidence would fail here even though it still validates against the schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.fr_tag_grammar import parse_source

_REPO = Path(__file__).resolve().parents[2]
_FIX = _REPO / "plugins/shipwright-compliance/tests/fixtures/traceability"
_APP = _FIX / "mini_repos/app"


def _parse_app():
    hits, invalid = [], []
    for f in sorted(_APP.rglob("*")):
        if f.is_file() and f.suffix in (".py", ".ts"):
            res = parse_source(f.relative_to(_APP).as_posix(), f.read_text(encoding="utf-8"))
            hits += res.hits
            invalid += res.invalid
    return hits, invalid


def _golden():
    return json.loads((_FIX / "golden" / "manifest.json").read_text(encoding="utf-8"))


def _evidence():
    return json.loads((_FIX / "evidence" / "evidence_index.json").read_text(encoding="utf-8"))["results"]


def test_golden_bindings_and_tag_sources_match_the_parser():
    hits, invalid = _parse_app()
    golden = _golden()

    parser_pairs = {(h.fr_id, h.test) for h in hits}
    parser_triples = {(h.fr_id, h.test, h.tag_source) for h in hits}

    link_triples, link_pairs = set(), set()
    for req in golden["requirements"].values():
        for links in req["tests"].values():
            for link in links:
                link_triples.add((req["id"], link["path"], link["tag_source"]))
                link_pairs.add((req["id"], link["path"]))
    orphan_pairs = {(o["tagged_fr"], o["test"]) for o in golden["orphans"]}

    # every parser binding is accounted for as either a coverage link or an orphan, and vice versa
    assert parser_pairs == link_pairs | orphan_pairs
    # each coverage link matches a real parser hit INCLUDING its tag_source
    assert link_triples <= parser_triples
    # malformed tags match exactly
    assert {i.raw for i in invalid} == {it["raw"] for it in golden["invalid_tags"]}
    # the untagged test really produced no binding
    for untagged in golden["untagged_tests"]:
        assert all(untagged != h.test for h in hits)


def test_golden_test_link_states_match_the_execution_evidence():
    golden, evidence = _golden(), _evidence()
    for req in golden["requirements"].values():
        for links in req["tests"].values():
            for link in links:
                ev = evidence[link["id"]]
                assert (ev["status"], ev["executed"]) == (link["status"], link["executed"]), link["id"]


def test_golden_coverage_agrees_with_evidence_per_layer():
    golden = _golden()
    for req in golden["requirements"].values():
        for layer, status in req["coverage"].items():
            links = req["tests"].get(layer, [])
            passing = any(l["status"] == "enabled" and l["executed"] == "pass" for l in links)
            if status == "ok":
                assert passing, (req["id"], layer)          # ok REQUIRES an enabled+pass link (R1)
            elif status == "MISSING":
                assert not passing, (req["id"], layer)      # MISSING must have no enabled+pass link
