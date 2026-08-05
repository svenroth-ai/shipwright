"""Discovery tests for the inline-suppression scanner.

**Every fixture builds the suppression text through an f-string placeholder or
runtime concatenation, never as a literal `nosemgrep:` + rule id in this file's
own source.** That is not style: this file is git-tracked, the scanner reads
git-tracked files, and a literal would make this test file itself a counted
suppression site — inflating the live repo baseline with its own test data.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import inline_suppression_scan as scan  # noqa: E402

_RULE = "python.lang.security.audit.non-literal-import.non-literal-import"
_OTHER = "python.lang.security.audit.subprocess-shell-true.subprocess-shell-true"


def _repo(tmp_path: Path, sources: dict[str, str]) -> Path:
    for rel, text in sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------
# The two forms actually used in this repo
# --------------------------------------------------------------------------

def test_finds_the_standalone_comment_form(tmp_path):
    """`fr_table_reader.py` puts the suppression on its own line."""
    root = _repo(tmp_path, {"a.py": f"x = 1\n# nosemgrep: {_RULE}\nimport os\n"})
    assert set(scan.scan_sites(root)) == {_RULE}


def test_finds_the_trailing_comment_form(tmp_path):
    """`test_runner.py` puts it on the code line itself."""
    root = _repo(tmp_path, {"a.py": f"run(shell=True)  # nosemgrep: {_OTHER}\n"})
    assert set(scan.scan_sites(root)) == {_OTHER}


def test_splits_a_comma_separated_rule_list(tmp_path):
    """`git_base.py` suppresses two rules on one line. Counting that as one
    would under-record a rule, which is the unsafe direction."""
    root = _repo(tmp_path, {"a.py": f"# nosemgrep: {_RULE},{_OTHER}\n"})
    assert set(scan.scan_sites(root)) == {_RULE, _OTHER}


def test_sites_carry_a_locatable_path_and_line(tmp_path):
    root = _repo(tmp_path, {"pkg/a.py": f"x\n# nosemgrep: {_RULE}\n"})
    assert scan.scan_sites(root)[_RULE] == ["pkg/a.py:2"]


# --------------------------------------------------------------------------
# Language coverage — a marker this list misses under-counts silently
# --------------------------------------------------------------------------

def test_every_documented_comment_marker_is_recognised():
    for marker in scan.COMMENT_MARKERS:
        assert scan.rules_on_line(f"code  {marker} nosemgrep: {_RULE}") == [_RULE]


@pytest.mark.parametrize("token", ["nosem", "nosemgrep", "NOSEM", "NoSemGrep"])
def test_every_spelling_semgrep_honours_is_counted(tmp_path, token):
    """Semgrep accepts `nosem` as an alias and matches the token
    case-insensitively. Keying to the literal lowercase `nosemgrep` left
    `# nosem: <rule-id>` as a REAL suppression the gate could not see — a
    working, undisclosed bypass, found in Stage-2 code review. Not a limit:
    a defect, and this is the control that keeps it fixed."""
    root = _repo(tmp_path, {"a.py": f"code()  # {token}: {_RULE}\n"})
    assert set(scan.scan_sites(root)) == {_RULE}


def test_a_large_file_is_scanned_rather_than_capped_out(tmp_path, monkeypatch):
    """There is no size cap any more. A 2 MB cap was a silent BYPASS (padding
    a file past it hid a live suppression); replacing it with a 50 MB BLOCK
    only moved the defect, red-lighting a perfectly readable large file with
    an untrue remedy. Streaming in chunks removes the reason a cap existed
    (Stage-3 doubt review, D10)."""
    monkeypatch.setattr(scan, "_CHUNK_BYTES", 64)
    root = _repo(tmp_path, {
        "big.py": "x = 1\n" * 200 + f"# nosemgrep: {_RULE}\n" + "y = 2\n" * 200})
    result = scan.scan(root)
    assert result["unreadable"] == []
    assert set(result["sites"]) == {_RULE}


def test_a_token_straddling_a_chunk_boundary_is_still_found(
    tmp_path, monkeypatch
):
    """The streaming pre-filter overlaps chunks. Without the overlap a token
    split across a read boundary is missed — a silent under-count, the unsafe
    direction."""
    monkeypatch.setattr(scan, "_CHUNK_BYTES", 8)
    root = _repo(tmp_path, {"a.py": f"abcdefg# nosemgrep: {_RULE}\n"})
    assert set(scan.scan_sites(root)) == {_RULE}


def test_a_non_utf8_source_file_is_still_scanned(tmp_path):
    """THE fail-open the byte-level pre-filter introduced: the decode is only
    reached for files the token filter already matched, so skipping on
    UnicodeDecodeError meant "this file holds a suppression token, and I will
    now discard it without reporting it". Reachable with any cp1252/latin-1
    source file — the Windows editor default (Stage-3 doubt review, D1)."""
    (tmp_path / "a.py").write_bytes(
        "# café legacy encoding\n".encode("cp1252")
        + f"# nosemgrep: {_RULE}\n".encode("ascii"))
    assert set(scan.scan_sites(tmp_path)) == {_RULE}


def test_a_tracked_file_missing_from_the_worktree_is_reported(
    tmp_path, monkeypatch
):
    """Sparse checkout, a worktree `rm` without `git rm`, or a path over
    Windows MAX_PATH. `Path.is_file()` swallows the OSError, so this used to
    `continue` silently — a partial count landing as an advisory `shrunk`
    while the gate stayed green (Stage-3 doubt review, D4)."""
    root = _repo(tmp_path, {"present.py": "x = 1\n"})
    monkeypatch.setattr(
        scan, "_git_tracked", lambda _r: ["present.py", "vanished.py"])
    assert scan.scan(root)["unreadable"] == ["vanished.py"]


@pytest.mark.parametrize("artifact", ["triage.jsonl", "reviews.json"])
def test_shipwrights_own_record_artifacts_are_not_counted(tmp_path, artifact):
    """Structural, not incidental: Shipwright's governance artifacts QUOTE
    code, and JSON has no comment syntax so the token can only be data. A
    triage card filed about a suppression quotes the offending line verbatim;
    a review record embeds reviewer prose discussing the syntax. Stage-3
    predicted the `.jsonl` half (D8) — and the F0 suite then found the `.json`
    half live, going red on THIS run's own `reviews.json`, which had invented
    rules called `rule` and `rule-id`. Filing or reviewing anything about this
    gate must not turn the repo red."""
    quoted = "the line reads # nosemgrep: " + _RULE + " as an example"
    root = _repo(tmp_path, {
        artifact: '{"detail": "' + quoted + '"}\n',
        "real.py": f"# nosemgrep: {_RULE}\n",
    })
    assert scan.scan_sites(root) == {_RULE: ["real.py:1"]}


def test_a_non_breaking_space_before_the_colon_is_still_a_suppression():
    """Semgrep's own pattern uses ``\\s*``; a literal ``[ \\t]`` missed the
    Unicode spaces a real editor emits (Stage-3 doubt review, D12)."""
    assert scan.rules_on_line(f"code  # nosemgrep : {_RULE}") == [_RULE]


def test_scan_reports_how_many_files_it_examined(tmp_path):
    """Without it no consumer can tell "0 suppressions across 3702 files" from
    "0 files examined" — and the latter rendered as a clean bill of health for
    a tree nothing was read from (Stage-3 doubt review, D3)."""
    root = _repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    assert scan.scan(root)["files_examined"] == 2


def test_a_requirements_txt_is_still_scanned(tmp_path):
    """`.txt` is deliberately NOT a prose suffix: Semgrep's supply-chain rules
    run over files like `requirements.txt`, so excluding it would under-count
    — the unsafe direction (Stage-2 code review)."""
    root = _repo(tmp_path, {"requirements.txt": f"# nosemgrep: {_RULE}\n"})
    assert set(scan.scan_sites(root)) == {_RULE}


def test_a_suppression_is_recognised_at_line_start_without_a_marker(tmp_path):
    assert scan.rules_on_line(f"  nosemgrep: {_RULE}") == [_RULE]


def test_a_rule_id_in_ordinary_prose_is_not_counted():
    """Without a comment marker AND with real text before it, this is prose."""
    assert scan.rules_on_line(f"The value nosemgrep: {_RULE} appears here") == []


# --------------------------------------------------------------------------
# Disclosed limits — pinned so a future reader sees them as decisions
# --------------------------------------------------------------------------

def test_the_bare_form_without_a_rule_id_is_not_counted(tmp_path):
    """Measured on this repo: all nine bare-token occurrences are prose in
    docstrings and none is a real suppression, so counting the bare form would
    be 100% false-positive. Known gap, disclosed in the module docstring."""
    root = _repo(tmp_path, {
        "a.py": '"""An inline ``# nosemgrep`` is source-controlled."""\n'
                "# nosemgrep\n"})
    assert scan.scan_sites(root) == {}


def test_a_rule_id_inside_a_string_literal_is_a_known_false_positive(tmp_path):
    """Pinned, not fixed. Excluding string literals needs a per-language
    parser; the failure is in the safe direction (a spurious BLOCK whose
    diagnostic names the exact path:line), never a hidden suppression. If this
    test ever starts failing, the scanner gained literal-awareness and the
    docstring's disclosure must be updated to match."""
    # Built at runtime so THIS file's source carries no matching text.
    literal = "# " + "nosemgrep" + ": " + _RULE
    root = _repo(tmp_path, {"a.py": f'MSG = "{literal}"\n'})
    assert set(scan.scan_sites(root)) == {_RULE}


# --------------------------------------------------------------------------
# File-set derivation
# --------------------------------------------------------------------------

def test_a_non_git_tree_falls_back_to_a_walk_and_says_so(tmp_path):
    """A discovery step that silently narrows its own scope reads as
    'all clear', so the mode is reported rather than assumed."""
    root = _repo(tmp_path, {"a.py": f"# nosemgrep: {_RULE}\n"})
    result = scan.scan(root)
    assert result["mode"] == "walk"
    assert set(result["sites"]) == {_RULE}


def test_the_fallback_walk_skips_vendored_and_worktree_directories(tmp_path):
    """`.worktrees/` holds sibling checkouts of this same repo — counting them
    would make the measurement depend on unrelated in-flight work."""
    root = _repo(tmp_path, {
        ".venv/lib/x.py": f"# nosemgrep: {_RULE}\n",
        "node_modules/y.js": f"// nosemgrep: {_RULE}\n",
        ".worktrees/other/z.py": f"# nosemgrep: {_RULE}\n",
        "__pycache__/w.py": f"# nosemgrep: {_RULE}\n",
    })
    assert scan.scan_sites(root) == {}


def test_non_code_formats_are_not_counted(tmp_path):
    """A suppression comment in a markdown document is in effect for NOTHING —
    Semgrep never applies a code rule to it. Found empirically, not theorised:
    `skills/security/references/suppression-syntax.md` documents the syntax and
    contributed seven phantom sites, two of them invented rule ids."""
    root = _repo(tmp_path, {
        "doc.md": f"Write it as `# nosemgrep: {_RULE}` on the line above.\n",
        "notes.rst": f"# nosemgrep: {_OTHER}\n",
        "real.py": f"# nosemgrep: {_RULE}\n",
    })
    assert scan.scan_sites(root) == {_RULE: ["real.py:1"]}


def test_a_git_tree_counts_tracked_files_and_ignores_untracked(tmp_path):
    """Deriving the file set from git is what makes 'source-controlled' — the
    property actually being measured — the definition, instead of an extension
    allowlist a new file type could slip past (external review, GPT #2)."""
    root = _repo(tmp_path, {
        "tracked.py": f"# nosemgrep: {_RULE}\n",
        "untracked.py": f"# nosemgrep: {_OTHER}\n",
    })
    env = {"GIT_CONFIG_GLOBAL": str(tmp_path / "nonexistent-gitconfig")}
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env={
        **_base_env(), **env})
    subprocess.run(["git", "add", "tracked.py"], cwd=root, check=True, env={
        **_base_env(), **env})

    result = scan.scan(root)
    assert result["mode"] == "git"
    assert set(result["sites"]) == {_RULE}, "untracked file must not be counted"


def _base_env() -> dict:
    import os  # noqa: PLC0415
    return dict(os.environ)


def test_an_unreadable_file_is_reported_not_skipped(tmp_path, monkeypatch):
    """A file that cannot be read yields a PARTIAL count, and a partial count
    in a security gate is a bypass (external review, GPT #4)."""
    root = _repo(tmp_path, {"a.py": f"# nosemgrep: {_RULE}\n"})
    real_read = Path.read_bytes

    def boom(self, *args, **kwargs):
        if self.name == "a.py":
            raise PermissionError("denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", boom)
    assert scan.scan(root)["unreadable"] == ["a.py"]


def test_a_binary_blob_is_skipped_without_suspicion(tmp_path):
    """Undecodable is NOT the same as unreadable: a binary file cannot hold a
    source comment, so it must not raise the partial-count alarm."""
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    (root / "blob.bin").write_bytes(b"\xff\xfe\x00nosemgrep\x00")
    result = scan.scan(root)
    assert result["unreadable"] == [] and result["sites"] == {}


def test_output_is_sorted_for_stable_diagnostics(tmp_path):
    root = _repo(tmp_path, {
        "z.py": f"# nosemgrep: {_RULE}\n",
        "a.py": f"# nosemgrep: {_RULE}\n",
    })
    assert scan.scan_sites(root)[_RULE] == ["a.py:1", "z.py:1"]
