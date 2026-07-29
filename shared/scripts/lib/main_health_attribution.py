"""Which commit broke `main` — the attribution half of the health core.

Split out of ``lib/main_health.py`` (which re-exports both functions as the one
public surface) so each file stays inside the 300-LOC source budget.

The two definitions here disagreed with each other in an early draft, and a
review round caught it: **``first_bad_commit`` is the OLDEST red after the last
green.** For a red streak of three, repairing the newest one fixes nothing.
``latest_red_commit`` is a genuinely different fact and is reported alongside.

Everything else in this module is about **refusing to answer**. Attribution
inside a partial data set is the failure mode that costs most, because it names
an innocent commit with exactly the same confidence it names a guilty one.
"""

from __future__ import annotations


def attribute(
    commits: list[dict],
    verdicts: dict[str, str],
    *,
    saturated: bool = False,
    oldest_run_sha: str | None = None,
) -> dict:
    """Which commit broke `main`, and how sure we are.

    ``commits`` is the first-parent series newest-first; ``verdicts`` maps SHA →
    ``green``/``red``/``running``/``incomplete``.

    Confidence is ``exact`` only when a green anchor exists AND every commit
    between it and the first bad one has a conclusive verdict. A gap —
    ``incomplete``, ``running``, or a cancelled run — downgrades to
    ``uncertain`` and is listed, because "we did not verify these" is a fact the
    repairing agent needs.

    Three refusals, each with its own reason code: ``no_red_commit`` (nothing to
    attribute), ``no_green_anchor_in_window`` (widen the window), and
    ``run_history_truncated`` — a saturated retrieval that stops before the
    anchor would be, which is missing evidence rather than evidence of absence.
    """
    order = [c["sha"] for c in commits]
    by_sha = {c["sha"]: c for c in commits}
    base = {
        "confidence": "none",
        "reason_code": None,
        "first_bad_commit": None,
        "latest_red_commit": None,
        "last_green_commit": None,
        "gaps": [],
        "window": len(commits),
    }

    # Attribution answers "what broke the branch I am about to build on", so it
    # is about the CURRENT tip. A red commit further back that was already
    # repaired is history: attributing it would present a resolved failure as an
    # active one AND spend the red-path API calls on a green branch, breaking
    # the one-call green budget the two skill hooks are affordable because of.
    if not order or verdicts.get(order[0]) not in {"red", "incomplete", "running"}:
        return {**base, "reason_code": "no_red_commit"}

    reds = [s for s in order if verdicts.get(s) == "red"]
    if not reds:
        return {**base, "reason_code": "no_red_commit"}

    latest_red = reds[0]
    latest_index = order.index(latest_red)
    anchor_index = None
    for i in range(latest_index + 1, len(order)):
        if verdicts.get(order[i]) == "green":
            anchor_index = i
            break

    if anchor_index is None:
        # Two different answers, two different fixes. If the retrieved runs
        # reach the OLDEST commit in the window, we genuinely looked at the
        # whole window and found no green — widen the window. If they stop
        # earlier and the response was saturated, we never saw the far end —
        # raise the limit. Saying "no anchor" for the second case would report
        # missing evidence as evidence of absence.
        covered_to_window_end = bool(order) and oldest_run_sha == order[-1]
        truncated = saturated and not covered_to_window_end
        return {
            **base,
            "latest_red_commit": by_sha[latest_red],
            "reason_code": (
                "run_history_truncated" if truncated else "no_green_anchor_in_window"
            ),
        }

    span = order[latest_index:anchor_index]
    first_bad = next(s for s in reversed(span) if verdicts.get(s) == "red")
    gaps = [
        {"sha": s, "verdict": verdicts.get(s, "incomplete")}
        for s in span
        if verdicts.get(s) != "red"
    ]
    return {
        **base,
        "confidence": "uncertain" if gaps else "exact",
        "first_bad_commit": by_sha[first_bad],
        "latest_red_commit": by_sha[latest_red],
        "last_green_commit": by_sha[order[anchor_index]],
        "gaps": gaps,
    }


def candidate_partners(
    *,
    base_sha: str | None,
    commits_between: list[dict] | None,
    reason_code: str | None = None,
) -> dict:
    """The changes the bad commit was never tested against.

    An **empty** list is an answer, not a refusal: it means the PR merged
    current, so the break is inside the commit itself rather than in a
    combination. ``None`` plus a reason code is the refusal — no PR association,
    a direct push, or a base that is not an ancestor (rebase / force-push).
    Nothing is ever invented to fill the field.
    """
    return {
        "base_sha": base_sha,
        "commits": commits_between,
        "reason_code": reason_code,
    }
