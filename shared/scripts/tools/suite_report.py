#!/usr/bin/env python3
"""Every operator-facing string of an F0 suite run - console block and triage card.

Pure composition: a `SuiteResult` (or one sanitized `RaceFacts`) in, lines of text
out. No I/O, no store, no subprocess. `run_test_suite.py` orchestrates and prints;
`suite_race_triage.py` persists. Keeping BOTH surfaces here is the point: the sentence
the console shows about a raced unit and the card that outlives the session are then
provably the same statement, not two copies that drift.

Two invariants live here because they are properties of the TEXT:

- **Allowlist, not reflection.** A card is assembled from named scalar fields (unit
  id, two exit codes, one boolean, two commands, fixed prose). A result object, an
  exception repr or a captured-output field can never reach it, so a later edit
  cannot leak test output into a log that is committed and published. The captured
  output IS printed - but only to the console, by `render_run_report`.
- **Untrusted-looking text is neutralised once, here.** Control characters stripped,
  lengths capped deterministically, anything entering a command `shlex`-quoted.

ASCII-only, like its callers: a cp1252 console raises UnicodeEncodeError on non-ASCII,
which on the retry path would abort the very gate this keeps honest (#244). Pinned by
`test_operator_facing_strings_are_ascii_only`.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_units import INFRA, PASS, TEST_FAILURE, UV_RUN  # noqa: E402

TRUNCATION_MARKER = "FAULT: output tail truncated to the bounded diagnostic limit\n"

#: dedup-key namespace for the race producer (one OPEN entry per unit)
DEDUP_PREFIX = "f0-race:"
_RUNNER = "shared/scripts/tools/run_test_suite.py"

MAX_TITLE = 160
MAX_DETAIL = 2000
MAX_UNIT_ID = 80

_TAGS = {PASS: "PASS", TEST_FAILURE: "FAIL", INFRA: "FAULT"}


@dataclass(frozen=True)
class RaceFacts:
    """The measured facts about one confirmed race, sanitized once.

    Two forms of the unit id, deliberately: `unit_key` is IDENTITY (control chars
    stripped so it cannot break a payload, but never truncated - two units sharing a
    prefix must not collapse onto one dedup key), `unit_id` is DISPLAY (also capped).
    """

    unit_id: str
    unit_key: str
    parallel_rc: int
    alone_rc: int
    xdist_allowlisted: bool
    alone_command: str


# --- sanitation -----------------------------------------------------------------

def clean(text: object, cap: int | None = None) -> str:
    """Strip non-printables (control chars, newlines); cap only when asked.

    Unit ids are repo-derived and validated against the discovered set today; this is
    defence in depth, and what FR-01.14 requires of any entry text the project does
    not author (it must not take over the display it appears in). `cap=None` is for
    values whose IDENTITY or executability matters more than their length - a dedup
    key or a paste-me command truncated mid-quote is worse than a long one.
    """
    printable = "".join(ch for ch in str(text) if ch.isprintable())
    return printable if cap is None else printable[:cap]


def reproduce_command(cwd: str, argv: list[str]) -> str:
    """Render an argv the operator can paste, quoted for a POSIX shell.

    The runner executes units with `cwd=project_root/unit.cwd`, so a plugin unit
    needs its directory or the command reproduces nothing.
    """
    joined = shlex.join(argv)
    return joined if cwd in ("", ".") else f"cd {shlex.quote(cwd)} && {joined}"


def suite_command(project_root, run_id: str | None = None) -> str:
    """The whole-suite command AS INVOKED - not a plausible-looking substitute.

    A hard-coded `--project-root .` is wrong for every run launched from anywhere
    but the project root, and a Fix-now command that quietly targets the wrong tree
    is worse than none. Same reasoning pins the interpreter: this string is published
    in a tracked triage card, and a card that resolves a different Python than the run
    it claims to reproduce is the plausible-looking substitute this docstring refuses.
    """
    argv = [*UV_RUN, _RUNNER, "--project-root", str(project_root)]
    if run_id:
        argv += ["--run-id", run_id]
    return shlex.join(argv)


def facts(result, xdist_ids) -> RaceFacts:
    """Build the fact record for one CONFIRMED race - the allowlist in action.

    Membership is tested against the RAW id (accurate); everything rendered uses a
    sanitized form (safe).
    """
    return RaceFacts(
        unit_id=clean(result.unit_id, MAX_UNIT_ID),
        unit_key=clean(result.unit_id),
        parallel_rc=int(result.rc),
        alone_rc=int(result.serial_rc if result.serial_rc is not None else 0),
        xdist_allowlisted=result.unit_id in tuple(xdist_ids or ()),
        alone_command=clean(getattr(result, "retry_cmd", "") or ""),
    )


def dedup_key(f: RaceFacts) -> str:
    """Keyed on IDENTITY, never on the truncated display form: two units sharing an
    80-character prefix must not suppress one another's card."""
    return DEDUP_PREFIX + f.unit_key


# --- the race card --------------------------------------------------------------

def race_note(f: RaceFacts) -> str:
    """The one canonical measured sentence. Console and card both quote it."""
    if f.xdist_allowlisted:
        tail = ("It IS on the suite.xdist allowlist, so the fan-out inside the unit "
                "is a candidate cause: fix it, or drop it from suite.xdist.")
    else:
        tail = ("It is NOT xdist-allowlisted, so this is inter-unit pollution or an "
                "unreliable test.")
    return (f"{f.unit_id}: red in parallel (rc {f.parallel_rc}), GREEN alone "
            f"(rc {f.alone_rc}). {tail}")


def entry_title(f: RaceFacts) -> str:
    return clean(
        f"[f0] {f.unit_id} failed in parallel and passed alone - race or flaky test",
        MAX_TITLE)


def entry_detail(f: RaceFacts, suite_cmd: str) -> str:
    """The card body. Scalars and fixed prose only - never captured test output: this
    log is committed and published (constitution: nothing sensitive in a tracked
    artifact), and the failing text is already in that run's F0 console."""
    body = (
        f"{race_note(f)}\n"
        "\n"
        "The F0 suite runner ran this unit twice. With every unit running side by "
        f"side it reported a pytest test failure (exit {f.parallel_rc}). Re-run "
        "ALONE - after the pool drained, without xdist, in a clean temp dir - it "
        f"PASSED (exit {f.alone_rc}). That alone-run verdict is authoritative, so the "
        "gate was NOT stopped.\n"
        "\n"
        "The runner cannot tell which of these it is:\n"
        "  - a race between concurrently running units (shared state, ports, temp "
        "files, the shared working tree), or\n"
        "  - a test that fails intermittently on its own.\n"
        "Both are real defects; only measurement separates them.\n"
        "\n"
        "Reproduce the unit exactly as the runner re-ran it (expect GREEN):\n"
        f"  {f.alone_command or '(command not captured)'}\n"
        "Reproduce the whole suite in parallel (expect the intermittent red):\n"
        f"  {suite_cmd}\n"
        "\n"
        "The failing output stayed in that run's F0 console and is deliberately not "
        "copied here.\n"
        "\n"
        "This entry is never closed automatically: one clean parallel run is not "
        "evidence the race is gone. Close it when the unit is fixed, or dismiss it "
        "deliberately."
    )
    if len(body) <= MAX_DETAIL:
        return body
    return body[:MAX_DETAIL - 14].rstrip() + " ... [truncated]"


def launch_payload(f: RaceFacts, suite_cmd: str) -> str:
    """The Fix-now block the inbox / Command Center offers for copy-paste.

    Deliberately NOT length-capped: both commands must stay executable, and a
    command truncated mid-quote is a broken CTA, not a shorter one.
    """
    return (
        "/shipwright-iterate --type bug\n"
        "\n"
        f"Context: F0 suite card {dedup_key(f)}. The test unit {f.unit_id} failed "
        "while the units ran side by side and passed when re-run alone, so the gate "
        "stayed green and nothing else recorded it.\n"
        f"Reproduce alone (expect GREEN): {f.alone_command or 'n/a'}\n"
        f"Reproduce in parallel (expect intermittent RED): {suite_cmd}\n"
        "Establish whether it is a race between units or an unreliable test, fix the "
        "cause, and close this card. Never weaken or delete the test to make it pass."
    )


# --- the console --------------------------------------------------------------

def render_run_report(result) -> list[str]:
    """Summary table, then the captured output of anything that failed or retried."""
    lines = []
    for res in sorted(result.results, key=lambda r: -r.seconds):
        note = "  [passed on a retry - gate not stopped]" if res.race else ""
        lines.append(f"  {_TAGS[res.outcome]:5} {res.seconds:7.1f}s  "
                     f"{res.unit_id}{note}")
    for res in result.results:  # output for what failed AND for a retry (its evidence)
        if res.outcome != PASS or res.race:
            serial = f", retry rc={res.serial_rc}" if res.serial_rc is not None else ""
            output = ((TRUNCATION_MARKER if getattr(res, "truncated", False) else "")
                      + res.output)
            lines.append(f"\n{'=' * 70}\n{res.unit_id} "
                         f"({'RETRY-GREEN' if res.race else res.outcome}, "
                         f"rc={res.rc}{serial})\n{'=' * 70}\n{output}")
            if getattr(res, "evidence_path", None):
                lines.append(f"  bounded diagnostic evidence: {res.evidence_path}")
            if getattr(res, "retry_evidence_path", None):
                lines.append(f"  retry diagnostic evidence: {res.retry_evidence_path}")
        if getattr(res, "evidence_error", None):
            lines.append(f"  FAULT: diagnostic evidence could not be retained for "
                         f"{res.unit_id}: {clean(res.evidence_error, 300)}")
    lines.append(f"\nF0 suite: {len(result.results)} units in "
                 f"{result.seconds / 60:.1f} min "
                 f"-> {'GREEN' if result.exit_code == 0 else 'RED'}")
    return lines


def render_retry_block(result, races, report) -> list[str]:
    """The block for every unit that passed only on a retry.

    Partitions by the caller-supplied confirmed-race list - it does not reclassify.
    Rendered AFTER persistence so each raced unit carries its durable handle (or an
    unmissable recording failure) rather than a warning to be agreed with.
    """
    retried = [r for r in result.results if r.race]
    if not retried:
        return []
    race_ids = {r.unit_id for r in races}
    # Bound to a name first: an implicitly-concatenated string INSIDE a list literal
    # reads as a missing comma (CodeQL py/implicit-string-concatenation-in-list).
    header = ("WARNING: unit(s) passed only on a retry, so the gate is GREEN but "
              "they are not sound:")
    lines = ["", header]
    for res in retried:
        if res.unit_id not in race_ids:
            lines.append(f"  {res.unit_id}: infrastructure fault (rc {res.rc}) that "
                         "did NOT reproduce - most likely contention between "
                         "concurrent units.")
            continue
        note = race_note(facts(res, result.xdist_ids))
        handle = report.recorded.get(res.unit_id)
        if handle == report.UNRESOLVED:
            lines.append(f"  {note} Already tracked as an open entry in "
                         ".shipwright/triage.jsonl (id could not be read back).")
        elif handle:
            lines.append(f"  {note} Tracked as {handle} in .shipwright/triage.jsonl "
                         "- committed with this run, so it outlives the session.")
        else:
            reason = report.failed.get(res.unit_id, "reason unknown")
            lines.append(f"  {note} *** FAILED TO RECORD: {reason} *** This "
                         "observation would be lost, so F0 stops instead.")
    return lines
