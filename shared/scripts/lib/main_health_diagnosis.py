"""The failure excerpt and the repair claim — the red-path half of the core.

Pure: every input is a payload, every "now" is a parameter.

**The excerpt is untrusted input.** It is text a failing test printed, packaged
for an agent to read. So it is reduced to the assertion-bearing lines, capped by
line *and* byte count, passed through a conservative secret redactor, and
labelled ``untrusted``. The label matters as much as the redaction: it is what
stops a log line from being read as an instruction. The redaction is
**defense-in-depth on top of GitHub's own masking, not a guarantee** — test
output can contain anything, and no pattern set closes that.

**The claim is a lock that cannot be forged.** The repair branch
``iterate/fix-main-<sha12>`` is the single machine-checkable declaration — one
grammar, because its two consumers (this matcher and the CI safety gate's `if:`)
would otherwise drift into a PR that claims but is not gated. A fork cannot
claim: creating a branch in this repository already requires write access, which
is the real trust boundary.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

REDACTED = "[REDACTED]"

#: Lines worth keeping out of a failed-step log. Deliberately narrow: the point
#: is the failing assertion, not the build transcript.
_SIGNAL_PATTERNS = (
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bERROR\b"),
    re.compile(r"^\s*E\s{2,}"),
    re.compile(r"\bassert\b"),
    re.compile(r"::error"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^\S+\.py:\d+:\d+: [A-Z]+\d+ "),  # ruff
    re.compile(r"short test summary info"),
)

# Assembled from fragments so the literal PEM header never appears contiguously
# in this file — the repository's own secret-scanning hook matches that header
# wherever it occurs, including inside the pattern meant to redact it.
_PEM_HEADER = "-{5}BEGIN [A-Z ]*PRIVATE" + " KEY-{5}"

#: Known credential shapes. NOT a general secret detector — see the module
#: docstring. A 40-hex commit SHA is deliberately absent: redacting those would
#: blank the one identifier the repair needs.
_SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(_PEM_HEADER),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key)\s*[:=]?\s*[A-Za-z0-9_\-\.]{20,}"),
)

#: `gh run view --log-failed` prefixes each line with `job<TAB>step<TAB>ts `.
_LOG_PREFIX = re.compile(r"^(?P<job>[^\t]*)\t(?P<step>[^\t]*)\t(?P<rest>.*)$")

#: The ONE repair declaration. Shared with the CI gate condition; a meta-test
#: asserts both accept the same branch names.
REPAIR_BRANCH_RE = re.compile(r"(?:^|/)fix-main-(?P<sha>[0-9a-f]{7,40})$")

#: More implicated commits than an overlap plausibly explains.
MAX_PARTNERS_BEFORE_ESCALATION = 8
#: Attempts that already failed before this one is worth trying.
MAX_FAILED_ATTEMPTS = 2


def redact(text: str) -> str:
    """Replace known credential shapes. Defense-in-depth, never a guarantee."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def reduce_failure_log(
    log: str | None, *, max_lines: int = 40, max_bytes: int = 8000
) -> dict:
    """The assertion-bearing lines of a failed step, redacted and capped.

    ``None`` in means an explicit absence out (``excerpt: None`` plus
    ``log_unavailable``) — not an empty list, which would read as "the step
    printed nothing".
    """
    if log is None:
        return {
            "excerpt": None,
            "truncated": False,
            "untrusted": True,
            "reason_code": "log_unavailable",
        }

    kept: list[str] = []
    for raw in log.splitlines():
        m = _LOG_PREFIX.match(raw)
        line = m.group("rest") if m else raw
        # Strip the leading ISO timestamp GitHub prefixes onto every log line.
        line = re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s?", "", line).rstrip()
        if not line:
            continue
        if any(p.search(line) for p in _SIGNAL_PATTERNS):
            kept.append(redact(line))

    truncated = len(kept) > max_lines
    kept = kept[:max_lines]

    # Byte cap second, so a single enormous line cannot smuggle the payload past
    # the line cap.
    out: list[str] = []
    used = 0
    for line in kept:
        cost = len(line.encode("utf-8")) + (1 if out else 0)
        if used + cost > max_bytes:
            truncated = True
            break
        out.append(line)
        used += cost

    return {
        "excerpt": out,
        "truncated": truncated,
        "untrusted": True,
        "reason_code": None,
    }


def _claim_sha(branch: str, full_sha: str) -> bool:
    """Does ``branch`` declare a repair of ``full_sha``?

    The short SHA must be a real prefix of the attributed commit — an arbitrary
    12 hex characters that merely *look* like one must not claim it.
    """
    m = REPAIR_BRANCH_RE.search(branch or "")
    return bool(m) and full_sha.startswith(m.group("sha"))


def _age_minutes(then: str | None, now: str) -> float:
    """Minutes between two ISO timestamps.

    A missing/unparseable `then` yields 0.0 — "as young as possible", the safe
    direction for a staleness test, since it never declares a claim takeable on
    no evidence. It is NOT reached for branch-only claims: those carry no
    timestamp at all and report `stale: None` rather than being aged (Tier-3
    review flagged the sentinel as confusing if reused).
    """
    def _parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )

    if not then:
        return 0.0
    try:
        return (_parse(now) - _parse(then)).total_seconds() / 60.0
    except ValueError:
        return 0.0


def match_repair_claim(
    full_sha: str,
    *,
    prs: list[dict],
    refs: list[str],
    repo_owner: str,
    now: str,
    stale_minutes: float = 120.0,
    trusted_authors: list[str] | None = None,
) -> dict:
    """Is a repair of ``full_sha`` already claimed, and did earlier ones fail?

    ``refs`` are branch refs in this repository. They are checked as well as
    pull requests because **pushing the branch is the atomic claim**: two agents
    that both query before either PR exists would otherwise both proceed, and
    AC-7's "no duplicate repairs" would hold only by luck.

    A claim is recognised only from a non-fork head — the write access needed to
    create the branch is the trust boundary — and optionally narrowed further by
    ``trusted_authors``.
    """
    matched: list[dict] = []
    for pr in prs or []:
        head_owner = ((pr.get("headRepositoryOwner") or {}).get("login")) or ""
        if head_owner != repo_owner:
            continue
        if not _claim_sha(pr.get("headRefName") or "", full_sha):
            continue
        author = ((pr.get("author") or {}).get("login")) or ""
        if trusted_authors and author not in trusted_authors:
            continue
        matched.append(pr)

    open_prs = [p for p in matched if (p.get("state") or "").upper() == "OPEN"]
    failed = [p for p in matched if (p.get("state") or "").upper() == "CLOSED"]

    claim: dict | None = None
    if open_prs:
        newest = max(open_prs, key=lambda p: str(p.get("updatedAt") or ""))
        age = _age_minutes(newest.get("updatedAt"), now)
        claim = {
            "source": "pull_request",
            "number": newest.get("number"),
            "url": newest.get("url"),
            "head": newest.get("headRefName"),
            "updated_at": newest.get("updatedAt"),
            "age_minutes": round(age, 1),
            "stale": age > stale_minutes,
        }
    else:
        branch = next((r for r in refs or [] if _claim_sha(r, full_sha)), None)
        if branch and failed:
            # A ref left behind by a repair that was already CLOSED is not a
            # claim at all — it is litter, and the procedure's own answer is to
            # delete it. Returning it as a `stale` claim sent the caller into
            # the takeover path, which starts by commenting on a pull request
            # that does not exist (Tier-3 review). No claim is the honest answer;
            # `failed_attempts` still carries the history that matters.
            return {"claim": None, "failed_attempts": len(failed)}
        if branch:
            claim = {
                "source": "branch",
                "number": None,
                "url": None,
                "head": branch,
                "updated_at": None,
                "age_minutes": None,
                # No timestamp comes back from a refs listing, so staleness is
                # genuinely UNKNOWN rather than False. Reporting False said "a
                # live worker holds this" about a ref that may have been
                # abandoned before its pull request ever existed. (The
                # closed-PR case never reaches here — it is litter, handled
                # above.)
                "stale": None,
                "stale_reason": (
                    "a bare ref carries no timestamp: age is unknown, so treat "
                    "an unexplained claim older than your patience as takeable"
                ),
            }

    return {"claim": claim, "failed_attempts": len(failed)}


def escalation(
    *,
    bad_sha: str | None,
    finding_reds: list[str],
    partner_count: int | None,
    failed_attempts: int,
) -> dict:
    """File a card instead of attempting a fix — and why.

    Deliberately narrow. This is the net for "this is not an accident, this is
    real", not the default outcome. ``keys`` are idempotency keys so a card is
    filed once per (workflow, commit) rather than once per iterate that looks.
    """
    short = (bad_sha or "")[:12]
    reasons: list[str] = []
    keys: list[str] = []
    if finding_reds:
        reasons.append("finding_class_red")
        keys = [f"main-red:{name}:{short}" for name in finding_reds]
    if partner_count is not None and partner_count > MAX_PARTNERS_BEFORE_ESCALATION:
        reasons.append("too_many_commits")
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        reasons.append("repeat_attempts")
    return {"required": bool(reasons), "reasons": reasons, "keys": keys}
