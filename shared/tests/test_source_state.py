"""Tests for ``shared/scripts/source_state.py`` — the one artifact-state stamp.

Card ``trg-4d5b6a56`` (REQ-3 Phase 2 walk, FR-01.10): a produced artifact must
name **which state of the project it describes**, not just when it was written.
This module owns the identifier's *shape* for both producers (the test-results
record and the compliance evidence documents), so the shape is defined once.

The round-trip cases here are the deliberate Boundary Probe for this change. The
diff-driven ``touches_io_boundary`` flag does NOT fire (it matches file paths and
this diff is ``.py``-only), but two serialized formats gain a field, so the
producer/consumer round-trip is proven anyway rather than assumed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from source_state import (  # noqa: E402
    BANNER_PREFIX,
    BANNER_STRIP_RE,
    UNKNOWN_RUN,
    SourceState,
    banner_line,
    from_block,
    parse_banner_line,
    resolve_git_state,
    safe_commit,
    safe_run_id,
    to_block,
)

RUN = "iterate-2026-07-27-artifact-state-stamping"
SHA = "ff88258795717661322e0d5cd5ccc5ff91efa17e"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one commit — resolution is tested against git, not a mock."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True, text=True, timeout=30)
    _git(["config", "user.email", "t@example.com"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(["add", "tracked.txt"], tmp_path)
    _git(["commit", "-qm", "initial"], tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# AC1 / AC6 — the shape is one shape, and both serializations round-trip
# --------------------------------------------------------------------------


class TestBannerRoundTrip:
    def test_full_state_round_trips_to_its_abbreviated_form(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=False)
        parsed = parse_banner_line(banner_line(state))
        # The banner deliberately carries the ABBREVIATED commit (a 40-hex blob
        # in an operator-facing header is noise), so the exact round-trip target
        # is the abbreviated projection. Stated, not silently lossy.
        assert parsed == state.abbreviated()
        assert parsed.run_id == RUN
        assert parsed.commit == SHA[:12]

    def test_dirty_flag_round_trips(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=True)
        line = banner_line(state)
        assert parse_banner_line(line).dirty is True

    @pytest.mark.parametrize("dirty", [True, False, None])
    def test_all_three_dirty_states_survive_the_banner(self, dirty):
        # "clean" and "git could not answer" must not render identically — that
        # collapse is the honesty distinction this stamp exists to make, and the
        # first implementation got it wrong (caught here, not in review).
        line = banner_line(SourceState(run_id=RUN, dirty=dirty))
        assert parse_banner_line(line).dirty is dirty

    def test_clean_and_unknown_render_differently(self):
        assert banner_line(SourceState(run_id=RUN, dirty=False)) != banner_line(
            SourceState(run_id=RUN, dirty=None)
        )

    def test_empty_state_round_trips_as_unknown(self):
        line = banner_line(SourceState())
        assert f"run={UNKNOWN_RUN}" in line
        parsed = parse_banner_line(line)
        assert parsed.run_id is None
        assert parsed.commit is None

    def test_banner_is_a_single_line_and_prefixed(self):
        line = banner_line(SourceState(run_id=RUN, commit=SHA, dirty=True))
        assert "\n" not in line
        assert line.startswith(BANNER_PREFIX)

    def test_parse_returns_none_when_no_banner_present(self):
        assert parse_banner_line("# Doc\n\nGenerated: 2026-07-27\n\nbody\n") is None

    def test_parse_finds_the_banner_inside_a_document(self):
        doc = f"# RTM\n\nGenerated: x\n{banner_line(SourceState(run_id=RUN))}\n\nbody\n"
        assert parse_banner_line(doc).run_id == RUN


class TestBlockRoundTrip:
    def test_json_block_round_trips_exactly_including_full_sha(self):
        state = SourceState(run_id=RUN, commit=SHA, dirty=False)
        assert from_block(to_block(state)) == state
        # The JSON side keeps the FULL sha — that is the side a gate compares.
        assert to_block(state)["commit"] == SHA

    def test_block_keys_are_the_declared_three(self):
        assert set(to_block(SourceState()).keys()) == {"run_id", "commit", "dirty"}

    def test_unresolved_fields_serialise_as_null_not_omitted(self):
        # AC7: absent must be visibly absent, never quietly dropped.
        block = to_block(SourceState())
        assert block == {"run_id": None, "commit": None, "dirty": None}

    @pytest.mark.parametrize("junk", [
        None, [], "x", 7,
        {"run_id": 5, "commit": object(), "dirty": "yes"},
        {"run_id": "a b", "commit": "nothex", "dirty": 1},
    ])
    def test_from_block_yields_an_empty_state_not_a_half_trusted_one(self, junk):
        # Asserts the VALUES, not merely that nothing raised: the guarantee is "this
        # record says nothing about its state", so a partially-trusted field is the bug.
        assert from_block(junk) == SourceState(run_id=None, commit=None, dirty=None)

    def test_from_block_rejects_a_non_bool_dirty(self):
        assert from_block({"dirty": "true"}).dirty is None


# --------------------------------------------------------------------------
# AC7 / security — untrusted values are single-line tokens or nothing
# --------------------------------------------------------------------------


class TestRunIdSanitisation:
    @pytest.mark.parametrize("bad", [
        "run\nSource-State: run=forged",   # banner forgery via newline
        "run\r\nGenerated: fake",
        "run\twith-tab",
        "run\x00null",
        "   ",
        "",
        None,
        123,
    ])
    def test_unusable_values_become_none(self, bad):
        assert safe_run_id(bad) is None

    def test_a_forged_newline_cannot_produce_a_second_banner_line(self):
        line = banner_line(SourceState(run_id="run\nSource-State: run=forged"))
        assert line.count(BANNER_PREFIX) == 1
        assert "\n" not in line
        assert UNKNOWN_RUN in line

    def test_surrounding_whitespace_is_trimmed_not_rejected(self):
        assert safe_run_id(f"  {RUN}  ") == RUN


# --------------------------------------------------------------------------
# AC5 — the strip regex is anchored (must not eat document body or layout)
# --------------------------------------------------------------------------


class TestBannerStripRegex:
    def test_strips_an_anchored_banner_line(self):
        text = f"# RTM\nGenerated: x\n{banner_line(SourceState(run_id=RUN))}\nbody\n"
        assert BANNER_STRIP_RE.sub("", text) == "# RTM\nGenerated: x\nbody\n"

    def test_does_not_strip_a_mid_line_occurrence(self):
        # Mirrors the existing Generated:-line guarantee in test_audit_staleness.
        text = f"the {BANNER_PREFIX} token appears mid-line\n"
        assert BANNER_STRIP_RE.sub("", text) == text

    def test_does_not_consume_the_blank_line_below_the_header(self):
        text = f"{banner_line(SourceState(run_id=RUN))}\n\nbody\n"
        assert BANNER_STRIP_RE.sub("", text) == "\nbody\n"

    def test_crlf_document_keeps_its_layout(self):
        text = f"# RTM\r\n{banner_line(SourceState(run_id=RUN))}\r\n\r\nbody\r\n"
        out = BANNER_STRIP_RE.sub("", text)
        assert "run=" not in out
        assert out == "# RTM\r\n\r\nbody\r\n"

    def test_strips_every_occurrence(self):
        one = banner_line(SourceState(run_id=RUN))
        assert BANNER_STRIP_RE.sub("", f"{one}\nmid\n{one}\n") == "mid\n"


# --------------------------------------------------------------------------
# AC2 / AC7 — git resolution, including every way git can be unavailable
# --------------------------------------------------------------------------


class TestGitResolution:
    def test_clean_repo_resolves_head_and_not_dirty(self, repo: Path):
        state = resolve_git_state(repo, run_id=RUN)
        assert state.run_id == RUN
        assert state.commit is not None and len(state.commit) == 40
        assert state.dirty is False

    def test_tracked_modification_is_dirty(self, repo: Path):
        (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
        assert resolve_git_state(repo).dirty is True

    def test_untracked_file_alone_is_not_dirty(self, repo: Path):
        # A scratch file does not change which code the tests ran against.
        (repo / "scratch.log").write_text("noise\n", encoding="utf-8")
        assert resolve_git_state(repo).dirty is False

    def test_the_stamped_artifact_itself_does_not_make_the_tree_dirty(self, repo: Path):
        # The reason this exclusion exists: the stamp runs AFTER the record is
        # written, so without it `dirty` would be True on every single run and
        # the field would carry no information at all.
        results = repo / "shipwright_test_results.json"
        results.write_text("{}\n", encoding="utf-8")
        _git(["add", "shipwright_test_results.json"], repo)
        _git(["commit", "-qm", "add results"], repo)
        results.write_text('{"unit": {"total": 1}}\n', encoding="utf-8")
        assert resolve_git_state(repo).dirty is True
        assert resolve_git_state(
            repo, exclude_paths=("shipwright_test_results.json",)
        ).dirty is False

    def test_excluding_the_artifact_still_sees_a_real_source_change(self, repo: Path):
        (repo / "tracked.txt").write_text("v2\n", encoding="utf-8")
        state = resolve_git_state(repo, exclude_paths=("shipwright_test_results.json",))
        assert state.dirty is True

    def test_non_repo_degrades_to_none_and_keeps_the_run_id(self, tmp_path: Path):
        state = resolve_git_state(tmp_path, run_id=RUN)
        assert state.commit is None
        assert state.dirty is None
        assert state.run_id == RUN

    def test_empty_repo_with_no_head_degrades(self, tmp_path: Path):
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                       check=True, capture_output=True, text=True, timeout=30)
        state = resolve_git_state(tmp_path, run_id=RUN)
        assert state.commit is None
        assert state.run_id == RUN

    def test_missing_git_binary_does_not_raise(self, repo: Path, monkeypatch):
        def boom(*a, **k):
            raise FileNotFoundError("git")
        monkeypatch.setattr(subprocess, "run", boom)
        state = resolve_git_state(repo, run_id=RUN)
        assert (state.commit, state.dirty, state.run_id) == (None, None, RUN)

    def test_git_timeout_does_not_raise(self, repo: Path, monkeypatch):
        def boom(*a, **k):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)
        monkeypatch.setattr(subprocess, "run", boom)
        assert resolve_git_state(repo).commit is None

    def test_git_is_never_invoked_through_a_shell(self, repo: Path, monkeypatch):
        seen: list[dict] = []
        real = subprocess.run

        def spy(*a, **k):
            seen.append(k)
            return real(*a, **k)
        monkeypatch.setattr(subprocess, "run", spy)
        resolve_git_state(repo)
        assert seen, "expected at least one git invocation"
        for kwargs in seen:
            assert kwargs.get("shell", False) is False
            assert kwargs.get("timeout") is not None

    def test_an_unusable_run_id_is_dropped_at_resolution(self, repo: Path):
        assert resolve_git_state(repo, run_id="bad\nvalue").run_id is None


class TestTokenCollisionRegression:
    """A run id containing a status word must not be read as that status.

    Found in self-review: ``"clean" in line`` matched ``iterate-2026-07-27-cleanup``
    and turned an unresolved ``dirty`` into a confident ``False`` — the banner would
    have asserted "clean tree" about a tree git was never asked about. SIMPLIFY-mode
    runs are named exactly like that, so this was reachable, not theoretical.
    """

    @pytest.mark.parametrize("run_id", [
        "iterate-2026-07-27-cleanup",
        "iterate-2026-07-27-declutter-clean",
        "iterate-2026-07-27-uncommitted-changes-audit",
    ])
    def test_unknown_dirty_stays_unknown(self, run_id):
        parsed = parse_banner_line(banner_line(SourceState(run_id=run_id, dirty=None)))
        assert parsed.run_id == run_id
        assert parsed.dirty is None

    @pytest.mark.parametrize("dirty", [True, False])
    def test_a_colliding_run_id_still_round_trips_a_real_flag(self, dirty):
        state = SourceState(run_id="iterate-2026-07-27-cleanup", commit=SHA, dirty=dirty)
        assert parse_banner_line(banner_line(state)) == state.abbreviated()


class TestExternalReviewRegressions:
    """Two defects external code review found in the first implementation.

    Both were forgery paths: a run id containing whitespace could inject a *status
    token* into the whitespace-delimited banner, and the control-character check was
    ASCII-only so Unicode line separators passed through.
    """

    @pytest.mark.parametrize("bad", [
        "run one",                    # parsed back as "run"
        "x clean",                    # forges dirty=False
        "x uncommitted-changes",      # forges dirty=True
        "x commit=deadbeefcafe",      # forges a commit
        "run\u00a0nbsp",              # non-breaking space
    ])
    def test_whitespace_bearing_run_ids_are_refused(self, bad):
        assert safe_run_id(bad) is None
        assert UNKNOWN_RUN in banner_line(SourceState(run_id=bad))

    @pytest.mark.parametrize("bad", ["a\u2028b", "a\u2029b", "a\u0085b", "a\u200eb"])
    def test_unicode_control_and_separator_chars_are_refused(self, bad):
        assert safe_run_id(bad) is None

    def test_a_forged_status_token_cannot_reach_the_parser(self):
        # The end-to-end property: whatever the run id, a banner built from a state
        # with dirty=None never parses back as a definite clean/dirty verdict.
        for attempt in ("x clean", "x uncommitted-changes", "plain-run"):
            parsed = parse_banner_line(banner_line(SourceState(run_id=attempt)))
            assert parsed.dirty is None

    def test_a_forged_commit_token_cannot_reach_the_parser(self):
        parsed = parse_banner_line(banner_line(SourceState(run_id="x commit=deadbeefcafe")))
        assert parsed.commit is None


class TestCommitIsValidatedOnBothSides:
    """`commit` bypassed validation in the first implementation (external review).

    Write side: an unvalidated commit could carry whitespace and inject a forged
    status token. Read side: ``commit=([0-9a-fA-F]+)`` was a substring search, so a
    run id that is a perfectly legal single token —
    ``iterate-2026-07-27-commit=deadbeef`` — parsed back carrying a commit nobody
    resolved.
    """

    @pytest.mark.parametrize("bad", [
        "a clean", "not-hex", "abc", "", None, 42,
        "deadbeefcafe\nSource-State: run=forged",
        "g" * 12,
    ])
    def test_implausible_commits_are_refused(self, bad):
        assert safe_commit(bad) is None

    @pytest.mark.parametrize("good", ["deadbee", SHA, SHA[:12]])
    def test_plausible_commits_are_accepted(self, good):
        assert safe_commit(good) == good

    def test_a_forged_commit_bearing_run_id_does_not_yield_a_commit(self):
        state = SourceState(run_id="iterate-2026-07-27-commit=deadbeefcafe")
        parsed = parse_banner_line(banner_line(state))
        assert parsed.commit is None, "a run id was read back as a commit"
        assert parsed.run_id == state.run_id

    def test_a_junk_commit_never_reaches_the_banner(self):
        line = banner_line(SourceState(run_id=RUN, commit="a clean"))
        assert line.count(BANNER_PREFIX) == 1
        assert "\n" not in line
        assert parse_banner_line(line).commit is None
        assert parse_banner_line(line).dirty is None

    def test_a_junk_commit_serialises_as_null(self):
        assert to_block(SourceState(run_id=RUN, commit="nope"))["commit"] is None


class TestUnsubstitutedPlaceholderRefused:
    """A literal ``{run_id}`` must never be stamped as a run id.

    Every caller is a runtime prompt, so an unsubstituted template placeholder is the
    realistic failure — external code review found exactly that in a call site. It is
    otherwise a well-formed token, so no other check would catch it, and stamping it
    would make a record confidently name a run that does not exist.
    """

    @pytest.mark.parametrize("bad", ["{run_id}", "{{run_id}}", "iterate-{date}-x", "a}b"])
    def test_placeholder_shaped_values_are_refused(self, bad):
        assert safe_run_id(bad) is None

    def test_the_banner_says_unknown_rather_than_echoing_the_placeholder(self):
        line = banner_line(SourceState(run_id="{run_id}"))
        assert f"run={UNKNOWN_RUN}" in line
        assert "{run_id}" not in line
