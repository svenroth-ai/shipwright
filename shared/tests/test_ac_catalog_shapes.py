"""The requirement catalog in every shape the product writes, and the cases where the decision is skipped (never asked, refused or held)."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC as _BASE_SPEC
from shared.tests.ac_test_helpers import PROMISE as _PROMISE
from shared.tests.ac_test_helpers import cat_of, commit as _commit, git as _git, repo as _repo
from lib import ac_catalog as cat
from lib import ac_decision as ad
from lib import ac_record as ar
from tools import ac_decision as cli
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-round3"


_GREENFIELD = """## Functional Requirements

| ID | Area | Name | Priority | Requirement |
|----|------|------|----------|-------------|
| FR-01.01 | Auth | User registration | Must | The system SHALL allow users to register |
| FR-01.02 | Auth | User login | Must | The system SHALL authenticate users |

### Acceptance Criteria

**FR-01.01: User Registration**
- [ ] User can register with valid email and password
- [ ] Duplicate email returns clear error message

**FR-01.02: User Login**
- [ ] Valid credentials return session token
"""
_ADOPTED = """### FR-01.01 — Org-chart validation

- (E) Given a document declaring version two, when it is validated, then it is accepted.
  It continues on a second line.
- (E) Given a lead whose manages links form a cycle, when validated, then it is rejected.

### FR-01.02 Task detail
- (E) **(iterate-2026-05-14 lead-foundation)** Given a viewer, when opened, then three panes show.
"""
_TABLE_ONLY = "| FR-01.01 | The system SHALL initialize a project | Must |\n| FR-01.02 | The system SHALL connect to a database | Must |\n\n- [ ] All tables use a prefix\n"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_parser_reads_this_repos_shape_the_greenfield_shape_adopted_repos_and_table_only_specs():
    acs, frs = cat.parse_catalog(_BASE_SPEC)
    assert set(acs) == {"FR-01.03.AC05", "FR-01.04.AC01"} and frs == {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}
    acs, frs = cat.parse_catalog(_GREENFIELD)   # **FR-xx.yy: title** headings, "- [ ]" criteria numbered by position, table rows
    assert set(acs) == {"FR-01.01.AC01", "FR-01.01.AC02", "FR-01.02.AC01"} and frs["FR-01.01"] == "User Registration" and frs["FR-01.02"] == "User Login"
    assert "register with valid email" in acs["FR-01.01.AC01"]
    acs, frs = cat.parse_catalog(_ADOPTED)      # unmarked "- (E)" criteria, em-dash and plain-space titles
    assert set(acs) == {"FR-01.01.AC01", "FR-01.01.AC02", "FR-01.02.AC01"} and frs == {"FR-01.01": "Org-chart validation", "FR-01.02": "Task detail"}
    assert "second line" in acs["FR-01.01.AC01"] and cat.ac_body(acs["FR-01.02.AC01"]).startswith("given a viewer")
    acs, frs = cat.parse_catalog(_TABLE_ONLY)   # FRs from the table, criteria not addressable without a heading
    assert acs == {} and set(frs) == {"FR-01.01", "FR-01.02"}
    assert cat.parse_catalog("") == ({}, {}) and cat.parse_catalog("## Notes\n\n- a bullet\n") == ({}, {})


@pytest.mark.covers("FR-01.11/AC49")
def test_a_greenfield_catalog_can_be_changed_and_restored_by_position_id():
    catalog = cat_of(_GREENFIELD)
    old = "User can register with valid email and password"
    r = ad.decide([{"kind": "change", "ac": "FR-01.01.AC01", "old_text": old, "new_text": "A visitor can sign up with an email and a password"}], catalog)
    assert r["status"] == "ask" and r["questions"][0]["row"] == 1
    assert ad.decide([{"kind": "restore", "restores_ac": "FR-01.02.AC01"}], catalog)["status"] == "ok"


@pytest.mark.covers("FR-01.11/AC49")
def test_a_catalog_with_text_but_no_readable_fr_is_skipped_never_asked_or_refused(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, "# Spec\n\nRequirement one is described in prose only.\n")
    loaded = cat.load_catalog(root, "HEAD")
    assert loaded["unparsed"] and loaded["frs"] == set()
    skipped = ad.decide([{"kind": "add", "new_text": _PROMISE}], loaded)
    assert skipped["status"] == "skipped" and "nothing is asked, refused or held" in skipped["note"]
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    assert cli.main(["--project-root", str(root), "--from-json", str(spec), "--base-ref", "HEAD"]) == 0
    capsys.readouterr()
    assert cli.main(["verify", "--project-root", str(root), "--run-id", "r", "--base-ref", "HEAD"]) == 0
    assert "skipped" in json.loads(capsys.readouterr().out)["note"]
    head = _commit(root, {"shared/scripts/a.py": "x = 1\n"})
    base = _git(root, "rev-parse", "HEAD~1")
    assert ar.verify(root, _RUN, base, head) == []
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).severity == "skipped"
    empty = cat_of("")
    assert not cat.load_catalog(_repo(tmp_path / "e", ""), "HEAD")["unparsed"] and empty["acs"] == {}


@pytest.mark.covers("FR-01.11/AC49")
def test_no_spec_at_all_or_any_spec_with_text_but_no_readable_fr_is_skipped(tmp_path, capsys):
    root = _repo(tmp_path / "none")
    _git(root, "rm", "-q", "-r", ".shipwright")
    _git(root, "commit", "-qm", "no spec")
    nothing = cat.load_catalog(root, "HEAD")
    assert nothing["unparsed"] and nothing["frs"] == set()
    assert ad.decide([{"kind": "add", "new_text": _PROMISE}], nothing)["status"] == "skipped"
    mixed = _repo(tmp_path / "mixed")                                   # one readable spec and one that is prose only
    _commit(mixed, {".shipwright/planning/02-notes/spec.md": "# Notes\n\nOnly prose, no requirement headings.\n"})
    loaded = cat.load_catalog(mixed, "HEAD")
    assert loaded["unparsed"] and loaded["frs"] == {"FR-01.03", "FR-01.04"}   # the readable FRs are still known, but the decision is skipped
    assert ad.decide([{"kind": "add", "new_text": _PROMISE}], loaded)["status"] == "skipped"
    spec = tmp_path / "s.json"
    spec.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    assert cli.main(["--project-root", str(mixed), "--from-json", str(spec), "--base-ref", "HEAD"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "skipped"
