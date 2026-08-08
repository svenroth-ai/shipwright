"""AC1 / AC1b — the four mandated `decision_log.md` readers must be index-first.

Permanent regression guard: without this, the "read completely" instruction
can quietly come back after this run ends. Opus plan-review finding 8 (see
the iterate spec for iterate-2026-08-08-index-readers-adr-lock) noted AC5
already had a permanent guard for the ADR-collision defect while AC1 (the
primary defect — four skills promising a read no single `Read` call can
deliver, since `decision_log.md` is 4,379 lines against a 2,000-line cap) had
none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MANDATED_READERS = [
    "plugins/shipwright-iterate/skills/iterate/references/context-loading.md",
    "plugins/shipwright-build/skills/build/references/first-actions.md",
    "plugins/shipwright-plan/skills/plan/references/first-actions.md",
    "plugins/shipwright-project/skills/project/references/step-1-interview.md",
]

_COMPLETE_READ_PHRASE = r"(?:read\s+(?:the\s+)?(?:complet\w*|entire|whole|full)|(?:complet\w*|entire|whole|full)\s+(?:file\s+)?read\w*)"
#: The other historical phrasing of the same promise — "read ALL the
#: decisions in decision_log.md" — carries no complete/entire/whole/full
#: token at all, so it needs its own alternation rather than folding into
#: _COMPLETE_READ_PHRASE (an external-code-review finding on this run).
_ALL_DECISIONS_PHRASE = r"\ball\b.{0,40}\bdecisions?\b"
_PROMISES_COMPLETE_READ = re.compile(
    rf"decision_log\.md.{{0,80}}\b{_COMPLETE_READ_PHRASE}\b"
    rf"|\b{_COMPLETE_READ_PHRASE}\b.{{0,80}}decision_log\.md"
    rf"|decision_log\.md.{{0,80}}{_ALL_DECISIONS_PHRASE}"
    rf"|{_ALL_DECISIONS_PHRASE}.{{0,80}}decision_log\.md",
    re.IGNORECASE | re.DOTALL,
)


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_reader_names_the_index_first(relpath):
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert "decision_log_index.md" in text, (
        f"{relpath} does not reference decision_log_index.md — "
        "AC1 requires index-first reading of decision_log.md"
    )


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_reader_no_longer_promises_a_complete_read(relpath):
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    match = _PROMISES_COMPLETE_READ.search(text)
    assert match is None, (
        f"{relpath} still instructs reading decision_log.md completely "
        f"({match.group(0)!r}) — a single Read call caps at 2000 lines, "
        "so this guarantee is already broken"
    )


def test_the_all_decisions_phrasing_alone_is_still_caught():
    """Mutation guard for the external-code-review finding on this run:
    the historical violation had no complete/entire/whole/full token at
    all, so a regression here would slip past _COMPLETE_READ_PHRASE
    alone."""
    text = "Read decision_log.md to see ALL architectural decisions."
    assert _PROMISES_COMPLETE_READ.search(text) is not None


_FALLBACK_NEAR_DECISION_LOG = re.compile(
    r"decision_log(?:_index)?\.md.{0,400}?\b(grep|offset)\b",
    re.IGNORECASE | re.DOTALL,
)


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_reader_names_a_fallback_for_no_index_match(relpath):
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert _FALLBACK_NEAR_DECISION_LOG.search(text), (
        f"{relpath} names no fallback (grep/offset-read) near a "
        "decision_log(.md|_index.md) mention for 'the index has no "
        "matching entry' — a bare 'grep' or 'offset' elsewhere in the file "
        "does not count"
    )
