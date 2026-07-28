"""What a *loss* is not — the three proofs behind ``check_no_silent_revert``.

The detector in :mod:`silent_revert` asks a deliberately narrow question: every
line the default branch gained while this branch was open must still be present
in the branch's tree. Asked with whole-line set subtraction, that question has
answers that are not losses at all — and #477 shipped without them, so the very
next long-running iterate produced **four** findings and cleared every one
through ``declared_removals``. An escape hatch in routine use is a gate on its
way to being decoration, which is the failure this module exists to prevent.

Each filter only ever REMOVES findings, so each has to be a proof rather than a
guess. In strength order, cheapest first:

* :func:`matches_default` — **this branch's file already IS the default
  branch's.** Then nothing in it can be a loss, whatever happened in between.
  This is the proof the operator who first hit the false positives reached for by
  hand: *"``git diff origin/main HEAD -- <path>`` is EMPTY for every path."*
* :func:`superseded_on_default` — **the default branch moved past the line
  itself, and this branch followed.** It deleted the line outright, or replaced
  it with something this branch carries. Either way the two trees end in the same
  place. The "and this branch followed" half is load-bearing: without it, the
  default branch merely fixing a typo in a line this branch really had reverted
  would make the finding disappear.
* :func:`unexplained_by_edit` — **the line was rewritten in place, not
  discarded.** The replacement must sit in the same minimal (``-U0``) hunk as the
  deletion, and must be a line this branch could only have written after seeing
  theirs. A minimum-token threshold was the obvious alternative and was rejected:
  it is a knob nobody can defend a value for, and it still clears a short line
  replaced from across the file.

**What the last one does NOT prove, stated plainly.** Token containment shows the
other side's *words* survive in the replacing line, in order. It does not show
their *meaning* survives: ``the gate blocks on X`` → ``the gate no longer blocks
on X`` keeps every token and inverts the sentence, and this module accepts it.
That is a deliberate trade, and it is bounded on three sides — same hunk, not the
merge base, not the branch's own pre-merge side — so what is accepted is an edit
this branch made to a line it had just received, landing in the PR diff as an
ordinary ``-``/``+`` pair. What must never be accepted is a loss that is
*invisible*, which is the #463 shape and stays reported. The bound is pinned by
``test_the_accepted_blind_spot_is_pinned_not_implied``; if it ever stops being
acceptable, that test is where the decision was written down.

**Failure is never silence.** A side that cannot be read is routed to the
caller's ``problems`` channel, and the detector reports the incomplete comparison
— alongside any findings it did make, never instead of them.
"""

from __future__ import annotations

from pathlib import Path

from .silent_revert_reading import (
    file_lines,
    is_subsequence,
    replacement_hunks,
    tip_state,
)


def matches_default(
    project_root: Path, ref: str, head: str, path: str, cache: dict,
    problems: list[str] | None = None,
) -> bool:
    """Is this branch's whole file already identical to the default branch's?

    If the two trees agree about a file, nothing in that file can be a loss —
    whatever the default branch gained and later threw away, this branch ends in
    exactly the state the default branch is in. Both sides absent counts as
    agreement; one side absent does not.

    A side that cannot be READ suppresses nothing: ``problems`` records why, so
    the run discloses an incomplete comparison rather than passing on one that
    never happened.
    """
    heads = cache.setdefault("_heads", {}).setdefault(head, {})
    if (ref, path) not in cache:
        cache[(ref, path)] = tip_state(project_root, ref, path)
    if path not in heads:
        heads[path] = tip_state(project_root, head, path)
    their_state, theirs = cache[(ref, path)]
    our_state, ours = heads[path]
    if "unreadable" in (their_state, our_state):
        if problems is not None:
            problems.append(f"cannot compare {path} between {ref} and {head}")
        return False
    if their_state == "absent" or our_state == "absent":
        return their_state == our_state
    return theirs == ours


def superseded_on_default(
    project_root: Path, ref: str, delivered: str, head: str, path: str,
    lines: set[str], cache: dict,
) -> set[str]:
    """Drop lines the default branch itself moved past, where this branch followed.

    Between the merge that ``delivered`` these lines and the tip, the default
    branch either deleted them outright or replaced them — and in the replacement
    case this branch carries what replaced them. Either way the branch's tree ends
    where the default branch's does, so there is nothing left to revert.

    The second condition is the whole point, and is what an earlier line-level
    version of this filter lacked. "The default branch no longer has this exact
    line" is true in two very different situations: it superseded the line (and we
    followed), and it merely FIXED A TYPO in a line we had really reverted.
    Stage-3 review built the second one and it came back clean. Requiring the
    replacement to be present here tells them apart — in the first case it is, in
    the second we carry neither the old line nor the new one.
    """
    key = (delivered, path)
    if key not in cache:
        cache[key] = replacement_hunks(project_root, delivered, ref, path)
    ours = file_lines(project_root, head, path)
    if ours is None:
        return set(lines)
    survivors = set(lines)
    for deleted, added in cache[key]:
        # No addition: the default branch simply dropped the line, and this branch
        # not having it agrees with the default branch exactly.
        if added and not all(a in ours for a in added):
            continue
        survivors -= deleted
    return survivors


def unexplained_by_edit(
    project_root: Path, ref: str, head: str, path: str,
    lines: set[str], excluded: set[str], cache: dict,
) -> set[str]:
    """The lines that are NOT explained by an in-place rewrite — i.e. still findings.

    A line is explained only when the hunk that deletes it also adds a line
    carrying every one of its tokens in order, **and** that replacement is one
    this branch could only have written *after* seeing theirs — i.e. it is in
    neither the merge's base nor the branch's own pre-merge side (``excluded``).

    Both halves of that exclusion were forced by Stage-3 review, and each closes a
    way of clearing a real revert:

    * *the base* — the default branch NARROWS a line (``do X and Y`` -> ``do X``)
      and this branch puts the wide version back. Same hunk, tokens contained, and
      it is a revert.
    * *the branch's own pre-merge side* — the branch already had a line that
      happens to contain theirs, and the merge threw theirs away. Nothing was
      "built on" anything: the vouching line predates the change it vouches for.
      Without this, the check's own motivating case (#463) goes green if the
      branch line is merely reworded to mention what it discards, and one long
      pre-existing line can clear any number of deleted ones.
    """
    if path not in cache:
        cache[path] = replacement_hunks(project_root, ref, head, path)
    survivors = set(lines)
    for deleted, added in cache[path]:
        candidates = lines & deleted
        if not candidates:
            continue
        # Tokenise each candidate replacement ONCE per hunk rather than once per
        # (missing line x replacement) pair: an F11 gate that hangs is an F11 gate
        # that gets switched off.
        replacements = [a.split() for a in added if a not in excluded]
        if not replacements:
            continue
        for line in candidates:
            needle = line.split()
            if any(is_subsequence(needle, r) for r in replacements):
                survivors.discard(line)
    return survivors


__all__ = [
    "matches_default",
    "superseded_on_default",
    "unexplained_by_edit",
]
