"""Hygiene filtering for mined acceptance criteria (trg-ac2ef362).

Split out of `test_test_acceptance_miner.py` at the 300-line guideline.
Mined `describe`/`it`/`test_*` labels must never carry the implementation-
detail shapes FR-01.02 #5 (`fr_hygiene_detectors.violations`) bans, since
there is no rollout-transition grace for content a producer keeps
generating after the gate's own rollout instant — see
`.shipwright/planning/iterate/2026-09-16-adopt-miner-hygiene-gate-conflict.md`.
"""

from __future__ import annotations

from pathlib import Path

from lib.test_acceptance_miner import mine_acceptance_criteria


def test_js_dirty_describe_prefix_with_clean_it_strips_the_prefix(tmp_path: Path) -> None:
    """A PascalCase component-name describe is the single largest source of
    hits — dropping the whole bullet would gut mining output. The clean `it`
    half survives on its own."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "card.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "card.test.ts").write_text(
        "describe('UserProfileCard', () => {\n"
        "  it('renders the avatar and username', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/card.ts")
    assert result == ["renders the avatar and username"]
    assert not any("UserProfileCard" in ac for ac in result)


def test_js_dirty_it_label_is_dropped_entirely(tmp_path: Path) -> None:
    """An HTTP-verb-shaped `it` label has no clean half to fall back to."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "api.test.ts").write_text(
        "describe('users endpoint', () => {\n"
        "  it('GET /api/users: returns 200 with the user list', () => {});\n"
        "  it('lists users successfully', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/api.ts")
    assert result == ["users endpoint: lists users successfully"]
    assert not any("GET" in ac for ac in result)


def test_js_bare_it_dirty_label_no_prefix_to_strip_is_dropped(tmp_path: Path) -> None:
    """No describe wrapper at all — a dirty label has nothing to fall back to."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "svc.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "svc.test.ts").write_text(
        "test('AuthService validates the token', () => {});\n"
        "test('rejects an expired session', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/svc.ts")
    assert result == ["rejects an expired session"]


def test_js_bare_empty_it_label_is_dropped(tmp_path: Path) -> None:
    """External code review, medium: `test('')` is a regex-non-empty match
    (whitespace/blank between the quotes) but a blank bullet has no value —
    guarded the same way `_mine_py`'s whitespace-only humanized name is."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "empty.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "empty.test.ts").write_text(
        "test('  ', () => {});\n"
        "test('a real case', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/empty.ts")
    assert result == ["a real case"]


def test_js_empty_it_under_dirty_describe_is_dropped_not_stripped_to_blank(tmp_path: Path) -> None:
    """External code review, medium: the prefix-strip fallback must not
    smuggle a blank bullet through when the `it` half is empty rather than
    genuinely clean — `combined` is dirty (PascalCase describe), the `it`
    half is blank, and neither branch should emit anything."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "card.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "card.test.ts").write_text(
        "describe('UserProfileCard', () => {\n"
        "  it('', () => {});\n"
        "  it('renders the header', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/card.ts")
    assert result == ["renders the header"]


def test_js_nested_describe_only_innermost_prefix_is_considered(tmp_path: Path) -> None:
    """The miner attributes an `it` to its single *innermost* describe only
    (pre-existing behavior, unchanged by this fix) — a dirty OUTER describe
    name never enters the combined string at all, so it can neither trip nor
    need stripping. Only the innermost label matters for hygiene."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "card.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "card.test.ts").write_text(
        "describe('UserProfileCard', () => {\n"
        "  describe('when props change', () => {\n"
        "    it('shows the avatar', () => {});\n"
        "  });\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/card.ts")
    assert result == ["when props change: shows the avatar"]


def test_js_prefix_stripping_dedupes_within_one_file(tmp_path: Path) -> None:
    """Two distinct dirty-prefixed bullets can collapse to the same clean
    `it` text once the describe prefix is dropped — the surviving list must
    not carry a literal duplicate line."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "auth.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "auth.test.ts").write_text(
        "describe('AuthService', () => {\n"
        "  it('validates input', () => {});\n"
        "});\n"
        "describe('UserService', () => {\n"
        "  it('validates input', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/auth.ts")
    assert result == ["validates input"]


def test_js_dedup_also_applies_to_bullets_never_stripped(tmp_path: Path) -> None:
    """External code review, low: dedup is not scoped to only prefix-stripped
    bullets — two already-clean, never-stripped, literally identical bullets
    (genuine source-file duplication) are deduped the same way. Non-goal text
    updated accordingly (module docstring)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "widget.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "widget.test.ts").write_text(
        "describe('widget', () => {\n"
        "  it('renders correctly', () => {});\n"
        "  it('renders correctly', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/widget.ts")
    assert result == ["widget: renders correctly"]


def test_js_all_candidates_dirty_returns_empty(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "http.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (src / "http.test.ts").write_text(
        "describe('HttpClient', () => {\n"
        "  it('GET /api/users: returns 200', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/http.ts")
    assert result == []


def test_py_all_candidates_dirty_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "card.py").write_text("def render(): pass\n", encoding="utf-8")
    (tmp_path / "src" / "test_card.py").write_text(
        "def test_UserProfileCard_renders():\n    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/card.py")
    assert result == []


def test_py_whitespace_only_humanized_name_is_dropped(tmp_path: Path) -> None:
    """External code review, low: an all-underscore test name humanizes to
    an all-whitespace string, which `violations()` trivially calls clean —
    guarded explicitly rather than emitted as a blank spec.md bullet."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("def x(): pass\n", encoding="utf-8")
    (tmp_path / "src" / "test_x.py").write_text(
        "def test___():\n    pass\n"
        "def test_real_behavior():\n    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/x.py")
    assert result == ["real behavior"]


def test_py_dirty_docstring_is_dropped(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.py").write_text("def render(): pass\n", encoding="utf-8")
    (tmp_path / "src" / "test_widget.py").write_text(
        "def test_render_calls_user_profile_card():\n"
        "    \"\"\"UserProfileCard renders the avatar correctly.\"\"\"\n"
        "    pass\n"
        "def test_render_shows_placeholder():\n"
        "    \"\"\"Shows a placeholder when no avatar is set.\"\"\"\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/widget.py")
    assert result == ["Shows a placeholder when no avatar is set."]


def test_py_dirty_humanized_name_is_dropped(tmp_path: Path) -> None:
    """A function name with no docstring humanizes to a bullet that can
    itself still be dirty (a PascalCase segment survives the underscore
    replace) — dropped, not emitted half-humanized."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "card.py").write_text("def handler(): pass\n", encoding="utf-8")
    (tmp_path / "src" / "test_card.py").write_text(
        "def test_UserProfileCard_renders():\n    pass\n"
        "def test_handles_missing_auth_header():\n    pass\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/card.py")
    assert result == ["handles missing auth header"]


def test_all_dirty_candidate_falls_through_to_next_sibling(tmp_path: Path) -> None:
    """Internal plan review finding: a candidate whose every raw label is
    dirty must fall through to the next sibling candidate, same as a
    candidate with no test calls at all — not silently stop the search with
    a discarded-to-empty result."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__tests__").mkdir()
    (tmp_path / "src" / "widget.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "widget.test.ts").write_text(
        "describe('WidgetCard', () => {\n"
        "  it('GET /api/widgets: returns 200', () => {});\n"
        "});\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "__tests__" / "widget.test.ts").write_text(
        "it('renders without crashing', () => {});\n",
        encoding="utf-8",
    )
    result = mine_acceptance_criteria(tmp_path, "src/widget.ts")
    assert result == ["renders without crashing"]


def test_hygiene_filter_runs_before_the_cap(tmp_path: Path) -> None:
    """Dirty candidates must not consume cap slots — filtering happens
    before the 10-item truncation, not after.

    External code review (glm + openai, medium): the dirty candidates must
    come FIRST in file order. A cap-before-filter bug caps to the first 10
    raw matches — if those 10 happen to already be the clean ones (as an
    earlier, weaker version of this test had them), the bug and the correct
    behavior produce the same result and the test can't tell them apart.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    lines = []
    for i in range(10):
        lines.append(f"it('GET /api/dirty{i}: returns 200', () => {{}});")
    for i in range(10):
        lines.append(f"it('clean case {i}', () => {{}});")
    (tmp_path / "src" / "x.test.ts").write_text("\n".join(lines), encoding="utf-8")
    result = mine_acceptance_criteria(tmp_path, "src/x.ts")
    assert len(result) == 10
    assert all(ac.startswith("clean case") for ac in result)
