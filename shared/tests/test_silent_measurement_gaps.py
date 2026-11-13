"""Two silent-measurement gaps closed together (leadwright cards, 2026-11-13).

1. The GitHub finding sync also consults ``origin/<default>``'s tracked triage log.
2. The FR-tag collector matches a curried ``it.skipIf(cond)('title', ...)`` declaration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from github_triage.origin_dedup import origin_known_dedup_keys, suppressing_keys_from_text  # noqa: E402
from github_triage.resolve import SOURCE  # noqa: E402
from lib.fr_tag_grammar import _TEST_DECL_RE, parse_ts_js  # noqa: E402

# ---------------------------------------------------------------- (2) curried declarations


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("line, title", [
    pytest.param('it.skipIf(process.platform === "win32")("win only @FR-01.03", () => {', "win only @FR-01.03", id="skipIf"),
    pytest.param("test.runIf(isCI())('ci only', async () => {", "ci only", id="runIf"),
    pytest.param("it.skipIf(check(os.platform()))('nested call', () => {", "nested call", id="two-levels"),
    pytest.param("it.skip('plain skip', () => {", "plain skip", id="plain-skip"),
    pytest.param("it('plain', () => {", "plain", id="plain"),
])
def test_a_curried_conditional_declaration_is_one_test(line, title):
    match = _TEST_DECL_RE.search(line)
    assert match and match.group("title") == title


@pytest.mark.covers("FR-01.11")
def test_a_curried_declaration_binds_its_title_suffix_tag():
    res = parse_ts_js('it.skipIf(process.platform === "win32")("x @FR-01.03", () => {});\n', "t.test.ts")
    assert [(h.fr_id, h.tag_source) for h in res.hits] == [("FR-01.03", "title_suffix")]


@pytest.mark.covers("FR-01.11")
def test_a_condition_nested_three_levels_deep_is_the_documented_limit():
    # Pins the documented 2-level limit: it must not bind a WRONG title (it stays uncollected).
    match = _TEST_DECL_RE.search('it.skipIf(a(b(c("s"))))("real title", () => {')
    assert match is None or match.group("title") != "s"


@pytest.mark.covers("FR-01.11")
def test_a_commented_curried_declaration_is_still_not_a_declaration():
    assert _TEST_DECL_RE.search('// it.skipIf(c)("x", () => {') is None


# ---------------------------------------------------------------- (1) origin-aware dedup


def _line(**rec) -> str:
    return json.dumps(rec)


_LOG = "\n".join([
    _line(event="append", id="trg-00000001", source=SOURCE, dedupKey="gh-pr-ci:1", status="triage"),
    _line(event="append", id="trg-00000002", source=SOURCE, dedupKey="gh-pr-ci:2", status="triage"),
    _line(event="status", id="trg-00000002", newStatus="dismissed", ts="2026-11-01T00:00:00Z", by="operator"),
    _line(event="append", id="trg-00000003", source="other-source", dedupKey="gh-pr-ci:3", status="triage"),
    "{broken line",
    _line(event="append", id="trg-00000004", source=SOURCE, dedupKey="gh-security:o/r:cs:9", status="triage"),
    _line(event="status", id="trg-00000004", newStatus="dismissed", ts="2026-11-02T00:00:00Z",
          by="githubImporter", reason="githubResolved"),
])


@pytest.mark.covers("FR-01.14")
def test_open_and_operator_dismissed_origin_items_suppress_but_other_sources_and_machine_closes_do_not():
    assert suppressing_keys_from_text(_LOG, source=SOURCE) == {"gh-pr-ci:1", "gh-pr-ci:2"}


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def behind_clone(tmp_path):
    origin, seed, behind = tmp_path / "origin.git", tmp_path / "seed", tmp_path / "behind"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(seed))
    for key, value in (("user.email", "t@example.com"), ("user.name", "t"), ("commit.gpgsign", "false"), ("core.hooksPath", "")):
        _git(seed, "config", key, value)
    (seed / "README.md").write_text("x\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "base")
    _git(seed, "push", "origin", "HEAD:main")
    _git(tmp_path, "clone", str(origin), str(behind))  # stands at the commit BEFORE the cards landed
    (seed / ".shipwright").mkdir()
    (seed / ".shipwright" / "triage.jsonl").write_text(_LOG + "\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "cards")
    _git(seed, "push", "origin", "HEAD:main")
    return behind


@pytest.mark.covers("FR-01.14")
def test_a_checkout_behind_origin_still_learns_the_keys_origin_holds(behind_clone):
    assert not (behind_clone / ".shipwright" / "triage.jsonl").exists()
    assert origin_known_dedup_keys(behind_clone, "main", source=SOURCE) == {"gh-pr-ci:1", "gh-pr-ci:2"}


@pytest.mark.covers("FR-01.14")
def test_an_unreachable_origin_is_fail_soft(tmp_path):
    assert origin_known_dedup_keys(tmp_path, "main", source=SOURCE) == set()


@pytest.mark.covers("FR-01.14")
def test_origin_never_outvotes_a_key_the_local_view_already_knows(behind_clone):
    """A card the local tree already holds (e.g. machine-closed, not yet on origin) is decided by the local scan alone."""
    from triage import append_triage_item  # noqa: PLC0415

    append_triage_item(behind_clone, source=SOURCE, severity="high", kind="bug", title="t", detail="d",
                       dedup_key="gh-pr-ci:1")
    assert origin_known_dedup_keys(behind_clone, "main", source=SOURCE) == {"gh-pr-ci:2"}


@pytest.mark.covers("FR-01.14")
def test_a_failed_fetch_never_suppresses_even_with_a_known_origin_ref(behind_clone):
    _git(behind_clone, "fetch", "--quiet", "origin", "main")  # the ref is now known locally
    _git(behind_clone, "remote", "set-url", "origin", str(behind_clone / "does-not-exist.git"))
    assert origin_known_dedup_keys(behind_clone, "main", source=SOURCE) == set()
