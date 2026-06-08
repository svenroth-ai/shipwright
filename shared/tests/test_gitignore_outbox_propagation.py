"""Outbox-path propagation guard (campaign 2026-06-08-triage-outbox-delivery / D3).

The per-tree background-triage buffer ``.shipwright/triage.outbox.jsonl`` is
ALREADY ignored by the canonical ``/.shipwright/*`` whitelist wildcard — there
is no current tracking gap. D3 makes that coverage EXPLICIT and robust:

* the SSoT template carries a redundant-but-explicit ``/.shipwright/triage.outbox.jsonl``
  ignore line (so a future ``!``-negation can't silently start tracking it), and
* the template carries NO ``!``-re-include for the outbox (the guard).

These tests prove the propagation empirically with real ``git check-ignore`` on a
fresh ``gitignore_canon``-scaffolded repo, and contrast it against the tracked
``triage.jsonl`` (which the canon block DELIBERATELY re-includes) — the
round-trip that pins the whitelist semantics.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# conftest.py adds shared/scripts to sys.path; lib is a package under it.
from lib.gitignore_canon import merge_canonical_block, read_canonical_rules

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"

_OUTBOX_RULE = "/.shipwright/triage.outbox.jsonl"
_OUTBOX_REL = ".shipwright/triage.outbox.jsonl"
_TRIAGE_REL = ".shipwright/triage.jsonl"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _require_git() -> None:
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                "git binary not found in CI — the outbox check-ignore probes require it"
            )
        pytest.skip("git binary not available")


def _check_ignored(repo: Path, rel: str) -> bool:
    """True if *rel* is ignored by the repo's .gitignore (check-ignore exit 0)."""
    proc = _git("check-ignore", rel, cwd=repo)
    assert proc.returncode in (0, 1), (
        f"check-ignore error rc={proc.returncode} stderr={proc.stderr!r}"
    )
    return proc.returncode == 0


# --------------------------------------------------------------------------
# Template-level guards (no git needed)
# --------------------------------------------------------------------------

def test_template_carries_explicit_outbox_ignore_rule() -> None:
    """The SSoT template names the outbox explicitly (not only via the wildcard)."""
    rules = read_canonical_rules(_TEMPLATE)
    assert _OUTBOX_RULE in rules, (
        "the canonical gitignore template must carry an explicit "
        f"{_OUTBOX_RULE!r} ignore line so the outbox coverage survives a future "
        "negation edit; found rules: " + repr(rules)
    )


def test_template_has_no_outbox_reinclude_negation() -> None:
    """Guard: NO ``!``-re-include for the outbox anywhere in the managed block.

    A future edit that adds ``!/.shipwright/triage.outbox.jsonl`` would start
    silently TRACKING the per-tree buffer (drift on every idle-main append). The
    outbox is gitignored-by-contract; this asserts the SSoT never re-includes it.
    """
    rules = read_canonical_rules(_TEMPLATE)
    negation = f"!{_OUTBOX_RULE}"
    assert negation not in rules, (
        f"the canonical gitignore template must NOT re-include the outbox: "
        f"{negation!r} would start tracking the per-tree background buffer. "
        "The outbox is gitignored-by-contract (campaign 2026-06-08)."
    )
    # Defensive: no negation for ANY outbox-suffixed path, even an oddly-spelled one.
    for rule in rules:
        assert not (rule.startswith("!") and "triage.outbox.jsonl" in rule), (
            f"unexpected outbox re-include negation in template: {rule!r}"
        )


def test_outbox_rule_ordered_after_broad_wildcard() -> None:
    """The explicit outbox ignore must sit after the broad ``/.shipwright/*``
    (a re-ignore inside the whitelist) — ordering keeps whitelist semantics valid.
    """
    rules = read_canonical_rules(_TEMPLATE)
    assert rules.index("/.shipwright/*") < rules.index(_OUTBOX_RULE)


# --------------------------------------------------------------------------
# Empirical — git check-ignore round-trips (the real proof)
# --------------------------------------------------------------------------

def test_fresh_repo_ignores_outbox_via_canon(tmp_path: Path) -> None:
    """A repo scaffolded by ``gitignore_canon`` ignores the outbox (real git)."""
    _require_git()
    _git("init", cwd=tmp_path)
    merge_canonical_block(tmp_path, template_path=_TEMPLATE)

    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    (tmp_path / _OUTBOX_REL).write_text(
        '{"event":"append","id":"trg-x","status":"triage"}\n', encoding="utf-8"
    )
    assert _check_ignored(tmp_path, _OUTBOX_REL), (
        "the per-tree outbox buffer must be ignored in a fresh canon-scaffolded repo"
    )


def test_round_trip_outbox_ignored_but_tracked_triage_not(tmp_path: Path) -> None:
    """Round-trip contrast: outbox IGNORED, tracked triage.jsonl NOT ignored.

    The canon whitelist re-includes ``triage.jsonl`` (the tracked SSoT backlog)
    via ``!/.shipwright/triage.jsonl`` but leaves the outbox buffer ignored. This
    pins both halves of the contract in one real-git probe.
    """
    _require_git()
    _git("init", cwd=tmp_path)
    merge_canonical_block(tmp_path, template_path=_TEMPLATE)

    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    (tmp_path / _OUTBOX_REL).write_text("{}\n", encoding="utf-8")
    (tmp_path / _TRIAGE_REL).write_text("{}\n", encoding="utf-8")

    assert _check_ignored(tmp_path, _OUTBOX_REL), "outbox buffer should be ignored"
    assert not _check_ignored(tmp_path, _TRIAGE_REL), (
        "the tracked triage.jsonl SSoT backlog must NOT be ignored "
        "(it is re-included by the canon whitelist)"
    )


def test_round_trip_with_user_content_before_managed_block(tmp_path: Path) -> None:
    """Calibration probe (external review Gemini#4 / OpenAI#5): the outbox stays
    ignored when the user already has a ``.gitignore`` with unrelated rules — the
    managed block is APPENDED below them, the line-level merge never touches them.
    """
    _require_git()
    _git("init", cwd=tmp_path)
    user = "# my project\nnode_modules/\n.env.local\ndist/\n"
    (tmp_path / ".gitignore").write_text(user, encoding="utf-8")

    merge_canonical_block(tmp_path, template_path=_TEMPLATE)

    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith(user), "user rules must be preserved verbatim, in place"
    assert _OUTBOX_RULE in text

    (tmp_path / ".shipwright").mkdir(parents=True, exist_ok=True)
    (tmp_path / _OUTBOX_REL).write_text("{}\n", encoding="utf-8")
    assert _check_ignored(tmp_path, _OUTBOX_REL), (
        "outbox must stay ignored even with user content before the managed block"
    )
    # The user's own unrelated rules still work too.
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("//", encoding="utf-8")
    assert _check_ignored(tmp_path, "node_modules/x.js")
