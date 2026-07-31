"""Drift-protection for the F11 auto-merge arm (B4.5 Phase 3, trg-bdc160e2).

After `gh pr create`, F11 must arm GitHub-native auto-merge so an iterate
PR squash-merges itself once the Required Checks pass — but ONLY for
`iterate/*` branches (a manual human PR must never self-arm) and ONLY
fail-soft (if "Allow auto-merge" / branch protection is off in repo
settings, `gh pr merge --auto` errors — that must warn and leave the PR
open, never fail the whole iterate run).

These assertions pin the four properties that make the arm safe:

1. The arm call exists with the exact flags `--auto --squash --delete-branch`.
2. It is guarded to `iterate/*` branches.
3. It is fail-soft — a refusal is classified, never a hard exit.
4. The Kern SKILL.md F11 one-liner advertises the arm so the index does
   not drift from the reference.

**Where they live moved; the properties did not**
(iterate-2026-07-31-f11-delivery-truth). Arming used to be a shell block in this
prose. It is now the first rung of `shared/scripts/tools/deliver_pr.py`, because
whether anything will EVER merge the PR is only answerable from how the arm turned
out — and on an unprotected base the answer is "nothing will", which prose alone
could not act on. So these tests pin the arm against the code that performs it, and
pin the prose against still delegating to that code.

The behavioural half — exact flags, fail-soft, campaign defer — is also asserted in
`shared/tests/test_deliver_pr.py`, which can drive the real function. This root only
reads text, because `import lib.pr_delivery` from a plugin test root resolves against
the plugin's OWN `lib` package (ADR-045).
"""

from __future__ import annotations

import re
from pathlib import Path

ITERATE_SKILL = (
    Path(__file__).resolve().parent.parent / "skills" / "iterate"
)
F11_PATH = ITERATE_SKILL / "references" / "F11.md"
SKILL_PATH = ITERATE_SKILL / "SKILL.md"


DRIVER_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared" / "scripts" / "tools" / "deliver_pr.py"
)


def _f11_text() -> str:
    return F11_PATH.read_text(encoding="utf-8")


PREDICATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared" / "scripts" / "lib" / "pr_delivery.py"
)


def _predicate_text() -> str:
    """The pure permission decisions the driver consults, as text."""
    assert PREDICATE_PATH.is_file(), f"delivery decisions missing at {PREDICATE_PATH}"
    return PREDICATE_PATH.read_text(encoding="utf-8")


def _driver_text() -> str:
    """The delivery driver's SOURCE, read as text rather than imported.

    Importing it here would pull `lib.pr_delivery` in against the iterate plugin's
    own `lib` package (ADR-045). The assertions that need real behaviour live in
    `shared/tests/test_deliver_pr.py`, which has the right test root for them."""
    assert DRIVER_PATH.is_file(), f"delivery driver missing at {DRIVER_PATH}"
    return DRIVER_PATH.read_text(encoding="utf-8")


def _join_line_continuations(text: str) -> str:
    """Collapse shell `\\`-newline continuations so a multi-line command
    is matched as one logical line."""
    return re.sub(r"\\\s*\n\s*", " ", text)


def test_f11_reference_exists() -> None:
    assert F11_PATH.is_file(), f"F11 reference missing at {F11_PATH}"


def test_arm_call_present_with_exact_flags() -> None:
    """The exact flag set, pinned in the code that now issues it."""
    assert re.search(
        r'"pr",\s*"merge",\s*pr_url,\s*"--auto",\s*"--squash",\s*"--delete-branch"',
        _driver_text(),
    ), (
        "deliver_pr.py must arm auto-merge with exactly "
        "`gh pr merge <pr_url> --auto --squash --delete-branch`."
    )


def test_f11_delegates_delivery_and_keeps_no_second_arm_of_its_own() -> None:
    """The prose hands delivery to the driver. It must NOT also carry a shell arm:
    two arms in two places is precisely the drift this file exists to prevent."""
    text = _f11_text()
    assert "deliver_pr.py" in text, (
        "F11.md must run deliver_pr.py, which arms and then decides who merges."
    )
    executable = [
        ln for ln in _join_line_continuations(text).splitlines()
        if "gh pr merge" in ln and "--auto" in ln
        and not ln.lstrip().startswith(("#", "*", "-", "1.", "2.", "3.", ">"))
    ]
    assert not executable, (
        "F11.md must no longer arm auto-merge in shell — the driver owns it: "
        + "; ".join(executable)
    )


def test_arm_is_guarded_to_iterate_branches() -> None:
    """The arm must be gated on an `iterate/*` branch check so a manual
    human PR never self-arms."""
    text = _f11_text()
    assert "iterate/*" in text, (
        "F11.md must state that ONLY `iterate/*` branches are armed — a manual "
        "human PR must never self-arm."
    )
    assert '--head-branch "iterate/{slug}"' in text, (
        "the driver must be told which branch is this run's, so it can refuse to "
        "merge a PR that is not the one this run opened."
    )
    driver = _driver_text()
    assert "wrong_pr(" in driver, (
        "the driver must check the PR is this run's before ANY mutating call. The check is "
        "`wrong_pr` rather than `identity_problem` on purpose: identity_problem also "
        "rejects a non-OPEN PR, and reading the terminal state first meant a MERGED PR "
        "short-circuited to exit 0 with no identity check at all (Stage 3)."
    )
    # …and it must come BEFORE the terminal-state read, not after it.
    assert driver.index("wrong_pr(") < driver.index("terminal_state_result("), (
        "identity must be checked before the terminal state is read, or any merged PR in "
        "the repository can be reported as this run's delivery."
    )


def test_arm_is_fail_soft_not_hard_exit() -> None:
    """A refusal must be CLASSIFIED, never fatal.

    The old `|| echo WARN` became `classify_arm_outcome`, which is strictly more
    than fail-soft: it also decides whether anything can ever merge this PR. What
    must not come back is an arm whose failure ends the run — a missing repo setting
    cannot be allowed to break every future iterate."""
    driver = _driver_text()
    assert "classify_arm_outcome(" in driver, (
        "deliver_pr.py must classify the arm's outcome rather than treating a "
        "non-zero exit as fatal."
    )
    arm_block = driver[driver.index('"--auto"'):]
    arm_block = arm_block[:arm_block.index("self_merging")]
    for fatal in ("raise ", "sys.exit"):
        assert fatal not in arm_block, (
            "an arm refusal must not raise or exit — it is an INPUT to the ladder: "
            + arm_block[:200]
        )


def test_existing_gates_preserved() -> None:
    """Regression: the patch must not drop F11's leak-guard or the
    deterministic finalization verifier."""
    text = _f11_text()
    assert "check_iterate_isolation.py" in text, "F11 lost its leak-guard"
    assert "verify_iterate_finalization.py" in text, (
        "F11 lost its deterministic finalization verifier"
    )


def test_skill_index_line_advertises_arm() -> None:
    """The Kern SKILL.md F11 one-liner must mention the auto-merge arm so
    the index does not drift from the reference."""
    skill = SKILL_PATH.read_text(encoding="utf-8")
    f11_rows = [
        ln for ln in skill.splitlines()
        if ln.startswith("| F11 ")
    ]
    assert f11_rows, "no `| F11 |` index row found in Kern SKILL.md"
    row = f11_rows[0]
    assert "--auto" in row and "iterate/" in row, (
        "Kern SKILL.md F11 index row must advertise the `--auto` arm and "
        "its `iterate/`-only scope: " + row
    )
    # The index must name the tool that actually delivers, or it sends a reader to a
    # step that no longer exists. Stage 1 review caught the row still naming
    # `watch_pr_delivery.py` while F11.md had moved on.
    assert "deliver_pr.py" in row, (
        "the F11 index row must name deliver_pr.py as the delivery step: " + row
    )
    assert "watch_pr_delivery.py" not in row, (
        "the F11 index row must not still present the read-only watcher as the "
        "delivery step: " + row
    )


# --- Refresh-if-behind guard + campaign-defer (Option A, Auto-merge churn fix,
#     iterate-2026-06-12-automerge-serial-integrate) ------------------------------
# GitHub auto-merge does a server-side 3-way merge and NEVER runs the
# regenerate-at-merge resolver, so a branch that fell behind origin/<default>
# would merge stale (Group-E staleness) or stall DIRTY on the regenerated
# snapshots. F11 must (1) bring the branch current via `integrate_main
# --ensure-current` BEFORE arming, and (2) honor a campaign-defer env var so an
# `--autonomous` campaign merges each PR in turn (interleaved-serial) instead of
# arming every PR at once.


def test_f11_has_refresh_if_behind_guard() -> None:
    """F11 must run the `ensure_current.py` refresh BEFORE push / PR-create / arm,
    so the PR arms from a current, already-regenerated tree (server-side merge
    cannot regenerate the derived snapshots), AND it must be fail-closed: a
    non-churn/source conflict STOPs the run (hard safety gate)."""
    text = _f11_text()
    assert "ensure_current.py" in text, (
        "F11.md must invoke ensure_current.py to refresh a behind branch before "
        "arming auto-merge (server-side merge cannot regenerate snapshots)."
    )
    guard_pos = text.index("ensure_current.py")
    push_pos = text.index("push -u origin")
    create_pos = text.index("gh pr create")
    arm_pos = text.index("--auto --squash --delete-branch")
    assert guard_pos < push_pos < create_pos < arm_pos, (
        "the ensure_current.py refresh must run BEFORE the push, the PR create, "
        "and the auto-merge arm (so the branch is current when it ships/arms)."
    )
    # Fail-closed: a non-zero exit between the guard and the push must STOP.
    guard_block = text[guard_pos:push_pos]
    assert "exit 1" in guard_block and "STOP" in guard_block, (
        "the ensure_current guard must STOP (exit 1) on a non-churn/source "
        "conflict — the same hard safety gate as the resolver."
    )


def test_f11_arm_respects_campaign_defer() -> None:
    """The arm must be gated on a CONCRETE `SHIPWRIGHT_ITERATE_AUTOMERGE` shell
    check that wraps the `gh pr merge --auto` command, so an autonomous campaign
    can defer arming (`=0`) and let the orchestrator merge each PR in turn.
    Substring presence is not enough — pin the exact condition and that it
    precedes the arm."""
    driver = _driver_text()
    # The driver consults ONE predicate rather than re-parsing the variable itself —
    # two readers of one switch is how they drift (Stage 2 review asked for this
    # consolidation, so pin the shape it asked for, not the literal it replaced).
    assert "campaign_defers(" in driver, (
        "deliver_pr.py must honour the campaign defer through "
        "`lib.pr_delivery.campaign_defers`."
    )
    gate_pos = driver.index("campaign_defers(")
    arm_pos = driver.index('"--auto"')
    assert gate_pos < arm_pos, (
        "the campaign-defer gate must precede the arm so =0 skips it entirely."
    )
    assert "campaign_defer" in driver, (
        "the deferred branch must be NAMED, not implicit — under a campaign it skips "
        "both the arm and the self-merge rung."
    )

    # The predicate itself: it must read THAT variable, and only the literal "0" may
    # defer, so a standalone iterate with the variable unset is unchanged.
    predicate = _predicate_text()
    assert "def campaign_defers(" in predicate, "the campaign predicate moved again"
    body = predicate[predicate.index("def campaign_defers("):]
    body = body[:body.index("\ndef ", 1)]
    assert "SHIPWRIGHT_ITERATE_AUTOMERGE" in body, (
        "the campaign predicate must read SHIPWRIGHT_ITERATE_AUTOMERGE."
    )
    assert '== "0"' in body, (
        "the defer must trigger on the literal 0 only, so an unset variable leaves "
        "single iterates unchanged."
    )
    # And it must also suppress the self-merge rung, not only the arm.
    permission = predicate[predicate.index("def self_merge_allowed("):]
    assert "SHIPWRIGHT_ITERATE_AUTOMERGE" in permission, (
        "a campaign must suppress the self-merge rung too — a sub-iterate merging "
        "itself would break the one-PR-at-a-time invariant the defer exists to hold."
    )
    assert "SHIPWRIGHT_ITERATE_SELF_MERGE" in _f11_text(), (
        "F11.md must document the self-merge switch, since it decides whether an "
        "un-armable PR is delivered or reported as not-delivered."
    )
