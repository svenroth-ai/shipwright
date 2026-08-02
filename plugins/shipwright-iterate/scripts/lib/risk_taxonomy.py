"""Canonical risk taxonomy for the Shipwright iterate workflow.

Extracted from ``classify_complexity.py`` (iterate-2026-07-18-ci-supplychain-risk-flag)
so that load-bearing module stays under the bloat limit — the same move the
diff-driven detectors got earlier. This registry only grows: every new risk flag
adds an entry, so it needed a home of its own rather than a widening exception.

SSoT. ``classify_complexity`` re-exports ``RISK_TAXONOMY`` so every existing
importer (SKILL.md consumers, shared.contracts.iterate, the taxonomy tests) keeps
resolving it from there.
"""

from __future__ import annotations


def _filename_token(name: str) -> str:
    """Wrap a filename regex so it matches a WHOLE filename, not a substring.

    The message surface matches prose; the diff surface matches an exact
    basename. They must agree on what counts as *naming* a build input, and
    the only reliable way to keep them agreeing is to apply the guard by
    construction — applying it by hand is what produced the defect this helper
    exists to close: iterate-2026-07-31-it5-classification-calibration added
    guards to the Python patterns it was introducing (an external review had
    found that bare ``\\b`` is not a filename boundary, since ``.`` satisfies
    it) and left the older, wholly unguarded JS patterns alone. All 21 JS build
    inputs then disagreed across the two surfaces.

    ``(?<![\\w.-])`` rejects a prefix, so ``my-package.json`` is not
    ``package.json``.

    The trailing guard is ``(?!\\w)(?!\\.\\w)`` rather than the symmetric
    ``(?![\\w.-])``, and the asymmetry is the whole design. A following
    character says one of three things:

    * a word character continues the NAME — ``setup.python`` is not
      ``setup.py``. Rejected by ``(?!\\w)``.
    * a ``.`` plus a word character adds an EXTENSION — ``package.json.bak``
      is a different file. Rejected by ``(?!\\.\\w)``.
    * anything else is PROSE around the filename — a sentence-ending ``.`` in
      "confined to package.json.", a compound hyphen in "a package.json-only
      bump", a comma, a backtick. The file is still what is being named, so
      these must fire.

    Both rejections were measured, in the direction that matters. The
    symmetric ``(?![\\w.-])`` this replaced suppressed the sentence-final case
    (`add a dependency to pyproject.toml.` raised nothing), and an
    intermediate ``(?![\\w-])`` suppressed the hyphen case (`a
    package.json-only bump` raised nothing, having fired before the guards
    existed at all). Each is a false NEGATIVE on a risk gate — the unsafe
    direction — so `-` is deliberately NOT in the class. The cost is that
    ``package.json-old`` fires; over-firing buys a spurious ``small`` floor,
    under-firing loses the gate.

    ``name`` is wrapped in a non-capturing group. Without it, ``|`` — which has
    the lowest precedence in the regex grammar — would split the guards across
    branches: ``gemfile|gemfile\\.lock`` would compile as
    ``((?<![\\w.-])gemfile)|(gemfile\\.lock(?!\\w)(?!\\.\\w))``, leaving the
    first branch with no trailing guard and the second with no leading one.
    That is both defects this helper exists to prevent, reintroduced by a call
    that reads as correct — and a purely structural check of the returned
    string still sees the guards at both ends. An alternation is the obvious
    way to write the Rust/Go/Ruby entries ``risk_detectors`` names as the
    deliberate next additions, so this is one token against a live trap.
    """
    return rf"(?<![\w.-])(?:{name})(?!\w)(?!\.\w)"


# --- Canonical Risk Taxonomy ---
# One authoritative list. Referenced by SKILL.md, references, and tests.

RISK_TAXONOMY = {
    "touches_auth": {
        "patterns": [
            r"auth", r"login", r"signup", r"sign.?up", r"session",
            r"middleware\.ts", r"supabase/.*auth",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_rls": {
        "patterns": [r"rls", r"row.?level", r"policy", r"policies"],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_middleware": {
        "patterns": [r"middleware", r"next\.config"],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_migrations": {
        "patterns": [
            r"migration", r"migrate", r"schema", r"alter\s+table",
            r"create\s+table", r"supabase/migrations",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review", "down_sql"],
    },
    "touches_billing": {
        "patterns": [
            r"stripe", r"payment", r"checkout", r"webhook",
            r"subscription", r"billing", r"invoice",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_shared_infra": {
        "patterns": [
            r"src/lib/", r"src/components/ui/", r"layout",
            r"shared.*component", r"global.*css", r"globals\.css",
        ],
        "min_complexity": "small",
        "enforces": ["full_test_suite"],
    },
    "touches_public_api": {
        "patterns": [
            r"api/", r"route\.ts", r"endpoint", r"export.*type",
            r"public.*api",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "cross_split": {
        "patterns": [],  # Detected by sync config, not keywords
        "min_complexity": "medium",
        "enforces": ["full_review", "full_test_suite"],
    },
    "touches_build": {
        # Triggers performance budget check on iterate (mirrors what
        # /shipwright-test Step 3.8 runs in the pipeline). Catches
        # dependency / build-config changes that can blow bundle size or
        # break Lighthouse score without anyone noticing until the next
        # full pipeline. Patterns match prompt keywords; diff-driven
        # detection uses TOUCHES_BUILD_FILE_PATTERNS via touches_build_files().
        # Python inputs added by iterate-2026-07-31-it5-classification-
        # calibration (trg-496e63a7): this surface is what actually fires at
        # SKILL.md Step E, so widening only the diff-driven file patterns
        # would have left the classifier blind on the path that runs.
        #
        # `requirements` DEMANDS a `.txt` filename. This is an IREB
        # requirements-engineering framework — a bare `requirements` pattern
        # would raise touches_build on ordinary prose about requirement
        # catalogues, on most iterates in this repo.
        #
        # EVERY name below goes through `_filename_token()`, JS and Python
        # alike — one entry, one matching rule. Half-guarding is the defect
        # this list carried: `my-package.json` and `package.json.bak` raised
        # touches_build from a message while the diff surface refused them
        # (pinned by test_touches_build_files_does_not_match_partial_basename).
        # Parity is asserted, not assumed, in
        # tests/test_touches_build_surface_parity.py — and it is parity on
        # TOKEN BOUNDARIES only: the surfaces disagree on case by decision
        # (`detect_risk_flags` lowercases prose, the diff half is
        # `fnmatchcase`), which that file pins too.
        #
        # The config families REQUIRE an extension (`next\.config\.\w+`),
        # because the diff surface holds only extensioned literals
        # (`next.config.js|ts|mjs|cjs`) and returns False for a bare
        # `next.config`. Making the extension optional would add five message
        # triggers with no diff-surface counterpart — the disagreement this
        # entry exists to remove. It is `\w+` rather than the four literals on
        # purpose: those per-family sets are irregular, and mirroring them here
        # would inherit five allowlists that drift silently.
        "patterns": [
            # JavaScript / TypeScript
            _filename_token(r"package\.json"),
            _filename_token(r"package-lock\.json"),
            _filename_token(r"yarn\.lock"),
            _filename_token(r"pnpm-lock\.yaml"),
            _filename_token(r"bun\.lockb"),
            _filename_token(r"npm-shrinkwrap\.json"),
            _filename_token(r"next\.config\.\w+"),
            _filename_token(r"vite\.config\.\w+"),
            _filename_token(r"tailwind\.config\.\w+"),
            _filename_token(r"webpack\.config\.\w+"),
            _filename_token(r"rollup\.config\.\w+"),
            _filename_token(r"tsconfig\.json"),
            # Python
            _filename_token(r"uv\.lock"),
            _filename_token(r"poetry\.lock"),
            _filename_token(r"pipfile(\.lock)?"),
            _filename_token(r"pyproject\.toml"),
            _filename_token(r"setup\.py"),
            _filename_token(r"setup\.cfg"),
            # `[^\s/\\]*`, not `[\w.-]*`: the diff surface matches this family
            # with the fnmatch glob `requirements*.txt`, whose `*` accepts ANY
            # character. `[\w.-]*` accepted a narrower alphabet, so
            # `requirements#.txt`, `requirements+extra.txt` and
            # `requirements@dev.txt` fired from a diff and not from a message —
            # the same cross-surface disagreement one alphabet over, found by
            # external review. Whitespace and path separators stay excluded so
            # the class cannot run across a sentence ("the requirements … see
            # notes.txt") or swallow a directory.
            _filename_token(r"requirements[^\s/\\]*\.txt"),
        ],
        "min_complexity": "small",
        # NOTE — for a Python change the enforced layer is largely a no-op by
        # its own skip-rules (no dev_url -> skip Lighthouse, no build
        # artifacts -> skip bundle). What is load-bearing there is the `small`
        # minimum plus the flag itself, which turns on "Full Code Review —
        # only if risk flags" at trivial/small. Written down so nobody reads a
        # Lighthouse promise into a lockfile bump.
        "enforces": ["performance_test_layer"],
    },
    "touches_io_boundary": {
        # Triggers Boundary Probe sub-step in Build TDD (see SKILL.md
        # Path A Step 6 + Phase Matrix). Catches producer/consumer
        # round-trip bugs where unit tests of each side pass but the
        # serialized format on disk drifts (motivating example: env
        # iterate's BOM + inline-comment bugs that survived 47 unit tests
        # AND two external reviews). Diff-driven detection uses
        # IO_BOUNDARY_FILE_PATTERNS via is_io_boundary_change() (the primary
        # detection). E spec MEDIUM-A1: prompt patterns are anchored function
        # names + stdlib calls + concrete file names only — the original loose
        # verb prefixes (`parse_`, `load_`, `write_`, `serialize`, …) fired on
        # unrelated prompts ("rewrite the page header", "add parse_query").
        "patterns": [
            # Concrete file patterns (still tight).
            r"\.env\b",
            r"\bhooks\.json\b",
            r"\bsettings\.json\b",
            r"_config\.json",
            r"_state\.json",
            # Anchored function names (specific, not verb prefixes).
            r"\bparse_env\b",
            # Specific stdlib calls (require the module qualifier).
            r"\bjson\.dump(s)?\b",
            r"\bjson\.loads?\b",
            r"\byaml\.dump\b",
            r"\byaml\.safe_load\b",
        ],
        "min_complexity": "small",
        "enforces": ["round_trip_test"],
    },
    "cross_component": {
        # Forces INTEGRATION coverage (Ledger `category:"integration"`), enforced
        # non-dodgeably by the F11 verifier `check_integration_coverage` which
        # RECOMPUTES the flag from the diff via CROSS_COMPONENT_FILE_PATTERNS. The
        # composition axis the boundary/app-surface machinery missed. These message
        # patterns are anchored Run-Summary hints; the diff path is primary.
        #
        # `min_complexity` below is the CLASSIFICATION escalation floor — what a
        # detected cross-component change forces the RUN to be classified as. It is
        # NOT an enforcement floor for the F11 gate, which applies at every
        # complexity (iterate-2026-08-01-coverage-gate-recompute-order). Coupling
        # the two meant the recompute was reached only for runs that had already
        # self-reported into the enforcing band, so it stood down in precisely the
        # missed-detection case it exists to backstop.
        "patterns": [
            r"\bcross.?component\b",
            r"\bmerge machinery\b",
            r"\bchurn (resolver|merge)\b",
            r"\bintegrate_main\b",
            r"\bhook fan.?out\b",
            r"\bcampaign (drain|serial)\b",
            r"\bpipeline phase\b",
        ],
        "min_complexity": "medium",
        "enforces": ["integration_coverage", "full_test_suite"],
    },
    "touches_ci_supplychain": {
        # CI trust boundary. Enforced non-dodgeably by `check_ci_supplychain_ack`
        # (recomputes from the diff, demands a recorded acknowledgement); these
        # hints are Run-Summary only. Rationale + the "never means pin everything"
        # rule: SKILL.md taxonomy row + docs/hooks-and-pipeline.md.
        # Hints are anchored to identifiers, not bare English — a plain
        # `\bworkflow\b` fires on "the iterate workflow" (message-prose FP class).
        "patterns": [
            r"\bgithub (actions?|workflows?)\b",
            r"\bworkflow file\b",
            r"\.github\b",
            r"\bdependabot\b",
            r"\brenovate\b",
            r"\bci (trust|supply.?chain)\b",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review", "ci_supplychain_ack"],
    },
}
