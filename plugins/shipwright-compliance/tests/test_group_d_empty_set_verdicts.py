"""What Group D reports when the requirement set is EMPTY (false verdict FV-2).

Split out of ``test_audit_groups_a_d.py`` rather than appended to it: that module
sits at its anti-ratchet ceiling, and these belong together anyway. They are all
one question — *what may a check claim about a set it never examined?* — asked of
the two sites the requirements-catalog campaign (S6) moved.

**Every assertion here is paired with its control.** The failure mode of "stop
reading green on nothing" is trading a false green for a false red: a project
that has not written requirements yet is a legitimate state, not a defect, and
reddening it would break the most common first-run path. So each flip below is
followed by a test proving the check did not simply become unconditional.

The sibling half of FV-2 — the D-layer manifest site — lives in
``test_group_d_traceability.py`` next to the rest of that check's coverage.

@FR-01.10
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_d  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402


def _events(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8",
    )


def _d2(tmp_path: Path):
    # Config inlined as None rather than behind a `_default_config()` helper:
    # the sibling module has a helper of that name returning a REAL config
    # dict, and shadowing it here would suggest these tests exercise a
    # configured path when they do not.
    findings = group_d.run(tmp_path, None, None)
    return next(f for f in findings if f.check_id == "D2")


def test_d2_fails_when_no_spec_but_events_still_reference_frs(tmp_path):
    """FLIPPED by S6 (was FROZEN-BUG FV-2). This used to assert ``skip``.

    With zero spec FRs, an event naming FR-99.99 is the maximally-red state --
    the reference cannot possibly resolve -- yet ``if not spec_frs: skip`` sat
    above the staleness loop and made the FAIL branch unreachable. Structurally
    the same defect as FV-1: a falsiness guard placed early enough that the
    check it guards can never run.
    """
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "fail"
    assert "FR-99.99" in d2.detail


def test_d2_still_skips_when_no_spec_and_no_fr_references(tmp_path):
    """Control: 'nothing to compare' must stay a skip.

    Without this, D2 could have been made unconditionally red on an empty spec
    and the assertion above would still pass -- trading a false green for a
    false red on every project that has not written requirements yet.
    """
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00"},
    ])
    d2 = _d2(tmp_path)
    assert d2.status == "skip"
    # The skip now NAMES which empty state it is (S6 FIX 2). It used to read
    # "no FR table rows in any spec.md" for every reason the set was empty.
    assert "no spec.md" in d2.detail


def test_zero_requirements_plus_a_tagged_test_yields_a_nonempty_orphan_list(tmp_path):
    """Closes the question S6 shipped OPEN, by probe rather than by argument.

    S6 flipped D-layer but deliberately left D-orphan alone, on the argument
    that its pass sentence over an empty requirement set is TRUE rather than
    vacuous: had any test carried an ``@FR`` tag, every one would be absent-FR
    and would land in ``orphans``, so an empty ``orphans`` means no tagged tests
    exist -- a claim about a universe that WAS examined.

    That argument had one falsifier, recorded at the time and not assumed away:
    if the COLLECTOR short-circuits before classifying tags when it finds no
    requirements, ``orphans`` is uninformative and the argument collapses. It
    does not short-circuit -- the tag walk is unconditional and every hit falls
    to the ``fr_absent`` / ``confirmed_orphan`` branch. This runs the collector
    for real and pins that, so the next reader inherits a check instead of a
    paragraph they have to re-derive.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_tagged.py").write_text(
        'import pytest\n'
        '@pytest.mark.covers("FR-01.01")\n'
        'def test_x():\n'
        '    assert True\n',
        encoding="utf-8")

    manifest = build_manifest(tmp_path, spec_files=[], test_roots=[tests_dir])

    assert not manifest.get("requirements"), "precondition: zero requirements"
    orphans = manifest.get("orphans") or []
    assert orphans, (
        "the collector short-circuited on an empty requirement set — D-orphan's "
        "empty-set pass IS vacuous after all, and FV-2 has a third site")
    assert any(o.get("tagged_fr") == "FR-01.01" for o in orphans)
    assert {o.get("category") for o in orphans} == {"confirmed_orphan"}


#: Every operator-facing document that describes D2's verdict, with the phrase
#: each must carry while D2 can fail, and whether the document is PERMANENT.
#: Covering ONE of them is what let the first correction ship 2/3 done: the guide
#: and the changelog drop were fixed, the ADR kept asserting the retracted claim
#: in Decision and Rationale, and the pin — which read only the guide — stayed
#: green throughout.
#:
#: ``permanent=False`` marks a deliberately EPHEMERAL artifact. An unreleased
#: changelog drop is consumed at release: ``aggregate_changelog`` folds it into
#: CHANGELOG.md and unlinks it. A permanent test that reads one by name is a
#: time bomb aimed at whichever release PR runs next — and it would land as a
#: FileNotFoundError, a run-time error rather than an assertion with a message,
#: inside a plugin unrelated to the release. Every other test in this repo that
#: touches ``CHANGELOG-unreleased.d`` builds its drops under ``tmp_path``; this
#: is the only one reading a committed one, so it tolerates the absence instead
#: of pinning the release open. The two permanent legs keep the pin's value.
_REPO_ROOT = PLUGIN_ROOT.parent.parent
_BLOCK_CLAIM_DOCS = (
    (_REPO_ROOT / "docs" / "migrations" / "requirements-catalog-merge.md",
     "CAN newly fail your audit", True),
    (_REPO_ROOT / "CHANGELOG-unreleased.d" / "Fixed"
     / "iterate-2026-07-19-requirements-merge-catalog_001.md",
     "can newly fail an audit", False),
    (_REPO_ROOT / ".shipwright" / "planning" / "adr"
     / "109-one-requirements-catalog.md",
     "D2's flip is a new block", True),
)

#: The retracted sentence, as a LITERAL. Scope is deliberately narrow and worth
#: stating plainly: this is a regression guard for one specific sentence that was
#: actually asserted and retracted, not a semantic check. A reworded reassertion
#: ("the exit code does not change") would slip past this negative half. The
#: positive half — the required phrase per document — is what covers wholesale
#: deletion or rewriting, and that is where the real protection lives.
_RETRACTED = "exit code is unchanged"


def _asserted_text(markdown: str) -> str:
    """The document minus its block quotations.

    A correction note has to QUOTE the sentence it retracts, or a reader cannot
    tell what was corrected. Quoting is not asserting, so blockquote lines are
    excluded — and only those. Everything a reader takes as the document's own
    voice stays in scope, including the sections an ADR exists to be read for.
    """
    return "\n".join(ln for ln in markdown.splitlines()
                     if not ln.lstrip().startswith(">"))


def test_every_operator_facing_document_matches_d2s_actual_verdict(tmp_path):
    """Ties the shipped DOCUMENTS to the shipped BEHAVIOUR — all three of them.

    S6 originally claimed, in the ADR, the changelog drop and the migration
    guide, that neither check was "a new block" and that "the audit exit code is
    unchanged" — while this same run's internal notes said plainly that zero
    requirements plus an FR-referencing event now FAILs. The internal record was
    right and the three operator-facing documents were wrong: the claim was
    correct for D-layer and was carried across to D2 without re-reading the
    branch.

    The first correction fixed two of the three and added a note to the ADR's
    Consequences while its Decision and Rationale went on asserting the retracted
    claim. This test read only the guide, so it passed. **That is the failure
    being pinned here**: a document-vs-code check that covers a subset of the
    documents proves nothing about the ones it skips.

    An operator upgrading reads these, not the notes. So each is checked against
    the behaviour rather than trusted, in both directions.

    The changelog leg is absence-tolerant; see ``_BLOCK_CLAIM_DOCS``. A drop is
    consumed at release, and a permanent test must not redden the release PR that
    consumes it.
    """
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    d2_can_fail = _d2(tmp_path).status == "fail"

    checked = 0
    for path, phrase, permanent in _BLOCK_CLAIM_DOCS:
        if not path.exists():
            assert not permanent, (
                f"{path.name} is a PERMANENT record and it is missing — the "
                f"document this pin exists to protect has been deleted, not "
                f"consumed")
            continue  # ephemeral drop, already folded into CHANGELOG.md
        checked += 1
        text = path.read_text(encoding="utf-8")
        if d2_can_fail:
            assert phrase in text, (
                f"D2 can fail an audit but {path.name} no longer says so — an "
                f"adopter reading it would upgrade into a red gate with no "
                f"notice")
            assert _RETRACTED not in _asserted_text(text), (
                f"{path.name} still ASSERTS the retracted claim somewhere "
                f"outside a block quotation of it — appending a correction is "
                f"not correcting")
        else:
            assert phrase not in text, (
                f"D2 no longer fails here, so {path.name}'s warning is now the "
                f"false statement — update the document with the behaviour")

    # Absence-tolerance must not become tolerance of checking nothing: the two
    # permanent legs are the reason this pin exists, and a skip-everything state
    # would pass silently — the exact failure mode of the one-document version.
    assert checked >= 2, (
        f"only {checked} document(s) were actually read; the permanent records "
        f"must always be checked")


def test_d2_still_skips_when_there_is_no_event_log_at_all(tmp_path):
    """Second control: the guard S6 moved must not have displaced this one.

    'No event log' and 'an event log with nothing to compare against' are
    different situations and were reported differently before S6. Moving the
    spec_frs guard downwards must leave the events guard where it was, above
    the loop -- there is nothing to iterate.
    """
    d2 = _d2(tmp_path)
    assert d2.status == "skip"
    assert d2.detail == "shipwright_events.jsonl not present"
