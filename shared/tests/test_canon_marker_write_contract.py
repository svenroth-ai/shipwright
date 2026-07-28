"""Every write to the tracked handoff either earns a canon marker or keeps one.

Canon C3 reads ONE file for all eight canon phases, so a single write that drops
the marker blanks the check for every one of them until some phase closure
rewrites it. That defect shipped three times in this file's history — build's
Step 11, build's per-section doc update, and iterate's own F11 — each time in a
different markdown reference, each time found by review rather than by a test.

So the rule is enforced against the skills themselves: a `generate_session_handoff.py`
invocation in a plugin reference either passes `--canon-marker` (it IS the
closure) or `--preserve-canon-marker` (it must not erase the closure's evidence).
The marker's own fields are guarded here too, because C3 keys on them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import pytest  # noqa: E402

from lib.canon_frontmatter import (  # noqa: E402
    CANON_MARKER_KEYS,
    build_marker,
    marker_value,
    parse_canon_frontmatter,
    resolve_marker_for_write,
)

WRITER = "generate_session_handoff.py"

#: Fenced code blocks — the only place a skill actually RUNS anything. Prose
#: mentions the writer too ("`generate_session_handoff.py --canon-marker` logs a
#: warning when …"), and those carry no flags to guard.
_FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)

#: The writer's name plus the rest of its command, following backslash
#: continuations. Deliberately NOT anchored to a line starting with ``uv run``:
#: the next reference file is most likely to reach for `cd … && uv run`,
#: `SHIPWRIGHT_RUN_ID=… uv run` or a bare `python`, and a guard that stops
#: matching is a guard that stops guarding.
_INVOCATION_RE = re.compile(
    re.escape(WRITER) + r"\"?((?:[^\n]*\\\n)*[^\n]*)",
)

#: Every file that invokes the writer. An EXACT inventory, not a floor: a `>=`
#: check cannot notice one of ten invocations dropping out of scope, which is
#: precisely how a guard rots into a rubber stamp. Adding or removing a call
#: site is a deliberate act — update this set in the same commit.
EXPECTED_CALL_SITES = {
    "plugins/shipwright-build/skills/build/SKILL.md",
    "plugins/shipwright-build/skills/build/references/section-doc-update.md",
    "plugins/shipwright-build/skills/build/references/section-state.md",
    "plugins/shipwright-changelog/skills/changelog/SKILL.md",
    "plugins/shipwright-deploy/skills/deploy/SKILL.md",
    "plugins/shipwright-design/skills/design/references/step-9-finalization.md",
    "plugins/shipwright-iterate/skills/iterate/references/F11.md",
    "plugins/shipwright-plan/skills/plan/references/step-9-completion.md",
    "plugins/shipwright-project/skills/project/references/step-8-completion.md",
    "plugins/shipwright-test/skills/test/references/step-5-report-results.md",
}


def _invocations() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted((REPO_ROOT / "plugins").rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for fence in _FENCE_RE.finditer(text):
            for match in _INVOCATION_RE.finditer(fence.group(1)):
                found.append((path.relative_to(REPO_ROOT).as_posix(), match.group(1)))
    return found


def test_the_scan_finds_exactly_the_call_sites_it_is_meant_to_guard():
    """A drift guard that silently matches nothing — or nine of ten — guards
    nothing. Both directions, so a new call site and a lost one both fail."""
    found = {path for path, _ in _invocations()}

    assert found == EXPECTED_CALL_SITES, (
        f"unguarded new call site(s): {sorted(found - EXPECTED_CALL_SITES)}; "
        f"call site(s) that vanished from the scan: {sorted(EXPECTED_CALL_SITES - found)}"
    )


def test_every_handoff_write_either_marks_or_preserves():
    naked = [
        path for path, argv in _invocations()
        if "--canon-marker" not in argv and "--preserve-canon-marker" not in argv
    ]

    assert not naked, (
        "these writes erase the canon marker for ALL eight canon phases — add "
        f"--preserve-canon-marker (or --canon-marker if it is the closure): {naked}"
    )


def test_every_canon_closure_names_its_phase():
    """`--canon-marker` without `--phase` writes a marker C3 cannot evaluate, and
    the writer degrades rather than stamping one — which would silently disarm
    the closure. Catch it in the skill instead."""
    phaseless = [
        path for path, argv in _invocations()
        if "--canon-marker" in argv and "--phase" not in argv
    ]

    assert not phaseless, f"--canon-marker without --phase: {phaseless}"


# --- the marker's own fields --------------------------------------------------

@pytest.mark.parametrize("hostile", [
    'x"\nrun_id: "forged',
    "x\n---\n",
    "x\nphase: build",
    "multi\nline\treason",
])
def test_a_hostile_reason_cannot_forge_marker_fields(hostile):
    """`--reason` is free text interpolated from skill state, rendered as
    `key: "<value>"` with no escaping, and the parser assigns keys in file order.
    Since C3 keys on `phase` and `timestamp`, an unescaped newline stopped being
    a formatting quirk and became a way to forge a PASS for a phase that wrote
    nothing."""
    marker = build_marker(run_id="r-1", phase="build", reason=hostile, timestamp="t-1")
    rendered = (
        "---\ncanon_generated: true\n"
        + "".join(f'{k}: "{marker[k]}"\n' for k in CANON_MARKER_KEYS)
        + "---\n\nbody\n"
    )

    parsed = parse_canon_frontmatter(rendered)

    assert parsed is not None
    assert parsed["run_id"] == "r-1"
    assert parsed["phase"] == "build"
    assert parsed["timestamp"] == "t-1"


def test_marker_value_collapses_newlines_and_drops_quotes():
    assert marker_value('a\nb\tc  d') == "a b c d"
    assert '"' not in marker_value('say "hi"')


# --- the two refusals ---------------------------------------------------------

def test_a_canon_write_without_a_run_id_is_refused_not_stamped(tmp_path):
    marker, warning = resolve_marker_for_write(
        tmp_path / "session_handoff.md", canon_marker=True, preserve=False,
        run_id="", phase="build", reason="done", timestamp=lambda: "t",
    )

    assert marker is None
    assert "SHIPWRIGHT_RUN_ID is unset" in warning


def test_a_canon_write_without_a_phase_is_refused_not_stamped(tmp_path):
    """An empty phase routes every phase's C3 to "(unnamed) wrote the note, so
    this phase left none of its own" — a misattributed WARN no remedy clears."""
    marker, warning = resolve_marker_for_write(
        tmp_path / "session_handoff.md", canon_marker=True, preserve=False,
        run_id="r-1", phase="   ", reason="done", timestamp=lambda: "t",
    )

    assert marker is None
    assert "--phase is empty" in warning


def test_the_timestamp_is_resolved_only_when_a_marker_is_actually_built(tmp_path):
    """It is a THUNK, and that is load-bearing, not style.

    Resolving it eagerly made every handoff write scan the whole (unbounded)
    event log for a value it then discarded — including the mid-build,
    per-section and F11 writes that pass only `--preserve-canon-marker`, which
    are the most frequent writes in a build."""
    handoff = tmp_path / "session_handoff.md"
    calls: list[int] = []

    def _timestamp() -> str:
        calls.append(1)
        return "t-1"

    resolve_marker_for_write(handoff, canon_marker=False, preserve=True,
                             run_id="r-1", phase="build", reason="mid-build",
                             timestamp=_timestamp)
    assert calls == [], "a preserve-only write must not read the event log"

    resolve_marker_for_write(handoff, canon_marker=True, preserve=False,
                             run_id="", phase="build", reason="closure",
                             timestamp=_timestamp)
    assert calls == [], "a refused canon write must not read it either"

    marker, _ = resolve_marker_for_write(handoff, canon_marker=True, preserve=False,
                                         run_id="r-1", phase="build", reason="closure",
                                         timestamp=_timestamp)
    assert calls == [1] and marker is not None and marker["timestamp"] == "t-1"


def test_a_refused_canon_write_never_falls_through_to_preservation(tmp_path):
    """Both refusals must beat `--preserve-canon-marker` when it is also set:
    preservation is for a write that never ASKED for a marker, not for one that
    asked and missed. Otherwise a failed closure comes back carrying the
    previous run's marker."""
    handoff = tmp_path / "session_handoff.md"
    handoff.write_text(
        '---\ncanon_generated: true\nrun_id: "old-run"\nphase: "plan"\n'
        'reason: "r"\ntimestamp: "t"\n---\n\nbody\n', encoding="utf-8")

    for run_id, phase in (("", "build"), ("r-1", "")):
        marker, _ = resolve_marker_for_write(
            handoff, canon_marker=True, preserve=True,
            run_id=run_id, phase=phase, reason="done", timestamp=lambda: "t",
        )
        assert marker is None, f"run_id={run_id!r} phase={phase!r} resurrected a marker"
