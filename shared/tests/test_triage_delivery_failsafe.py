"""Delivery-side fail-safes: the CI routing decision, the single CI predicate,
and the atomic-write retry counter.

F1 drift detection (AC-7) lives in ``test_artifact_sync_drift_failsafe.py``, split
out when this module crossed the 300-line guideline.

Run-ID: iterate-2026-07-31-triage-store-failsafe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from lib import atomic_write as aw  # noqa: E402
from lib.ci_env import ci_active  # noqa: E402

# NOTE: the two `_f1_record` tests that used to live here now sit in
# `shared/scripts/tools/tests/test_finalize_bundle_f1_record.py`. Importing
# `finalize_bundle` from THIS root is order-dependent by construction — see that
# module's docstring for the measured mechanism.


# ---------------------------------------------------------------------------
# AC-9 — a card filed under CI must reach the TRACKED store
# ---------------------------------------------------------------------------

@pytest.fixture
def origin_repo_on_default(git_origin_repo):
    """A REAL repo with an `origin` and HEAD on the default branch.

    A plain `tmp_path` is not good enough and that is the whole point: with no origin
    and no git, `should_route_to_outbox` already returns False through its pre-existing
    "every no-origin repo and git error fails safe to tracked" path — so a test built
    on tmp_path passes with OR without the CI guard. External review (GPT) caught
    that; measured before fixing: both CI-set and CI-unset returned False.
    """
    work, _origin = git_origin_repo
    subprocess.run(["git", "-C", str(work), "config", "user.email", "t@t.invalid"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)
    return work


def test_without_ci_an_idle_default_branch_DOES_route_to_the_outbox(
        origin_repo_on_default, monkeypatch) -> None:
    """The control. Without this the CI assertions below prove nothing."""
    monkeypatch.delenv("CI", raising=False)
    assert triage.should_route_to_outbox(origin_repo_on_default) is True


def test_ci_routes_to_the_tracked_store(origin_repo_on_default, monkeypatch) -> None:
    """On a runner both other conditions hold — so without the guard the card is
    buried in a gitignored file the runner then discards."""
    monkeypatch.setenv("CI", "true")
    assert triage.should_route_to_outbox(origin_repo_on_default) is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " true "])
def test_ci_truthy_spellings_all_route_to_tracked(
        origin_repo_on_default, monkeypatch, value) -> None:
    monkeypatch.setenv("CI", value)
    assert triage.should_route_to_outbox(origin_repo_on_default) is False


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsy_ci_still_routes_to_the_outbox(
        origin_repo_on_default, monkeypatch, value) -> None:
    """A falsy `$CI` must leave the predicate ALONE — asserted on the real predicate,
    not merely on `ci_active()`, so the guard cannot become a kill switch."""
    monkeypatch.setenv("CI", value)
    assert triage.should_route_to_outbox(origin_repo_on_default) is True


# ---------------------------------------------------------------------------
# AC-10 — ONE ci predicate, not five copies
# ---------------------------------------------------------------------------

def test_every_ci_predicate_delegates_to_the_shared_leaf(monkeypatch) -> None:
    """Both directions of drift protection for the de-duplicated helper.

    ``$CI`` is driven BOTH ways rather than compared at whatever the ambient value
    happens to be — doubt review pointed out that a module hardcoding `return False`
    passes locally and one hardcoding `return True` passes in Actions, so the
    single-value form proved nothing. Reverse direction: no module re-declares
    ``_CI_TRUTHY``, so a fifth copy cannot creep back in without failing here.
    """
    from lib import (
        gitattributes_selfheal,
        gitignore_selfheal,
        reconcile_triage,
        sweep_outbox,
    )

    modules = [gitattributes_selfheal, gitignore_selfheal, reconcile_triage, sweep_outbox]
    for value, expected in (("true", True), ("", False), ("1", True), ("0", False)):
        monkeypatch.setenv("CI", value)
        assert ci_active() is expected, value
        for mod in modules:
            assert mod._ci_active() is expected, f"{mod.__name__} at CI={value!r}"
    for mod in modules:
        assert not hasattr(mod, "_CI_TRUTHY"), (
            f"{mod.__name__} re-declares the CI vocabulary instead of importing it"
        )


def test_shared_leaf_has_no_intra_package_imports() -> None:
    """``ci_env`` is reached through ``load_shared_lib``, whose by-file-location
    fallback is documented as only safe for lib modules with NO intra-package
    imports. A ``from lib.x import`` here would break it in exactly the ADR-045
    collision that fallback exists to survive."""
    import ast

    tree = ast.parse((_SCRIPTS / "lib" / "ci_env.py").read_text(encoding="utf-8"))
    # Parsed, not grepped: this module's own docstring NAMES the forbidden idiom in
    # order to explain it, and a text search cannot tell prose from an import.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import: {ast.dump(node)}"
            assert not (node.module or "").startswith("lib."), f"intra-package: {node.module}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("lib."), f"intra-package: {alias.name}"


# ---------------------------------------------------------------------------
# AC-8 — the silent-retry counter (trg-0a294ef3)
# ---------------------------------------------------------------------------

def test_unobstructed_write_records_zero_retries(tmp_path: Path) -> None:
    """The property the card actually wanted: no contention => no retries.

    This is the consumer. If an unlocked reader is ever introduced INSIDE the write
    path, this count stops being 0 and the test goes red — which is what the silent
    successful retry made impossible to notice.
    """
    aw.reset_sharing_violation_retries()
    aw.durable_atomic_write(tmp_path / "f.json", '{"a":1}')
    assert aw.sharing_violation_retries() == 0


def test_counter_increments_when_a_retry_actually_happens(monkeypatch) -> None:
    """Proves the counter is wired to the retry, not merely present and always 0.

    Drives ``_retry_past_sharing_violations`` directly with a forced Windows branch
    and a synthetic sharing violation, so it is deterministic on every platform
    rather than depending on a real concurrent holder.
    """
    aw.reset_sharing_violation_retries()
    monkeypatch.setattr(aw, "_is_windows", lambda: True)

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            exc = PermissionError("in use")
            exc.winerror = 32
            raise exc
        return "ok"

    assert aw._retry_past_sharing_violations(flaky, 5.0) == "ok"
    assert aw.sharing_violation_retries() == 2, "one count per retry performed"


def test_reset_zeroes_the_counter(tmp_path: Path) -> None:
    aw.reset_sharing_violation_retries()
    assert aw.sharing_violation_retries() == 0


def test_the_primitive_still_refuses_a_surrogate_str(tmp_path: Path) -> None:
    """The write side stays STRICT, and that is the point.

    An earlier cut made this primitive lenient "for symmetry" with the triage
    readers. Doubt review showed the beneficiary analysis had never been done for the
    write side: ~35 callers write git-tracked JSON that is read back strictly and
    have no repair pass, so a lone surrogate would silently persist invalid UTF-8 and
    relocate the crash to every future reader. It must fail HERE, where the caller
    knows what it was writing.
    """
    with pytest.raises(UnicodeEncodeError):
        aw.durable_atomic_write(tmp_path / "f.json", '{"title":"caf\udcc3"}')


def test_the_triage_callers_carry_the_leniency_themselves(tmp_path: Path) -> None:
    """…and the store that legitimately round-trips undecodable bytes still can.

    The leniency lives with the two modules that need it — they encode and pass
    ``bytes`` — rather than on a primitive shared by thirty-five that do not.
    """
    from lib.sweep_text import read_text_verbatim

    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"title":"caf\xc3"}\n')
    text = read_text_verbatim(p)

    out = tmp_path / "out.jsonl"
    aw.durable_atomic_write(out, text.encode("utf-8", errors="surrogateescape"))
    assert out.read_bytes() == b'{"title":"caf\xc3"}\n'
