"""Regression guard: no skill/agent doc regresses to a bare `/tmp/` path
literal — the class of bug scripts.lib.review_scratch exists to close, since
bash and native Python resolve it to different files on Windows. See
iterate-2026-09-03-review-scratch-path."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
# `/tmp/...` (three literal dots) is the generic illustrative shorthand this
# fix's own remediation prose uses ("never a bare /tmp/... literal") — that
# is documentation ABOUT the bug, not an instance of it, so it is excluded
# by name rather than by code-fence position (simpler and doesn't need the
# fenced-vs-inline distinction the guard would otherwise have to draw).
# The negative lookbehind requires `/tmp/` to be the ROOT of an absolute
# path (preceded by nothing, or by whitespace/quote/backtick/paren) rather
# than a substring of a longer, unrelated path — a bare `/tmp/...` literal
# is always written as an absolute root path, never as `.../tmp/...` under
# something else. Without it this guard's own glob (217 files across every
# plugin's skills+agents trees, not just the docs this fix touched) would
# false-positive on legitimate unrelated paths like `/var/tmp/` (a doubt-
# reviewer finding, iterate-2026-09-03-review-scratch-path).
_BARE_TMP_RE = re.compile(r"(?<![\w/])/tmp/(?!\.\.\.)")

# Scoped to the docs an LLM agent actually executes bash/python from. Deploy
# guides and standalone CLI examples (CONTRIBUTING.md, docs/*) are out of
# scope on purpose — a human running one command in their own terminal has
# no bash-write/python-read boundary to diverge across.
_SCANNED_GLOBS = (
    "plugins/*/skills/**/*.md",
    "plugins/*/agents/**/*.md",
    "shared/prompts/**/*.md",
)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _SCANNED_GLOBS:
        files.extend(_REPO_ROOT.glob(pattern))
    return files


def test_no_bare_tmp_path_literal_in_review_pipeline_docs():
    offenders = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BARE_TMP_RE.search(line):
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "bare /tmp/... path literal(s) found in a skill/agent doc — bash "
        "and native Python resolve that to different files on Windows. Use "
        "shared/scripts/tools/review_scratch.py resolve instead:\n"
        + "\n".join(offenders)
    )


def test_regex_does_not_false_positive_on_unrelated_paths_containing_tmp():
    assert not _BARE_TMP_RE.search("/var/tmp/cache")
    assert not _BARE_TMP_RE.search("/private/tmp/x")


def test_regex_still_catches_a_bare_root_tmp_literal():
    assert _BARE_TMP_RE.search('git diff HEAD > "/tmp/shipwright-review-diff.txt"')
    assert _BARE_TMP_RE.search("`/tmp/foo.json`")


def test_scanned_globs_actually_match_something():
    # A silently-empty glob (renamed dir, typo) would make the assertion
    # above a no-op pass instead of a real check. Per-glob, not just an
    # aggregate threshold — an aggregate can stay "healthy" while one of
    # the three trees goes silently empty.
    for pattern in _SCANNED_GLOBS:
        assert list(_REPO_ROOT.glob(pattern)), f"glob matched nothing: {pattern}"
