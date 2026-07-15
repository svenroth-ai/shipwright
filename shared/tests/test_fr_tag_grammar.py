"""Tests for the @FR tag grammar reference parser (traceability AC2 / R4).

Proves each accepted form binds to a test and each malformed form -> invalid_tags,
both on focused inline sources and over the fixture mini-repo (the answer key).
"""

from __future__ import annotations

from pathlib import Path

from lib.fr_tag_grammar import (
    TAG_SOURCES,
    TAG_TOKEN_RE,
    canonical_fr_id,
    parse_python,
    parse_source,
    parse_ts_js,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP = (
    _REPO_ROOT
    / "plugins/shipwright-compliance/tests/fixtures/traceability/mini_repos/app"
)


def test_canonical_fr_id():
    assert canonical_fr_id("@FR-01.03") == "FR-01.03"
    assert canonical_fr_id("FR-01.03") == "FR-01.03"
    assert canonical_fr_id("@FR-1.3") is None
    assert canonical_fr_id("FR-01.033") is None


# --- pytest marker (AST) ---------------------------------------------------

def test_pytest_marker_binds_to_function():
    src = 'import pytest\n@pytest.mark.covers("FR-01.03", "FR-01.04")\ndef test_a():\n    pass\n'
    res = parse_python(src, "tests/test_a.py")
    assert {h.fr_id for h in res.hits} == {"FR-01.03", "FR-01.04"}
    assert all(h.tag_source == "pytest_marker" for h in res.hits)
    assert all(h.test == "tests/test_a.py::test_a" for h in res.hits)
    assert not res.invalid


def test_pytest_marker_malformed_and_nonstring_are_invalid():
    src = 'import pytest\n@pytest.mark.covers("FR-1.3", 42)\ndef test_a():\n    pass\n'
    res = parse_python(src, "tests/test_a.py")
    assert not res.hits
    reasons = {i.reason for i in res.invalid}
    assert "non_canonical_fr_id" in reasons
    assert "non_string_arg" in reasons


def test_non_covers_decorator_ignored():
    src = 'import pytest\n@pytest.mark.parametrize("x", [1])\ndef test_a(x):\n    pass\n'
    assert parse_python(src, "t.py") .hits == ()


# --- TS/JS forms -----------------------------------------------------------

def test_covers_comment_binds_to_next_test():
    src = "// @covers FR-02.02\nit('does x', () => {})\n"
    res = parse_ts_js(src, "unit/x.test.ts")
    assert len(res.hits) == 1
    h = res.hits[0]
    assert h.fr_id == "FR-02.02" and h.tag_source == "covers_comment"
    assert h.test == "unit/x.test.ts::does x"


def test_native_tag_form():
    src = "test('shows board', { tag: ['@FR-01.03'] }, async () => {})\n"
    res = parse_ts_js(src, "e2e/board.spec.ts")
    assert res.hits[0].fr_id == "FR-01.03"
    assert res.hits[0].tag_source == "native_tag"


def test_title_suffix_form():
    src = "it('persists order @FR-03.03', () => {})\n"
    res = parse_ts_js(src, "unit/orders.test.ts")
    assert res.hits[0].fr_id == "FR-03.03"
    assert res.hits[0].tag_source == "title_suffix"


def test_ts_malformed_tag_is_invalid():
    src = "it('bad @FR-1.3', () => {})\n"
    res = parse_ts_js(src, "unit/x.test.ts")
    assert not res.hits
    assert res.invalid[0].raw == "@FR-1.3"


def test_trailing_junk_token_is_invalid_not_a_valid_prefix():
    # A whole-token capture rejects @FR-01.03x / @FR-01.03.4 instead of accepting FR-01.03.
    for src in ("it('a @FR-01.03x', () => {})\n", "it('b @FR-01.03.4', () => {})\n"):
        res = parse_ts_js(src, "unit/x.test.ts")
        assert not res.hits, src
        assert res.invalid, src
    # native-tag array form too
    res = parse_ts_js("test('c', { tag: ['@FR-01.03x'] }, () => {})\n", "e2e/x.spec.ts")
    assert not res.hits and res.invalid[0].raw == "@FR-01.03x"


def test_title_tag_binds_only_as_a_suffix():
    # prefix / middle occurrences are ambiguous -> informational, never bound
    for src in ("it('@FR-01.03 leads', () => {})\n", "it('mid @FR-01.03 word', () => {})\n"):
        assert parse_ts_js(src, "unit/x.test.ts").hits == (), src
    # a true suffix binds
    res = parse_ts_js("it('ok @FR-01.03', () => {})\n", "unit/x.test.ts")
    assert res.hits[0].fr_id == "FR-01.03" and res.hits[0].tag_source == "title_suffix"


def test_covers_comment_binds_only_when_immediately_adjacent():
    # a blank/intervening line between the comment and the test breaks the binding
    assert parse_ts_js("// @covers FR-01.03\n\nit('x', () => {})\n", "u.test.ts").hits == ()
    # a describe declaration is not a binding target for the reference
    assert parse_ts_js("// @covers FR-01.03\ndescribe('s', () => {})\n", "u.test.ts").hits == ()
    # adjacent it() does bind
    res = parse_ts_js("// @covers FR-01.03\nit('x', () => {})\n", "u.test.ts")
    assert res.hits[0].tag_source == "covers_comment"


def test_covers_comment_on_same_line_binds_to_that_test():
    # a trailing `// @covers` on the test's own line binds to it (does not drop the test)
    res = parse_ts_js("it('writes it', () => {}) // @covers FR-03.03\n", "u.test.ts")
    assert res.hits[0].fr_id == "FR-03.03" and res.hits[0].tag_source == "covers_comment"
    assert res.hits[0].test == "u.test.ts::writes it"


def test_malformed_covers_recorded_even_when_unbound():
    # a malformed // @covers that never binds (non-adjacent) is STILL surfaced (AC2)
    res = parse_ts_js("// @covers FR-1.3\n\nit('x', () => {})\n", "u.test.ts")
    assert res.hits == () and res.invalid[0].raw == "FR-1.3"
    # a valid-but-unbound covers is informational — dropped, not invalid
    res2 = parse_ts_js("// @covers FR-01.03\nconst x = 1\n", "u.test.ts")
    assert res2.hits == () and res2.invalid == ()


def test_exported_tag_token_re_rejects_continuations():
    # the exported valid-token regex must not expose a valid prefix from a malformed token
    assert TAG_TOKEN_RE.findall("@FR-01.03 ok") == ["@FR-01.03"]
    for junk in ("@FR-01.03.4", "@FR-01.03x", "@FR-01.033"):
        assert TAG_TOKEN_RE.findall(junk) == [], junk


def test_test_describe_is_not_a_binding_target():
    # `test.describe(` is a suite, not an it/test — a leading @covers must NOT bind to it
    assert parse_ts_js("// @covers FR-01.03\ntest.describe('auth', () => {})\n", "e2e/a.spec.ts").hits == ()
    # but it.skip / test.only ARE tests and still bind
    assert parse_ts_js("it.skip('x @FR-01.03', () => {})\n", "u.test.ts").hits[0].fr_id == "FR-01.03"
    assert parse_ts_js(
        "test.only('x', { tag: ['@FR-01.03'] }, () => {})\n", "e2e/a.spec.ts"
    ).hits[0].tag_source == "native_tag"


# --- over the fixture mini-repo (the answer key) ---------------------------

def _parse_app():
    hits, invalid = [], []
    for f in sorted(_APP.rglob("*")):
        if f.is_file() and f.suffix in (".py", ".ts"):
            rel = f.relative_to(_APP).as_posix()
            res = parse_source(rel, f.read_text(encoding="utf-8"))
            hits += res.hits
            invalid += res.invalid
    return hits, invalid


def test_fixture_repo_exercises_all_four_tag_sources():
    hits, _ = _parse_app()
    assert {h.tag_source for h in hits} == set(TAG_SOURCES)


def test_fixture_repo_binds_expected_frs():
    hits, invalid = _parse_app()
    by_fr = {}
    for h in hits:
        by_fr.setdefault(h.fr_id, set()).add(h.tag_source)
    assert by_fr["FR-03.01"] == {"pytest_marker", "native_tag"}
    assert by_fr["FR-03.02"] == {"native_tag"}
    assert by_fr["FR-03.03"] == {"pytest_marker", "covers_comment", "title_suffix"}
    assert by_fr["FR-03.09"] == {"native_tag"}          # the orphan's tag still binds
    # the malformed FR-1.3 is the only invalid, and it never becomes a hit
    assert [i.raw for i in invalid] == ["FR-1.3"]
    assert "FR-1.3" not in by_fr


def test_fixture_untagged_test_produces_no_hit():
    hits, _ = _parse_app()
    assert not any("test_health_endpoint" in h.test for h in hits)
