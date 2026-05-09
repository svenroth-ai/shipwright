"""TODO/FIXME inventory at known_issues.md (Fix 6).

The first thing /shipwright-iterate users grep for after adoption is
`TODO|FIXME|HACK`. Pre-compute it: a deterministic scan over source
files that respects .gitignore, groups by marker type and file, and
caps at 200 entries.
"""

from __future__ import annotations

from pathlib import Path

from lib.known_issues_inventory import write_known_issues_inventory


def test_writes_known_issues_md_when_markers_present(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text(
        "// TODO: support unicode in user names\n"
        "export const x = 1;\n",
        encoding="utf-8",
    )
    (src / "b.py").write_text(
        "# FIXME: handle empty list\n"
        "# HACK: temporary workaround for upstream bug\n"
        "x = 2\n",
        encoding="utf-8",
    )
    inv = write_known_issues_inventory(tmp_path)
    assert inv["entries"] >= 3
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "TODO" in body
    assert "FIXME" in body
    assert "HACK" in body
    assert "support unicode" in body
    assert "handle empty list" in body


def test_groups_by_marker_type(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text(
        "// TODO: 1\n// TODO: 2\n// FIXME: 3\n",
        encoding="utf-8",
    )
    write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    # Section per marker type (`## TODO` and `## FIXME`).
    assert "## TODO" in body
    assert "## FIXME" in body
    # Summary table at the top.
    assert "Marker" in body and "Count" in body


def test_skips_node_modules_and_build_artifacts(tmp_path: Path) -> None:
    """Common artifact dirs are noisy and not actionable — skip them."""
    (tmp_path / "node_modules" / "lib").mkdir(parents=True)
    (tmp_path / "node_modules" / "lib" / "a.ts").write_text(
        "// TODO: noise from a dep\n", encoding="utf-8"
    )
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("// TODO: bundled\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text(
        "// TODO: real concern\n", encoding="utf-8"
    )
    write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "real concern" in body
    assert "noise from a dep" not in body
    assert "bundled" not in body


def test_respects_gitignore(tmp_path: Path) -> None:
    """Files explicitly gitignored should not surface in known_issues.md."""
    import subprocess as _sp

    _sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "a.ts").write_text(
        "// TODO: gitignored\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("// TODO: tracked\n", encoding="utf-8")
    write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "tracked" in body
    assert "gitignored" not in body


def test_writes_empty_state_when_no_markers(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.ts").write_text("export const x = 1;\n", encoding="utf-8")
    write_known_issues_inventory(tmp_path)
    md = tmp_path / ".shipwright" / "agent_docs" / "known_issues.md"
    assert md.exists()
    body = md.read_text(encoding="utf-8")
    # Operator should see an explicit "no markers" message — not a blank file.
    assert "no" in body.lower() or "0" in body


def test_caps_at_two_hundred_entries(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    big = "\n".join(f"// TODO: case {i}" for i in range(300))
    (src / "huge.ts").write_text(big + "\n", encoding="utf-8")
    inv = write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    # Beyond 200 entries we just list counts + the top 50.
    # Either a soft "truncated" note or an explicit "300 markers" count.
    assert inv["total"] >= 300
    assert inv["truncated"] is True
    assert "truncat" in body.lower() or "first 50" in body.lower()


def test_truncates_long_marker_text_to_200_chars(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    long_text = "x" * 500
    (src / "a.ts").write_text(f"// TODO: {long_text}\n", encoding="utf-8")
    write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    # Per-bullet truncation keeps spec.md scannable.
    assert "x" * 500 not in body


# ---------------------------------------------------------------------------
# Self-detection regression suite (iterate-2026-05-09).
#
# The pre-fix scanner matched any occurrence of `\b(TODO|FIXME|...)\b:?\s*(.*)`,
# so a tuple element like `_MARKERS = ("TODO", "FIXME", ...)` self-matched.
# Post-fix the scanner requires a recognised comment context.
# ---------------------------------------------------------------------------


def test_skips_marker_strings_in_source_code(tmp_path: Path) -> None:
    """Bare marker strings in source code (regex patterns, tuple elements)
    must NOT be detected — only markers in comment context count.

    Pairs the bare-string file with a sibling file containing a legitimate
    `# TODO: real`. If a broken implementation accidentally skipped all
    `.py` files (or simply never scanned), the comparator file would also
    register zero hits and the test would still pass on the first
    assertion alone. Asserting `total == 1` AND that the legitimate marker
    text appears proves scanning ran but the bare-string file produced
    zero hits.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "scanner.py").write_text(
        "import re\n"
        '_MARKERS = ("TODO", "FIXME", "HACK", "XXX", "DEPRECATED")\n'
        '_PATTERN = re.compile(r"\\b(TODO|FIXME|HACK|XXX|DEPRECATED)\\b:?\\s*(.*)")\n'
        'def render():\n'
        '    return "TODO / FIXME inventory"\n',
        encoding="utf-8",
    )
    # Comparator: legitimate Python comment in a sibling file. Must match.
    (src / "real.py").write_text(
        "# TODO: real-comment-marker\nx = 1\n", encoding="utf-8"
    )
    inv = write_known_issues_inventory(tmp_path)
    assert inv["total"] == 1, (
        f"Bare marker strings must produce zero matches; comparator file's "
        f"legitimate `# TODO` must produce one. Got {inv}"
    )
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "real-comment-marker" in body, "comparator file's marker must appear"
    # Implicit: the scanner.py bare-string lines do NOT contribute, so the
    # rendered body must not contain any marker text from scanner.py.
    assert "scanner.py" not in body


def test_python_docstring_is_not_comment_context(tmp_path: Path) -> None:
    """Python docstrings are string literals, not comments. Markers inside
    `\"\"\"...\"\"\"` blocks must NOT be detected. Explicit negative test
    protects against future regressions that might widen the predicate to
    match string literals.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "module.py").write_text(
        'def foo():\n'
        '    """TODO: docstring marker that should NOT match."""\n'
        '    return 1\n',
        encoding="utf-8",
    )
    # Comparator: real `# TODO` in same file. Must still match.
    (src / "real.py").write_text(
        "# TODO: real-comparator\n", encoding="utf-8"
    )
    inv = write_known_issues_inventory(tmp_path)
    assert inv["total"] == 1, (
        f"Docstring TODO must NOT match; only the comparator file's "
        f"`# TODO` should count. Got {inv}"
    )
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "real-comparator" in body
    assert "docstring marker" not in body


def test_detects_markers_in_comment_contexts(tmp_path: Path) -> None:
    """Each recognised comment-opener form contributes one match.

    The allowlist covers the comment forms used by file extensions in
    `_SOURCE_SUFFIXES`. SQL/Lua/Haskell `--` is intentionally NOT in the
    allowlist because none of their extensions are scanned today.
    """
    src = tmp_path / "src"
    src.mkdir()
    # Python / shell / Ruby line comment.
    (src / "py.py").write_text("# TODO: real-py\nx = 1\n", encoding="utf-8")
    # JS / TS / Java / Go / Rust line comment.
    (src / "js.js").write_text("// TODO: real-js\nconst x = 1;\n", encoding="utf-8")
    # C-style block opener (single-line form).
    (src / "c.c").write_text("/* TODO: real-c */\n", encoding="utf-8")
    # JSDoc / Javadoc continuation line (asterisk preceded by whitespace).
    (src / "doc.ts").write_text(" * TODO: real-doc\n", encoding="utf-8")
    # HTML comment (preserves existing .html-file detection).
    (src / "page.html").write_text("<!-- TODO: real-html -->\n", encoding="utf-8")
    inv = write_known_issues_inventory(tmp_path)
    # Five files × one TODO each = 5 markers.
    assert inv["total"] == 5, f"Expected 5 markers across 5 comment forms, got {inv}"
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    for tag in ("real-py", "real-js", "real-c", "real-doc", "real-html"):
        assert tag in body, f"Missing marker text {tag!r} in rendered inventory"


def test_detects_inline_markers_after_code(tmp_path: Path) -> None:
    """Markers after code on the same line (inline comments) must be detected."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1  # TODO: inline-py\n", encoding="utf-8")
    (src / "b.ts").write_text("foo();  // TODO: inline-ts\n", encoding="utf-8")
    inv = write_known_issues_inventory(tmp_path)
    assert inv["total"] == 2, f"Expected 2 inline markers, got {inv}"


def test_inline_asterisk_is_not_jsdoc(tmp_path: Path) -> None:
    """Inline `*` between code tokens is multiplication, not a JSDoc
    continuation. `a * TODO`-shaped lines must NOT match.
    """
    src = tmp_path / "src"
    src.mkdir()
    # JSDoc continuation: asterisk anchored at start of line — must match.
    (src / "doc.ts").write_text(
        "/**\n"
        " * TODO: jsdoc-real\n"
        " */\n",
        encoding="utf-8",
    )
    # Inline math expression: `a * TODO` is NOT JSDoc — must NOT match.
    (src / "math.ts").write_text(
        "const y = a * TODO_constant;\n"
        "const z = a * b * TODO_another;\n",
        encoding="utf-8",
    )
    inv = write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert inv["total"] == 1, f"Expected only the JSDoc TODO to match, got {inv}"
    assert "jsdoc-real" in body
    assert "TODO_constant" not in body
    assert "TODO_another" not in body


def test_markdown_bullet_matches_single_dash_only(tmp_path: Path) -> None:
    """`- TODO: foo` (single-dash bullet) matches; `--- TODO` (horizontal rule)
    does NOT match — three dashes is not a markdown list bullet.
    """
    src = tmp_path / "src"
    src.mkdir()
    # Markdown bullet WITHIN a source file — files like .vue / .svelte / .astro
    # carry markdown-shaped strings inside templates. Only single-dash bullets
    # should match.
    (src / "ok.svelte").write_text("- TODO: bullet-ok\n", encoding="utf-8")
    (src / "no.svelte").write_text("--- TODO: rule-no\n", encoding="utf-8")
    inv = write_known_issues_inventory(tmp_path)
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    # Exactly one match: the bullet line. The horizontal rule must be ignored.
    assert inv["total"] == 1, f"Expected exactly 1 bullet match, got {inv}"
    assert "bullet-ok" in body
    assert "rule-no" not in body


def test_skips_self_reference_file(tmp_path: Path) -> None:
    """The scanner's own source file is excluded from the scan (belt-and-
    suspenders against any future regex regression). Test isolates the skip
    by placing a LEGITIMATE comment-context marker that the new predicate
    WOULD otherwise match — proving _SKIP_FILES intercepts independently.
    """
    self_ref_rel = "plugins/shipwright-adopt/scripts/lib/known_issues_inventory.py"
    self_ref = tmp_path / self_ref_rel
    self_ref.parent.mkdir(parents=True, exist_ok=True)
    self_ref.write_text("# TODO: real-marker-in-self-ref\n", encoding="utf-8")
    # Add a separate file with a legitimate marker to ensure the scanner ran.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "other.py").write_text(
        "# TODO: real-elsewhere\n", encoding="utf-8"
    )
    inv = write_known_issues_inventory(tmp_path)
    assert inv["total"] == 1, (
        f"Self-reference file must be skipped; only 'other.py' should count. Got {inv}"
    )
    body = (tmp_path / ".shipwright" / "agent_docs" / "known_issues.md").read_text(
        encoding="utf-8"
    )
    assert "real-elsewhere" in body
    assert "real-marker-in-self-ref" not in body
