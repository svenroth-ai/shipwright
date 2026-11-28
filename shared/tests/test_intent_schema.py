"""intent.md format (campaign intent-pyramid U0): the schema validates a sample file and rejects a malformed one.

``_parse`` below is a minimal reference reader for the format, only so the schema can be exercised on real files.
The shipped parser is ``lib/intent_parser.py`` (U1b); it must produce this same shape.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

pytestmark = pytest.mark.covers("FR-01.16")  # the format of the human-owned intent file; no AC is claimed

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "shared" / "schemas" / "intent.schema.json").read_text(encoding="utf-8"))
FIXTURES = ROOT / "shared" / "tests" / "fixtures" / "intent"
_SECTIONS = {"Intent": "intent", "Non-goals": "non_goals", "Capabilities": "capabilities", "Key scenarios": "scenarios"}
_ELEMENT = re.compile(r"^- ([A-Z]+-[0-9]+)(?: ([^:]+))?: (.*) \[([^\]]*)\]$")


def _parse(text: str) -> dict:
    head, body = re.match(r"---\n(.*?)\n---\n(.*)", text.replace("\r\n", "\n"), re.S).groups()
    meta = dict(line.split(": ", 1) for line in head.splitlines())
    doc: dict = {"intent_version": int(meta["intent_version"]), "product": meta["product"],
                 "intent": [], "non_goals": [], "capabilities": [], "scenarios": []}
    key = None
    for line in body.splitlines():
        if line.startswith("## "):
            key = _SECTIONS[line[3:].strip()]
        elif not line.strip():
            continue
        elif not (m := _ELEMENT.match(line)) or key is None:
            raise ValueError(f"unparseable line (never dropped silently): {line!r}")
        else:
            el = {"id": m[1], "status": m[4], "text": m[3]}
            if m[2]:
                el["name"] = m[2]
            doc[key].append(el)
    return doc


def _sample() -> dict:
    return _parse((FIXTURES / "sample_intent.md").read_text(encoding="utf-8"))


def test_sample_validates() -> None:
    jsonschema.validate(_sample(), SCHEMA)


def test_malformed_file_is_rejected() -> None:
    doc = _parse((FIXTURES / "malformed_intent.md").read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(doc))
    by_rule = {(tuple(e.absolute_path), e.validator) for e in errors}
    cap = ("capabilities", 0)
    assert (cap + ("status",), "enum") in by_rule, by_rule      # bad status
    assert (cap + ("id",), "pattern") in by_rule, by_rule       # bad id
    assert (cap + ("text",), "not") in by_rule, by_rule         # FR id in human text
    assert (cap, "required") in by_rule, by_rule                # no capability name


def test_no_upper_limits() -> None:
    doc = _sample()
    doc["capabilities"] = [{"id": f"CAP-{n:02d}", "name": "n", "status": "assumption", "text": "x" * 5000} for n in range(1, 60)]
    jsonschema.validate(doc, SCHEMA)


@pytest.mark.parametrize("name,ok", [("Collection: recipes", False), ("FR-01.02", False), ("Pantry search", True)])
def test_capability_name_rules(name: str, ok: bool) -> None:
    doc = _sample()
    doc["capabilities"][0]["name"] = name
    assert jsonschema.Draft202012Validator(SCHEMA).is_valid(doc) is ok


def test_fr_like_words_that_are_not_catalog_ids_are_allowed() -> None:
    doc = _sample()
    doc["capabilities"][0]["text"] = "Design FR4 circuit boards for hobbyists."
    jsonschema.validate(doc, SCHEMA)
    doc["capabilities"][0]["text"] = "Design boards (see FR-01.02)."
    assert not jsonschema.Draft202012Validator(SCHEMA).is_valid(doc)


@pytest.mark.parametrize("old,new", [
    ("- NG-01: Not a meal-delivery or grocery-ordering service. [confirmed]", "- NG-01 [confirmed]: Not a meal-delivery or grocery-ordering service."),
    ("- CAP-01 Collection: Keep recipes in a personal collection. [confirmed]", "- CAP-01 [confirmed] Collection: Keep recipes in a personal collection."),
])
def test_the_old_status_before_the_text_form_is_rejected(old: str, new: str) -> None:
    text = (FIXTURES / "sample_intent.md").read_text(encoding="utf-8")
    assert old in text
    with pytest.raises(ValueError):
        _parse(text.replace(old, new))


def test_a_status_inside_the_capability_name_is_rejected() -> None:
    doc = _sample()
    doc["capabilities"][0]["name"] = "[confirmed] Collection"
    assert not jsonschema.Draft202012Validator(SCHEMA).is_valid(doc)


def test_an_unparseable_element_line_is_an_error_not_dropped() -> None:
    bad = (FIXTURES / "sample_intent.md").read_text(encoding="utf-8").replace("- NG-01: Not a meal-delivery or grocery-ordering service. [confirmed]", "- NG-01: Not a meal-delivery service. confirmed")
    with pytest.raises(ValueError):
        _parse(bad)


@pytest.mark.parametrize("text", ["x\n", "\tx", "x\ty\n", "a\nb", "links CAP-02 here", "see SCN-01", "FR-03.10 holds"])
def test_text_must_be_one_trimmed_line_without_ids(text: str) -> None:
    doc = _sample()
    doc["scenarios"][0]["text"] = text
    assert not jsonschema.Draft202012Validator(SCHEMA).is_valid(doc)


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(intent=[]),                      # the intent text is required
    lambda d: d["scenarios"][0].update(text=" padded "),  # untrimmed text
    lambda d: d["scenarios"][0].update(id="CAP-01"),      # id of the wrong kind
    lambda d: d["non_goals"][0].update(extra=1),          # unknown key
    lambda d: d.update(intent_version=2),
    lambda d: d["capabilities"][0].pop("name"),            # a capability needs its short name
])
def test_structural_violations_are_rejected(mutate) -> None:
    doc = _sample()
    mutate(doc)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)


@pytest.mark.parametrize("kind,section", [("INT", "intent"), ("NG", "non_goals"), ("CAP", "capabilities"), ("SCN", "scenarios")])
def test_an_id_with_a_trailing_newline_is_rejected(kind: str, section: str) -> None:
    doc = _sample()
    doc[section][0]["id"] = f"{kind}-01\n"
    assert not jsonschema.Draft202012Validator(SCHEMA).is_valid(doc)


def test_a_status_token_inside_the_text_is_rejected() -> None:
    line = "- NG-01: [confirmed] Not a delivery service [assumption]"
    m = _ELEMENT.match(line)
    doc = _sample()
    doc["non_goals"][0] = {"id": m[1], "text": m[3], "status": m[4]}
    assert m[3] == "[confirmed] Not a delivery service" and m[4] == "assumption"
    assert not jsonschema.Draft202012Validator(SCHEMA).is_valid(doc)
