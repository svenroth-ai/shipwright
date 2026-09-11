"""``check_ac_coverage_ratchet.py``'s push-only auxiliary signal (trg-91532c29
/ trg-e69bf1ba finding 6, iterate-2026-09-11-ac-ratchet-push-observe).

External code review (openai, HIGH) on the first version of the push-trigger
fix: re-running the SAME comparison against the SAME committed baseline on
every push detects nothing new for a same-PR self-grandfathered entry — by
the time that commit reaches `main`, the baseline already contains it, so
``unbound - baselined`` is empty on push exactly as it was on the introducing
PR. Closing that specific escape needs a signal the static baseline-vs-unbound
comparison structurally cannot produce: *did the baseline FILE ITSELF change
since main last moved, and by how much.*

:func:`baseline_grown_since_parent` answers exactly that, by diffing the
baseline's own committed bytes against a caller-supplied ``parent_sha`` — the
push event's own ``before`` SHA (`ci.yml` passes it explicitly), never a
merge-base (this is a push-only auxiliary check with no PR to diff against).
**Using the push's ``before`` SHA, not a bare ``HEAD~1``, is load-bearing**
(external code review, openai, HIGH, second round): a push can carry more
than one commit — a non-squash merge, a rebase-merge, or a direct multi-commit
push, all real paths this repo's own solo-maintainer `--admin` override
already uses on occasion — and if the baseline grew in an EARLIER commit of
that push while the pushed tip leaves it untouched, ``HEAD~1`` (the tip's
immediate parent) already contains the grown entry, silently missing it.
``before`` is what `main` pointed at immediately before this entire push
landed, so it is the one comparison point that covers every commit the push
actually introduced, regardless of how many. Falls back to resolving
``HEAD~1`` only when no ``parent_sha`` is supplied (local/manual invocation
outside CI) — ``ci.yml`` always supplies one. Read-only throughout, same as
the primary gate.

**What this does and does not close**, stated once, precisely:

* A ``--write`` that adds a newly-unbound AC to the baseline anywhere within
  the pushed commit range — SURFACED, not durably closed (Stage-3 doubt
  review, medium): this function reports it as a red push-triggered run the
  moment it lands, regardless of which commit in a multi-commit push made
  the change, but that run is detective, not preventive — it fires
  post-merge (on `push` to `main` itself, not as a required PR check) and
  self-clears on the very next push once the grown entry is already inside
  every later ``before``, with no persisted record, ledger entry, or issue
  filed. A maintainer who misses that one red run gets no further automated
  signal for that specific entry, ever — this closes the "never observed
  again" gap the original bug had (an unconditional silence), not the
  general risk of a missed alarm. Durable closure needs the same persisted
  resolution ledger named below for the regression case.
* An AC already listed in the baseline (from the original snapshot, or from
  any earlier legitimate growth) that regresses — bound, then unbound again,
  in a commit that never touches the baseline file — NOT closed. The
  baseline's own bytes are unchanged across that regression, so there is
  nothing here to diff. Real closure needs either a periodic full ``--write``
  refresh or a persisted resolution ledger with cross-run memory — disclosed
  as real design work in ``.shipwright/planning/iterate/2026-09-10-p3-7-feeder-checks.md``
  §7, not built here.
* A force-push to ``main`` that rewrites history out from under an already-
  landed ``before`` SHA — NOT closed, by the same fail-open contract as any
  other unresolvable parent: the rewritten commit is no longer reachable, so
  ``git rev-parse --verify`` fails and this warns instead of blocking (external
  code review, glm, round 4). A self-grandfathering edit riding such a
  force-push is a silent bypass of this auxiliary signal specifically; the
  primary same-commit comparison and normal review are still the backstop.
* The parent blob's shape check only requires a string-list ``unbound`` and
  does not compare ``schema_version`` — a parent baseline from a differently-
  versioned schema is accepted and diffed as a plain string set. This is
  intentional (the signal only ever needs "was this string present before",
  not the file's full shape), not an oversight (external code review, glm,
  round 4).
**The parent-baseline read goes through** :mod:`git_blob_read`, **not a raw
``git show <commit>:<path>``** (Stage-3 doubt review): that raw form has two
defects this repo already found and fixed elsewhere — it is a Windows
``MAX_PATH`` trap, and a non-zero exit conflates "file absent at that commit"
(a legit bootstrap) with "the read itself is broken" (a real infra fault that
must still warn, never go silent). :func:`~.git_blob_read.blob_oid` answers
those two questions separately, so this module never has to. Likewise
``git rev-parse`` runs through :func:`~.git_helpers._run_git`, which decodes
with ``errors="ignore"`` and never raises — a raw ``subprocess.run(...,
text=True)`` decodes strictly and can raise ``UnicodeDecodeError`` on a
historically-committed non-UTF-8 baseline, which would escape uncaught to
``main()``'s catch-all and return ``EXIT_INFRA``, indistinguishable from
``EXIT_BLOCKED`` at the shell-exit-code level GitHub Actions actually reads —
exactly the red-`main`-from-an-infra-hiccup this signal exists not to cause.
"""

from __future__ import annotations

import json
from pathlib import Path

from .git_blob_read import blob_oid
from .git_helpers import _run_git


def baseline_grown_since_parent(project_root: Path, baseline_path: Path,
                                 current: set[str],
                                 parent_sha: str | None = None) -> tuple[list[str], list[str]]:
    """``(newly_grandfathered, warnings)``.

    ``parent_sha`` should be the push event's ``before`` SHA in CI (covers
    every commit the push introduced); defaults to resolving ``HEAD~1`` for
    local/manual invocation, where there is no push range to speak of.

    Fails OPEN (empty list, a warning) on anything that stops the parent
    read from being trustworthy — no resolvable parent (repo root / shallow
    history / a null `before` on a brand-new branch), the baseline not
    existing at the parent (this exact push is the one that FIRST introduced
    the file — a bootstrap, not a growth event), a `--baseline` path outside
    `project_root`, or a parent blob that fails the same shape check the
    primary gate applies to the current file. This is an auxiliary signal:
    it must never turn an unrelated infra hiccup into a red `main` the way
    the primary gate's fail-CLOSED default correctly does for a corrupt
    CURRENT baseline — this one only ever adds information about what
    changed."""
    if parent_sha:
        # Distinguish "not a real commit" (unresolvable `before` — all-zeros
        # on a brand-new branch, a rewritten/force-pushed ref) from "a real
        # commit that simply predates the baseline file" (a legit bootstrap):
        # only the first is a fault worth a warning (external code review,
        # glm, low) — the growth check's own silence on the second is by
        # design, not an omission.
        rc, _, _ = _run_git(project_root, "rev-parse", "--verify", f"{parent_sha}^{{commit}}")
        if rc != 0:
            return [], [f"--parent-sha {parent_sha} does not resolve to a commit in this repo "
                        "— cannot check baseline growth against it"]
        resolved = parent_sha
    else:
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD~1")
        if rc != 0:
            return [], ["could not resolve HEAD~1 to check baseline growth"]
        resolved = out.strip()

    try:
        rel = baseline_path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        return [], [f"--baseline {baseline_path} is not under --project-root {project_root}: {exc}"]

    oid, err = blob_oid(project_root, resolved, rel)
    if err:
        # A genuine git-level read fault (corrupt tree, unreadable object) —
        # NOT the same thing as the file simply not existing there yet.
        return [], [f"could not read the baseline at the parent commit ({resolved}): {err}"]
    if oid is None:
        # The parent commit is real (verified above, or trusted as HEAD~1)
        # but does not carry the file at that path — this push/commit is the
        # one that FIRST introduced it. A bootstrap, not a growth event.
        return [], []
    rc, body, _ = _run_git(project_root, "cat-file", "blob", oid)
    if rc != 0:
        return [], [f"the baseline blob at the parent commit ({resolved}) is present but unreadable"]
    try:
        doc = json.loads(body)
    except ValueError as exc:
        return [], [f"the baseline at the parent commit ({resolved}) is not valid JSON: {exc}"]
    if not isinstance(doc, dict) or not isinstance(doc.get("unbound"), list) \
            or not all(isinstance(x, str) for x in doc["unbound"]):
        return [], [f"the baseline at the parent commit ({resolved}) does not have the expected shape"]

    parent_set = set(doc["unbound"])
    return sorted(current - parent_set), []
