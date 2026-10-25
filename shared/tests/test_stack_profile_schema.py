"""Stack-profile schema + hand checker (S1 item 14, D6 forward registry).

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_resolver as pr  # noqa: E402
import profile_schema_check as psc  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401  (module-local fixtures: "project", "user_dir")

pytestmark = pytest.mark.covers("FR-01.06")
_SCHEMA = json.loads(Path(pr.schema_path()).read_text(encoding="utf-8"))
_BUNDLED = {n: json.loads((Path(pr.bundled_dir()) / f"{n}.json").read_text(encoding="utf-8"))
            for n in pr.bundled_names()}

# D5: the keys the loaders read and the brief types strictly.
_D5_KEYS = {"name", "schema_version", "services", "dev_server", "testing",
            "required_env_vars", "rules", "folder_structure", "migrations", "design_system"}
_D5_TESTING = {"unit", "command", "integration", "e2e", "db_tests", "performance"}


def _json_schema_ok(data) -> bool:
    return not list(jsonschema.Draft202012Validator(_SCHEMA).iter_errors(data))


def _mutations() -> dict:
    base = _BUNDLED["vite-hono"]
    out = {}
    patches = {
        "services-string": {"services": "x"},
        "services-item-string": {"services": ["x"]},
        "port-float": {"services": [{"name": "a", "command": "c", "port": 1.5}]},
        "port-bool": {"services": [{"port": True}]},
        "port-int-float": {"services": [{"port": 3000.0}]},
        "sv-one-float": {"schema_version": 1.0},
        "primary-str": {"services": [{"primary": "yes"}]},
        "depends-on-str": {"services": [{"depends_on": "a"}]},
        "dev-server-list": {"dev_server": []},
        "testing-list": {"testing": []},
        "unit-number": {"testing": {"unit": 3}},
        "unit-string": {"testing": {"unit": "pytest"}},
        "perf-str": {"testing": {"performance": "on"}},
        "rules-dict": {"rules": {}},
        "env-list": {"required_env_vars": []},
        "sv-str": {"schema_version": "1"},
        "sv-zero": {"schema_version": 0},
        "name-int": {"name": 3},
        "port-placeholder": {"services": [{"port": "${PORT:-3847}"}]},
        "underscore-comments": {"_comment": 1, "stack": {"_comment": "text"}},
        "null-blocks": {"dev_server": None, "migrations": None, "design_system": None},
        "ux-ui-strings": {"ux_shape": "chat-first", "ui_host": "webui"},
        "ux-shape-int": {"ux_shape": 3},
        "ui-host-dict": {"ui_host": {"host": "x"}},
    }
    for label, patch in patches.items():
        d = copy.deepcopy(base)
        d.update(patch)
        out[label] = d
    out["missing-name"] = {k: v for k, v in base.items() if k != "name"}
    out["not-object"] = []
    return out


@pytest.mark.parametrize("name", sorted(_BUNDLED))
def test_bundled_profiles_validate_and_checkers_agree(name):
    assert pr.validate_profile_data(_BUNDLED[name], f"{name}.json") == 1
    assert psc.check(_BUNDLED[name], _SCHEMA) == []
    assert _json_schema_ok(_BUNDLED[name])


@pytest.mark.parametrize("label,data", sorted(_mutations().items()))
def test_hand_checker_agrees_with_jsonschema_on_mutations(label, data):
    try:
        pr.validate_profile_data(data, "fixture.json")
        hand_ok = True
    except ValueError:
        hand_ok = False
    assert hand_ok == _json_schema_ok(data), label


def test_polymorphic_cases_each_have_a_passing_and_failing_fixture():
    ok = {k for k, v in _mutations().items() if _json_schema_ok(v)}
    assert {"port-placeholder", "unit-string", "null-blocks", "underscore-comments",
            "port-int-float"} <= ok
    assert {"port-float", "unit-number", "dev-server-list", "services-string"}.isdisjoint(ok)


def test_schema_file_uses_only_supported_constructs():
    psc.assert_supported(_SCHEMA)


@pytest.mark.parametrize("bad", [{"oneOf": []}, {"pattern": "x"}, {"enum": [1]},
                                 {"additionalProperties": {"type": "string"}},
                                 {"type": "date"}, {"properties": {"a": {"$ref": "#"}}}])
def test_unsupported_construct_rejected_loudly(bad):
    with pytest.raises(psc.UnsupportedConstruct):
        psc.assert_supported(bad)


def test_missing_or_corrupt_schema_file_keeps_the_error_contract(monkeypatch, project, tmp_path):
    write_profile(proj_dir(project), "ok-two")
    for path in (tmp_path / "absent.json", tmp_path / "corrupt.json"):
        if path.name == "corrupt.json":
            path.write_text("{", encoding="utf-8")
        monkeypatch.setattr("profile_model.schema_path", lambda p=path: str(p))
        with pytest.raises(ValueError) as ei:
            pr.resolve_profile("ok-two", project)
        assert ei.value.kind == "schema_unsupported" and ei.value.exit_code == 3


def test_resolver_refuses_to_run_with_unsupported_schema(monkeypatch, project):
    write_profile(proj_dir(project), "ok-one")
    evil = proj_dir(project) / "evil.schema"
    evil.write_text(json.dumps({"oneOf": []}), encoding="utf-8")
    monkeypatch.setattr("profile_model.schema_path", lambda: str(evil))
    with pytest.raises(ValueError) as ei:
        pr.resolve_profile("ok-one", project)
    assert ei.value.kind == "schema_unsupported"


def test_additional_properties_false_is_unsupported_not_silently_divergent():
    with pytest.raises(psc.UnsupportedConstruct):
        psc.assert_supported({"type": "object", "additionalProperties": False})


def test_registry_d5_keys_exist_in_schema():
    props = _SCHEMA["properties"]
    assert _D5_KEYS <= set(props)
    assert _D5_TESTING <= set(props["testing"]["properties"])
    assert set(props["services"]["items"]["properties"]) == {
        "name", "command", "port", "ready_path", "depends_on", "primary"}
    assert _SCHEMA["additionalProperties"] is True and props["testing"]["additionalProperties"] is True


def test_schema_version_is_distinct_from_profile_version():
    assert "version" not in _SCHEMA["properties"]
    assert "THIS schema" in _SCHEMA["properties"]["schema_version"]["description"]


def test_ux_shape_and_ui_host_are_optional_plain_strings():
    props = _SCHEMA["properties"]
    for key in ("ux_shape", "ui_host"):
        assert props[key]["type"] == "string" and "enum" not in props[key]
        assert key not in _SCHEMA["required"]
    ok = {k for k, v in _mutations().items() if _json_schema_ok(v)}
    assert "ux-ui-strings" in ok and {"ux-shape-int", "ui-host-dict"}.isdisjoint(ok)
