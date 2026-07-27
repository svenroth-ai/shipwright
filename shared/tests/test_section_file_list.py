"""Tests for the section's declared-file list and the attribution predicate.

Section files are written by an LLM (``/shipwright-plan``'s section-writer), so
the parser meets real formatting variance rather than the template's ideal. A
brittle parser here produces *false* build failures, which is worse than no check
at all — external review flagged exactly this as the top risk of part (3).

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import pytest

from lib.section_file_list import (
    is_framework_bookkeeping,
    parse_declared_files,
    unattributed_paths,
)

_HEADING = "## Files to Create/Modify"

TEMPLATE = """# Section: 01-auth

## Implementation Steps
1. Create `src/lib/supabase/client.ts` with browser client factory

## Files to Create/Modify
- `src/lib/supabase/client.ts` — Supabase browser client singleton
- `src/app/login/page.tsx` — Login page with email + OAuth

## Verification
- [ ] All tests pass
"""


def test_parses_the_template_shape():
    assert parse_declared_files(TEMPLATE) == [
        "src/lib/supabase/client.ts",
        "src/app/login/page.tsx",
    ]


def test_stops_at_the_next_heading():
    """`## Verification`'s checkboxes must not be read as declared files."""
    assert "All tests pass" not in " ".join(parse_declared_files(TEMPLATE))


def test_missing_block_yields_empty_list():
    assert parse_declared_files("# Section\n\n## Verification\n- [ ] ok\n") == []


@pytest.mark.parametrize("heading", [
    "## Files to Create/Modify",
    "## Files to Create / Modify",
    "## files to create/modify",
    "### Files to Create/Modify",
    "## Files to Create/Modify (5)",
])
def test_heading_variants_are_recognized(heading):
    doc = f"{heading}\n- `src/a.ts` — thing\n"
    assert parse_declared_files(doc) == ["src/a.ts"]


@pytest.mark.parametrize("line,expected", [
    ("- `src/a.ts` — description", "src/a.ts"),
    ("- src/a.ts — description", "src/a.ts"),
    ("* `src/a.ts`: description", "src/a.ts"),
    ("+ **`src/a.ts`** — bold path", "src/a.ts"),
    ("- [ ] `src/a.ts` — a task-style bullet", "src/a.ts"),
    ("- [x] src/a.ts", "src/a.ts"),
    ("- `./src/a.ts` — leading dot-slash", "src/a.ts"),
    (r"- `src\a.ts` — windows separators", "src/a.ts"),
    ("- src/a.ts", "src/a.ts"),
    ("-   `src/a.ts`   —   padded", "src/a.ts"),
    ("- `src/my-file.ts` — hyphens in the name survive", "src/my-file.ts"),
    ("- `src/a.ts` - ascii hyphen separator", "src/a.ts"),
])
def test_messy_bullet_forms_normalize_to_a_path(line, expected):
    assert parse_declared_files(f"## Files to Create/Modify\n{line}\n") == [expected]


@pytest.mark.parametrize("line,expected", [
    ("- `src/_utils.py` — leading underscore survives", "src/_utils.py"),
    ("- `src/__init__.py` — dunder survives", "src/__init__.py"),
    ("- **`src/a.ts`** — balanced bold is stripped, path intact", "src/a.ts"),
    ("- _`src/a.ts`_ — balanced italic", "src/a.ts"),
])
def test_emphasis_stripping_does_not_eat_real_filenames(line, expected):
    """A per-character strip turned `_utils.py` into `utils.py` — a phantom path."""
    assert parse_declared_files(f"{_HEADING}\n{line}\n") == [expected]


def test_backtick_in_the_description_does_not_hijack_the_path():
    """A back-ticked word in the prose must not become the declared path."""
    doc = f"{_HEADING}\n- src/a.ts — wraps `fetch` for retries\n"
    assert parse_declared_files(doc) == ["src/a.ts"]


@pytest.mark.parametrize("line,expected", [
    ("- Modify: `src/lib/http.ts`", "src/lib/http.ts"),
    ("- Tests: `src/x.test.ts`", "src/x.test.ts"),
    ("- New file: `src/a.ts`", "src/a.ts"),
])
def test_label_prefixed_bullets_still_yield_the_path(line, expected):
    """`Label: path` is an ordinary bullet form; taking the label drops the path."""
    assert parse_declared_files(f"{_HEADING}\n{line}\n") == [expected]


def test_a_bare_prose_token_does_not_become_a_covering_directory():
    """`- src/lib helpers as needed` must not pre-attribute everything beneath."""
    declared = parse_declared_files(f"{_HEADING}\n- src/lib helpers as needed\n")
    assert unattributed_paths(
        ["src/lib/http.ts"], declared=declared, extras=[]) == ["src/lib/http.ts"]


def test_an_explicit_trailing_slash_does_cover_files_beneath():
    declared = parse_declared_files(f"{_HEADING}\n- `src/auth/` — the whole module\n")
    assert unattributed_paths(
        ["src/auth/login.ts"], declared=declared, extras=[]) == []


def test_multiple_paths_on_one_bullet_are_all_declared():
    """Keeping only the first would report the rest as unattributed."""
    doc = f"{_HEADING}\n- Create `a.ts` and `b.ts` together\n"
    assert parse_declared_files(doc) == ["a.ts", "b.ts"]


def test_prose_lines_without_a_path_are_ignored():
    doc = "## Files to Create/Modify\nNone — this section only adds tests.\n"
    assert parse_declared_files(doc) == []


def test_duplicates_collapse():
    doc = "## Files to Create/Modify\n- `a.ts` — x\n- `a.ts` — y\n"
    assert parse_declared_files(doc) == ["a.ts"]


# --------------------------------------------------------------------------
# unattributed_paths — the actual rule of part (3)
# --------------------------------------------------------------------------

def test_declared_file_is_attributed():
    assert unattributed_paths(["src/a.ts"], declared=["src/a.ts"], extras=[]) == []


def test_undeclared_file_is_unattributed():
    assert unattributed_paths(["src/b.ts"], declared=["src/a.ts"], extras=[]) == \
        ["src/b.ts"]


def test_recorded_extra_makes_a_shared_touch_legitimate():
    """The whole point of part (3): the section MAY touch shared code, if recorded."""
    assert unattributed_paths(
        ["src/lib/http.ts"],
        declared=["src/a.ts"],
        extras=[{"path": "src/lib/http.ts", "reason": "needed a retry helper"}],
    ) == []


def test_comparison_is_separator_and_prefix_insensitive():
    assert unattributed_paths(
        [r"src\a.ts"], declared=["./src/a.ts"], extras=[]) == []


def test_a_declared_directory_covers_files_beneath_it():
    """Sections routinely name a directory when they add several files in it.

    Only with an explicit trailing slash — see
    ``test_a_bare_prose_token_does_not_become_a_covering_directory``.
    """
    assert unattributed_paths(
        ["src/auth/login.ts", "src/auth/logout.ts"],
        declared=["src/auth/"], extras=[]) == []


@pytest.mark.parametrize("path", [
    ".shipwright/planning/requirement-impact/run__build__01__abc123.json",
    ".shipwright/agent_docs/decision_log.md",
    "shipwright_events.jsonl",
    "shipwright_build_config.json",
    "design-fidelity-report.json",
])
def test_framework_bookkeeping_is_not_section_work(path):
    """`git add -A` sweeps the previous section's bookkeeping into this commit."""
    assert is_framework_bookkeeping(path) is True
    assert unattributed_paths([path], declared=[], extras=[]) == []


@pytest.mark.parametrize("path", [
    "src/app.ts",
    ".shipwright/planning/01-checkout/spec.md",
    "shipwright_events.jsonl.bak",
])
def test_ordinary_files_are_not_bookkeeping(path):
    assert is_framework_bookkeeping(path) is False


def test_unattributed_list_is_deduped_and_ordered():
    assert unattributed_paths(
        ["z.ts", "a.ts", "z.ts"], declared=[], extras=[]) == ["a.ts", "z.ts"]


def test_a_declaration_verified_spec_edit_is_attributed():
    """Part (2) REQUIRES the correction; part (3) must not then punish it."""
    spec = ".shipwright/planning/01-checkout/spec.md"
    assert unattributed_paths(
        [spec], declared=["src/a.ts"], extras=[], requirement_specs=[spec]) == []


def test_a_spec_edit_is_unattributed_when_the_declaration_claims_none():
    """An `--impact none` section that edits requirements anyway is still caught.

    The caller passes ``requirement_specs`` only for a behaviour-affecting
    declaration, so this is the shape that reaches the predicate.
    """
    spec = ".shipwright/planning/01-checkout/spec.md"
    assert unattributed_paths(
        [spec], declared=["src/a.ts"], extras=[], requirement_specs=[]) == [spec]
