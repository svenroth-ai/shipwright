"""Whether a path may contribute to skipping the PR-review gate entirely.

Split out of `pr_review_generated.py` (iterate-2026-09-12-generated-prefixes-
provenance-anchor) along that file's two independently-consumed public
functions, once it crossed the 300-line source guideline: `is_generated_path`
(hide-from-the-model, lower stakes, stays in that file) versus
`is_safe_to_skip_review` here (skip-the-gate-entirely, higher stakes — the
PR-REVIEW GATE ITSELF may post `success` with no model call at all on this
function's say-so). The two have disjoint call sites
(`pr_review_diff_filter.py` vs. `review_record_tier.classify_generated_only`)
and disjoint test files, which is what makes this a natural seam rather than
a forced cut — code review, iterate-2026-09-12-generated-prefixes-
provenance-anchor.
"""

from __future__ import annotations

import re

__all__ = ["is_safe_to_skip_review"]

# The canonical, repo-root location of each `pr_review_generated.
# _GENERATED_BASENAMES` file. `is_generated_path` stays basename-only,
# matched at ANY directory, because its stakes are lower: it only hides a
# section from the model while everything else in the diff is still
# reviewed. `is_safe_to_skip_review` decides whether the PR-REVIEW GATE
# ITSELF may post green with no model call at all, so a brand-new file
# merely NAMED e.g. `triage.jsonl` planted at an attacker-chosen path —
# never the actual regenerated artifact the basename rule was written for —
# must not borrow that classification (Stage-3 doubt review, medium finding).
_SKIP_REVIEW_CANONICAL_BASENAME_PATHS = frozenset({
    "shipwright_test_results.json",
    "shipwright_events.jsonl",
    ".shipwright/triage.jsonl",
    ".shipwright/triage.outbox.jsonl",
})

# The one `_GENERATED_PREFIXES` entry kept skip-safe, and only in this
# anchored shape — see the "PER-PREFIX ANCHORING" comment below for why the
# other three (`.shipwright/compliance/`, `.shipwright/agent_docs/iterates/`,
# `.shipwright/agent_docs/runtime/`) are removed from skip-safety outright.
_SKIP_REVIEW_CHANGELOG_PREFIX = "CHANGELOG-unreleased.d/"

# Must stay in sync with write_changelog_drop.ALLOWED_CATEGORIES — that
# module's own top-of-file comment makes the same sync trade-off for the same
# six names, since both describe the one real Keep-a-Changelog category set.
_SKIP_REVIEW_CHANGELOG_CATEGORIES = frozenset(
    {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
)
# `[0-9]`, not `\d`: unqualified `\d` matches any Unicode decimal digit (e.g.
# Arabic-Indic ١٢٣), not only the ASCII counter `write_changelog_drop.
# _next_counter_path` actually writes (`{counter:03d}`, counter capped at 999
# by `_MAX_COUNTER = 1000`) — external code review, this iterate.
#
# `[^/]+` (not `.+`, not dropped): a live PR-review gate finding on this
# iterate's own PR #746 claimed this pattern accepts an empty name before
# the counter (citing `_001.md`) via `[^/]+` "consuming the separator". That
# claim is false — verified directly: `fullmatch` against `filename` requires
# `[^/]+` to consume >=1 char BEFORE the fixed-length literal `_[0-9]{3}\.md`
# suffix, so `_001.md` (7 chars, exactly the suffix's own length) leaves zero
# chars available and does not match. `.+` was tried as a "clarifying"
# alternative and reverted: unlike `[^/]+`, `.` also matches `/`, which
# reopened the EXTRA-NESTING case (`Fixed/nested/x_001.md`) that this same
# regex must reject — `filename` is only the piece after `rest.partition("/")`
# splits off the category, so it CAN still contain further `/`s the pattern
# must not cross. `test_changelog_drop_off_shape_is_NOT_safe_to_skip` asserts
# both the literal `_001.md` case the (incorrect) review flagged and the
# nesting case a naive "fix" would have broken.
_SKIP_REVIEW_CHANGELOG_DROP_RE = re.compile(r"^[^/]+_[0-9]{3}\.md$")

# PER-PREFIX ANCHORING for `pr_review_generated._GENERATED_PREFIXES`
# (iterate-2026-09-12-generated-prefixes-provenance-anchor, closing
# trg-dd297923). `_GENERATED_PREFIXES` stayed a blanket directory-prefix
# match for `is_safe_to_skip_review` from 2026-09-10 through this iterate —
# the same no-provenance shape Round 4 below already found unsafe for
# `reviews.json`, just never re-examined here, despite every other category
# in this function (basenames, review evidence) having already been anchored
# after a prior doubt-review finding closed the same class of gap. A
# follow-up doubt review on this iterate's own parent run
# (iterate-2026-09-11-pr-review-evidence-filter-gap, Round 4 doubt review)
# traced ONE entry to a concrete downstream consumer:
# `.shipwright/compliance/ci-security.json` is read by
# `shipwright-compliance/scripts/lib/security_gate.py` (`read_security_
# summary` + `decide`) as the pass/fail ORACLE for a deploy-time PreToolUse
# gate (`check_security_scan.py` blocks `deploy`/`jelastic`/`vercel`/... Bash
# commands on it) — content trusted with no hash/HEAD/regeneration check,
# exactly the "an exact path is not provenance" shape Round 4 already closed
# for `reviews.json`. Applying that same reasoning per prefix:
#
# - `.shipwright/compliance/` — REMOVED from skip-safety entirely, not
#   narrowed. `ci-security.json` alone is a live gate oracle, so anchoring it
#   to its own canonical path would repeat Round 4's exact mistake (an exact
#   path still isn't provenance for something a gate trusts as ground truth).
#   Its siblings (dashboard.md, sbom.md, ...) have no single small closed set
#   in the generator source either — a repo-wide survey of the compliance
#   plugin found 8+ fixed report names (dashboard.md, sbom.md, test-
#   evidence.md, change-history.md, traceability-matrix.md, test-
#   traceability.json, test-evidence-index.json, audit-report.md/.json) plus
#   genuinely per-run drops (`evidence/junit-NN.xml` staged reports) with no
#   fixed name to enumerate — and narrowing to "just the ones that are safe"
#   would need auditing every report's downstream readers to be sure none of
#   the rest is also consumed as an oracle the way ci-security.json is. Full
#   removal costs one extra (trivial) review call for a compliance-only PR —
#   the same trade-off already accepted for every review-evidence shape
#   since Round 3.
# - `.shipwright/agent_docs/iterates/` — REMOVED, not merely narrowed. The
#   first version of this fix anchored the filename to `<run_id>.json` /
#   `<run_id>.test-results.json` with `run_id` matching `RUN_ID_STRICT`, on
#   the reasoning that `iterate_entry.py` and `iterate_test_results.py`
#   already enforce that exact shape at write time. Stage-3 doubt review
#   disproved that this closes the gap: `RUN_ID_STRICT` is a public, freely
#   choosable shape, not a signature — an attacker's own PR can commit a
#   brand-new, fully self-authored
#   `.shipwright/agent_docs/iterates/iterate-<any-date>-<any-slug>.json`
#   that satisfies the shape while carrying forged content. That content is
#   then read, unauthenticated, by a concrete real consumer:
#   `plugins/shipwright-iterate/scripts/lib/complexity_history.py::
#   load_history_prior` globs every `*.json` directly under this dir and
#   accepts any file with a valid `complexity` + parseable `date`, feeding
#   it into later iterates' complexity default — the exact "filename shape
#   is not provenance" defect this fix closed for `ci-security.json`, left
#   open one directory over. Blast radius is bounded (the prior is capped at
#   `small`), but the fix removes skip-safety here too rather than leave a
#   narrower-but-still-forgeable anchor with a "genuinely closed shape"
#   claim the doubt review showed was not true of authorship.
# - `CHANGELOG-unreleased.d/` — ANCHORED, the one prefix kept skip-safe.
#   Every legitimate drop is `<one of six ALLOWED_CATEGORIES>/<name>_<NNN>.md`
#   (`write_changelog_drop.py`'s own `_next_counter_path`) — closed on the
#   category segment (exactly six real names) and the zero-padded counter
#   suffix; the run-id segment of the filename stays a wildcard
#   (`sanitize_run_id_for_filename` allows a broad charset with no fixed
#   shape). Unlike `.shipwright/agent_docs/iterates/`, this prefix has no
#   identified downstream reader that trusts drop CONTENT for a gate or
#   automated decision — drops are aggregated into `CHANGELOG.md` at release
#   time by a human-run `/shipwright-changelog`, not consumed as an oracle —
#   so the residual risk of a shape-conforming, content-forged drop is a
#   cosmetic release-notes entry, not an unreviewed trust-corpus write.
#   Stage-3 doubt review flagged that this residual is still stronger than
#   the comparable hide-side wildcard for `external-*review*`: hiding a
#   section still leaves it inside a diff a model reviews; this grants
#   skip-safety, so a PR whose only change is one shape-conforming drop gets
#   literally zero review, human or model, not merely one hidden section
#   within an otherwise-reviewed diff. Accepted on that basis (no gate reads
#   the content), not treated as equivalent to the hide-side case.
# - `.shipwright/agent_docs/runtime/` — REMOVED, not merely left un-anchored:
#   this directory is gitignored (root `.gitignore`) and
#   `shared/tests/test_runtime_dir_gitignored.py::test_runtime_dir_never_
#   committed` is a CI-gating empirical probe asserting no tracked file ever
#   exists under it. Reaching this path in a real PR diff at all already
#   requires `git add -f` against that guard; granting it skip-safety on top
#   would be pure downside (a free pass for a path that should never be
#   there) with no legitimate write this repo ever makes to preserve.

# NO review-evidence path is skip-safe, as of Round 4 (the live PR-review gate's
# own bot, on this iterate's own PR #727 — the tool built to enforce this rule
# caught the rule's last remaining gap by exercising it for real). Rounds 1-3
# (see `is_safe_to_skip_review`'s docstring below) narrowed this set from "share
# `pr_review_generated._REVIEW_EVIDENCE_RE` verbatim" down to "`reviews.json`
# only, run-anchored, exact basename" — and Round 4 found that floor was
# still unsafe: an EXACT PATH is not PROVENANCE any more than an exact
# basename is. A contributor's own PR can commit
# `.shipwright/planning/iterate/<self-chosen-run>/reviews.json` with forged
# `SHIPWRIGHT_VERDICT: approve` content — nothing here checks WHO wrote the
# file or that its content came from `record_review_pass.py` — and a PR
# whose only changed file is that forgery would skip the review gate with
# zero model call. The fix is to stop granting skip-safety by path at all,
# not to chase a fourth narrower pattern: the origin bug (PR #722) only ever
# needed review evidence HIDDEN from the model (`is_generated_path` /
# `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`, unaffected by this), never SKIP-safe.
# Real provenance validation (verifying `reviews.json` was actually produced
# by the tool, not merely path-shaped like its output) is a materially larger
# change than this fix and is out of scope here.


def _is_canonical_changelog_drop(rest: str) -> bool:
    """True iff ``rest`` (the path after `_SKIP_REVIEW_CHANGELOG_PREFIX`) is
    `<real category>/<name>_<NNN>.md` — never an attacker-chosen category or
    an uncounted filename."""
    category, sep, filename = rest.partition("/")
    if not sep or category not in _SKIP_REVIEW_CHANGELOG_CATEGORIES:
        return False
    return bool(_SKIP_REVIEW_CHANGELOG_DROP_RE.fullmatch(filename))


def is_safe_to_skip_review(path: str) -> bool:
    """True iff ``path`` may contribute to skipping the PR-review gate entirely
    (posting `success` with no model call), NOT merely to hiding its section
    from a model that still reviews the rest of the diff.

    Strictly narrower than `pr_review_generated.is_generated_path`, in four
    ways (1-2 from Stage-3 doubt review on
    iterate-2026-09-10-pr-review-generated-only, 3 from
    iterate-2026-09-11-pr-review-evidence-filter-gap, 4 from this iterate):

    1. Excludes `_GENERATED_AGENT_DOCS` (`build_dashboard.md`,
       `session_handoff.md`, `triage_inbox.md`). That set exists so the diff
       shown to the model isn't padded with noise — but this repo's own
       architecture reads these three files back as agent context in later
       sessions (docs/hooks-and-pipeline.md), and they carry free-form prose a
       contributor controls. Skipping the reviewer entirely for a PR touching
       ONLY these is exactly the "an agent obeys it" case `is_generated_path`'s
       own module docstring warns is unsafe — they need a reviewer's eyes for
       injected instructions, they are not "no reviewable content".
    2. Anchors the otherwise-basename-only `_GENERATED_BASENAMES` matches to
       their one canonical repo-root path (`_SKIP_REVIEW_CANONICAL_BASENAME_PATHS`)
       rather than matching the basename at any directory.
    3. Grants NO review-evidence path skip-safety at all, not even
       `reviews.json` — see the "Round 4" comment above for why: an exact
       path match is not provenance, and a contributor's own PR can commit a
       forged `reviews.json` at a self-chosen run directory. Every
       review-evidence file (`reviews.json`, the reply family,
       `external-*review*`, `self-review-payload.json`) is hidden from the
       model (`is_generated_path`, unaffected) but NEVER skip-safe: a PR
       touching only one still goes through a real (if trivial) review call
       rather than an automatic skip.
    4. Replaces `_GENERATED_PREFIXES`'s blanket directory-prefix match with
       a per-prefix decision — one anchored to its real closed write shape
       AND confirmed to have no content-trusting consumer, three removed
       from skip-safety entirely. See the "PER-PREFIX ANCHORING" comment
       above for the full trace, including a doubt-review round that
       disproved an earlier, broader version of this same fix.

    Deliberately does NOT `.strip()` the input (live PR-review gate, this
    iterate's own PR #746) — the earlier draft normalized whitespace before
    matching, which let a real, distinct on-disk path such as
    `" CHANGELOG-unreleased.d/Fixed/x_001.md"` (leading space) borrow the
    canonical path's classification. This is a HIGHER bar than
    `is_generated_path` (hide-only, lower stakes) needs, which is why the two
    diverge on this point rather than sharing one normalization rule.
    """
    p = path or ""
    if p.startswith(_SKIP_REVIEW_CHANGELOG_PREFIX):
        return _is_canonical_changelog_drop(p[len(_SKIP_REVIEW_CHANGELOG_PREFIX):])
    return p in _SKIP_REVIEW_CANONICAL_BASENAME_PATHS
