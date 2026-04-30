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
