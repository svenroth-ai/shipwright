"""The observed-baseline input, and the consumer that reads the result.

Split from ``test_inherited_baseline.py`` (300-LOC cap). Two concerns:

1. **`parse_observed_failures` fails closed.** "Observed" is a claim about a
   test run that actually happened. A hand-written list of test names is not
   one, and a malformed payload must not degrade into an empty register that
   silently reads as a clean inheritance.
2. **the register round-trips through the real shared reader** —
   `shared/scripts/known_failures.load_accepted_baseline`, which since #453 is
   the ONE reader both the audit and the test phase go through. Testing against
   a plugin-local copy would prove agreement with the wrong thing.

@FR-01.13
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.inherited_baseline import (  # noqa: E402
    BaselineInputError,
    build_register,
    parse_observed_failures,
    write_register,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _register(observed=None) -> dict:
    """A minimal register. Deliberately built here rather than imported from the
    sibling test module — a cross-test import would tie two files together for
    six lines and break under a different pytest invocation root."""
    return build_register(
        fr_ids=["FR-01.01"], backfill_report={}, skip_inventory=[],
        observed=observed, adopted_at="2026-07-27T00:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# Fails closed (external review O7, O9)
# --------------------------------------------------------------------------- #

def test_a_failure_list_without_provenance_is_rejected() -> None:
    """A hand-written list of test names is not an observed baseline. Without
    the command that produced it, "observed" would be a claim nobody made."""
    with pytest.raises(BaselineInputError):
        parse_observed_failures({"failing_tests": [{"test": "a"}]})


@pytest.mark.parametrize("bad", [
    [],
    {"source": "s", "command": "c", "failing_tests": "nope"},
    {"source": "s", "command": "c", "failing_tests": [{"test": ""}]},
    {"source": "s", "command": "c", "failing_tests": ["a"]},
    {"source": "s", "command": "", "failing_tests": []},
])
def test_a_malformed_payload_is_rejected_rather_than_read_as_empty(bad) -> None:
    with pytest.raises(BaselineInputError):
        parse_observed_failures(bad)


def test_a_declared_count_that_disagrees_with_the_list_is_rejected() -> None:
    with pytest.raises(BaselineInputError):
        parse_observed_failures({
            "source": "s", "command": "c", "baseline_failure_count": 9,
            "failing_tests": [{"test": "a"}],
        })


def test_only_the_fields_the_audit_phase_reads_are_copied() -> None:
    """External review O9. The payload may be produced from raw test output; a
    stray environment dump must not be copied into a committed artifact."""
    observed = parse_observed_failures({
        "source": "s", "command": "c",
        "failing_tests": [{
            "test": "a", "description": "d", "ticket": "T-1", "added": "2026-07-27",
            "count": 1,
            "env": {"AWS_SECRET_ACCESS_KEY": "hunter2"},
            "stdout": "…traceback with /home/me/.ssh/id_rsa…",
        }],
    })
    entry = observed.failures[0]
    assert set(entry) == {"test", "description", "ticket", "added", "count"}
    assert "hunter2" not in json.dumps(entry)


def test_count_defaults_to_one_and_must_be_a_positive_integer() -> None:
    ok = parse_observed_failures({"source": "s", "command": "c",
                                  "failing_tests": [{"test": "a"}]})
    assert ok.failures[0]["count"] == 1
    with pytest.raises(BaselineInputError):
        parse_observed_failures({"source": "s", "command": "c",
                                 "failing_tests": [{"test": "a", "count": 0}]})


# --------------------------------------------------------------------------- #
# The boundary probe — the real consumer, in its own interpreter
# --------------------------------------------------------------------------- #

_READER_PROBE = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from known_failures import load_accepted_baseline
b = load_accepted_baseline(Path(sys.argv[2]))
print(json.dumps({
    "baseline": b.baseline_failure_count,
    "present": b.present,
    "malformed": b.malformed,
    "failures": [{"test": e.test, "count": e.count} for e in b.entries],
}))
"""


def _read_back_through_the_consumer(project_root: Path) -> dict:
    """Run the REAL compliance collector against the register adopt wrote.

    In a SUBPROCESS, deliberately (ADR-045): the collector lives under its own
    ``scripts.lib`` package, and importing it into adopt's test session would
    bind a second ``lib``/``scripts`` beside the plugin's own — the shadowing
    collision that discipline forbids. ``seed_traceability_baseline``
    subprocesses the backfill engine for exactly the same reason.

    A failure here is a FAILURE, never a skip: an unverified producer/consumer
    boundary is the defect class this test exists to catch.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _READER_PROBE,
         str(REPO_ROOT / "shared" / "scripts"), str(project_root)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, (
        "the compliance collector could not be run, so the producer/consumer "
        f"boundary is unverified:\n{proc.stderr}"
    )
    return json.loads(proc.stdout)


def test_the_shared_reader_reads_back_what_adopt_wrote(tmp_path: Path) -> None:
    """The producer's shape is the one the ONE reader parses, and the additive
    keys adopt writes beside it are inert there."""
    observed = parse_observed_failures({
        "source": "s", "command": "pytest -q",
        "failing_tests": [{"test": "a::b", "description": "d", "count": 2}],
    })
    write_register(tmp_path, _register(observed=observed))

    read_back = _read_back_through_the_consumer(tmp_path)
    assert read_back["baseline"] == 2
    assert read_back["failures"] == [{"test": "a::b", "count": 2}]
    assert read_back["present"] is True and read_back["malformed"] is False


def test_an_unobserved_register_reads_as_zero_baseline_not_as_forgiveness(
    tmp_path: Path,
) -> None:
    """Today's consumer does not yet understand `baseline_observed` (that half
    is `trg-12b4cf3f`). What it must NOT do is read an unobserved register as a
    licence to excuse failures — so the count stays 0, exactly as it is when no
    file exists at all."""
    write_register(tmp_path, _register())
    back = _read_back_through_the_consumer(tmp_path)
    assert back["baseline"] == 0 and back["failures"] == []
    # `present` and `baseline_observed` are DIFFERENT facts and this pins the
    # distinction: the reader sees a well-formed declaration (present=True,
    # malformed=False) describing a run that never happened.
    assert back["present"] is True and back["malformed"] is False


@pytest.mark.parametrize("bad", [
    {"source": {"token": "secret"}, "command": "c", "failing_tests": []},
    {"source": "s", "command": [], "failing_tests": []},
    {"source": 42, "command": "c", "failing_tests": []},
    {"source": "s", "command": None, "failing_tests": []},
])
def test_source_and_command_must_be_real_strings(bad) -> None:
    """`str({"token": "secret"})` is a non-empty string, so a coerce-then-truthy
    check accepts an object and persists its repr as `baseline_source` — which
    reopens the very boundary that dropping the command closed."""
    with pytest.raises(BaselineInputError, match="non-empty string"):
        parse_observed_failures(bad)


def test_a_source_label_has_a_ceiling() -> None:
    """It is a short name for a run, and it lands in a committed file. A field
    with no ceiling is a field someone eventually pastes test output into."""
    with pytest.raises(BaselineInputError, match="short label"):
        parse_observed_failures({
            "source": "x" * 500, "command": "pytest -q", "failing_tests": [],
        })
