"""The shipped action-pinning posture, pinned in BOTH directions.

The framework's decided asymmetry: **GitHub-owned** actions (``actions/*``,
``github/*``) ride mutable major tags; **third-party** actions are pinned to a
full commit SHA. The reason is portability — SHA-pinning needs an automated
updater to avoid tag rot, and this framework deliberately runs no hosted
dependency updater. That holds even where the service is free, so a cost
argument does not reopen it.

A one-directional guard is not enough here, because the posture has been
reversed in *both* directions in practice:

* a well-meant "let's pin everything for supply-chain safety" re-pins a
  GitHub-owned action (webui #285 — a repo whose state was right, but whose
  reason was never written down);
* a convenience edit unpins a third-party action back to a floating tag.

So both are failures, and both are asserted. Templates are checked as text
rather than parsed YAML: they carry ``{PLACEHOLDER}`` tokens and ``if: ${{ … }}``
expressions that break a strict loader (the same reasoning that made the
accepted-risk reconciler read ``security.yml`` by targeted text extraction).

Scope note: this guards what the framework SHIPS to adopted repos
(``shared/templates/``). The monorepo's own workflows are covered by the same
posture but are not this file's subject — an adopter never sees them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "shared" / "templates" / "github-actions"

#: Capture the whole ``uses:`` scalar, then classify it in Python. Matching the
#: action shape directly in the regex was the first cut and it was WRONG:
#: ``uses: "evil/action@v1"`` and ``uses: evil/action@${{ inputs.version }}`` are
#: both valid workflow YAML, and both simply failed to match — so they slipped
#: past every check while the non-vacuity count still passed (external review,
#: GPT high + Gemini). Anything unparseable now fails closed instead.
#: Bounded repetition, no nesting — linear, ReDoS-safe.
_USES_RE = re.compile(
    r"^[^\S\n]*(?:-[^\S\n]+)?uses:[^\S\n]*(\S[^\n]{0,300})$", re.MULTILINE
)

#: A full git commit SHA — the only form that actually freezes an action.
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: Hosted dependency-updater configs. Broader than Dependabot on purpose:
#: reintroducing the posture under another vendor's filename must not escape
#: (mirrors ``risk_detectors.CI_SUPPLYCHAIN_FILE_PATTERNS``).
UPDATER_CONFIG_NAMES = (
    "dependabot.yml", "dependabot.yaml",
    "renovate.json", "renovate.json5", ".renovaterc", ".renovaterc.json",
)


def _parse_uses(raw: str) -> tuple[str, str]:
    """``uses:`` scalar -> ``(action, ref)``; ``ref`` is ``""`` when absent.

    Strips YAML quoting and any trailing ``# version`` comment, then splits on
    the LAST ``@`` (an action path never contains one; a ref may).
    """
    value = raw.strip()
    if "#" in value:
        value = value.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        value = value[1:-1].strip()
    action, sep, ref = value.rpartition("@")
    return (action, ref) if sep else (value, "")

#: Publishers whose mutable major tags the framework accepts by decision.
GITHUB_OWNED = ("actions/", "github/")

#: First-party framework actions consumed by adopters from this repo. The
#: ``@main`` ref is deliberate and separately pinned by
#: ``test_ci_template_diff_coverage`` / ``test_diff_coverage_action``: adopters
#: track the gate as the framework evolves it. Listed here so this guard does
#: not silently contradict a decision another test already enforces.
FIRST_PARTY_PREFIXES = ("svenroth-ai/shipwright/", "./")


def _uses(text: str) -> list[tuple[str, str]]:
    return [_parse_uses(m) for m in _USES_RE.findall(text)]


def _templates() -> list[Path]:
    """``rglob``: a template in a subdirectory is still shipped to adopters and
    must not fall outside the guard (external review, GPT medium)."""
    return sorted(TEMPLATE_DIR.rglob("*.template"))


def _classify(action: str) -> str:
    if action.startswith(FIRST_PARTY_PREFIXES):
        return "first-party"
    if action.startswith(GITHUB_OWNED):
        return "github-owned"
    return "third-party"


def test_templates_exist_so_this_guard_is_not_vacuous():
    """A guard that scans nothing passes forever. Assert it has real input."""
    templates = _templates()
    assert templates, f"no workflow templates found under {TEMPLATE_DIR}"
    total = sum(len(_uses(p.read_text(encoding="utf-8"))) for p in templates)
    assert total >= 10, f"only {total} `uses:` found — the scan is too thin to trust"


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_third_party_actions_are_sha_pinned(template: Path):
    """Direction 1: nobody may unpin a third-party action back to a tag."""
    offenders = [
        f"{action}@{ref}"
        for action, ref in _uses(template.read_text(encoding="utf-8"))
        if _classify(action) == "third-party" and not _SHA_RE.match(ref)
    ]
    assert not offenders, (
        f"{template.name}: third-party action(s) not pinned to a full commit "
        f"SHA: {offenders}\n"
        "Third-party publishers are not trusted to hold a mutable tag stable. "
        "Pin to the 40-char SHA with the version in a trailing comment "
        "(`@71345be...  # v4`).\n"
        "If the action no longer exists, REMOVE it — an unresolvable reference "
        "has no SHA to pin and cannot ever run."
    )


@pytest.mark.parametrize("template", _templates(), ids=lambda p: p.name)
def test_github_owned_actions_stay_on_mutable_tags(template: Path):
    """Direction 2: nobody may 'harden' a GitHub-owned action to a SHA.

    This is the direction that actually gets reversed, because pinning reads as
    unambiguously safer until you account for tag rot with no updater.
    """
    offenders = [
        f"{action}@{ref}"
        for action, ref in _uses(template.read_text(encoding="utf-8"))
        if _classify(action) == "github-owned" and _SHA_RE.match(ref)
    ]
    assert not offenders, (
        f"{template.name}: GitHub-owned action(s) SHA-pinned: {offenders}\n"
        "This is a REGRESSION, not a hardening. A pinned SHA never receives "
        "security patches, so it needs a hosted dependency updater to avoid "
        "rotting — and this framework runs none, for PORTABILITY (the reason "
        "holds even where the service is free).\n"
        "Use the major tag (`@v4`). Raise it for discussion rather than "
        "inverting it in a PR."
    )


def test_no_dependency_updater_config_is_shipped_to_adopters():
    """The posture only holds if adopters inherit no hosted updater either —
    a scaffolded `dependabot.yml` would silently reintroduce the pressure to
    pin everything."""
    shipped = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in (REPO_ROOT / "shared" / "templates").rglob("*")
        if p.is_file() and p.name.lower() in UPDATER_CONFIG_NAMES
    ]
    assert not shipped, (
        f"dependency-updater config shipped to adopters: {shipped}\n"
        "Any hosted updater reintroduces the pressure to SHA-pin everything, "
        "which is the posture this guard exists to hold."
    )


def test_the_posture_rule_reaches_adopters_not_just_the_state():
    """The point of the card this test ships with: an adopted repo used to get
    correct workflows and no explanation, so the first well-meant 'pin
    everything' silently reversed it. The rule must travel with the state."""
    template = (
        REPO_ROOT / "shared" / "templates" / "claude-md-template.md"
    ).read_text(encoding="utf-8")
    assert "## GitHub Actions pinning" in template, (
        "claude-md-template.md must carry the pinning posture, or adopters "
        "inherit the state without the reason — which is how it gets reversed."
    )
    body = template.lower()
    # Assert the NORMATIVE claims, not just vocabulary. The first cut checked
    # for three bare words and would still have passed if the rule had been
    # inverted into "pin everything and add Dependabot" (external review, GPT
    # low) — a rule-shipping test that survives the rule being reversed is
    # exactly the vacuous green this whole card is about.
    required = {
        "third-party actions must be SHA-pinned":
            "third-party" in body and "sha" in body,
        "GitHub-owned actions stay on a mutable major tag":
            "github-owned" in body and "mutable" in body,
        "the reason is portability, explicitly NOT cost":
            "portability" in body and "not cost" in body,
        "a dependency updater is forbidden, not merely absent":
            "never add a dependency-updater config" in body,
        "pinning a GitHub-owned action is called out as a regression":
            "regression" in body,
    }
    missing = [claim for claim, present in required.items() if not present]
    assert not missing, (
        "the shipped posture rule no longer states:\n"
        + "\n".join(f"  - {c}" for c in missing)
        + "\nAn adopter who cannot reconstruct the REASONING will reverse the "
        "posture in good faith — which is precisely what happened in #285."
    )


class TestParserCannotBeEvaded:
    """The evasion forms the external review found. Each was a real blind spot
    in the first cut: the value simply did not match, so it slipped past BOTH
    direction checks while the non-vacuity count still passed."""

    @pytest.mark.parametrize("line,expected", [
        ("      - uses: actions/checkout@v4", ("actions/checkout", "v4")),
        ('      - uses: "evil/action@v1"', ("evil/action", "v1")),
        ("      - uses: 'evil/action@v1'", ("evil/action", "v1")),
        ("        uses: a/b@71345be0265236311c031f5c7866368bd1eff043  # v4",
         ("a/b", "71345be0265236311c031f5c7866368bd1eff043")),
        ("      - uses: evil/action@${{ inputs.version }}",
         ("evil/action", "${{ inputs.version }}")),
        ("      - uses: ./.github/actions/local", ("./.github/actions/local", "")),
    ])
    def test_quoted_dynamic_and_bare_forms_are_all_extracted(self, line, expected):
        assert _uses(line) == [expected]

    @pytest.mark.parametrize("evasion", [
        '      - uses: "evil/action@v1"',
        "      - uses: 'evil/action@v1'",
        "      - uses: evil/action@${{ inputs.version }}",
        "      - uses: evil/action",
    ])
    def test_third_party_evasions_are_caught_not_skipped(self, evasion):
        """Fail CLOSED: anything that is not a literal 40-char SHA is an
        offender, including a ref this parser cannot resolve at all."""
        offenders = [
            f"{a}@{r}" for a, r in _uses(evasion)
            if _classify(a) == "third-party" and not _SHA_RE.match(r)
        ]
        assert offenders, f"evasion slipped through: {evasion!r}"

    def test_a_quoted_github_owned_sha_pin_is_still_caught(self):
        offenders = [
            f"{a}@{r}"
            for a, r in _uses('  - uses: "actions/checkout@' + "a" * 40 + '"')
            if _classify(a) == "github-owned" and _SHA_RE.match(r)
        ]
        assert offenders, "a quoted SHA-pin of a GitHub-owned action must fail"
