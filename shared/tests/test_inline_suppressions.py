"""The ratchet rule, with negative controls.

Every block this gate can raise is proven to FIRE here against synthetic
fixtures, so the live repo guard can stay a thin "does THIS repo comply?"
assertion. A gate whose blocks are never proven to fire is indistinguishable
from one that always passes — the defect the accepted-risk register's first
draft shipped, and the reason that register grew the same tests/guards split
this file mirrors.

Baseline-document validation is covered by
``test_inline_suppression_baseline.py`` and discovery by
``test_inline_suppression_scan.py`` — the three test files mirror the three
source leaves. As there, every fixture builds its suppression text through an
f-string placeholder so this file's own source is never counted as a
suppression site.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
# The ratchet rule
# --------------------------------------------------------------------------

def test_growth_beyond_the_baseline_blocks(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"},
        baseline=_baseline({_RULE: 1}),
    )
    result = isup.reconcile(root)
    assert not result["ok"]
    assert [r["rule"] for r in result["ratchets"]] == [_RULE]
    assert result["ratchets"][0]["measured"] == 2


def test_a_rule_with_no_baseline_entry_blocks_as_unrecorded(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_OTHER}\n"},
        baseline=_baseline({_RULE: 1}),
    )
    result = isup.reconcile(root)
    assert not result["ok"]
    assert [r["rule"] for r in result["unrecorded"]] == [_OTHER]


def test_shrinking_is_advisory_and_never_blocks(tmp_path):
    """Blocking on a REDUCTION would penalise the outcome this gate exists to
    encourage, so `shrunk` must never reach `ok`."""
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline({_RULE: 3}),
    )
    result = isup.reconcile(root)
    assert result["ok"]
    assert [r["rule"] for r in result["shrunk"]] == [_RULE]


def test_a_rule_suppressed_nowhere_is_a_dead_entry_and_blocks(tmp_path):
    """The one place a reduction DOES block, and the contract says so: an
    entry whose rule has no sites left is a dormant licence to silence it
    again, up to `max_sites`, with no fresh decision. Distinct from `shrunk`
    (advisory) precisely so `reconcile`'s promise that shrink never affects
    `ok` stays literally true."""
    root = _repo(
        tmp_path,
        sources={"a.py": "x = 1\n"},
        baseline=_baseline({_RULE: 2}),
    )
    result = isup.reconcile(root)
    assert not result["ok"]
    assert result["shrunk"] == [], "a dead entry is not a mere shrink"
    assert result["dead"] == [
        {"rule": _RULE, "baseline_max": 2, "measured": 0}]
    assert "delete this entry" in "\n".join(isup.format_report(result))


def test_an_exactly_matching_count_passes_cleanly(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline({_RULE: 1}),
    )
    result = isup.reconcile(root)
    assert result["ok"] and not result["shrunk"]


def test_an_unreadable_file_blocks_because_the_count_is_partial(
    tmp_path, monkeypatch
):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline({_RULE: 1}),
    )
    real_read = Path.read_bytes

    def boom(self, *args, **kwargs):
        if self.name == "a.py":
            raise PermissionError("denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", boom)
    result = isup.reconcile(root)
    assert not result["ok"] and result["unreadable"] == ["a.py"]


# --------------------------------------------------------------------------
# Absent is not exempt
# --------------------------------------------------------------------------

def test_an_absent_baseline_does_not_silence_the_gate(tmp_path):
    """The register learned this the hard way: returning success on a MISSING
    file meant deleting it silenced the gate while every suppression stayed
    live (iterate-2026-07-31-accepted-risk-gate-holes)."""
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    result = isup.reconcile(root)
    assert not result["baseline_present"]
    assert not result["ok"]
    assert [r["rule"] for r in result["unrecorded"]] == [_RULE]


def test_an_absent_baseline_with_no_suppressions_passes(tmp_path):
    """A fresh or legacy repo suppresses nothing, so it passes — by
    comparison, not by exemption."""
    assert isup.reconcile(_repo(tmp_path, sources={"a.py": "x = 1\n"}))["ok"]


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def test_the_block_report_names_the_rule_the_site_and_a_remedy(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"},
        baseline=_baseline({_RULE: 1}),
    )
    report = "\n".join(isup.format_report(isup.reconcile(root)))
    assert _RULE in report
    assert "a.py:1" in report
    assert isup.BASELINE_NAME in report
