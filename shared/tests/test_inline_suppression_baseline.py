"""The baseline DOCUMENT: fail-closed validation + the boundary probe.

Every block this gate can raise is proven to FIRE here against synthetic
fixtures, so the live repo guard can stay a thin "does THIS repo comply?"
assertion. A gate whose blocks are never proven to fire is indistinguishable
from one that always passes — the defect the accepted-risk register's first
draft shipped, and the reason that register grew the same tests/guards split
this file mirrors.

Split from ``test_inline_suppressions.py`` when it crossed the 300-line cap,
along the same seam the source trio uses. As there, every
fixture builds its suppression text through an f-string placeholder so this
file's own source is never counted as a suppression site.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import inline_suppressions as isup  # noqa: E402

_RULE = "python.lang.security.audit.non-literal-import.non-literal-import"
_OTHER = "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true"
_REF = "iterate-2026-08-05-inline-suppression-ratchet"
_STATEMENT = "First-party module identifiers only, never untrusted input."


def _baseline(rules: dict[str, int]) -> dict:
    return {
        "schema": isup.SCHEMA_VERSION,
        "rules": [
            {
                "rule": rule,
                "max_sites": count,
                "rationale_ref": _REF,
                "statement": _STATEMENT,
            }
            for rule, count in rules.items()
        ],
    }


def _repo(tmp_path: Path, *, sources: dict[str, str], baseline=...) -> Path:
    for rel, text in sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if baseline is not ...:
        (tmp_path / isup.BASELINE_NAME).write_text(
            baseline if isinstance(baseline, str) else json.dumps(baseline),
            encoding="utf-8",
        )
    return tmp_path


# --------------------------------------------------------------------------
# Fail-closed baseline validation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body", [
    "{not json",
    "[]",
    '{"schema": 99, "rules": []}',
    '{"schema": 1}',
    '{"schema": 1, "rules": {}}',
])
def test_a_corrupt_baseline_fails_closed(tmp_path, body):
    """A corrupt baseline must never read as 'nothing accepted' — that is the
    exact state a truncating edit would otherwise produce."""
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=body)
    with pytest.raises(isup.BaselineError):
        isup.reconcile(root)


def test_a_duplicate_json_key_is_refused(tmp_path):
    """`json.loads` keeps the LAST of two identical keys, so a hand-edited
    baseline could carry a shadowed `max_sites` no reader reports."""
    body = (
        '{"schema": 1, "rules": [{"rule": "r", "max_sites": 1, '
        '"max_sites": 99, "rationale_ref": "#1", '
        f'"statement": "{_STATEMENT}"}}]}}'
    )
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=body)
    with pytest.raises(isup.BaselineError):
        isup.reconcile(root)


@pytest.mark.parametrize("mutation", [
    {"rationale_ref": "TODO"},
    {"rationale_ref": "we talked about it"},
    {"statement": "short"},
    {"max_sites": -1},
    {"max_sites": "3"},
    {"max_sites": True},          # bool is an int subclass — must not pass as 1
    {"rule": ""},
    {"surprise": "extra key"},
])
def test_a_half_filled_entry_is_an_error_not_a_skipped_row(tmp_path, mutation):
    """A skipped row reads as 'nothing accepted' while the suppression stays
    live — the register refuses that, and so does this."""
    doc = _baseline({_RULE: 1})
    doc["rules"][0].update(mutation)
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=doc)
    with pytest.raises(isup.BaselineError):
        isup.reconcile(root)


def test_an_unknown_top_level_key_is_refused(tmp_path):
    """Symmetric with the per-entry check. Without it a governance-looking key
    such as `expires` would sit in the file reading as though it constrained
    something, while nothing ever read it (Stage-2 code review)."""
    doc = _baseline({_RULE: 1})
    doc["expires"] = "2027-01-01"
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=doc)
    with pytest.raises(isup.BaselineError):
        isup.reconcile(root)


def test_the_readme_key_is_allowed_because_json_has_no_comments(tmp_path):
    """`_readme` is load-bearing: the baseline is hand-edited and JSON cannot
    carry comments, so the operating instructions live inside the document."""
    doc = _baseline({_RULE: 1})
    doc["_readme"] = ["how to edit this file"]
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=doc,
    )
    assert isup.reconcile(root)["ok"]


def test_a_max_sites_of_zero_is_refused(tmp_path):
    """Such an entry is DEAD the moment it is written and blocks forever with
    "delete this entry" — a schema accepting a value its own rule makes
    permanently unsatisfiable (Stage-3 doubt review, D7). Absence already means
    "may never be suppressed", and says it without a record to maintain."""
    doc = _baseline({_RULE: 0})
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=doc)
    with pytest.raises(isup.BaselineError, match="dead on arrival"):
        isup.reconcile(root)


def test_a_duplicate_rule_entry_is_refused(tmp_path):
    doc = _baseline({_RULE: 1})
    doc["rules"].append(dict(doc["rules"][0]))
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=doc)
    with pytest.raises(isup.BaselineError):
        isup.reconcile(root)


def test_rationale_ref_validation_is_the_registers_own_rule():
    """Imported, not copied — the two must not be able to drift apart
    (external review, DeepSeek #5). The register's `verifiers/ci_supplychain`
    duplicate exists for a self-containment reason that does not apply between
    two leaves in the same directory."""
    from accepted_risks import DECISION_REF_RE  # noqa: PLC0415

    assert isup.DECISION_REF_RE is DECISION_REF_RE
    assert DECISION_REF_RE.search(_REF)
    assert not DECISION_REF_RE.search("TODO")


# --------------------------------------------------------------------------
# Boundary probe — the baseline is hand-written JSON crossing a file boundary
# --------------------------------------------------------------------------

def test_baseline_round_trips_through_the_file_boundary(tmp_path):
    """Round-trip probe (`touches_io_boundary`): what `load_baseline` returns
    must survive being written back out and re-read, or a regenerated baseline
    would silently differ from the one an operator hand-authored."""
    doc = _baseline({_RULE: 9, _OTHER: 1})
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline=doc)

    first = isup.load_baseline(root)
    (root / isup.BASELINE_NAME).write_text(
        json.dumps(isup.dump_baseline(first), indent=2), encoding="utf-8")
    assert isup.load_baseline(root) == first


def test_a_seeded_baseline_is_accepted_by_the_gate_that_reads_it(tmp_path):
    """The seed path must emit a document this same reader accepts — otherwise
    the generator produces a baseline the gate then rejects."""
    root = _repo(tmp_path, sources={
        "a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_OTHER}\n"})
    seeded = isup.seed_baseline(root, rationale_ref=_REF, statement=_STATEMENT)
    (root / isup.BASELINE_NAME).write_text(
        json.dumps(seeded, indent=2), encoding="utf-8")
    assert isup.reconcile(root)["ok"]


def test_a_seeded_baseline_pins_the_exact_count_with_no_headroom(tmp_path):
    """A ratchet whose baseline starts loose permits the first regression for
    free."""
    root = _repo(tmp_path, sources={
        "a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"})
    seeded = isup.seed_baseline(root, rationale_ref=_REF, statement=_STATEMENT)
    assert seeded["rules"][0]["max_sites"] == 2


